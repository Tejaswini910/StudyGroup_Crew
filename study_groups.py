"""Local JSON-backed collaboration for study groups, meetings, materials, and goals."""

from __future__ import annotations

import json
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_STORE_PATH = PROJECT_ROOT / "outputs" / "study_groups.json"
DEFAULT_UPLOAD_DIR = PROJECT_ROOT / "outputs" / "group_uploads"
_STORE_LOCK = threading.RLock()
_ALLOWED_UPLOADS = {".md", ".txt", ".pdf", ".doc", ".docx", ".ppt", ".pptx"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(path: Path) -> dict[str, Any]:
    try:
        store = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"groups": []}
    if not isinstance(store, dict) or not isinstance(store.get("groups"), list):
        return {"groups": []}
    return store


def _save(path: Path, store: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


def _clean_name(value: str, label: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"Enter a {label}.")
    if len(cleaned) > 100:
        raise ValueError(f"{label.title()} must be 100 characters or fewer.")
    return cleaned


def list_groups(store_path: Path = DEFAULT_STORE_PATH) -> list[dict[str, Any]]:
    with _STORE_LOCK:
        return _load(store_path)["groups"]


def get_group(code: str, store_path: Path = DEFAULT_STORE_PATH) -> dict[str, Any] | None:
    normalized = code.strip().upper()
    with _STORE_LOCK:
        return next(
            (group for group in _load(store_path)["groups"] if group["code"] == normalized),
            None,
        )


def create_group(
    name: str,
    creator: str,
    store_path: Path = DEFAULT_STORE_PATH,
) -> dict[str, Any]:
    group_name = _clean_name(name, "group name")
    member_name = _clean_name(creator, "display name")
    with _STORE_LOCK:
        store = _load(store_path)
        existing_codes = {group["code"] for group in store["groups"]}
        code = secrets.token_hex(4).upper()
        while code in existing_codes:
            code = secrets.token_hex(4).upper()
        group = {
            "code": code,
            "name": group_name,
            "created_at": _now(),
            "created_by": member_name,
            "members": [{"name": member_name, "joined_at": _now()}],
            "meetings": [],
            "materials": [],
            "messages": [],
            "goals": [],
        }
        store["groups"].insert(0, group)
        _save(store_path, store)
        return group


def join_group(
    code: str,
    member: str,
    store_path: Path = DEFAULT_STORE_PATH,
) -> dict[str, Any]:
    member_name = _clean_name(member, "display name")
    normalized = code.strip().upper()
    with _STORE_LOCK:
        store = _load(store_path)
        group = next((item for item in store["groups"] if item["code"] == normalized), None)
        if group is None:
            raise ValueError("No study group matches that code.")
        if not any(item["name"].casefold() == member_name.casefold() for item in group["members"]):
            group["members"].append({"name": member_name, "joined_at": _now()})
        _save(store_path, store)
        return group


def _update_group(
    code: str,
    update: Callable[[dict[str, Any]], Any],
    store_path: Path = DEFAULT_STORE_PATH,
) -> dict[str, Any]:
    normalized = code.strip().upper()
    with _STORE_LOCK:
        store = _load(store_path)
        group = next((item for item in store["groups"] if item["code"] == normalized), None)
        if group is None:
            raise ValueError("Study group not found. Check the group code.")
        update(group)
        _save(store_path, store)
        return group


def schedule_meeting(
    code: str,
    topic: str,
    starts_at: str,
    duration_minutes: int,
    agenda: str,
    organizer: str,
    store_path: Path = DEFAULT_STORE_PATH,
) -> dict[str, Any]:
    meeting_topic = _clean_name(topic, "session topic")
    organizer_name = _clean_name(organizer, "organizer name")
    if not 15 <= duration_minutes <= 360:
        raise ValueError("Session duration must be between 15 and 360 minutes.")
    try:
        datetime.fromisoformat(starts_at)
    except ValueError as error:
        raise ValueError("Choose a valid session date and time.") from error
    meeting = {
        "meeting_id": uuid.uuid4().hex,
        "topic": meeting_topic,
        "starts_at": starts_at,
        "duration_minutes": duration_minutes,
        "agenda": agenda.strip()[:4000],
        "organizer": organizer_name,
        "status": "scheduled",
        "created_at": _now(),
    }
    _update_group(code, lambda group: group["meetings"].append(meeting), store_path)
    return meeting


def update_meeting(
    code: str,
    meeting_id: str,
    *,
    starts_at: str | None = None,
    status: str | None = None,
    store_path: Path = DEFAULT_STORE_PATH,
) -> dict[str, Any]:
    if status is not None and status not in {"scheduled", "cancelled", "completed"}:
        raise ValueError("Invalid meeting status.")
    if starts_at is not None:
        try:
            datetime.fromisoformat(starts_at)
        except ValueError as error:
            raise ValueError("Choose a valid session date and time.") from error

    def apply(group: dict[str, Any]) -> None:
        meeting = next((item for item in group["meetings"] if item["meeting_id"] == meeting_id), None)
        if meeting is None:
            raise ValueError("Study session not found.")
        if starts_at is not None:
            meeting["starts_at"] = starts_at
        if status is not None:
            meeting["status"] = status

    return _update_group(code, apply, store_path)


def add_note(
    code: str,
    title: str,
    content: str,
    author: str,
    store_path: Path = DEFAULT_STORE_PATH,
) -> dict[str, Any]:
    note_title = _clean_name(title, "note title")
    author_name = _clean_name(author, "display name")
    note_content = content.strip()
    if not note_content:
        raise ValueError("Add note content before sharing.")
    if len(note_content) > 100_000:
        raise ValueError("Shared notes must be 100,000 characters or fewer.")
    material = {
        "material_id": uuid.uuid4().hex,
        "kind": "note",
        "title": note_title,
        "author": author_name,
        "created_at": _now(),
        "content": note_content,
    }
    _update_group(code, lambda group: group["materials"].insert(0, material), store_path)
    return material


def add_file(
    code: str,
    filename: str,
    content: bytes,
    author: str,
    *,
    store_path: Path = DEFAULT_STORE_PATH,
    upload_dir: Path = DEFAULT_UPLOAD_DIR,
) -> dict[str, Any]:
    author_name = _clean_name(author, "display name")
    original_name = Path(filename).name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_UPLOADS:
        raise ValueError("Share a .md, .txt, .pdf, .doc, .docx, .ppt, or .pptx file.")
    if not content:
        raise ValueError("The selected file is empty.")
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("Files must be 10 MB or smaller.")
    group = get_group(code, store_path)
    if group is None:
        raise ValueError("Study group not found. Check the group code.")

    group_upload_dir = upload_dir / group["code"]
    group_upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = group_upload_dir / f"{uuid.uuid4().hex}{suffix}"
    stored_path.write_bytes(content)
    material = {
        "material_id": uuid.uuid4().hex,
        "kind": "file",
        "title": original_name[:180],
        "author": author_name,
        "created_at": _now(),
        "path": str(stored_path.resolve()),
        "size_bytes": len(content),
    }
    _update_group(code, lambda item: item["materials"].insert(0, material), store_path)
    return material


def read_shared_file(
    material: dict[str, Any],
    upload_dir: Path = DEFAULT_UPLOAD_DIR,
) -> bytes | None:
    stored_path = material.get("path")
    if not stored_path:
        return None
    try:
        safe_root = upload_dir.resolve()
        file_path = Path(stored_path).resolve()
        file_path.relative_to(safe_root)
        return file_path.read_bytes()
    except (OSError, ValueError):
        return None


def add_message(
    code: str,
    author: str,
    content: str,
    store_path: Path = DEFAULT_STORE_PATH,
) -> dict[str, Any]:
    author_name = _clean_name(author, "display name")
    message_text = content.strip()
    if not message_text:
        raise ValueError("Write a message before posting.")
    if len(message_text) > 10_000:
        raise ValueError("Discussion posts must be 10,000 characters or fewer.")
    message = {"message_id": uuid.uuid4().hex, "author": author_name, "created_at": _now(), "content": message_text}
    _update_group(code, lambda group: group["messages"].append(message), store_path)
    return message


def add_goal(
    code: str,
    member: str,
    title: str,
    target_date: str,
    store_path: Path = DEFAULT_STORE_PATH,
) -> dict[str, Any]:
    member_name = _clean_name(member, "display name")
    goal_title = _clean_name(title, "goal")
    goal = {
        "goal_id": uuid.uuid4().hex,
        "member": member_name,
        "title": goal_title,
        "target_date": target_date,
        "progress": 0,
        "cheers": [],
        "created_at": _now(),
    }
    _update_group(code, lambda group: group["goals"].insert(0, goal), store_path)
    return goal


def update_goal_progress(
    code: str,
    goal_id: str,
    progress: int,
    *,
    cheer_from: str | None = None,
    store_path: Path = DEFAULT_STORE_PATH,
) -> dict[str, Any]:
    if not 0 <= progress <= 100:
        raise ValueError("Goal progress must be between 0 and 100.")

    def apply(group: dict[str, Any]) -> None:
        goal = next((item for item in group["goals"] if item["goal_id"] == goal_id), None)
        if goal is None:
            raise ValueError("Study goal not found.")
        goal["progress"] = progress
        if cheer_from:
            cheer = _clean_name(cheer_from, "display name")
            if cheer not in goal["cheers"]:
                goal["cheers"].append(cheer)

    return _update_group(code, apply, store_path)
