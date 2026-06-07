from __future__ import annotations

import io
import pickle
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np
import pyarrow.parquet as pq
from PIL import Image

from .config import Settings, get_settings
from .frame_cache import FrameCacheKey, LRUFrameCache
from .schemas import (
    DatasetInfo,
    EpisodeDetail,
    EpisodeSummary,
    FrameInfo,
    VideoSegment,
    WarningItem,
)

ACTION_KEYS = ("action",)
STATE_KEYS = ("observation.state", "obs_state", "state")
TIMESTAMP_KEYS = ("timestamp",)


class DatasetError(RuntimeError):
    pass


def _to_float_list(value: Any) -> list[float] | None:
    if value is None:
        return None
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    arr = np.asarray(value)
    if arr.ndim == 0:
        return [float(arr)]
    return [float(x) for x in arr.reshape(-1)]


def _to_image(value: Any) -> Image.Image:
    if value is None:
        raise DatasetError("Image field is missing.")
    if isinstance(value, Image.Image):
        return value.convert("RGB")
    if hasattr(value, "detach"):
        value = value.detach().cpu()
        if str(value.dtype).endswith("float32") or str(value.dtype).endswith("float64"):
            value = (value.clamp(0, 1) * 255).byte()
        value = value.numpy()
    arr = np.asarray(value)
    if arr.ndim != 3:
        raise DatasetError(f"Expected a 3D image array, got shape {arr.shape}.")
    if (
        arr.shape[0] in (1, 3, 4)
        and arr.shape[0] < arr.shape[1]
        and arr.shape[0] < arr.shape[2]
    ):
        arr = np.transpose(arr, (1, 2, 0))
    if arr.dtype != np.uint8:
        if np.issubdtype(arr.dtype, np.floating) and float(np.nanmax(arr)) <= 1.0:
            arr = arr * 255.0
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    if arr.shape[-1] == 1:
        arr = np.repeat(arr, 3, axis=-1)
    return Image.fromarray(arr[..., :3], mode="RGB")


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=max(1, min(95, quality)), optimize=True)
    return buffer.getvalue()


def _column_values(table: Any, key: str, start: int, end: int) -> list | None:
    try:
        column = table[key]
        return list(column[start:end])
    except Exception:
        pass
    try:
        subset = table.select(range(start, end))
        return list(subset[key])
    except Exception:
        return None


def _item_value_to_python(value: Any) -> Any:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


