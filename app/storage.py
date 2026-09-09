"""사용자 홈 폴더의 JSON 파일로 설정과 대화를 저장한다. plan2 4.3절.

Windows: %APPDATA%\\MyChatGPTWeb\\
macOS:   ~/Library/Application Support/MyChatGPTWeb/
그 외:   ~/.mychatgptweb/
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.models import ENV_KEY_NAME, Conversation, Settings

APP_DIR_NAME = "MyChatGPTWeb"
CONFIG_FILE = "config.json"
CONVERSATIONS_FILE = "conversations.json"


def data_dir() -> Path:
    override = os.environ.get("MCW_DATA_DIR")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / APP_DIR_NAME
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        path = Path.home() / ".mychatgptweb"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _config_path() -> Path:
    return data_dir() / CONFIG_FILE


def _conversations_path() -> Path:
    return data_dir() / CONVERSATIONS_FILE


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        # 손상된 파일은 백업해 두고 기본값으로 시작한다.
        try:
            path.replace(path.with_suffix(path.suffix + ".corrupt"))
        except OSError:
            pass
        return default


def _write_json(path: Path, data: Any) -> None:
    """임시 파일에 쓴 뒤 교체해서, 쓰는 도중 프로그램이 죽어도 원본이 깨지지 않게 한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------- 설정 ----------

def env_api_key() -> str:
    """환경변수에 등록된 키. 없으면 빈 문자열."""
    return os.environ.get(ENV_KEY_NAME, "").strip()


def load_settings() -> Settings:
    return Settings.from_dict(_read_json(_config_path(), {}))


def save_settings(settings: Settings) -> None:
    """remember_key가 False면 api_key는 파일에 쓰지 않는다."""
    _write_json(_config_path(), settings.to_dict(include_key=settings.remember_key))


def clear_api_key() -> None:
    s = load_settings()
    s.api_key = ""
    _write_json(_config_path(), s.to_dict(include_key=False))


# ---------- 대화 ----------

def load_conversations() -> list[Conversation]:
    raw = _read_json(_conversations_path(), [])
    if not isinstance(raw, list):
        return []
    convs = [Conversation.from_dict(d) for d in raw if isinstance(d, dict)]
    convs.sort(key=lambda c: c.updated_at, reverse=True)
    return convs


def save_conversations(convs: list[Conversation]) -> None:
    _write_json(_conversations_path(), [c.to_dict() for c in convs])
