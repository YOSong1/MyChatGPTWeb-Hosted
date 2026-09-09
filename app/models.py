"""데이터 구조 정의. plan1 5.2절의 Conversation / Message 구조를 따른다."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

# 이 이름의 환경변수에 키가 있으면 키 입력 화면 없이 바로 시작한다.
ENV_KEY_NAME = "OPENAI_API_KEY"

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_SYSTEM_PROMPT = "당신은 학생을 돕는 친절한 학습 도우미입니다. 한국어로 답합니다."
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_HISTORY = 20  # 전송 시 포함할 최근 메시지 수


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str
    created_at: int = field(default_factory=now_ms)
    # 답변이 만든 파일: [{"name": "보고서.docx", "path": "C:/.../files/<conv>/보고서.docx"}]
    files: list[dict[str, str]] = field(default_factory=list)
    # 웹 검색 출처: [{"title": "...", "url": "..."}]
    citations: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not self.files:
            d.pop("files")
        if not self.citations:
            d.pop("citations")
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Message":
        return Message(
            role=d.get("role", "user"),
            content=d.get("content", ""),
            created_at=int(d.get("created_at", now_ms())),
            files=[f for f in d.get("files", []) if isinstance(f, dict)],
            citations=[c for c in d.get("citations", []) if isinstance(c, dict)],
        )


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    title: str = "새 대화"
    created_at: int = field(default_factory=now_ms)
    updated_at: int = field(default_factory=now_ms)
    messages: list[Message] = field(default_factory=list)

    def add_message(
        self,
        role: str,
        content: str,
        files: list[dict[str, str]] | None = None,
        citations: list[dict[str, str]] | None = None,
    ) -> Message:
        msg = Message(role=role, content=content, files=files or [], citations=citations or [])
        self.messages.append(msg)
        self.updated_at = now_ms()
        if role == "user" and self.title == "새 대화":
            self.title = make_title(content)
        return msg

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Conversation":
        return Conversation(
            id=d.get("id") or uuid.uuid4().hex,
            title=d.get("title") or "새 대화",
            created_at=int(d.get("created_at", now_ms())),
            updated_at=int(d.get("updated_at", now_ms())),
            messages=[Message.from_dict(m) for m in d.get("messages", [])],
        )


@dataclass
class Settings:
    api_key: str = ""
    remember_key: bool = True
    model: str = DEFAULT_MODEL
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    temperature: float = DEFAULT_TEMPERATURE
    max_history: int = DEFAULT_MAX_HISTORY
    web_search: bool = False        # 🌐 웹 검색 도구 사용
    code_interpreter: bool = False  # 📎 파일 생성(코드 실행) 도구 사용

    def to_dict(self, include_key: bool = True) -> dict[str, Any]:
        d = asdict(self)
        if not include_key:
            d["api_key"] = ""
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Settings":
        s = Settings()
        s.api_key = str(d.get("api_key", "") or "")
        s.remember_key = bool(d.get("remember_key", True))
        s.model = str(d.get("model", DEFAULT_MODEL) or DEFAULT_MODEL)
        s.system_prompt = str(d.get("system_prompt", DEFAULT_SYSTEM_PROMPT) or DEFAULT_SYSTEM_PROMPT)
        try:
            s.temperature = float(d.get("temperature", DEFAULT_TEMPERATURE))
        except (TypeError, ValueError):
            s.temperature = DEFAULT_TEMPERATURE
        try:
            s.max_history = int(d.get("max_history", DEFAULT_MAX_HISTORY))
        except (TypeError, ValueError):
            s.max_history = DEFAULT_MAX_HISTORY
        s.web_search = bool(d.get("web_search", False))
        s.code_interpreter = bool(d.get("code_interpreter", False))
        return s


def make_title(text: str, limit: int = 30) -> str:
    """첫 사용자 메시지에서 제목을 만든다. 줄바꿈은 공백으로 바꾸고 앞 30자만 쓴다."""
    one_line = " ".join(text.split())
    if not one_line:
        return "새 대화"
    return one_line[:limit] + ("…" if len(one_line) > limit else "")
