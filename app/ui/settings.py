"""설정 패널. 사이드바의 접이식 영역으로 표시한다.

- 시스템 프롬프트, temperature, 대화 기록 포함 개수
- 대화 내보내기(JSON) / 가져오기
- 키 변경·삭제
"""

from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

from app import openai_client, storage
from app.models import (
    ENV_KEY_NAME,
    DEFAULT_MAX_HISTORY,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    Conversation,
    Settings,
)

EXPORT_VERSION = 1


def export_json(convs: list[Conversation]) -> str:
    payload = {
        "app": "MyChatGPTWeb",
        "version": EXPORT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "conversations": [c.to_dict() for c in convs],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_import(data: bytes | str) -> list[Conversation]:
    """내보낸 JSON 또는 대화 배열을 읽는다. 형식이 틀리면 ValueError."""
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    raw = json.loads(text)
    items = raw.get("conversations") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError("대화 목록을 찾을 수 없습니다.")
    convs = []
    for d in items:
        if not isinstance(d, dict) or not isinstance(d.get("messages"), list):
            raise ValueError("대화 형식이 올바르지 않습니다.")
        convs.append(Conversation.from_dict(d))
    return convs


def merge_conversations(existing: list[Conversation], incoming: list[Conversation]) -> int:
    """id가 겹치지 않는 대화만 추가한다. 추가된 개수를 돌려준다."""
    known = {c.id for c in existing}
    added = 0
    for c in incoming:
        if c.id in known:
            continue
        existing.append(c)
        known.add(c.id)
        added += 1
    existing.sort(key=lambda c: c.updated_at, reverse=True)
    return added


def render(settings: Settings, conversations: list[Conversation], on_clear_key) -> None:
    with st.expander("⚙️ 설정", expanded=False):
        # ----- 답변 방식 -----
        prompt = st.text_area(
            "시스템 프롬프트",
            value=settings.system_prompt,
            height=100,
            help="도우미의 역할과 말투를 정합니다. 매 요청의 맨 앞에 붙습니다.",
        )
        temp_ok = openai_client.is_temperature_supported(settings.model)
        temperature = st.slider(
            "창의성 (temperature)",
            min_value=0.0,
            max_value=2.0,
            value=float(settings.temperature),
            step=0.1,
            disabled=not temp_ok,
            help="낮을수록 일관된 답, 높을수록 다양한 답. gpt-4 계열에서만 적용됩니다.",
        )
        if not temp_ok:
            st.caption(f"{settings.model}은(는) 이 값을 지원하지 않아 기본값으로 동작합니다.")
        max_history = st.number_input(
            "요청에 포함할 최근 메시지 수",
            min_value=2,
            max_value=100,
            value=int(settings.max_history),
            step=2,
            help="많을수록 앞 내용을 잘 기억하지만 비용이 늘어납니다.",
        )

        col_save, col_reset = st.columns(2)
        with col_save:
            if st.button("저장", type="primary", use_container_width=True, key="settings-save"):
                settings.system_prompt = prompt.strip() or DEFAULT_SYSTEM_PROMPT
                settings.temperature = float(temperature)
                settings.max_history = int(max_history)
                storage.save_settings(settings)
                st.toast("설정을 저장했습니다.")
        with col_reset:
            if st.button("기본값", use_container_width=True, key="settings-reset"):
                settings.system_prompt = DEFAULT_SYSTEM_PROMPT
                settings.temperature = DEFAULT_TEMPERATURE
                settings.max_history = DEFAULT_MAX_HISTORY
                storage.save_settings(settings)
                st.rerun()

        st.divider()

        # ----- 내보내기 / 가져오기 -----
        st.download_button(
            "📤 대화 내보내기 (JSON)",
            data=export_json(conversations),
            file_name=f"mychatgpt-{datetime.now():%Y%m%d-%H%M}.json",
            mime="application/json",
            use_container_width=True,
            disabled=not conversations,
        )
        uploaded = st.file_uploader("📥 대화 가져오기", type=["json"], key="import-file")
        if uploaded is not None:
            token = f"{uploaded.name}:{uploaded.size}"
            if st.session_state.get("last_import") != token:
                try:
                    added = merge_conversations(conversations, parse_import(uploaded.getvalue()))
                    storage.save_conversations(conversations)
                    st.session_state["last_import"] = token
                    st.success(f"대화 {added}개를 가져왔습니다.")
                except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
                    st.error(f"가져올 수 없는 파일입니다: {e}")

        st.divider()

        # ----- 저장 위치, 키 -----
        st.caption(f"저장 위치: `{storage.data_dir()}`")
        st.caption("생성된 파일은 위 폴더의 `files/` 아래에 대화별로 저장됩니다. 대화를 삭제하면 함께 지워집니다.")
        source = st.session_state.get("key_source")
        if source == "env":
            st.caption(f"키 출처: 환경변수 `{ENV_KEY_NAME}`")
            label = "🔑 다른 키 입력"
        elif source == "session":
            st.caption("키 출처: 이번 실행에만 기억 (종료 시 삭제)")
            label = "🔑 키 변경 / 삭제"
        else:
            st.caption("키 출처: 이 컴퓨터에 저장된 키")
            label = "🔑 키 변경 / 삭제"
        if st.button(label, use_container_width=True, key="settings-clear-key"):
            on_clear_key()
            st.rerun()
