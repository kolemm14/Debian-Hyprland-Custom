"""Inspect local projects without evaluating their content."""
from dataclasses import dataclass
import json
from pathlib import Path

from ..playback import MEDIA_EXTENSIONS


@dataclass(frozen=True)
class Project:
    path: Path
    kind: str
    media: Path | None = None


def detect_project(path: str | Path) -> Project:
    root = Path(path).expanduser().resolve(strict=True)
    if root.is_file() and root.suffix.lower() in MEDIA_EXTENSIONS:
        kind = 'image' if root.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.avif', '.bmp'} else 'video'
        return Project(root, kind, root)
    if root.name == 'project.json' and root.is_file():
        root = root.parent
    manifest = root / 'project.json'
    if not root.is_dir() or not manifest.is_file():
        raise ValueError('Expected a local media file or project directory with project.json')
    if not manifest.resolve().is_relative_to(root):
        raise ValueError('project.json escapes the project directory')
    with manifest.open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('project.json exceeds 1 MiB')
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('project.json must be an object')
    kind = str(data.get('type', '')).lower()
    if kind not in {'video', 'image', 'scene', 'web'}:
        raise ValueError('Unsupported project type')
    entry = data.get('file')
    if not isinstance(entry, str) or not entry or Path(entry).is_absolute():
        raise ValueError('Project must declare a relative file')
    target = (root / entry).resolve(strict=True)
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError('Project entry escapes the directory or is not a file')
    if kind in {'video', 'image'} and target.suffix.lower() not in MEDIA_EXTENSIONS:
        raise ValueError('Unsupported original media; previews are never substituted')
    return Project(root, kind, target if kind in {'video', 'image'} else None)
