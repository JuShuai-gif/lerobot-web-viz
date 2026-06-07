# Backend

FastAPI backend for `lerobot-web-viz`.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export LEROBOT_DATASET_PATH=/path/to/dataset
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Optional environment variables:

- `LEROBOT_REPO_ID`: override repo id when the dataset path name is not the repo id.
- `LEROBOT_PRELOAD_FRAMES`: number of future frames decoded after each image request.
- `LEROBOT_FRAME_CACHE_SIZE`: JPEG frame LRU cache size.
- `LEROBOT_JPEG_QUALITY`: default JPEG quality.
- `LEROBOT_BROWSE_ROOTS`: colon-separated server directories that the frontend may browse.

Runtime dataset loading:

```bash
curl -X POST http://localhost:8000/api/dataset/load \
  -H 'Content-Type: application/json' \
  -d '{"dataset_path":"/path/to/dataset","repo_id":null}'
```

Video playback endpoints:

```txt
GET /api/episodes/{episode_id}/videos
GET /api/episodes/{episode_id}/videos/file/{camera_name}
```

The metadata endpoint returns mp4 URLs plus per-episode `from_timestamp` and `to_timestamp` offsets for each camera.
