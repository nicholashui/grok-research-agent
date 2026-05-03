from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel


class GrokError(RuntimeError):
    pass


class GrokTimeoutError(GrokError):
    pass


class GrokQuotaError(GrokError):
    pass


@dataclass(frozen=True)
class GrokConfig:
    api_key: str
    model: str
    base_url: str = "https://api.x.ai/v1"
    max_output_tokens: int = 50000
    request_timeout_seconds: int = 300


class ChatMessage(BaseModel):
    role: str
    content: str


class GrokClient:
    def __init__(self, env_path: Path | None = None):
        load_dotenv(dotenv_path=env_path, override=False)
        api_key = os.getenv("GROK_API_KEY", "").strip()
        model = os.getenv("GROK_MODEL", "grok-3").strip() or "grok-3"
        max_output_tokens_raw = os.getenv("GROK_MAX_OUTPUT_TOKENS", "").strip()
        request_timeout_raw = os.getenv("GROK_REQUEST_TIMEOUT_SECONDS", "").strip()
        max_output_tokens = 50000
        request_timeout_seconds = 300
        if max_output_tokens_raw:
            try:
                max_output_tokens = int(max_output_tokens_raw)
            except ValueError:
                max_output_tokens = 50000
        if request_timeout_raw:
            try:
                request_timeout_seconds = int(request_timeout_raw)
            except ValueError:
                request_timeout_seconds = 300
        if max_output_tokens < 1:
            max_output_tokens = 1
        if request_timeout_seconds < 1:
            request_timeout_seconds = 1
        if not api_key:
            raise GrokError("Missing GROK_API_KEY in .env or environment")

        self.config = GrokConfig(
            api_key=api_key,
            model=model,
            max_output_tokens=max_output_tokens,
            request_timeout_seconds=request_timeout_seconds,
        )
        self.client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)

    def _map_api_error(self, err: Exception) -> GrokError:
        msg = str(err).strip()
        lower = msg.lower()
        if any(token in lower for token in ("insufficient_quota", "quota", "out of credit", "billing", "payment")):
            return GrokQuotaError(
                "Grok API quota/credit error. Please top up credits, check billing, or lower request volume."
            )
        if any(token in lower for token in ("timeout", "timed out", "deadline")):
            return GrokTimeoutError(
                f"Grok API call timed out after {self.config.request_timeout_seconds} seconds."
            )
        return GrokError(f"Grok API failed: {msg}")

    def chat_text(
        self,
        *,
        system: str,
        user: str,
        max_retries: int = 5,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        max_tokens = max_output_tokens if max_output_tokens is not None else self.config.max_output_tokens
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=self.config.request_timeout_seconds,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001
                mapped = self._map_api_error(e)
                if isinstance(mapped, GrokQuotaError):
                    raise mapped from e
                if isinstance(mapped, GrokTimeoutError):
                    raise mapped from e
                last_err = e
                sleep_s = min(2 ** attempt, 30)
                time.sleep(sleep_s)
        raise self._map_api_error(last_err or RuntimeError("unknown error"))

    def prompt_from_file(self, prompt_path: Path) -> str:
        return prompt_path.read_text(encoding="utf-8")

    def render_template(self, template: str, values: dict[str, Any]) -> str:
        text = template
        for k, v in values.items():
            text = text.replace("{{" + k + "}}", str(v))
        return text
