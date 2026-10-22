"""JSON-backed persistence for study sessions and quiz attempts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_history(history_path: Path) -> list[dict[str, Any]]:
    try:
        history = json.loads(history_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    return history if isinstance(history, list) else []


def save_history(history_path: Path, history: list[dict[str, Any]]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = history_path.with_suffix(history_path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(history_path)


def record_session(
    history_path: Path,
    context: dict[str, Any],
    report_path: Path,
) -> list[dict[str, Any]]:
    history = load_history(history_path)
    history = [item for item in history if item.get("session_id") != context["session_id"]]
    history.insert(
        0,
        {
            "session_id": context["session_id"],
            "created_at": context["created_at"],
            "subject": context["subject"],
            "topic": context["topic"],
            "source_count": len(context["sources"]),
            "quiz_count": len(context["questions"]),
            "generation_mode": context["generation_mode"],
            "fact_check_passed": context["fact_check_passed"],
            "report_path": str(report_path),
            "attempts": [],
        },
    )
    save_history(history_path, history[:100])
    return history[:100]


def record_quiz_attempt(
    history_path: Path,
    session_id: str,
    attempt: dict[str, Any],
) -> list[dict[str, Any]]:
    history = load_history(history_path)
    for item in history:
        if item.get("session_id") == session_id:
            item.setdefault("attempts", []).append(attempt)
            item["latest_score"] = attempt["score"]
            item["latest_total"] = attempt["total"]
            break
    save_history(history_path, history)
    return history
