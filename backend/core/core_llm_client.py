"""
LLM abstraction supporting OpenAI and Google Gemini.
Provides a single `complete()` interface for all downstream modules.
"""

from __future__ import annotations
import json
import logging
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)


class LLMClient: #Unified async LLM client.

    def __init__(self) -> None:
        self._provider = settings.llm_provider

        if self._provider == "openai":
            self._openai = AsyncOpenAI(api_key=settings.openai_api_key)
            self._model = settings.openai_model
        elif self._provider == "gemini":
            # Gemini via OpenAI-compatible endpoint
            self._openai = AsyncOpenAI(
                api_key=settings.gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            self._model = settings.gemini_model
        else:
            raise ValueError(f"Unsupported LLM provider: {self._provider}")

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str: #Send a prompt and return the raw text response.
        response = await self._openai.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> dict: #Send a prompt and parse the response as JSON.
        raw = await self.complete(system_prompt, user_prompt, temperature)

        # Strip markdown code fences if the model wraps output
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error("LLM returned non-JSON: %s", raw[:200])
            raise


#Singleton
llm_client = LLMClient()
