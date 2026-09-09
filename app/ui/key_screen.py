"""키 입력 화면. plan1 4.1절.

형식 검사 후 OpenAI 서버에 모델 목록을 요청해 키를 검증한다.
환경변수(ENV_KEY_NAME)에 키를 등록해 두면 이 화면을 건너뛴다는 안내를 함께 보여준다.
"""

from __future__ import annotations

import streamlit as st

from app import openai_client, storage
from app.models import ENV_KEY_NAME, Settings


def _looks_like_key(key: str) -> bool:
    key = key.strip()
    return key.startswith("sk-") and len(key) >= 20 and " " not in key


def _render_env_hint() -> None:
    st.info(
        f"💡 환경변수 **{ENV_KEY_NAME}** 에 키를 등록해 두면 다음부터는 이 화면 없이 바로 시작합니다."
    )
    with st.expander("환경변수로 등록하는 방법"):
        st.markdown(
            f"""
**Windows**
1. 시작 메뉴에서 "환경 변수"를 검색해 **시스템 환경 변수 편집**을 엽니다.
2. **환경 변수** → 사용자 변수 **새로 만들기**
3. 변수 이름 `{ENV_KEY_NAME}`, 변수 값에 키를 넣고 확인합니다.
4. 프로그램을 완전히 종료한 뒤 다시 실행합니다.

또는 PowerShell에서 한 줄로:
```
setx {ENV_KEY_NAME} "sk-여기에키"
```

**Mac**
터미널에서 아래를 실행하고 새 터미널을 연 뒤, 그 터미널에서 앱을 실행합니다.
```
echo 'export {ENV_KEY_NAME}="sk-여기에키"' >> ~/.zshrc
```
Mac은 Finder에서 더블클릭으로 실행하면 터미널 환경변수를 읽지 못합니다.
그 경우에는 이 화면에서 키를 입력하고 "이 컴퓨터에 기억하기"를 켜는 편이 간단합니다.
"""
        )


def render(settings: Settings, notice: str | None = None) -> None:
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.title("API Key를 입력하세요")
        st.caption("키는 이 컴퓨터에만 저장되며 관리자 서버로 전송되지 않습니다.")
        if notice:
            st.warning(notice)

        env_key = storage.env_api_key()
        if env_key and st.session_state.get("ignore_env_key"):
            if st.button(f"↩ 환경변수 {ENV_KEY_NAME} 의 키로 시작", use_container_width=True):
                st.session_state.pop("ignore_env_key", None)
                st.rerun()

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
            elif not _looks_like_key(key):
                st.error("키 형식이 올바르지 않습니다. 보통 'sk-'로 시작하는 긴 문자열입니다.")
            else:
                with st.spinner("OpenAI 서버에 연결을 확인하는 중..."):
                    result = openai_client.validate_key(key)

                if not result.ok:
                    st.error(result.message)
                else:
                    settings.api_key = key
                    settings.remember_key = remember
                    if settings.model not in result.models:
                        settings.model = result.models[0]
                    storage.save_settings(settings)

                    st.session_state["api_key"] = key
                    st.session_state["key_source"] = "file" if remember else "session"
                    st.session_state["settings"] = settings
                    st.session_state["models"] = result.models
                    st.rerun()

        if not env_key:
            _render_env_hint()
