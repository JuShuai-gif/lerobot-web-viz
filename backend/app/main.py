from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .dataset_loader import DatasetError
from .routers import dataset, episodes, frames, health

settings = get_settings()

app = FastAPI(
    title="lerobot-web-viz",
    description="Web visualization platform for local LeRobot datasets.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials="*" not in settings.origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=500)

app.include_router(health.router)
app.include_router(dataset.router)
app.include_router(episodes.router)
app.include_router(frames.router)


@app.exception_handler(DatasetError)
async def dataset_error_handler(_request: Request, exc: DatasetError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})
