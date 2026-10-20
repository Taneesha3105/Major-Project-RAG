"""Gemini LLM gateway. Every call to the generative model goes through this module."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any, TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMError(ServiceUnavailableError):
    code = "llm_error"


@lru_cache(maxsize=1)
def _client() -> genai.Client:
    if not settings.llm_configured:
        raise LLMError("GEMINI_API_KEY is not configured on the server.")
    return genai.Client(api_key=settings.gemini_api_key)


def _config(
    *,
    system: str | None,
    temperature: float | None,
    max_tokens: int | None,
    schema: type[BaseModel] | None = None,
) -> types.GenerateContentConfig:
    kwargs: dict[str, Any] = {
        "temperature": settings.gemini_temperature if temperature is None else temperature,
        "max_output_tokens": max_tokens or settings.gemini_max_output_tokens,
    }
    if system:
        kwargs["system_instruction"] = system
    if schema is not None:
        kwargs["response_mime_type"] = "application/json"
        kwargs["response_schema"] = schema
    return types.GenerateContentConfig(**kwargs)


def _translate(exc: Exception) -> LLMError:
    if isinstance(exc, genai_errors.APIError):
        logger.warning("Gemini API error %s: %s", exc.code, exc.message)
        if exc.code in (401, 403):
            return LLMError("Gemini rejected the API key. Check GEMINI_API_KEY.")
        if exc.code == 404:
            return LLMError(f"Gemini model '{settings.gemini_chat_model}' was not found. Check GEMINI_CHAT_MODEL.")
        if exc.code == 429:
            return LLMError("Gemini rate limit reached. Please wait a moment and try again.")
        return LLMError(f"Gemini request failed ({exc.code}).")
    logger.exception("Unexpected Gemini failure", exc_info=exc)
    return LLMError("The language model is temporarily unavailable.")


async def generate_text(
    prompt: str | list[Any],
    *,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
) -> str:
    try:
        response = await _client().aio.models.generate_content(
            model=model or settings.gemini_chat_model,
            contents=prompt,
            config=_config(system=system, temperature=temperature, max_tokens=max_tokens),
        )
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalised into LLMError
        raise _translate(exc) from exc
    return (response.text or "").strip()


async def stream_text(
    contents: list[types.Content] | str,
    *,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncIterator[str]:
    try:
        stream = await _client().aio.models.generate_content_stream(
            model=settings.gemini_chat_model,
            contents=contents,
            config=_config(system=system, temperature=temperature, max_tokens=max_tokens),
        )
        async for chunk in stream:
            if chunk.text:
                yield chunk.text
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc


async def generate_structured(
    prompt: str,
    schema: type[SchemaT],
    *,
    system: str | None = None,
    temperature: float | None = 0.1,
    max_tokens: int | None = None,
) -> SchemaT:
    """Ask Gemini for JSON constrained to `schema` and validate it with Pydantic."""
    try:
        response = await _client().aio.models.generate_content(
            model=settings.analysis_model,
            contents=prompt,
            config=_config(system=system, temperature=temperature, max_tokens=max_tokens or 8192, schema=schema),
        )
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc

    if isinstance(response.parsed, schema):
        return response.parsed
    raw = (response.text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    try:
        return schema.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Gemini returned malformed JSON: %s", raw[:300])
        raise LLMError("The language model returned an unexpected response format.") from exc


async def transcribe_image(png_bytes: bytes) -> str:
    """OCR fallback using Gemini's multimodal input (used when OCR_ENGINE=gemini)."""
    prompt = (
        "Transcribe all text in this scanned business document page exactly as written. "
        "Preserve reading order, keep table rows on single lines with ' | ' between cells, "
        "and do not add commentary."
    )
    return await generate_text(
        [types.Part.from_bytes(data=png_bytes, mime_type="image/png"), prompt],
        temperature=0.0,
        max_tokens=4096,
    )


def to_contents(history: list[tuple[str, str]], final_user_text: str) -> list[types.Content]:
    contents = [
        types.Content(role="user" if role == "user" else "model", parts=[types.Part.from_text(text=text)])
        for role, text in history
    ]
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=final_user_text)]))
    return contents
