import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache
import json
import re

import httpx
from openai import AsyncOpenAI
from httpx import ResponseNotRead

from app.core.config import settings
from app.retrieval.schemas import RetrievalMatch


@dataclass(slots=True)
class ChatGenerationRequest:
    question: str
    system_prompt: str
    prompt: str
    matches: list[RetrievalMatch]


class ProviderRequestError(Exception):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class BaseChatProvider(ABC):
    provider_name: str
    model_name: str

    @property
    def display_name(self) -> str:
        if self.provider_name == "mock":
            return "mock"
        return f"{self.provider_name}:{self.model_name}"

    @abstractmethod
    async def generate_answer(self, request: ChatGenerationRequest) -> str:
        """Generate a full answer in one response."""

    @abstractmethod
    async def stream_answer(self, request: ChatGenerationRequest) -> AsyncIterator[str]:
        """Stream an answer in small text chunks."""

    @staticmethod
    def build_openai_compatible_messages(request: ChatGenerationRequest) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.prompt},
        ]


async def _iter_sse_data(response: httpx.Response) -> AsyncIterator[str]:
    current_data_lines: list[str] = []

    async for raw_line in response.aiter_lines():
        line = raw_line.strip()

        if not line:
            if current_data_lines:
                payload = "\n".join(current_data_lines).strip()
                if payload and payload != "[DONE]":
                    yield payload
                current_data_lines = []
            continue

        if line.startswith("data:"):
            current_data_lines.append(line[5:].strip())

    if current_data_lines:
        payload = "\n".join(current_data_lines).strip()
        if payload and payload != "[DONE]":
            yield payload


def _extract_gemini_text(payload: dict[str, object]) -> str:
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        return ""

    text_parts: list[str] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        content = candidate.get("content", {})
        if not isinstance(content, dict):
            continue

        parts = content.get("parts", [])
        if not isinstance(parts, list):
            continue

        for part in parts:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)

    return "".join(text_parts)


def _extract_gemini_finish_reason(payload: dict[str, object]) -> str | None:
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        return None

    for candidate in candidates:
        if isinstance(candidate, dict):
            finish_reason = candidate.get("finishReason")
            if isinstance(finish_reason, str):
                return finish_reason

    return None


def _extract_gemini_block_reason(payload: dict[str, object]) -> str | None:
    prompt_feedback = payload.get("promptFeedback", {})
    if not isinstance(prompt_feedback, dict):
        return None

    block_reason = prompt_feedback.get("blockReason")
    if isinstance(block_reason, str):
        return block_reason
    return None


def _build_gemini_completion_warning(payload: dict[str, object]) -> str | None:
    block_reason = _extract_gemini_block_reason(payload)
    if block_reason:
        return f"Gemini blocked part of the response with block reason {block_reason}. The answer may be incomplete."

    finish_reason = _extract_gemini_finish_reason(payload)
    if not finish_reason or finish_reason == "STOP":
        return None

    finish_reason_messages = {
        "MAX_TOKENS": "Gemini hit the output token limit. The answer may be incomplete.",
        "SAFETY": "Gemini stopped for a safety reason. The answer may be incomplete.",
        "RECITATION": "Gemini stopped because the response looked too close to source text. The answer may be incomplete.",
        "SPII": "Gemini stopped because the response may contain sensitive personal information. The answer may be incomplete.",
        "PROHIBITED_CONTENT": "Gemini stopped because the response may contain prohibited content. The answer may be incomplete.",
        "BLOCKLIST": "Gemini stopped because the response hit a blocked term or policy rule. The answer may be incomplete.",
        "OTHER": "Gemini ended the response early for a provider-side reason. The answer may be incomplete.",
    }
    return finish_reason_messages.get(
        finish_reason,
        f"Gemini ended the response with finish reason {finish_reason}. The answer may be incomplete.",
    )


class MockChatProvider(BaseChatProvider):
    """Simple local chat provider for non-streaming development."""

    def __init__(self) -> None:
        self.provider_name = "mock"
        self.model_name = "local-template"

    async def generate_answer(self, request: ChatGenerationRequest) -> str:
        if not request.matches:
            return (
                "I could not find enough relevant context in the stored documents to answer that confidently."
            )

        top_match = request.matches[0]
        answer_lines = [
            f"Based on the retrieved context, the best match is from `{top_match.filename}`.",
            top_match.chunk_text,
        ]

        if len(request.matches) > 1:
            supporting_files = ", ".join(f"`{match.filename}`" for match in request.matches[1:])
            answer_lines.append(f"Additional supporting context was also found in {supporting_files}.")

        answer_lines.append(f"Question answered using {len(request.matches)} retrieved chunk(s).")
        return "\n\n".join(answer_lines)

    async def stream_answer(
        self,
        request: ChatGenerationRequest,
    ) -> AsyncIterator[str]:
        answer = await self.generate_answer(request)
        chunk_size = settings.chat_stream_chunk_words
        delay_seconds = settings.chat_stream_delay_ms / 1000

        if not answer:
            return

        chunk_buffer: list[str] = []
        word_count = 0

        # Keep whitespace attached to the preceding visible token so streamed
        # output preserves paragraphs and list formatting from the full answer.
        for token in re.findall(r"\S+\s*|\s+", answer):
            chunk_buffer.append(token)

            if token.strip():
                word_count += 1

            if word_count >= chunk_size:
                yield "".join(chunk_buffer)
                chunk_buffer = []
                word_count = 0

                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)

        if chunk_buffer:
            yield "".join(chunk_buffer)