class LeRobotDatasetLoader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.dataset_path = settings.dataset_path.expanduser().resolve()
        self.repo_id = settings.repo_id or self.dataset_path.name
        self._lock = RLock()
        self._dataset = None
        self.meta = self._load_metadata()
        self.root = self.meta.root
        self._hf_dataset = None
        self._pq_dataset = None
        self._pq_columns: list[str] | None = None
        self._series_cache_dir: Path | None = None
        self._cached_jump_threshold: float | None = None
        self.camera_keys = self._discover_camera_keys()
        self.episode_ranges = self._discover_episode_ranges()
        self.frame_cache = LRUFrameCache(settings.frame_cache_size)
        self._decode_locks: dict[tuple[int, int, int], RLock] = {}
        self._decode_locks_guard = RLock()
        self._cached_jump_threshold: float | None = None

    def _load_metadata(self) -> Any:
        try:
            from lerobot.datasets.dataset_metadata import LeRobotDatasetMetadata
        except Exception as exc:
            raise DatasetError(
                "Cannot import LeRobotDatasetMetadata. Install lerobot in the backend environment."
            ) from exc

        if not self.dataset_path.exists():
            raise DatasetError(f"Dataset path does not exist: {self.dataset_path}")

        # Quick check: is this a valid LeRobot dataset directory?
        meta_dir = self.dataset_path / "meta"
        info_json = meta_dir / "info.json"
        if not info_json.exists():
            # Check parent dir as well
            parent_info = self.dataset_path.parent / "meta" / "info.json"
            if not parent_info.exists():
                raise DatasetError(
                    f"No LeRobot dataset found at {self.dataset_path}. "
                    f"Expected {info_json} or {parent_info} to exist. "
                    f"Make sure the path points to the dataset root (containing meta/ and data/)."
                )

        attempts: list[dict] = [
            {
                "repo_id": self.repo_id,
                "root": self.dataset_path,
                "force_cache_sync": False,
            },
        ]
        if self.dataset_path.parent != self.dataset_path:
            attempts.append(
                {
                    "repo_id": self.repo_id,
                    "root": self.dataset_path.parent,
                    "force_cache_sync": False,
                }
            )

        last_error: Exception | None = None
        for kwargs in attempts:
            try:
                return LeRobotDatasetMetadata(**kwargs)
            except Exception as exc:
                if last_error is None:
                    last_error = exc
                continue

        raise DatasetError(
            f"Failed to load LeRobot metadata from {self.dataset_path}: {last_error}"
        )

        last_error: Exception | None = None
        for kwargs in attempts:
            try:
                return LeRobotDatasetMetadata(**kwargs)
            except Exception as exc:
                if last_error is None:
                    last_error = exc
                continue

        raise DatasetError(
            f"Failed to load LeRobot metadata from {self.dataset_path}: {last_error}"
        )

    def _ensure_dataset(self) -> Any:
        if self._dataset is not None:
            return self._dataset
        try:
            from lerobot.datasets import LeRobotDataset
        except Exception as exc:
            raise DatasetError(
                "Cannot import LeRobotDataset. Install lerobot in the backend environment."
            ) from exc

        attempts = [
            {
                "repo_id": self.repo_id,
                "root": self.root,
                "download_videos": False,
                "force_cache_sync": False,
            },
            {
                "repo_id": self.repo_id,
                "root": self.dataset_path,
                "download_videos": False,
                "force_cache_sync": False,
            },
        ]
        if self.dataset_path.parent != self.dataset_path:
            attempts.append(
                {
                    "repo_id": self.repo_id,
                    "root": self.dataset_path.parent,
                    "download_videos": False,
                    "force_cache_sync": False,
                }
            )
        last_error: Exception | None = None
        for kwargs in attempts:
            try:
                self._dataset = LeRobotDataset(**kwargs)
                self._hf_dataset = getattr(self._dataset, "hf_dataset", None)
                return self._dataset
            except Exception as exc:
                if last_error is None:
                    last_error = exc
        raise DatasetError(
            f"Failed to load LeRobot dataset table data from {self.dataset_path}: {last_error}"
        )

    def _discover_camera_keys(self) -> list[str]:
        keys = list(getattr(self.meta, "camera_keys", []) or [])
        if keys:
            return keys
        features = getattr(self.meta, "features", {}) or {}
        inferred = [
            key
            for key, value in features.items()
            if isinstance(value, dict) and value.get("dtype") in {"image", "video"}
        ]
        if not inferred:
            raise DatasetError(
                "No camera image keys were found in the dataset metadata."
            )
        return inferred

    def _discover_episode_ranges(self) -> dict[int, tuple[int, int]]:
        episodes = getattr(self.meta, "episodes", None)
        ranges: dict[int, tuple[int, int]] = {}
        if episodes is not None:
            for row_idx in range(len(episodes)):
                try:
                    ep = episodes[row_idx]
                except Exception:
                    ep = episodes.iloc[row_idx]
                if hasattr(ep, "to_dict"):
                    ep = ep.to_dict()
                episode_id = int(ep.get("episode_index", row_idx))
                start = ep.get("dataset_from_index")
                end = ep.get("dataset_to_index")
                if start is None and "length" in ep:
                    previous_end = ranges[max(ranges)][1] if ranges else 0
                    start = previous_end
                    end = previous_end + int(ep["length"])
                if start is not None and end is not None:
                    ranges[episode_id] = (int(start), int(end))
        if ranges:
            return ranges
        total_frames = int(getattr(self.meta, "total_frames", 0) or 0)
        total_episodes = int(getattr(self.meta, "total_episodes", 1) or 1)
        if total_episodes <= 1:
            return {0: (0, total_frames)}
        raise DatasetError("Could not infer episode frame ranges from metadata.")

    def _get_series_cache_path(self) -> Path:
        if self._series_cache_dir is None:
            self._series_cache_dir = Path(self.root) / ".webviz_cache"
            self._series_cache_dir.mkdir(exist_ok=True)
        return self._series_cache_dir

    def _ensure_parquet_reader(self) -> pq.ParquetDataset:
        if self._pq_dataset is not None:
            return self._pq_dataset
        data_dir = Path(self.root) / "data"
        if not data_dir.exists():
            raise DatasetError(f"Data directory does not exist: {data_dir}")
        parquet_paths = sorted(data_dir.glob("*/*.parquet"))
        if not parquet_paths:
            raise DatasetError(f"No parquet files found in: {data_dir}")
        self._pq_dataset = pq.ParquetDataset(
            sorted(parquet_paths),
            memory_map=True,
        )
        self._pq_columns = self._pq_dataset.schema.names
        return self._pq_dataset

    def _parquet_series(
        self, episode_id: int, keys: tuple[str, ...]
    ) -> tuple[list | None, str | None]:
        pqs = self._ensure_parquet_reader()
        start, end = self._episode_slice(episode_id)

        for key in keys:
            if key not in self._pq_columns:
                continue

            table = pqs.read(columns=[key], use_threads=True)
            col = table.column(key)
            values_raw = col[start:end]
            values = [_item_value_to_python(v.as_py()) for v in values_raw]
            return values, key

        return None, None

    def _parquet_batch_columns(
        self, episode_id: int, column_keys: list[str]
    ) -> dict[str, list]:
        """Read multiple columns for an episode in a single parquet pass."""
        pqs = self._ensure_parquet_reader()
        start, end = self._episode_slice(episode_id)

        existing = [k for k in column_keys if k in self._pq_columns]
        if not existing:
            return {}

        table = pqs.read(columns=existing, use_threads=True)
        result: dict[str, list] = {}
        for key in existing:
            col = table.column(key)
            values_raw = col[start:end]
            result[key] = [_item_value_to_python(v.as_py()) for v in values_raw]
        return result

    def _get_series_from_cache(self, cache_key: str) -> list | None:
        cache_path = self._get_series_cache_path() / f"{cache_key}.pkl"
        if cache_path.exists():
            try:
                with open(cache_path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                return None
        return None

    def _save_series_to_cache(self, cache_key: str, values: list) -> None:
        cache_path = self._get_series_cache_path() / f"{cache_key}.pkl"
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(values, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            pass

    def _sample(self, episode_id: int, frame_id: int) -> dict[str, Any]:
        if episode_id not in self.episode_ranges:
            raise DatasetError(f"Episode {episode_id} does not exist.")
        start, end = self.episode_ranges[episode_id]
        global_index = start + frame_id
        if global_index < start or global_index >= end:
            raise DatasetError(
                f"Frame {frame_id} is outside episode {episode_id} range 0..{end - start - 1}."
            )
        with self._lock:
            return self._ensure_dataset()[global_index]

    def _first_present(self, sample: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in sample:
                return sample[key]
        return None

    def _sample_timestamp(self, sample: dict[str, Any]) -> float | None:
        value = self._first_present(sample, TIMESTAMP_KEYS)
        values = _to_float_list(value)
        return values[0] if values else None

    def _episode_slice(self, episode_id: int) -> tuple[int, int]:
        if episode_id not in self.episode_ranges:
            raise DatasetError(f"Episode {episode_id} does not exist.")
        return self.episode_ranges[episode_id]

    def _hf_series(
        self, episode_id: int, keys: tuple[str, ...]
    ) -> tuple[list | None, str | None]:
        # Try fast PyArrow parquet reader first (avoids loading full LeRobotDataset)
        pq_values, pq_key = self._parquet_series(episode_id, keys)
        if pq_values is not None:
            return pq_values, pq_key

        if self._hf_dataset is None:
            self._ensure_dataset()
        if self._hf_dataset is None:
            return None, None
        start, end = self._episode_slice(episode_id)
        for key in keys:
            values = _column_values(self._hf_dataset, key, start, end)
            if values is not None:
                return [_item_value_to_python(value) for value in values], key
        return None, None

    def _sample_dimension(self, keys: tuple[str, ...]) -> int | None:
        features = getattr(self.meta, "features", {}) or {}
        for key in keys:
            feature = features.get(key)
            if isinstance(feature, dict):
                shape = feature.get("shape")
                if shape:
                    size = 1
                    for dim in shape:
                        size *= int(dim)
                    return size
        return None

    def _feature_names(self, keys: tuple[str, ...]) -> list[str] | None:
        features = getattr(self.meta, "features", {}) or {}
        for key in keys:
            feature = features.get(key)
            if isinstance(feature, dict):
                names = feature.get("names")
                if names:
                    return names
        return None

    def _feature_keys(self) -> list[str]:
        features = getattr(self.meta, "features", {}) or {}
        if isinstance(features, dict):
            return list(features.keys())
        if isinstance(features, list):
            return [item.get("key", "") for item in features if isinstance(item, dict)]
        return []

    def _task_map(self) -> dict[int, str]:
        tasks = getattr(self.meta, "tasks", None)
        if tasks is None:
            return {}
        try:
            result: dict[int, str] = {}
            for task_name in tasks.index:
                idx = int(tasks.loc[task_name, "task_index"])
                result[idx] = str(task_name)
            return result
        except Exception:
            return {}

    def _data_stats(self, keys: tuple[str, ...]) -> dict | None:
        stats_attr = getattr(self.meta, "stats", None)
        if stats_attr is None:
            return None
        for key in keys:
            s = stats_attr.get(key)
            if s:
                result = {}
                for k in ("min", "max", "mean", "std"):
                    v = s.get(k)
                    if v is not None:
                        if hasattr(v, "tolist"):
                            result[k] = v.tolist()
                        elif isinstance(v, (list, tuple)):
                            result[k] = [float(x) for x in v]
                        else:
                            result[k] = float(v)
                return result
        return None
        for key in keys:
            s = stats_attr.get(key)
            if s:
                return {
                    k: v for k, v in s.items() if k in ("min", "max", "mean", "std")
                }
        return None

    def dataset_info(self) -> DatasetInfo:
        fps = getattr(self.meta, "fps", None)
        total_frames = int(
            getattr(self.meta, "total_frames", 0)
            or sum(end - start for start, end in self.episode_ranges.values())
        )
        return DatasetInfo(
            dataset_path=str(self.root),
            repo_id=str(getattr(self.meta, "repo_id", self.repo_id)),
            fps=float(fps) if fps is not None else None,
            total_frames=total_frames,
            total_episodes=len(self.episode_ranges),
            camera_keys=self.camera_keys,
            action_dim=self._sample_dimension(ACTION_KEYS),
            state_dim=self._sample_dimension(STATE_KEYS),
            action_names=self._feature_names(ACTION_KEYS),
            state_names=self._feature_names(STATE_KEYS),
            feature_keys=self._feature_keys(),
            task_map=self._task_map(),
            action_stats=self._data_stats(ACTION_KEYS),
            state_stats=self._data_stats(STATE_KEYS),
        )

    def episodes(self) -> list[EpisodeSummary]:
        result = []
        fps = getattr(self.meta, "fps", None)
        for episode_id, (start, end) in sorted(self.episode_ranges.items()):
            tasks = self._episode_tasks(episode_id)
            frame_count = end - start
            duration = frame_count / float(fps) if fps else None
            result.append(
                EpisodeSummary(
                    id=episode_id,
                    start_index=start,
                    end_index=end,
                    frame_count=frame_count,
                    duration=round(duration, 1) if duration else None,
                    tasks=tasks,
                )
            )
        return result

    def _episode_tasks(self, episode_id: int) -> list[str]:
        episodes = getattr(self.meta, "episodes", None)
        if episodes is None:
            return []
        try:
            ep = episodes[episode_id]
        except Exception:
            try:
                ep = episodes.iloc[episode_id]
            except Exception:
                return []
        if hasattr(ep, "to_dict"):
            ep = ep.to_dict()
        tasks = ep.get("tasks", [])
        if tasks is None:
            return []
        return tasks if isinstance(tasks, list) else [tasks]

    def episode(self, episode_id: int) -> EpisodeDetail:
        base = next((item for item in self.episodes() if item.id == episode_id), None)
        if base is None:
            raise DatasetError(f"Episode {episode_id} does not exist.")
        info = self.dataset_info()
        return EpisodeDetail(
            **base.model_dump(),
            fps=info.fps,
            camera_keys=self.camera_keys,
            action_dim=info.action_dim,
            state_dim=info.state_dim,
        )

    def _episode_metadata(self, episode_id: int) -> dict[str, Any]:
        episodes = getattr(self.meta, "episodes", None)
        if episodes is None:
            return {}
        try:
            item = episodes[episode_id]
        except Exception:
            try:
                item = episodes.iloc[episode_id]
            except Exception:
                return {}
        if hasattr(item, "to_dict"):
            return item.to_dict()
        if isinstance(item, dict):
            return item
        return dict(item) if item is not None else {}

    def video_segments(self, episode_id: int) -> list[VideoSegment]:
        detail = self.episode(episode_id)
        meta = self.meta
        if meta is None or not hasattr(meta, "get_video_file_path"):
            return []
        episode_meta = self._episode_metadata(episode_id)
        fps = detail.fps
        fallback_duration = (detail.frame_count / fps) if fps else 0.0
        segments: list[VideoSegment] = []
        for camera in self.camera_keys:
            try:
                video_rel = meta.get_video_file_path(episode_id, camera)
                video_path = (self.root / video_rel).resolve()
            except Exception:
                continue
            if not video_path.exists():
                continue
            from_ts = episode_meta.get(f"videos/{camera}/from_timestamp")
            to_ts = episode_meta.get(f"videos/{camera}/to_timestamp")
            if from_ts is None:
                from_ts = 0.0
            if to_ts is None:
                to_ts = float(from_ts) + float(fallback_duration or 0.0)
            from_ts = float(from_ts)
            to_ts = max(from_ts, float(to_ts))
            segments.append(
                VideoSegment(
                    camera=camera,
                    url=f"/api/episodes/{episode_id}/videos/file/{camera}",
                    file_path=str(video_path),
                    from_timestamp=from_ts,
                    to_timestamp=to_ts,
                    duration=max(0.0, to_ts - from_ts),
                    fps=fps,
                )
            )
        return segments

    def frame_info(self, episode_id: int, frame_id: int) -> FrameInfo:
        try:
            action_values = self.series(episode_id, "actions")
        except DatasetError:
            action_values = []
        try:
            state_values = self.series(episode_id, "states")
        except DatasetError:
            state_values = []
        try:
            timestamp_values = self.series(episode_id, "timestamps")
        except DatasetError:
            timestamp_values = []
        return FrameInfo(
            episode_id=episode_id,
            frame_id=frame_id,
            timestamp=timestamp_values[frame_id]
            if frame_id < len(timestamp_values)
            else None,
            cameras=self.camera_keys,
            action=action_values[frame_id] if frame_id < len(action_values) else None,
            state=state_values[frame_id] if frame_id < len(state_values) else None,
        )

    def _decode_lock(self, episode_id: int, frame_id: int, quality: int) -> RLock:
        lock_key = (episode_id, frame_id, quality)
        with self._decode_locks_guard:
            lock = self._decode_locks.get(lock_key)
            if lock is None:
                lock = RLock()
                self._decode_locks[lock_key] = lock
            return lock

    def _cache_all_camera_jpegs(
        self, episode_id: int, frame_id: int, sample: dict[str, Any], quality: int
    ) -> None:
        # LeRobot decodes all cameras when one video frame is requested, so cache every camera now.
        for camera in self.camera_keys:
            key = FrameCacheKey(episode_id, frame_id, camera, quality)
            if self.frame_cache.get(key) is not None:
                continue
            value = sample.get(camera)
            if value is None:
                continue
            self.frame_cache.put(key, _encode_jpeg(_to_image(value), quality))

    def frame_jpeg(
        self, episode_id: int, frame_id: int, camera_name: str, quality: int
    ) -> bytes:
        if camera_name not in self.camera_keys:
            raise DatasetError(
                f"Camera '{camera_name}' does not exist. Available cameras: {self.camera_keys}"
            )
        key = FrameCacheKey(episode_id, frame_id, camera_name, quality)
        cached = self.frame_cache.get(key)
        if cached is not None:
            return cached

        with self._decode_lock(episode_id, frame_id, quality):
            cached = self.frame_cache.get(key)
            if cached is not None:
                return cached
            sample = self._sample(episode_id, frame_id)
            self._cache_all_camera_jpegs(episode_id, frame_id, sample, quality)
            cached = self.frame_cache.get(key)
            if cached is None:
                raise DatasetError(
                    f"Frame {frame_id} does not contain camera '{camera_name}'."
                )
            return cached

    def preload_frames(self, episode_id: int, frame_id: int, quality: int) -> None:
        try:
            if not self.camera_keys:
                return
            detail = self.episode(episode_id)
            last = min(detail.frame_count, frame_id + 1 + self.settings.preload_frames)
            first_camera = self.camera_keys[0]
            for next_frame in range(frame_id + 1, last):
                key = FrameCacheKey(episode_id, next_frame, first_camera, quality)
                if self.frame_cache.get(key) is None:
                    self.frame_jpeg(episode_id, next_frame, first_camera, quality)
        except Exception:
            return

    def series_raw(self, episode_id: int, feature_key: str) -> list:
        """Return series data for an arbitrary feature key."""
        cache_key = f"series_raw_{self.root.name}_{episode_id}_{feature_key}"
        cached = self._get_series_from_cache(cache_key)
        if cached is not None:
            return cached

        values, _found_key = self._hf_series(episode_id, (feature_key,))
        if values is not None:
            converted = [_to_float_list(v) for v in values]
            self._save_series_to_cache(cache_key, converted)
            return converted

        detail = self.episode(episode_id)
        result = []
        for frame_id in range(detail.frame_count):
            sample = self._sample(episode_id, frame_id)
            v = sample.get(feature_key)
            result.append(_to_float_list(v))
        self._save_series_to_cache(cache_key, result)
        return result

    @lru_cache(maxsize=128)
    def series(
        self,
        episode_id: int,
        key_group: str,
        start_frame: int = 0,
        end_frame: int | None = None,
    ) -> list:
        # Try disk cache first for the full series
        if start_frame == 0 and end_frame is None:
            cache_key = f"series_{self.root.name}_{episode_id}_{key_group}"
            cached = self._get_series_from_cache(cache_key)
            if cached is not None:
                return cached

        detail = self.episode(episode_id)
        keys = {
            "actions": ACTION_KEYS,
            "states": STATE_KEYS,
            "timestamps": TIMESTAMP_KEYS,
        }[key_group]
        values, _key = self._hf_series(episode_id, keys)
        if values is not None:
            if key_group == "timestamps":
                converted = []
                for value in values:
                    numbers = _to_float_list(value)
                    converted.append(numbers[0] if numbers else None)
                values = converted
            else:
                values = [_to_float_list(value) for value in values]

            # Cache the full series to disk
            if start_frame == 0 and end_frame is None:
                self._save_series_to_cache(cache_key, values)

            if end_frame is not None:
                values = values[start_frame:end_frame]
            elif start_frame > 0:
                values = values[start_frame:]
            return values

        result = []
        missing = True
        for frame_id in range(detail.frame_count):
            sample = self._sample(episode_id, frame_id)
            if key_group == "timestamps":
                value = self._sample_timestamp(sample)
            else:
                value = _to_float_list(self._first_present(sample, keys))
            if value is not None:
                missing = False
            result.append(value)
        if missing:
            raise DatasetError(
                f"Dataset field for {key_group} is missing. Tried keys: {list(keys)}"
            )

        # Cache the full series to disk
        if start_frame == 0 and end_frame is None:
            self._save_series_to_cache(cache_key, result)

        if end_frame is not None:
            result = result[start_frame:end_frame]
        elif start_frame > 0:
            result = result[start_frame:]
        return result

    def trajectories(self, episode_id: int) -> dict[str, Any]:
        cache_key = f"traj_{self.root.name}_{episode_id}"
        cached = self._get_series_from_cache(cache_key)
        if cached is not None:
            return cached

        detail = self.episode(episode_id)

        # Read all action/state/timestamp columns in a single parquet pass
        all_keys = list(ACTION_KEYS) + list(STATE_KEYS) + list(TIMESTAMP_KEYS)
        batch = self._parquet_batch_columns(episode_id, all_keys)

        # Extract and convert each group
        def _convert_group(keys_tuple, batch_data):
            for k in keys_tuple:
                if k in batch_data:
                    raw = batch_data[k]
                    return [_to_float_list(v) for v in raw]
            return []

        actions = _convert_group(ACTION_KEYS, batch)
        states = _convert_group(STATE_KEYS, batch)

        # Timestamps
        timestamps_raw = None
        for k in TIMESTAMP_KEYS:
            if k in batch:
                timestamps_raw = batch[k]
                break
        if timestamps_raw is not None:
            timestamps = []
            for v in timestamps_raw:
                numbers = _to_float_list(v)
                timestamps.append(numbers[0] if numbers else None)
        else:
            timestamps = []

        # Fall back to _sample-based loading if parquet didn't have data
        missing_action = len(actions) == 0
        missing_state = len(states) == 0
        missing_ts = len(timestamps) == 0

        if missing_action or missing_state or missing_ts:
            for frame_id in range(detail.frame_count):
                sample = self._sample(episode_id, frame_id)
                if missing_action:
                    act = _to_float_list(self._first_present(sample, ACTION_KEYS))
                    actions.append(act)
                if missing_state:
                    st = _to_float_list(self._first_present(sample, STATE_KEYS))
                    states.append(st)
                if missing_ts:
                    ts = self._sample_timestamp(sample)
                    timestamps.append(ts)

        # Compute warnings
        warnings = self._compute_warnings(episode_id, detail, timestamps, actions)

        result = {
            "actions": actions,
            "states": states,
            "timestamps": timestamps,
            "warnings": warnings,
        }
        self._save_series_to_cache(cache_key, result)
        return result

    def _compute_warnings(
        self,
        episode_id: int,
        detail: EpisodeDetail,
        timestamps: list,
        actions: list,
    ) -> list[WarningItem]:
        warnings: list[WarningItem] = []
        if detail.frame_count < self.settings.min_episode_frames:
            warnings.append(
                WarningItem(
                    type="short_episode",
                    level="warning",
                    message="Episode is very short.",
                )
            )

        ts_clean = [x for x in timestamps if x is not None]
        if len(ts_clean) >= 3:
            diffs = np.diff(np.asarray(ts_clean, dtype=np.float64))
            positive = diffs[diffs > 0]
            expected = (
                1.0 / detail.fps
                if detail.fps
                else float(np.median(positive))
                if len(positive)
                else 0.0
            )
            threshold = expected * self.settings.timestamp_gap_ratio
            for idx, gap in enumerate(diffs):
                if expected > 0 and (gap <= 0 or gap > threshold):
                    warnings.append(
                        WarningItem(
                            type="timestamp_gap",
                            level="warning",
                            message=f"Frame {idx + 1} has abnormal timestamp gap.",
                        )
                    )
                    break

            # FPS stability: actual median fps vs nominal
            if detail.fps and len(positive) > 0:
                actual_fps = 1.0 / float(np.median(positive))
                fps_ratio = actual_fps / float(detail.fps)
                if fps_ratio < 0.7 or fps_ratio > 1.5:
                    warnings.append(
                        WarningItem(
                            type="fps_deviation",
                            level="warning",
                            message=f"Actual FPS ({actual_fps:.1f}) deviates from nominal ({detail.fps:.0f}), ratio={fps_ratio:.2f}",
                        )
                    )

        # Frame index continuity check (only for episodes with > 1 frame)
        try:
            frame_idx_data = self._parquet_batch_columns(episode_id, ["frame_index"])
            if "frame_index" in frame_idx_data:
                fi_vals = frame_idx_data["frame_index"]
                # Check for gaps: each frame_index should be strictly increasing
                gaps = []
                for i in range(1, len(fi_vals)):
                    prev = fi_vals[i - 1]
                    curr = fi_vals[i]
                    if isinstance(prev, (int, float)) and isinstance(
                        curr, (int, float)
                    ):
                        if int(curr) != int(prev) + 1:
                            gaps.append(i)
                    if len(gaps) >= 3:
                        break
                if gaps:
                    warnings.append(
                        WarningItem(
                            type="frame_index_gap",
                            level="warning",
                            message=f"Frame index has gaps at positions {gaps[:3]} (among others)"
                            if len(gaps) >= 3
                            else f"Frame index gaps at {gaps}",
                        )
                    )
        except Exception:
            pass

        if len(actions) > 0 and all(a is not None for a in actions):
            action_arr = np.asarray(actions, dtype=np.float64)
            if action_arr.ndim == 2 and action_arr.shape[0] > 3:
                jumps = np.linalg.norm(np.diff(action_arr, axis=0), axis=1)
                median = float(np.median(jumps))
                mad = float(np.median(np.abs(jumps - median))) or 1e-9
                threshold = (
                    self._cached_jump_threshold or self.settings.action_jump_zscore
                )
                for idx, jump in enumerate(jumps):
                    z = (jump - median) / mad
                    if z > threshold:
                        warnings.append(
                            WarningItem(
                                type="action_jump",
                                level="warning",
                                message=f"帧 {idx} → {idx + 1} 动作跳变 (z={z:.1f})",
                            )
                        )
                        break

                # Action range check against dataset-level stats
                stats = self._data_stats(ACTION_KEYS)
                if stats:
                    mins = stats.get("min", [])
                    maxs = stats.get("max", [])
                    if mins and maxs:
                        global_min = np.asarray(mins, dtype=np.float64)
                        global_max = np.asarray(maxs, dtype=np.float64)
                        global_range = global_max - global_min
                        ep_min = action_arr.min(axis=0)
                        ep_max = action_arr.max(axis=0)
                        ep_range = ep_max - ep_min
                        for dim in range(len(ep_range)):
                            if global_range[dim] < 0.002:
                                continue  # Skip joints with negligible global range (grippers, fixed)
                            ratio = ep_range[dim] / max(global_range[dim], 1e-9)
                            if ratio < 0.10:
                                warnings.append(
                                    WarningItem(
                                        type="action_dim_low",
                                        level="info",
                                        message=f"Dim {dim} range is {ratio:.0%} of global ({ep_range[dim]:.4f} vs {global_range[dim]:.4f}), may be inactive.",
                                    )
                                )
                                break
        else:
            warnings.append(
                WarningItem(
                    type="missing_action",
                    level="info",
                    message="Action field is missing.",
                )
            )

        meta = self.meta
        missing_cameras = []
        for camera in self.camera_keys:
            try:
                video_path = self.root / meta.get_video_file_path(episode_id, camera)
                if not video_path.exists():
                    missing_cameras.append(camera)
            except Exception:
                continue
        if missing_cameras:
            warnings.append(
                WarningItem(
                    type="missing_image",
                    level="warning",
                    message=f"Episode video file is missing cameras: {', '.join(missing_cameras)}.",
                )
            )
        return warnings

    def warnings(self, episode_id: int) -> list[WarningItem]:
        detail = self.episode(episode_id)
        timestamps = self.series(episode_id, "timestamps")
        actions = self.series(episode_id, "actions")
        return self._compute_warnings(episode_id, detail, timestamps, actions)

    def analyze(self) -> dict:
        """Full dataset analysis across all episodes."""
        cache_key = f"analysis_{self.root.name}_{hash(str(self.root))}"
        cached = self._get_series_from_cache(cache_key)
        if cached is not None:
            return cached

        episodes = self.episodes()
        fps_nominal = getattr(self.meta, "fps", None)
        total_frames = 0
        total_duration = 0.0

        action_jumps = []
        fps_deviations = []
        frame_gaps = []
        issues = []
        all_fps_values = []
        all_per_episode_zscores = []  # (ep_id, zscores_list, median, mad)

        # Per-dimension global range for joint activity analysis
        stats = self._data_stats(ACTION_KEYS)
        global_min = []
        global_max = []
        joint_names = self._feature_names(ACTION_KEYS) or []
        if stats:
            global_min = stats.get("min", [])
            global_max = stats.get("max", [])

        for ep in episodes:
            ts = self.series(ep.id, "timestamps")
            actions = self.series(ep.id, "actions")
            total_frames += ep.frame_count

            # --- Duration ---
            ts_clean = [x for x in ts if x is not None]
            if len(ts_clean) >= 2:
                dur = ts_clean[-1] - ts_clean[0]
                total_duration += dur

            # --- FPS stability ---
            if len(ts_clean) >= 3 and fps_nominal:
                diffs = np.diff(np.asarray(ts_clean, dtype=np.float64))
                positive = diffs[diffs > 0]
                if len(positive) > 0:
                    actual_fps = float(1.0 / np.median(positive))
                    all_fps_values.append(actual_fps)
                    ratio = actual_fps / float(fps_nominal)
                    if ratio < 0.8 or ratio > 1.3:
                        fps_deviations.append(
                            {
                                "episode": ep.id,
                                "nominal": fps_nominal,
                                "actual": round(actual_fps, 1),
                                "ratio": round(ratio, 2),
                            }
                        )

            # --- Action jumps: collect per-episode zscores ---
            act_clean = [a for a in actions if a is not None]
            if len(act_clean) > 3:
                action_arr = np.asarray(act_clean, dtype=np.float64)
                if action_arr.ndim == 2:
                    jumps = np.linalg.norm(np.diff(action_arr, axis=0), axis=1)
                    ep_median = float(np.median(jumps))
                    ep_mad = float(np.median(np.abs(jumps - ep_median))) or 1e-9
                    ep_zscores = ((jumps - ep_median) / ep_mad).tolist()
                    all_per_episode_zscores.append(
                        (ep.id, ep_zscores, ep_median, ep_mad)
                    )

            # --- Frame index continuity ---
            try:
                fi_data = self._parquet_batch_columns(ep.id, ["frame_index"])
                if "frame_index" in fi_data:
                    fi_vals = fi_data["frame_index"]
                    for i in range(1, len(fi_vals)):
                        prev = fi_vals[i - 1]
                        curr = fi_vals[i]
                        if isinstance(prev, (int, float)) and isinstance(
                            curr, (int, float)
                        ):
                            gap = int(curr) - int(prev) - 1
                            if gap > 0:
                                frame_gaps.append(
                                    {
                                        "episode": ep.id,
                                        "position": i,
                                        "gap": gap,
                                    }
                                )
                                break
            except Exception:
                pass

        # --- Adaptive action jump threshold ---
        adaptive_threshold = None
        if all_per_episode_zscores:
            all_zs = np.concatenate([zs for _, zs, _, _ in all_per_episode_zscores])
            all_zs = all_zs[all_zs > 0]  # Only consider positive zscores (upward jumps)
            if len(all_zs) > 0:
                z_median = float(np.median(all_zs))
                z_mad = float(np.median(np.abs(all_zs - z_median))) or 1e-9
                # Threshold = max(99.7 percentile, median + 8 * MAD) of zscore distribution
                p99_7 = float(np.percentile(all_zs, 99.7))
                mad_threshold = z_median + 8.0 * z_mad
                adaptive_threshold = max(
                    p99_7, mad_threshold, self.settings.action_jump_zscore
                )
                self._cached_jump_threshold = adaptive_threshold
                # Apply threshold to detect jumps
                for ep_id, zscores, ep_median, ep_mad in all_per_episode_zscores:
                    for idx, z in enumerate(zscores):
                        if z > adaptive_threshold:
                            action_jumps.append(
                                {
                                    "episode": ep_id,
                                    "from_frame": idx,
                                    "to_frame": idx + 1,
                                    "zscore": round(float(z), 1),
                                }
                            )

        # --- Joint activity (per-episode aggregate) ---
        active_joints = set()
        inactive_joints = []
        if global_min and global_max:
            seen_inactive = set()
            for dim in range(len(global_min)):
                r = global_max[dim] - global_min[dim]
                name = joint_names[dim] if dim < len(joint_names) else f"dim{dim}"
                parts = name.split("_")
                if parts[0] in ("left", "right"):
                    short = parts[0][0].upper() + "_" + parts[-1]
                else:
                    short = parts[-1]
                if r >= 0.002:
                    active_joints.add(short)
                elif short not in seen_inactive:
                    seen_inactive.add(short)
                    inactive_joints.append(short)

        # --- Summary ---
        actual_fps_median = float(np.median(all_fps_values)) if all_fps_values else None
        summaries = []

        summaries.append(
            f"共 {len(episodes)} 个 episode，{total_frames} 帧，录制时长 {total_duration:.1f}s"
        )
        if fps_nominal:
            summaries.append(
                f"标称 FPS: {fps_nominal:.0f}"
                + (
                    f"，实际中位数 FPS: {actual_fps_median:.1f}"
                    if actual_fps_median
                    else ""
                )
            )

        if active_joints:
            summaries.append(f"活跃关节: {', '.join(sorted(active_joints))}")
        if inactive_joints:
            summaries.append(
                f"基本不动: {', '.join(inactive_joints)}（全局范围 < 0.002，可能是 gripper 或录制时未操作）"
            )

        if action_jumps and adaptive_threshold is not None:
            summaries.append(
                f"动作跳变: 共 {len(action_jumps)} 处（阈值 z>{adaptive_threshold:.1f}），分布在 {len(set(j['episode'] for j in action_jumps))} 个 episode"
            )
        elif action_jumps:
            summaries.append(
                f"动作跳变: 共 {len(action_jumps)} 处，分布在 {len(set(j['episode'] for j in action_jumps))} 个 episode"
            )
        if fps_deviations:
            summaries.append(f"帧率异常: 共 {len(fps_deviations)} 个 episode")
        if frame_gaps:
            summaries.append(f"帧索引缺失: 共 {len(frame_gaps)} 个 episode")

        issue_episodes = (
            set(j["episode"] for j in action_jumps)
            | set(d["episode"] for d in fps_deviations)
            | set(g["episode"] for g in frame_gaps)
        )
        clean_count = len(episodes) - len(issue_episodes)
        if issue_episodes:
            summaries.append(
                f"有异常的 episode: {sorted(issue_episodes)}，无异常的: {clean_count} 个"
            )
        else:
            summaries.append("所有 episode 均无明显异常")

        result = {
            "total_episodes": len(episodes),
            "total_frames": total_frames,
            "total_duration": round(total_duration, 1),
            "nominal_fps": fps_nominal,
            "actual_fps": round(actual_fps_median, 1) if actual_fps_median else None,
            "active_joints": active_joints,
            "inactive_joints": inactive_joints,
            "action_jumps": action_jumps,
            "fps_deviations": fps_deviations,
            "frame_gaps": frame_gaps,
            "summary": "\n".join(summaries),
        }
        self._save_series_to_cache(cache_key, result)
        return result


@lru_cache
def get_loader() -> LeRobotDatasetLoader:
    return LeRobotDatasetLoader(get_settings())


def load_dataset_from_path(
    dataset_path: str, repo_id: str | None = None
) -> DatasetInfo:
    settings = get_settings()
    settings.dataset_path = Path(dataset_path).expanduser().resolve()
    settings.repo_id = repo_id or None
    get_loader.cache_clear()
    return get_loader().dataset_info()
