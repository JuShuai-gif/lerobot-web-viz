from pydantic import BaseModel


class CameraInfo(BaseModel):
    name: str


class DatasetLoadRequest(BaseModel):
    dataset_path: str
    repo_id: str | None = None


class DatasetInfo(BaseModel):
    dataset_path: str
    repo_id: str
    fps: float | None = None
    total_frames: int
    total_episodes: int
    camera_keys: list[str]
    action_dim: int | None = None
    state_dim: int | None = None
    action_names: list[str] | None = None
    state_names: list[str] | None = None
    feature_keys: list[str] = []
    task_map: dict[int, str] = {}
    action_stats: dict | None = None
    state_stats: dict | None = None


class EpisodeSummary(BaseModel):
    id: int
    start_index: int
    end_index: int
    frame_count: int
    duration: float | None = None
    tasks: list[str] = []


class EpisodeDetail(EpisodeSummary):
    fps: float | None = None
    camera_keys: list[str]
    action_dim: int | None = None
    state_dim: int | None = None


class FrameInfo(BaseModel):
    episode_id: int
    frame_id: int
    timestamp: float | None = None
    cameras: list[str]
    action: list[float] | None = None
    state: list[float] | None = None


class SeriesResponse(BaseModel):
    episode_id: int
    values: list


class WarningItem(BaseModel):
    type: str
    level: str
    message: str


class WarningResponse(BaseModel):
    episode_id: int
    warnings: list[WarningItem]


class DirectoryEntry(BaseModel):
    name: str
    path: str
    is_dataset_candidate: bool = False


class DirectoryBrowseResponse(BaseModel):
    path: str
    parent: str | None = None
    roots: list[str]
    entries: list[DirectoryEntry]


class VideoSegment(BaseModel):
    camera: str
    url: str
    file_path: str
    from_timestamp: float
    to_timestamp: float
    duration: float
    fps: float | None = None


class EpisodeVideosResponse(BaseModel):
    episode_id: int
    videos: list[VideoSegment]


class TrajectoryResponse(BaseModel):
    episode_id: int
    actions: list
    states: list
    timestamps: list
    warnings: list[WarningItem]