class OpenAIChatProvider(BaseChatProvider):
    """OpenAI chat provider for real LLM-backed answers."""

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str | None,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        self.provider_name = "openai"
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
        )

    async def generate_answer(self, request: ChatGenerationRequest) -> str:
        try:
            response = await self.client.responses.create(
                model=self.model_name,
                instructions=request.system_prompt,
                input=request.prompt,
                max_output_tokens=self.max_output_tokens,
                temperature=settings.chat_temperature,
            )
        except Exception as exc:
            raise ProviderRequestError(
                "OpenAI chat request failed. Check your API key, model, and account limits.",
            ) from exc
        answer = response.output_text.strip()
        if answer:
            return answer
        return "The model returned an empty answer."

    async def stream_answer(self, request: ChatGenerationRequest) -> AsyncIterator[str]:
        try:
            stream = await self.client.responses.create(
                model=self.model_name,
                instructions=request.system_prompt,
                input=request.prompt,
                max_output_tokens=self.max_output_tokens,
                temperature=settings.chat_temperature,
                stream=True,
            )
        except Exception as exc:
            raise ProviderRequestError(
                "OpenAI streaming request failed. Check your API key, model, and account limits.",
            ) from exc

        async for event in stream:
            if event.type == "response.output_text.delta":
                yield event.delta


class GeminiChatProvider(BaseChatProvider):
    """Gemini chat provider using the public Gemini REST API."""

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        self.provider_name = "gemini"
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

    async def generate_answer(self, request: ChatGenerationRequest) -> str:
        payload = self._build_payload(request)

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/models/{self.model_name}:generateContent",
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            await _raise_for_provider_status(
                response,
                provider_name="Gemini",
                rate_limit_message=(
                    "Gemini chat is currently rate-limited for this project. "
                    "This can happen even with a new API key because limits are applied per project, "
                    "not per key."
                ),
            )
            response_payload = response.json()
            answer = _extract_gemini_text(response_payload).strip()
            warning = _build_gemini_completion_warning(response_payload)

        if answer:
            if warning:
                return f"{answer}\n\n[Note: {warning}]"
            return answer

        if warning:
            return f"[Note: {warning}]"

        return "The model returned an empty answer."

    async def stream_answer(self, request: ChatGenerationRequest) -> AsyncIterator[str]:
        payload = self._build_payload(request)
        warning: str | None = None

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/models/{self.model_name}:streamGenerateContent",
                params={"alt": "sse"},
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                await _raise_for_provider_status(
                    response,
                    provider_name="Gemini",
                    rate_limit_message=(
                        "Gemini streaming is currently rate-limited for this project. "
                        "Try again in a minute, use non-streaming mode, or switch to another provider."
                    ),
                )

                async for event_data in _iter_sse_data(response):
                    event_payload = json.loads(event_data)
                    chunk_text = _extract_gemini_text(event_payload)
                    if chunk_text:
                        yield chunk_text

                    event_warning = _build_gemini_completion_warning(event_payload)
                    if event_warning:
                        warning = event_warning

        if warning:
            yield f"\n\n[Note: {warning}]"

    def _build_payload(self, request: ChatGenerationRequest) -> dict[str, object]:
        return {
            "system_instruction": {
                "parts": [
                    {
                        "text": request.system_prompt,
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": request.prompt,
                        }
                    ],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": self.max_output_tokens,
                "temperature": settings.chat_temperature,
            },
        }


class OpenRouterChatProvider(BaseChatProvider):
    """OpenRouter chat provider using its OpenAI-compatible chat completions API."""

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        self.provider_name = "openrouter"
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    async def generate_answer(self, request: ChatGenerationRequest) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=self.build_openai_compatible_messages(request),
                max_tokens=self.max_output_tokens,
                temperature=settings.chat_temperature,
            )
        except Exception as exc:
            raise ProviderRequestError(
                "OpenRouter chat request failed. Check your API key, selected model, and provider limits.",
            ) from exc
        answer = response.choices[0].message.content or ""
        answer = answer.strip()
        if answer:
            return answer
        return "The model returned an empty answer."

    async def stream_answer(self, request: ChatGenerationRequest) -> AsyncIterator[str]:
        try:
            stream = await self.client.chat.completions.create(
                model=self.model_name,
                messages=self.build_openai_compatible_messages(request),
                max_tokens=self.max_output_tokens,
                temperature=settings.chat_temperature,
                stream=True,
            )
        except Exception as exc:
            raise ProviderRequestError(
                "OpenRouter streaming request failed. Check your API key, selected model, and provider limits.",
            ) from exc

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


