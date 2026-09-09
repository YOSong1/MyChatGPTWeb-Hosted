"""채팅 화면. plan1 4.2절.

사이드바: 새 대화, 대화 목록, 모델 선택, 설정.
본문: 제목(수정 가능), 메시지 목록, 스트리밍 응답, 출처, 생성 파일 다운로드, 코드 블록 저장,
      다시 생성, 오류 시 다시 시도. 입력창 위에 🌐 웹 검색 / 📎 파일 생성 스위치.
"""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from app import openai_client, storage
from app.models import Conversation, Message, Settings, make_title
from app.openai_client import ChatError
from app.ui import settings as settings_ui

# 코드 블록 언어 -> 저장 확장자
_EXT = {
    "python": "py", "py": "py", "javascript": "js", "js": "js", "typescript": "ts", "ts": "ts",
    "html": "html", "css": "css", "json": "json", "csv": "csv", "markdown": "md", "md": "md",
    "bash": "sh", "sh": "sh", "shell": "sh", "sql": "sql", "java": "java", "c": "c", "cpp": "cpp",
    "c++": "cpp", "cs": "cs", "csharp": "cs", "go": "go", "rust": "rs", "kotlin": "kt", "swift": "swift",
    "yaml": "yml", "yml": "yml", "xml": "xml", "powershell": "ps1", "ps1": "ps1", "txt": "txt",
    "text": "txt", "r": "R", "matlab": "m", "dart": "dart", "php": "php", "ruby": "rb",
}
_CODE_BLOCK_RE = re.compile(r"```([\w+#-]*)[^\n]*\n(.*?)```", re.DOTALL)
_MIN_CODE_LINES = 3  # 이보다 짧은 코드 블록에는 저장 버튼을 붙이지 않는다


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
    storage.delete_files(conv_id)
    _persist()


def _clear_key(notice: str | None = None) -> None:
    storage.clear_api_key()
    for k in ("api_key", "key_source", "settings", "models", "pending_error"):
        st.session_state.pop(k, None)
    # 환경변수 키를 쓰던 중이었다면, 이번 세션에서는 환경변수를 무시하고 키 화면을 보여준다.
    st.session_state["ignore_env_key"] = True
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


def _code_blocks(content: str) -> list[tuple[str, str]]:
    """(파일이름, 코드) 목록. 언어를 확장자로 바꾸고 snippet-1.py 식으로 이름 짓는다."""
    out = []
    for i, m in enumerate(_CODE_BLOCK_RE.finditer(content), start=1):
        lang, code = m.group(1).lower().strip(), m.group(2)
        if code.count("\n") + 1 < _MIN_CODE_LINES:
            continue
        ext = _EXT.get(lang, "txt")
        out.append((f"snippet-{i}.{ext}", code))
    return out


def _render_message_extras(msg: Message, key_prefix: str) -> None:
    """생성 파일 다운로드, 코드 블록 저장, 출처. assistant 메시지 아래에 붙는다."""
    downloads: list[tuple[str, bytes, str]] = []  # (label, data, filename)
    for f in msg.files:
        path = Path(f.get("path", ""))
        if path.exists():
            downloads.append((f"📎 {f['name']}", path.read_bytes(), f["name"]))
        else:
            st.caption(f"📎 {f.get('name', '')} (파일이 삭제되어 다시 받을 수 없습니다)")
    for name, code in _code_blocks(msg.content):
        downloads.append((f"💾 {name}", code.encode("utf-8"), name))

    if downloads:
        cols = st.columns(min(len(downloads), 4))
        for i, (label, data, name) in enumerate(downloads):
            with cols[i % len(cols)]:
                st.download_button(label, data=data, file_name=name, key=f"{key_prefix}-dl-{i}", use_container_width=True)

    if msg.citations:
        with st.expander(f"🌐 출처 {len(msg.citations)}개"):
            for c in msg.citations:
                st.markdown(f"- [{c.get('title') or c.get('url')}]({c.get('url')})")


