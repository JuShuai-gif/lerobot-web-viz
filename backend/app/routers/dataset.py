from pathlib import Path
import shutil
import subprocess

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..config import get_settings
from ..dataset_loader import DatasetError, get_loader, load_dataset_from_path
from ..schemas import (
    DatasetInfo,
    DatasetLoadRequest,
    DirectoryBrowseResponse,
    DirectoryEntry,
)

router = APIRouter(prefix="/api/dataset", tags=["dataset"])


@router.get("/info", response_model=DatasetInfo)
def dataset_info() -> DatasetInfo:
    try:
        return get_loader().dataset_info()
    except DatasetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/load", response_model=DatasetInfo)
def load_dataset(request: DatasetLoadRequest) -> DatasetInfo:
    try:
        return load_dataset_from_path(request.dataset_path, request.repo_id)
    except DatasetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _dataset_candidate(path: Path) -> bool:
    markers = ("meta", "data", "videos", "episode_data_index", "episodes")
    return any((path / marker).exists() for marker in markers)


@router.get("/browse", response_model=DirectoryBrowseResponse)
def browse_dataset_dirs(
    path: str | None = Query(default=None),
) -> DirectoryBrowseResponse:
    settings = get_settings()
    roots = settings.allowed_browse_roots
    if not roots:
        raise HTTPException(
            status_code=400,
            detail="No browse roots are available. Set LEROBOT_BROWSE_ROOTS.",
        )

    current = Path(path).expanduser().resolve() if path else roots[0]
    if not any(_is_within(current, root) for root in roots):
        raise HTTPException(
            status_code=403, detail="Path is outside allowed browse roots."
        )
    if not current.exists() or not current.is_dir():
        raise HTTPException(
            status_code=404, detail=f"Directory does not exist: {current}"
        )

    parent = current.parent if current.parent != current else None
    if parent is not None and not any(_is_within(parent, root) for root in roots):
        parent = None

    entries: list[DirectoryEntry] = []
    try:
        children = sorted(
            [child for child in current.iterdir() if child.is_dir()],
            key=lambda item: item.name.lower(),
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403, detail=f"Permission denied: {current}"
        ) from exc

    for child in children:
        if child.name.startswith("."):
            continue
        entries.append(
            DirectoryEntry(
                name=child.name,
                path=str(child),
                is_dataset_candidate=_dataset_candidate(child),
            )
        )

    return DirectoryBrowseResponse(
        path=str(current),
        parent=str(parent) if parent else None,
        roots=[str(root) for root in roots],
        entries=entries,
    )


class NativePickResponse(BaseModel):
    path: str


class ScanResult(BaseModel):
    paths: list[str]


@router.get("/scan", response_model=ScanResult)
def scan_datasets(
    max_depth: int = Query(default=3, ge=1, le=6),
    max_results: int = Query(default=50, ge=1, le=200),
) -> ScanResult:
    settings = get_settings()
    roots = settings.allowed_browse_roots
    if not roots:
        raise HTTPException(status_code=400, detail="No scan roots configured.")

    found: list[str] = []
    seen: set[str] = set()
    markers = (
        "meta/info.json",
        "data/chunk-000/file-000.parquet",
        "videos",
        "episodes",
    )

    for root in roots:
        if not root.exists():
            continue
        try:
            for entry in root.rglob("*"):
                if len(found) >= max_results:
                    break
                if not entry.is_dir():
                    continue
                rel = entry.relative_to(root)
                if len(rel.parts) > max_depth:
                    continue
                path_str = str(entry)
                if path_str in seen:
                    continue
                seen.add(path_str)
                for marker in markers:
                    if (entry / marker).exists():
                        found.append(path_str)
                        break
        except PermissionError:
            continue

    return ScanResult(paths=sorted(found))


@router.post("/pick-folder", response_model=NativePickResponse)
def native_pick_folder() -> NativePickResponse:
    dialogs = [
        (
            "zenity",
            ["--file-selection", "--directory", "--title=Select Dataset Folder"],
        ),
        ("kdialog", ["--getexistingdirectory"]),
        (
            "osascript",
            ["-e", 'POSIX path of (choose folder with prompt "Select Dataset Folder")'],
        ),
    ]

    # Build env with proper X11 auth for the local display
    import os as _os
    import pwd as _pwd

    env = dict(_os.environ)
    if not env.get("DISPLAY"):
        x11_dir = Path("/tmp/.X11-unix")
        if x11_dir.exists():
            displays = sorted(
                [f.name for f in x11_dir.iterdir() if f.name.startswith("X")],
                key=lambda x: int(x[1:]) if x[1:].isdigit() else 999,
            )
            if displays:
                env["DISPLAY"] = ":" + displays[0][1:]

    if not env.get("XAUTHORITY"):
        uid = _os.getuid()
        candidates = [
            f"/run/user/{uid}/gdm/Xauthority",
            f"/run/user/{uid}/.mutter-Xwaylandauth.*",
            str(Path.home() / ".Xauthority"),
        ]
        for cand in candidates:
            import glob as _glob

            matches = _glob.glob(cand)
            if matches:
                env["XAUTHORITY"] = str(Path(matches[0]).resolve())
                break

    for cmd, args in dialogs:
        binary = shutil.which(cmd)
        if binary is None:
            continue
        try:
            result = subprocess.run(
                [binary] + args,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip().strip('"').strip("'")
                if path and Path(path).expanduser().resolve().is_dir():
                    return NativePickResponse(path=path)
        except Exception:
            continue

    raise HTTPException(
        status_code=400,
        detail="No native file dialog available. Install zenity, kdialog, or use the server Browse button instead.",
    )