class GroqChatProvider(BaseChatProvider):
    """Groq chat provider using its OpenAI-compatible chat completions API."""

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        timeout_seconds: float,
        max_output_tokens: int,
    ) -> None:
        self.provider_name = "groq"
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    async def generate_answer(self, request: ChatGenerationRequest) -> str:
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=self.build_openai_compatible_messages(request),
                max_tokens=self.max_output_tokens,
                temperature=settings.chat_temperature,
            )
        except Exception as exc:
            raise ProviderRequestError(
                "Groq chat request failed. Check your API key, selected model, and provider limits.",
            ) from exc
        answer = response.choices[0].message.content or ""
        answer = answer.strip()
        if answer:
            return answer
        return "The model returned an empty answer."

    async def stream_answer(self, request: ChatGenerationRequest) -> AsyncIterator[str]:
        try:
            stream = await self.client.chat.completions.create(
                model=self.model_name,
                messages=self.build_openai_compatible_messages(request),
                max_tokens=self.max_output_tokens,
                temperature=settings.chat_temperature,
                stream=True,
            )
        except Exception as exc:
            raise ProviderRequestError(
                "Groq streaming request failed. Check your API key, selected model, and provider limits.",
            ) from exc

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


@lru_cache
def get_chat_provider(provider_name: str) -> BaseChatProvider:
    normalized_provider = provider_name.strip().lower()

    if normalized_provider == "mock":
        return MockChatProvider()

    if normalized_provider == "openai":
        return OpenAIChatProvider(
            api_key=settings.openai_api_key,
            model_name=settings.openai_chat_model,
            base_url=settings.openai_base_url or None,
            timeout_seconds=settings.provider_timeout_seconds,
            max_output_tokens=settings.chat_max_output_tokens,
        )

    if normalized_provider == "gemini":
        if not settings.gemini_api_key.strip():
            raise ValueError("GEMINI_API_KEY is required when CHAT_PROVIDER is gemini.")

        return GeminiChatProvider(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_chat_model,
            base_url=settings.gemini_base_url,
            timeout_seconds=settings.provider_timeout_seconds,
            max_output_tokens=settings.chat_max_output_tokens,
        )

    if normalized_provider == "groq":
        if not settings.groq_api_key.strip():
            raise ValueError("GROQ_API_KEY is required when CHAT_PROVIDER is groq.")

        return GroqChatProvider(
            api_key=settings.groq_api_key,
            model_name=settings.groq_chat_model,
            base_url=settings.groq_base_url,
            timeout_seconds=settings.provider_timeout_seconds,
            max_output_tokens=settings.chat_max_output_tokens,
        )

    if normalized_provider == "openrouter":
        if not settings.openrouter_api_key.strip():
            raise ValueError("OPENROUTER_API_KEY is required when CHAT_PROVIDER is openrouter.")

        return OpenRouterChatProvider(
            api_key=settings.openrouter_api_key,
            model_name=settings.openrouter_chat_model,
            base_url=settings.openrouter_base_url,
            timeout_seconds=settings.provider_timeout_seconds,
            max_output_tokens=settings.chat_max_output_tokens,
        )

    raise ValueError(f"Unsupported chat provider: {provider_name}")


async def _raise_for_provider_status(
    response: httpx.Response,
    *,
    provider_name: str,
    rate_limit_message: str,
) -> None:
    if response.is_success:
        return

    try:
        response_text = response.text.strip()
    except ResponseNotRead:
        await response.aread()
        response_text = response.text.strip()

    if response.status_code == 429:
        raise ProviderRequestError(rate_limit_message, status_code=429)

    if response.status_code == 401:
        raise ProviderRequestError(
            f"{provider_name} rejected the API key. Check the configured credentials.",
            status_code=401,
        )

    if response.status_code == 403:
        raise ProviderRequestError(
            f"{provider_name} denied access for this request. Check project permissions or billing.",
            status_code=403,
        )

    if response.status_code == 400:
        raise ProviderRequestError(
            f"{provider_name} rejected the request. Check the configured model or request format.",
            status_code=400,
        )

    raise ProviderRequestError(
        f"{provider_name} request failed with status {response.status_code}. {response_text[:200]}",
        status_code=502,
    )
