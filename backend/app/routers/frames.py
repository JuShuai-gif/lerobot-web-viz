from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from ..config import get_settings
from ..dataset_loader import DatasetError, get_loader
from ..schemas import FrameInfo
from ..video_stream import jpeg_response

router = APIRouter(prefix="/api/episodes", tags=["frames"])


@router.get("/{episode_id}/frames/{frame_id}", response_model=FrameInfo)
def get_frame_info(episode_id: int, frame_id: int) -> FrameInfo:
    try:
        return get_loader().frame_info(episode_id, frame_id)
    except DatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{episode_id}/frames/{frame_id}/{camera_name:path}")
def get_frame_image(
    episode_id: int,
    frame_id: int,
    camera_name: str,
    background_tasks: BackgroundTasks,
    quality: int | None = Query(default=None, ge=1, le=95),
):
    settings = get_settings()
    jpeg_quality = quality or settings.default_jpeg_quality
    try:
        loader = get_loader()
        content = loader.frame_jpeg(episode_id, frame_id, camera_name, jpeg_quality)
        background_tasks.add_task(loader.preload_frames, episode_id, frame_id, jpeg_quality)
        return jpeg_response(content)
    except DatasetError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
