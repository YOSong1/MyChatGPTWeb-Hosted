"""호스팅 모드 저장소. 접속자(브라우저 세션)별 메모리에만 둔다.

- 여러 학생이 한 서버를 같이 쓰므로 서버 디스크에 키·설정·대화를 쓰지 않는다.
- API Key는 st.session_state에만 있다가 탭을 닫거나 새로고침하면 사라진다.
- 서버의 환경변수 키는 절대 사용하지 않는다(관리자 키가 학생에게 노출되면 안 된다).
- 답변이 만든 파일만 세션별 임시 폴더에 두고, 오래된 폴더는 주기적으로 지운다.

로컬 실행 버전(MyChatGPTWeb)의 storage.py와 함수 이름·시그니처를 맞춰 두어 UI 코드를 공유한다.
"""

from __future__ import annotations

import shutil
import tempfile
import time
import uuid
from pathlib import Path

import streamlit as st

from app.models import Conversation, Settings

APP_DIR_NAME = "mychatgptweb-hosted"
FILES_MAX_AGE_SEC = 6 * 3600  # 이보다 오래된 세션 파일 폴더는 삭제


# ---------- 세션 식별 ----------

def session_id() -> str:
    sid = st.session_state.get("_sid")
    if not sid:
        sid = uuid.uuid4().hex
        st.session_state["_sid"] = sid
    return sid


def data_dir() -> Path:
    """세션 파일의 루트. 서버 임시 폴더 아래."""
    path = Path(tempfile.gettempdir()) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------- 설정 ----------

def env_api_key() -> str:
    """호스팅 모드에서는 서버 환경변수의 키를 쓰지 않는다."""
    return ""


def load_settings() -> Settings:
    s = st.session_state.get("_settings")
    if s is None:
        s = Settings()
        s.remember_key = False
        st.session_state["_settings"] = s
    return s


def save_settings(settings: Settings) -> None:
    settings.remember_key = False
    st.session_state["_settings"] = settings


def clear_api_key() -> None:
    s = load_settings()
    s.api_key = ""


# ---------- 생성 파일 ----------

def _cleanup_old_sessions() -> None:
    """한 세션당 한 번, 오래된 세션 폴더를 정리한다."""
    if st.session_state.get("_cleaned"):
        return
    st.session_state["_cleaned"] = True
    now = time.time()
    try:
        for d in data_dir().iterdir():
            try:
                if d.is_dir() and now - d.stat().st_mtime > FILES_MAX_AGE_SEC:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                pass
    except OSError:
        pass


def files_dir(conv_id: str) -> Path:
    """답변이 만든 파일을 두는 폴더. 세션별 → 대화별."""
    _cleanup_old_sessions()
    path = data_dir() / session_id() / conv_id
    path.mkdir(parents=True, exist_ok=True)
    # 폴더 수정 시각을 갱신해 정리 대상에서 제외한다.
    try:
        (data_dir() / session_id()).touch()
    except OSError:
        pass
    return path


def delete_files(conv_id: str) -> None:
    path = data_dir() / session_id() / conv_id
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


# ---------- 대화 ----------

def load_conversations() -> list[Conversation]:
    convs = st.session_state.get("_conversations")
    if convs is None:
        convs = []
        st.session_state["_conversations"] = convs
    convs.sort(key=lambda c: c.updated_at, reverse=True)
    return convs


def save_conversations(convs: list[Conversation]) -> None:
    st.session_state["_conversations"] = convs
