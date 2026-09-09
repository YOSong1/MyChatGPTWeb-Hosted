"""Streamlit 앱 본체.

개발 중 실행: streamlit run app/main.py  또는  python launcher.py
빌드 후에는 streamlit_entry.py가 이 모듈의 main()을 부른다.
키가 없으면 키 입력 화면, 있으면 채팅 화면을 보여준다.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run app/main.py`로 실행하면 sys.path에 app/만 들어가므로 프로젝트 루트를 추가한다.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from app import storage  # noqa: E402
from app.models import Settings  # noqa: E402
from app.ui import chat_screen, key_screen  # noqa: E402


def _load_state() -> Settings:
    if "settings" not in st.session_state:
        st.session_state["settings"] = storage.load_settings()
    settings: Settings = st.session_state["settings"]

    if "api_key" not in st.session_state:
        env_key = storage.env_api_key()
        if env_key and not st.session_state.get("ignore_env_key"):
            # 1순위: 환경변수. 파일에는 저장하지 않는다.
            st.session_state["api_key"] = env_key
            st.session_state["key_source"] = "env"
        elif settings.api_key:
            # 2순위: 파일에 저장된 키(remember_key=True)
            st.session_state["api_key"] = settings.api_key
            st.session_state["key_source"] = "file"
    return settings


def main() -> None:
    st.set_page_config(
        page_title="MyChatGPTWeb",
        page_icon="💬",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    settings = _load_state()

    if st.session_state.get("api_key"):
        settings.api_key = st.session_state["api_key"]
        chat_screen.render(settings)
    else:
        key_screen.render(settings, notice=st.session_state.pop("key_notice", None))


if __name__ == "__main__":
    main()
