"""Which app to download. Store-specific behavior stays in each script."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Project:
    slug: str
    name: str
    ios_app_id: str
    android_package: str


def load_project() -> Project:
    _load_dotenv(ROOT / ".env")
    project = Project(
        slug=_required("PROJECT"),
        name=_required("APP_NAME"),
        ios_app_id=_required("IOS_APP_ID"),
        android_package=_required("ANDROID_PACKAGE"),
    )
    _validate(project)
    return project


def _required(key: str) -> str:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        raise SystemExit(
            f"{key} が未設定です。.env.example を .env にコピーして設定してください"
        )
    return raw.strip()


def _validate(project: Project) -> None:
    if not project.slug or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for char in project.slug
    ):
        raise SystemExit(f"PROJECT が不正です: {project.slug}")
    if not project.name:
        raise SystemExit("APP_NAME が空です")
    if not project.ios_app_id.isdigit():
        raise SystemExit(f"IOS_APP_ID は数字です: {project.ios_app_id}")
    parts = project.android_package.split(".")
    if len(parts) < 2 or any(
        not part or any(not (char.isalnum() or char == "_") for char in part)
        for part in parts
    ):
        raise SystemExit(f"ANDROID_PACKAGE が不正です: {project.android_package}")


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        if text.startswith("export "):
            text = text[len("export ") :].strip()
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)