def _render_messages(conv: Conversation) -> None:
    if not conv.messages:
        st.markdown(
            "<div style='text-align:center; color:#888; margin-top:20vh; font-size:1.2rem;'>"
            "무엇을 도와드릴까요?</div>",
            unsafe_allow_html=True,
        )
        return
    for i, m in enumerate(conv.messages):
        with st.chat_message("user" if m.role == "user" else "assistant"):
            st.markdown(m.content)
            if m.role == "assistant":
                _render_message_extras(m, f"{conv.id}-{i}")


_STATUS_TEXT = {
    ("search", "in_progress"): "🌐 웹 검색 준비 중…",
    ("search", "searching"): "🌐 웹 검색 중…",
    ("search", "completed"): "🌐 검색 결과를 읽는 중…",
    ("code", "in_progress"): "🐍 코드 실행 준비 중…",
    ("code", "interpreting"): "🐍 코드 실행 중…",
    ("code", "completed"): "🐍 코드 실행 완료, 답변 작성 중…",
}


def _request_reply(conv: Conversation, settings: Settings) -> None:
    """대화의 마지막 사용자 메시지에 대한 답을 스트리밍으로 받아 저장한다."""
    history = [{"role": m.role, "content": m.content} for m in conv.messages]
    messages = openai_client.build_messages(settings.system_prompt, history, settings.max_history)

    with st.chat_message("assistant"):
        status = st.empty()
        file_errors: list[str] = []

        def on_event(kind: str, detail: str) -> None:
            if kind == "file":
                status.caption(f"📎 파일 받는 중: {detail}")
            elif kind == "file_error":
                file_errors.append(detail)
            else:
                text = _STATUS_TEXT.get((kind, detail))
                if text:
                    status.caption(text)

        try:
            stream = openai_client.stream_chat(
                settings.api_key,
                settings.model,
                messages,
                settings.temperature,
                web_search=settings.web_search,
                code_interpreter=settings.code_interpreter,
                save_dir=storage.files_dir(conv.id) if settings.code_interpreter else None,
                on_event=on_event,
            )
            text = st.write_stream(stream)
        except ChatError as err:
            status.empty()
            if err.auth_failed:
                _clear_key(err.message)
                st.rerun()
            st.session_state["pending_error"] = err.message
            return
        status.empty()

    if isinstance(text, str) and (text.strip() or stream.files):
        content = openai_client.clean_sandbox_links(text) if stream.files or "sandbox:" in text else text
        if not content.strip():
            content = "파일을 만들었습니다."
        conv.add_message("assistant", content, files=stream.files, citations=stream.citations)
        st.session_state.pop("pending_error", None)
        if file_errors:
            st.session_state["pending_error"] = "일부 파일을 받지 못했습니다: " + ", ".join(file_errors)
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


def _render_tool_toggles(settings: Settings) -> None:
    """입력창 바로 위의 🌐 웹 검색 / 📎 파일 생성 스위치. 설정 파일에 저장된다."""
    col_web, col_code, col_hint = st.columns([1.2, 1.2, 4])
    with col_web:
        web = st.toggle(
            "🌐 웹 검색",
            value=settings.web_search,
            key="toggle-web",
            help="최신 정보가 필요한 질문에 모델이 인터넷을 검색하고 출처를 답니다. 검색 1회당 소액 요금이 추가됩니다.",
        )
    with col_code:
        code = st.toggle(
            "📎 파일 생성",
            value=settings.code_interpreter,
            key="toggle-code",
            help="pptx, docx, xlsx, pdf, 차트 등 실제 파일을 만들어 다운로드 버튼으로 제공합니다. 사용 시 소액 요금이 추가됩니다.",
        )
    with col_hint:
        hints = []
        if web:
            hints.append("검색 켜짐")
        if code:
            hints.append("파일 생성 켜짐: \"~를 pptx로 만들어줘\"처럼 요청하세요")
        if hints:
            st.caption(" · ".join(hints))
    if web != settings.web_search or code != settings.code_interpreter:
        settings.web_search = web
        settings.code_interpreter = code
        storage.save_settings(settings)


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
    _render_tool_toggles(settings)

    text = st.chat_input("메시지를 입력하세요...")
    if text and text.strip():
        st.session_state.pop("pending_error", None)
        conv.add_message("user", text.strip())
        _persist()
        with st.chat_message("user"):
            st.markdown(text.strip())
        _request_reply(conv, settings)
        st.rerun()
