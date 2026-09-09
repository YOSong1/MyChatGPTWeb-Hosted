"""채팅 화면. plan1 4.2절.

사이드바: 새 대화, 대화 목록, 모델 선택, 설정.
본문: 제목(수정 가능), 메시지 목록, 스트리밍 응답, 다시 생성, 오류 시 다시 시도.
"""

from __future__ import annotations

import streamlit as st

from app import openai_client, storage
from app.models import Conversation, Settings, make_title
from app.openai_client import ChatError
from app.ui import settings as settings_ui


# ---------- 상태 헬퍼 ----------

def _conversations() -> list[Conversation]:
    if "conversations" not in st.session_state:
        st.session_state["conversations"] = storage.load_conversations()
    return st.session_state["conversations"]


def _active() -> Conversation | None:
    active_id = st.session_state.get("active_id")
    for c in _conversations():
        if c.id == active_id:
            return c
    return None


def _persist() -> None:
    storage.save_conversations(_conversations())


def _new_conversation() -> None:
    conv = Conversation()
    _conversations().insert(0, conv)
    st.session_state["active_id"] = conv.id
    st.session_state.pop("pending_error", None)
    _persist()


def _delete_conversation(conv_id: str) -> None:
    convs = _conversations()
    convs[:] = [c for c in convs if c.id != conv_id]
    if st.session_state.get("active_id") == conv_id:
        st.session_state["active_id"] = convs[0].id if convs else None
    st.session_state.pop("pending_error", None)
    _persist()


def _clear_key(notice: str | None = None) -> None:
    storage.clear_api_key()
    for k in ("api_key", "settings", "models", "pending_error"):
        st.session_state.pop(k, None)
    if notice:
        st.session_state["key_notice"] = notice


def _models(settings: Settings) -> list[str]:
    """세션에 모델 목록이 없으면(저장된 키로 바로 진입한 경우) 서버에서 가져온다."""
    if "models" not in st.session_state:
        result = openai_client.validate_key(settings.api_key)
        if result.ok:
            st.session_state["models"] = result.models
        elif "올바르지 않" in result.message:
            _clear_key(result.message)
            st.rerun()
        else:
            # 네트워크 오류 등: 저장된 모델만으로 진행하고 나중에 다시 시도한다.
            return [settings.model]
    models = st.session_state["models"]
    if settings.model not in models:
        models = [settings.model] + models
    return models


# ---------- 사이드바 ----------

def _render_sidebar(settings: Settings) -> None:
    with st.sidebar:
        st.button("➕ 새 대화", use_container_width=True, on_click=_new_conversation)
        st.divider()

        convs = _conversations()
        if not convs:
            st.caption("대화가 없습니다. 새 대화를 시작하세요.")
        for c in convs:
            is_active = c.id == st.session_state.get("active_id")
            col_title, col_del = st.columns([5, 1])
            with col_title:
                if st.button(
                    c.title,
                    key=f"conv-{c.id}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state["active_id"] = c.id
                    st.session_state.pop("pending_error", None)
                    st.rerun()
            with col_del:
                if st.button("🗑", key=f"del-{c.id}", help="삭제"):
                    _delete_conversation(c.id)
                    st.rerun()

        st.divider()
        models = _models(settings)
        chosen = st.selectbox(
            "모델",
            models,
            index=models.index(settings.model),
            help="위쪽이 최신 모델입니다. mini/nano는 빠르고 저렴합니다.",
        )
        if chosen != settings.model:
            settings.model = chosen
            storage.save_settings(settings)
            st.rerun()  # temperature 지원 여부 등 설정 패널 표시를 갱신

        settings_ui.render(settings, convs, on_clear_key=_clear_key)


# ---------- 본문 ----------

def _render_header(conv: Conversation) -> None:
    col_title, col_edit = st.columns([8, 1])
    with col_title:
        st.subheader(conv.title)
    with col_edit:
        with st.popover("✏️", help="제목 수정"):
            new_title = st.text_input("제목", value=conv.title, key=f"title-{conv.id}", max_chars=60)
            if st.button("저장", key=f"title-save-{conv.id}", type="primary"):
                conv.title = make_title(new_title, limit=60) if new_title.strip() else conv.title
                _persist()
                st.rerun()


def _render_messages(conv: Conversation) -> None:
    if not conv.messages:
        st.markdown(
            "<div style='text-align:center; color:#888; margin-top:20vh; font-size:1.2rem;'>"
            "무엇을 도와드릴까요?</div>",
            unsafe_allow_html=True,
        )
        return
    for m in conv.messages:
        with st.chat_message("user" if m.role == "user" else "assistant"):
            st.markdown(m.content)


def _request_reply(conv: Conversation, settings: Settings) -> None:
    """대화의 마지막 사용자 메시지에 대한 답을 스트리밍으로 받아 저장한다."""
    history = [{"role": m.role, "content": m.content} for m in conv.messages]
    messages = openai_client.build_messages(settings.system_prompt, history, settings.max_history)

    with st.chat_message("assistant"):
        try:
            text = st.write_stream(
                openai_client.stream_chat(
                    settings.api_key, settings.model, messages, settings.temperature
                )
            )
        except ChatError as err:
            if err.auth_failed:
                _clear_key(err.message)
                st.rerun()
            st.session_state["pending_error"] = err.message
            return

    if isinstance(text, str) and text.strip():
        conv.add_message("assistant", text)
        st.session_state.pop("pending_error", None)
        _persist()
    else:
        st.session_state["pending_error"] = "빈 응답을 받았습니다. 다시 시도하세요."


def _render_actions(conv: Conversation, settings: Settings) -> None:
    """마지막 메시지 아래의 오류 문구, 다시 시도, 다시 생성 버튼."""
    err = st.session_state.get("pending_error")
    if err:
        st.error(err)

    if not conv.messages:
        return
    last = conv.messages[-1]

    if last.role == "user":
        # 답변을 받지 못한 상태
        if st.button("🔄 다시 시도", key="retry"):
            st.session_state.pop("pending_error", None)
            _request_reply(conv, settings)
            st.rerun()
    elif last.role == "assistant" and len(conv.messages) >= 2:
        if st.button("🔁 다시 생성", key="regenerate", help="마지막 답변을 지우고 다시 받습니다."):
            conv.messages.pop()
            _persist()
            _request_reply(conv, settings)
            st.rerun()


def render(settings: Settings) -> None:
    _render_sidebar(settings)

    conv = _active()
    if conv is None:
        convs = _conversations()
        if convs:
            st.session_state["active_id"] = convs[0].id
            conv = convs[0]
        else:
            _new_conversation()
            conv = _active()

    _render_header(conv)
    _render_messages(conv)
    _render_actions(conv, settings)

    text = st.chat_input("메시지를 입력하세요...")
    if text and text.strip():
        st.session_state.pop("pending_error", None)
        conv.add_message("user", text.strip())
        _persist()
        with st.chat_message("user"):
            st.markdown(text.strip())
        _request_reply(conv, settings)
        st.rerun()
