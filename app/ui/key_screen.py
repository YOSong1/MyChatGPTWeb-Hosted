"""키 입력 화면. plan1 4.1절.

형식 검사 후 OpenAI 서버에 모델 목록을 요청해 키를 검증한다.
"""

from __future__ import annotations

import streamlit as st

from app import openai_client, storage
from app.models import Settings


def _looks_like_key(key: str) -> bool:
    key = key.strip()
    return key.startswith("sk-") and len(key) >= 20 and " " not in key


def render(settings: Settings, notice: str | None = None) -> None:
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.title("API Key를 입력하세요")
        st.caption("키는 이 컴퓨터에만 저장되며 관리자 서버로 전송되지 않습니다.")
        if notice:
            st.warning(notice)

        with st.form("key_form", clear_on_submit=False):
            key = st.text_input(
                "OpenAI API Key",
                type="password",
                placeholder="sk-...",
                autocomplete="off",
            )
            remember = st.checkbox(
                "이 컴퓨터에 기억하기",
                value=True,
                help="해제하면 프로그램을 종료할 때 키가 사라집니다. 공용 PC에서는 해제하세요.",
            )
            submitted = st.form_submit_button("연결 확인 후 시작", type="primary", use_container_width=True)

        if submitted:
            key = key.strip()
            if not key:
                st.error("키를 입력하세요.")
                return
            if not _looks_like_key(key):
                st.error("키 형식이 올바르지 않습니다. 보통 'sk-'로 시작하는 긴 문자열입니다.")
                return

            with st.spinner("OpenAI 서버에 연결을 확인하는 중..."):
                result = openai_client.validate_key(key)

            if not result.ok:
                st.error(result.message)
                return

            settings.api_key = key
            settings.remember_key = remember
            if settings.model not in result.models:
                settings.model = result.models[0]
            storage.save_settings(settings)

            st.session_state["api_key"] = key
            st.session_state["settings"] = settings
            st.session_state["models"] = result.models
            st.rerun()
