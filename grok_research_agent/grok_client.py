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


@dataclass(frozen=True)
class GrokConfig:
    api_key: str
    model: str
    base_url: str = "https://api.x.ai/v1"


class ChatMessage(BaseModel):
    role: str
    content: str


class GrokClient:
    def __init__(self, env_path: Path | None = None):
        load_dotenv(dotenv_path=env_path, override=False)
        api_key = os.getenv("GROK_API_KEY", "").strip()
        model = os.getenv("GROK_MODEL", "grok-3").strip() or "grok-3"
        if not api_key:
            raise GrokError("Missing GROK_API_KEY in .env or environment")

        self.config = GrokConfig(api_key=api_key, model=model)
        self.client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)

    def chat_text(
        self,
        *,
        system: str,
        user: str,
        max_retries: int = 5,
        temperature: float = 0.2,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=temperature,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001
                last_err = e
                sleep_s = min(2 ** attempt, 30)
                time.sleep(sleep_s)
        raise GrokError(f"Grok API failed after retries: {last_err}")

    def prompt_from_file(self, prompt_path: Path) -> str:
        return prompt_path.read_text(encoding="utf-8")

    def render_template(self, template: str, values: dict[str, Any]) -> str:
        text = template
        for k, v in values.items():
            text = text.replace("{{" + k + "}}", str(v))
        return text

