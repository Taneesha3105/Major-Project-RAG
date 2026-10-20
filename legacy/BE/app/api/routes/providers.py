from fastapi import APIRouter, Request

from app.core.config import settings

router = APIRouter(prefix="/providers", tags=["providers"])


def _is_configured(provider_name: str) -> bool:
    if provider_name in {"mock", "local"}:
        return True
    if provider_name == "openai":
        return bool(settings.openai_api_key.strip())
    if provider_name == "gemini":
        return bool(settings.gemini_api_key.strip())
    if provider_name == "groq":
        return bool(settings.groq_api_key.strip())
    if provider_name == "openrouter":
        return bool(settings.openrouter_api_key.strip())
    return False


def _missing_message(provider_name: str) -> str | None:
    if _is_configured(provider_name):
        return None

    if provider_name == "openai":
        return "OPENAI_API_KEY is not set in the backend environment."
    if provider_name == "gemini":
        return "GEMINI_API_KEY is not set in the backend environment."
    if provider_name == "groq":
        return "GROQ_API_KEY is not set in the backend environment."
    if provider_name == "openrouter":
        return "OPENROUTER_API_KEY is not set in the backend environment."
    return None


@router.get("/status")
async def get_provider_status(request: Request) -> dict[str, object]:
    chat_providers = ["mock", "openai", "gemini", "groq", "openrouter"]
    embedding_providers = ["mock", "local", "openai", "gemini"]
    chat_reranker = getattr(request.app.state, "chat_reranker", None)
    flashrank_available = bool(chat_reranker and chat_reranker.enabled)
    available_rerank_strategies = ["fast", *(["hybrid", "neural"] if flashrank_available else [])]

    return {
        "defaults": {
            "chat_provider": settings.chat_provider,
            "rerank_strategy": settings.chat_rerank_strategy_default,
            "embedding_provider": settings.embedding_provider,
            "vector_size": settings.vector_size,
        },
        "reranker": {
            "flashrank_enabled": settings.flashrank_enabled,
            "flashrank_available": flashrank_available,
            "default_strategy": settings.chat_rerank_strategy_default,
            "available_strategies": available_rerank_strategies,
            "flashrank_model": chat_reranker.model_name if flashrank_available else None,
        },
        "chat_providers": [
            {
                "name": provider_name,
                "configured": _is_configured(provider_name),
                "missing_message": _missing_message(provider_name),
            }
            for provider_name in chat_providers
        ],
        "embedding_providers": [
            {
                "name": provider_name,
                "configured": _is_configured(provider_name),
                "missing_message": _missing_message(provider_name),
            }
            for provider_name in embedding_providers
        ],
    }
