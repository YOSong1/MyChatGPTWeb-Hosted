"""키 입력 화면 (호스팅 모드).

형식 검사 후 OpenAI 서버에 모델 목록을 요청해 키를 검증한다.
키는 접속자의 세션 메모리에만 두고 서버에 저장하지 않는다.
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
        st.caption(
            "키는 저장되지 않습니다. 이 서버는 키를 OpenAI에 전달만 하며, "
            "브라우저 탭을 닫거나 새로고침하면 다시 입력해야 합니다."
        )
        if notice:
            st.warning(notice)

        with st.form("key_form", clear_on_submit=False):
            key = st.text_input(
                "OpenAI API Key",
                type="password",
                placeholder="sk-...",
                autocomplete="off",
            )
            submitted = st.form_submit_button("연결 확인 후 시작", type="primary", use_container_width=True)

        if submitted:
            key = key.strip()
            if not key:
                st.error("키를 입력하세요.")
            elif not _looks_like_key(key):
                st.error("키 형식이 올바르지 않습니다. 보통 'sk-'로 시작하는 긴 문자열입니다.")
            else:
                with st.spinner("OpenAI 서버에 연결을 확인하는 중..."):
                    result = openai_client.validate_key(key)

                if not result.ok:
                    st.error(result.message)
                else:
                    settings.api_key = key
                    if settings.model not in result.models:
                        settings.model = result.models[0]
                    storage.save_settings(settings)

                    st.session_state["api_key"] = key
                    st.session_state["key_source"] = "session"
                    st.session_state["settings"] = settings
                    st.session_state["models"] = result.models
                    st.rerun()

        st.info(
            "💡 대화 내용도 이 탭 안에서만 유지됩니다. 남겨 두고 싶은 대화는 "
            "왼쪽 **⚙️ 설정 → 📤 대화 내보내기**로 파일로 받아 두세요."
        )
