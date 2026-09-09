"""OpenAI API 호출. 키 검증, 모델 목록 필터, 스트리밍 채팅.

프록시 서버로 전환할 일이 생기면 BASE_URL 하나만 바꾼다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

BASE_URL: str | None = None  # None이면 SDK 기본값(https://api.openai.com/v1)
REQUEST_TIMEOUT = 60.0

# 채팅에 쓸 수 없는 용도의 모델을 이름으로 걸러낸다.
_EXCLUDE_WORDS = (
    "audio", "image", "realtime", "transcribe", "tts", "search", "codex",
    "instruct", "live", "whisper", "translate", "embedding", "moderation",
    "pro",  # pro 모델은 느리고 비싸서 학생용 목록에서 제외
)
# 날짜가 붙은 스냅샷(gpt-4o-2024-08-06)과 구식 접미사는 숨기고 별칭만 보여준다.
_SNAPSHOT_RE = re.compile(r"-(\d{4}-\d{2}-\d{2}|\d{4}|16k)$")
# temperature를 자유롭게 받는 계열. 그 외 모델은 보내지 않는다.
_TEMPERATURE_OK_PREFIXES = ("gpt-4", "gpt-3.5")

FALLBACK_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"]


class ChatError(Exception):
    """사용자에게 그대로 보여줄 수 있는 문구를 담은 예외."""

    def __init__(self, message: str, *, auth_failed: bool = False):
        super().__init__(message)
        self.message = message
        self.auth_failed = auth_failed


@dataclass
class ValidationResult:
    ok: bool
    message: str = ""
    models: list[str] = field(default_factory=list)


# ---------- 모델 목록 ----------

def _version_key(model_id: str) -> tuple:
    """gpt-5.4-mini -> (5, 4, ...) 형태로 정렬 키를 만든다. 최신이 앞에 오도록 호출부에서 reverse."""
    m = re.match(r"gpt-(\d+)(?:\.(\d+))?", model_id)
    major = int(m.group(1)) if m else 0
    minor = int(m.group(2)) if m and m.group(2) else 0
    # 같은 버전 안에서는 기본 > chat-latest > mini > nano 순으로 보여준다.
    rank = 3
    if model_id.endswith("chat-latest"):
        rank = 2
    elif "-mini" in model_id:
        rank = 1
    elif "-nano" in model_id:
        rank = 0
    return (major, minor, rank, model_id)


def filter_chat_models(model_ids: list[str]) -> list[str]:
    out = []
    for mid in model_ids:
        if not mid.startswith("gpt-"):
            continue
        if any(w in mid for w in _EXCLUDE_WORDS):
            continue
        if _SNAPSHOT_RE.search(mid):
            continue
        out.append(mid)
    out.sort(key=_version_key, reverse=True)
    return out


def is_temperature_supported(model_id: str) -> bool:
    return model_id.startswith(_TEMPERATURE_OK_PREFIXES)


# ---------- 클라이언트 ----------

def _client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=BASE_URL, timeout=REQUEST_TIMEOUT, max_retries=1)


def friendly_error(exc: Exception, model: str = "") -> ChatError:
    if isinstance(exc, AuthenticationError):
        return ChatError("API Key가 올바르지 않거나 만료되었습니다. 키를 다시 입력하세요.", auth_failed=True)
    if isinstance(exc, PermissionDeniedError):
        return ChatError("이 키로는 해당 기능이나 모델을 사용할 권한이 없습니다.")
    if isinstance(exc, RateLimitError):
        return ChatError("요청 한도를 초과했거나 사용 가능한 크레딧이 없습니다. 잠시 후 다시 시도하세요.")
    if isinstance(exc, NotFoundError):
        return ChatError(f"모델 '{model}'을(를) 사용할 수 없습니다. 폐기되었거나 이 키에 허용되지 않은 모델입니다. 다른 모델을 선택하세요.")
    if isinstance(exc, BadRequestError):
        return ChatError(f"요청이 거부되었습니다: {getattr(exc, 'message', str(exc))[:200]}")
    if isinstance(exc, APITimeoutError):
        return ChatError("응답 시간이 초과되었습니다. 다시 시도하세요.")
    if isinstance(exc, APIConnectionError):
        return ChatError("OpenAI 서버에 연결할 수 없습니다. 인터넷 연결을 확인하세요.")
    if isinstance(exc, APIStatusError):
        return ChatError(f"OpenAI 서버 오류 (HTTP {exc.status_code}). 잠시 후 다시 시도하세요.")
    return ChatError(f"알 수 없는 오류: {type(exc).__name__}: {str(exc)[:200]}")


def validate_key(api_key: str) -> ValidationResult:
    """모델 목록 조회로 키를 검증한다. 성공 시 채팅용 모델 목록을 함께 돌려준다."""
    try:
        page = _client(api_key).models.list()
        ids = [m.id for m in page]
    except Exception as exc:  # noqa: BLE001
        err = friendly_error(exc)
        return ValidationResult(ok=False, message=err.message)
    models = filter_chat_models(ids)
    if not models:
        models = list(FALLBACK_MODELS)
    return ValidationResult(ok=True, models=models)


def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float | None = None,
) -> Iterator[str]:
    """스트리밍으로 답변 조각(str)을 낸다. 오류는 ChatError로 변환해 던진다.

    messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
    """
    client = _client(api_key)
    kwargs: dict = {"model": model, "messages": messages, "stream": True}
    if temperature is not None and is_temperature_supported(model):
        kwargs["temperature"] = temperature

    def _open(kw: dict):
        return client.chat.completions.create(**kw)

    try:
        try:
            stream = _open(kwargs)
        except BadRequestError as exc:
            # 모델이 temperature를 거부하면 빼고 한 번 더 시도한다.
            if "temperature" in kwargs and "temperature" in str(exc):
                kwargs.pop("temperature")
                stream = _open(kwargs)
            else:
                raise
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
    except ChatError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise friendly_error(exc, model) from exc


def build_messages(system_prompt: str, history: list[dict[str, str]], max_history: int) -> list[dict[str, str]]:
    """시스템 프롬프트 + 최근 max_history개 메시지."""
    recent = history[-max_history:] if max_history > 0 else history
    msgs: list[dict[str, str]] = []
    if system_prompt.strip():
        msgs.append({"role": "system", "content": system_prompt.strip()})
    msgs.extend(recent)
    return msgs
