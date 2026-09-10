"""OpenAI API 호출. 키 검증, 모델 목록 필터, 스트리밍 채팅(Responses API).

- 웹 검색(web_search)과 파일 생성(code_interpreter) 도구는 Responses API에서만 쓸 수 있다.
- 프록시 서버로 전환할 일이 생기면 BASE_URL 하나만 바꾼다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

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
REQUEST_TIMEOUT = 180.0  # 코드 실행 도구는 수십 초가 걸릴 수 있다

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

# 항상 붙이는 지침: 여러 파일 코드는 파일명 제목 + 코드 블록으로. 앱이 개별 저장과 zip 묶음을 제공한다.
_BASE_GUIDE = (
    "코드 파일을 여러 개 만들어 달라는 요청이면 파일마다 '### 경로/파일명' 제목을 쓰고 바로 아래에 "
    "코드 블록을 하나씩 둔다(예: '### src/app.py'). 사용자는 이 앱에서 각 파일을 개별로 또는 "
    "전체를 zip으로 내려받을 수 있으므로, '폴더를 만들어 복사하라'거나 '압축은 불가능하다'고 답하지 않는다."
)
# 도구를 켰을 때 추가하는 지침
_TOOL_GUIDE_SEARCH = (
    "최신 정보나 사실 확인이 필요한 질문에는 웹 검색을 사용하고, 답에 출처를 밝힌다."
)
_TOOL_GUIDE_FILES = (
    "사용자가 문서, 슬라이드, 스프레드시트, 코드 파일, 압축 파일 등 '파일'을 요청하면 파이썬으로 실제 파일을 "
    "/mnt/data 에 만들어 제공한다. 여러 파일로 된 프로젝트나 폴더를 요청받으면 폴더 구조 그대로 만든 뒤 "
    "zip 하나로 묶어 제공한다(zipfile 모듈). 파일 이름은 내용을 알 수 있게 짓는다. "
    "만든 파일마다 답변 끝에 반드시 다운로드 링크를 하나씩 적는다. "
    "사용한 코드는 사용자가 요청하지 않는 한 답변에 보여주지 않는다."
)

# 답변 속 sandbox 링크는 앱 밖에서 열리지 않으므로 이름만 남긴다.
_SANDBOX_LINK_RE = re.compile(r"\[([^\]]+)\]\(sandbox:[^)]+\)")
_SANDBOX_PATH_RE = re.compile(r"sandbox:/mnt/data/([^\s)\]]+)")


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
    if isinstance(exc, ChatError):
        return exc
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


def build_messages(system_prompt: str, history: list[dict[str, str]], max_history: int) -> list[dict[str, str]]:
    """시스템 프롬프트 + 최근 max_history개 메시지. (system은 Responses API의 instructions로 옮겨 보낸다.)"""
    recent = history[-max_history:] if max_history > 0 else history
    msgs: list[dict[str, str]] = []
    if system_prompt.strip():
        msgs.append({"role": "system", "content": system_prompt.strip()})
    msgs.extend(recent)
    return msgs


def clean_sandbox_links(text: str) -> str:
    text = _SANDBOX_LINK_RE.sub(r"**\1**", text)
    text = _SANDBOX_PATH_RE.sub(r"\1", text)
    return text


# ---------- 스트리밍 응답 ----------

EventCallback = Callable[[str, str], None]  # (kind, detail) kind: "search" | "code" | "file"


class ResponseStream:
    """Responses API 스트리밍. 이터레이터로 텍스트 조각을 내고, 끝나면 files/citations가 채워진다.

    for piece in stream: ...   # 또는 st.write_stream(stream)
    stream.files      -> [{"name":..., "path":...}]
    stream.citations  -> [{"title":..., "url":...}]
    """

    def __init__(
        self,
        client: OpenAI,
        kwargs: dict,
        model: str,
        save_dir: Path | None,
        on_event: EventCallback | None,
    ):
        self._client = client
        self._kwargs = kwargs
        self._model = model
        self._save_dir = save_dir
        self._on_event = on_event or (lambda kind, detail: None)
        self.text = ""
        self.files: list[dict[str, str]] = []
        self.citations: list[dict[str, str]] = []

    def __iter__(self) -> Iterator[str]:
        try:
            try:
                stream = self._client.responses.create(**self._kwargs, stream=True)
            except BadRequestError as exc:
                # 모델이 temperature를 거부하면 빼고 한 번 더 시도한다.
                if "temperature" in self._kwargs and "temperature" in str(exc):
                    self._kwargs.pop("temperature")
                    stream = self._client.responses.create(**self._kwargs, stream=True)
                else:
                    raise

            for ev in stream:
                t = getattr(ev, "type", "")
                if t == "response.output_text.delta":
                    self.text += ev.delta
                    yield ev.delta
                elif t.startswith("response.web_search_call."):
                    self._on_event("search", t.rsplit(".", 1)[-1])
                elif t.startswith("response.code_interpreter_call."):
                    self._on_event("code", t.rsplit(".", 1)[-1])
                elif t == "response.completed":
                    self._collect(ev.response)
                elif t in ("response.failed", "response.incomplete"):
                    detail = ""
                    try:
                        detail = ev.response.error.message  # type: ignore[union-attr]
                    except AttributeError:
                        pass
                    raise ChatError(f"응답이 완료되지 않았습니다. {detail}".strip())
                elif t == "error":
                    raise ChatError(f"OpenAI 오류: {getattr(ev, 'message', '')}")
        except ChatError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise friendly_error(exc, self._model) from exc

    # ----- 완료 후 출처·파일 수집 -----

    def _collect(self, response) -> None:
        seen_urls: set[str] = set()
        seen_files: set[str] = set()
        containers: list[str] = []
        for item in getattr(response, "output", None) or []:
            kind = getattr(item, "type", "")
            if kind == "code_interpreter_call":
                cid = getattr(item, "container_id", "")
                if cid and cid not in containers:
                    containers.append(cid)
                continue
            if kind != "message":
                continue
            for part in getattr(item, "content", None) or []:
                for ann in getattr(part, "annotations", None) or []:
                    akind = getattr(ann, "type", "")
                    if akind == "url_citation":
                        url = getattr(ann, "url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            self.citations.append({"title": getattr(ann, "title", "") or url, "url": url})
                    elif akind == "container_file_citation":
                        fid = getattr(ann, "file_id", "")
                        if fid and fid not in seen_files:
                            seen_files.add(fid)
                            self._download(getattr(ann, "container_id", ""), fid, getattr(ann, "filename", "") or fid)

        # 모델이 링크를 적지 않아 annotation이 없으면, 코드 실행 컨테이너의 파일 목록에서 직접 찾는다.
        if containers and self._save_dir is not None:
            for cid in containers:
                try:
                    for f in self._client.containers.files.list(cid):
                        fid = getattr(f, "id", "")
                        if not fid or fid in seen_files:
                            continue
                        if getattr(f, "source", "") == "user":  # 사용자가 올린 입력 파일은 제외
                            continue
                        path = getattr(f, "path", "") or ""
                        name = path.rsplit("/", 1)[-1] if path else fid
                        seen_files.add(fid)
                        self._download(cid, fid, name)
                except Exception as exc:  # noqa: BLE001
                    self._on_event("file_error", f"목록 조회 실패: {type(exc).__name__}")

    def _download(self, container_id: str, file_id: str, filename: str) -> None:
        if not self._save_dir or not container_id:
            return
        safe = re.sub(r"[\\/:*?\"<>|]", "_", filename).strip() or file_id
        target = self._save_dir / safe
        # 같은 이름이 있으면 (2), (3)… 을 붙인다.
        if target.exists():
            stem, suffix = target.stem, target.suffix
            n = 2
            while target.exists():
                target = self._save_dir / f"{stem} ({n}){suffix}"
                n += 1
        try:
            self._on_event("file", safe)
            data = self._client.containers.files.content.retrieve(file_id, container_id=container_id).read()
            target.write_bytes(data)
            self.files.append({"name": target.name, "path": str(target)})
        except Exception as exc:  # noqa: BLE001
            # 파일 하나를 못 받아도 답변 자체는 살린다.
            self._on_event("file_error", f"{safe}: {type(exc).__name__}")


def stream_chat(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float | None = None,
    *,
    web_search: bool = False,
    code_interpreter: bool = False,
    save_dir: Path | None = None,
    on_event: EventCallback | None = None,
) -> ResponseStream:
    """Responses API 스트리밍 호출. messages의 system 항목은 instructions로 보낸다."""
    instructions_parts = [m["content"] for m in messages if m.get("role") == "system"]
    instructions_parts.append(_BASE_GUIDE)
    if web_search:
        instructions_parts.append(_TOOL_GUIDE_SEARCH)
    if code_interpreter:
        instructions_parts.append(_TOOL_GUIDE_FILES)
    inputs = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") != "system"]

    kwargs: dict = {"model": model, "input": inputs}
    if instructions_parts:
        kwargs["instructions"] = "\n\n".join(p for p in instructions_parts if p.strip())
    if temperature is not None and is_temperature_supported(model):
        kwargs["temperature"] = temperature
    tools: list[dict] = []
    if web_search:
        tools.append({"type": "web_search"})
    if code_interpreter:
        tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
    if tools:
        kwargs["tools"] = tools

    return ResponseStream(_client(api_key), kwargs, model, save_dir, on_event)
