from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..dataset_loader import DatasetError, get_loader
from ..schemas import (
    EpisodeDetail,
    EpisodeSummary,
    EpisodeVideosResponse,
    SeriesResponse,
    TrajectoryResponse,
    WarningResponse,
)

router = APIRouter(prefix="/api/episodes", tags=["episodes"])


@router.get("", response_model=list[EpisodeSummary])
def list_episodes() -> list[EpisodeSummary]:
    try:
        return get_loader().episodes()
    except DatasetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{episode_id}", response_model=EpisodeDetail)
def get_episode(episode_id: int) -> EpisodeDetail:
    try:
        return get_loader().episode(episode_id)
    except DatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{episode_id}/actions", response_model=SeriesResponse)
def get_actions(
    episode_id: int,
    start: int = Query(default=0, ge=0),
    end: int | None = Query(default=None, ge=0),
) -> SeriesResponse:
    try:
        return SeriesResponse(
            episode_id=episode_id,
            values=get_loader().series(
                episode_id, "actions", start_frame=start, end_frame=end
            ),
        )
    except DatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{episode_id}/states", response_model=SeriesResponse)
def get_states(
    episode_id: int,
    start: int = Query(default=0, ge=0),
    end: int | None = Query(default=None, ge=0),
) -> SeriesResponse:
    try:
        return SeriesResponse(
            episode_id=episode_id,
            values=get_loader().series(
                episode_id, "states", start_frame=start, end_frame=end
            ),
        )
    except DatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{episode_id}/timestamps", response_model=SeriesResponse)
def get_timestamps(
    episode_id: int,
    start: int = Query(default=0, ge=0),
    end: int | None = Query(default=None, ge=0),
) -> SeriesResponse:
    try:
        return SeriesResponse(
            episode_id=episode_id,
            values=get_loader().series(
                episode_id, "timestamps", start_frame=start, end_frame=end
            ),
        )
    except DatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{episode_id}/trajectories", response_model=TrajectoryResponse)
def get_trajectories(episode_id: int) -> TrajectoryResponse:
    try:
        data = get_loader().trajectories(episode_id)
        return TrajectoryResponse(
            episode_id=episode_id,
            actions=data["actions"],
            states=data["states"],
            timestamps=data["timestamps"],
            warnings=data["warnings"],
        )
    except DatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{episode_id}/feature/{feature_key:path}", response_model=SeriesResponse)
def get_feature_series(episode_id: int, feature_key: str) -> SeriesResponse:
    try:
        return SeriesResponse(
            episode_id=episode_id,
            values=get_loader().series_raw(episode_id, feature_key),
        )
    except DatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{episode_id}/warnings", response_model=WarningResponse)
def get_warnings(episode_id: int) -> WarningResponse:
    try:
        return WarningResponse(
            episode_id=episode_id, warnings=get_loader().warnings(episode_id)
        )
    except DatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{episode_id}/videos", response_model=EpisodeVideosResponse)
def get_episode_videos(episode_id: int) -> EpisodeVideosResponse:
    try:
        return EpisodeVideosResponse(
            episode_id=episode_id, videos=get_loader().video_segments(episode_id)
        )
    except DatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{episode_id}/videos/file/{camera_name:path}")
def get_episode_video_file(episode_id: int, camera_name: str) -> FileResponse:
    try:
        segment = next(
            (
                item
                for item in get_loader().video_segments(episode_id)
                if item.camera == camera_name
            ),
            None,
        )
        if segment is None:
            raise DatasetError(f"Video for camera '{camera_name}' does not exist.")
        return FileResponse(
            segment.file_path,
            media_type="video/mp4",
            filename=f"episode_{episode_id}_{camera_name}.mp4",
        )
    except DatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
