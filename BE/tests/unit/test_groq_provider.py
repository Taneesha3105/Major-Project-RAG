import unittest
from unittest.mock import patch

from app.api.routes import providers as provider_routes
from app.chat.provider import GroqChatProvider, get_chat_provider
from app.chat.schemas import ChatRequest
from app.core.config import settings


class GroqProviderTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_chat_provider.cache_clear()

    def test_chat_request_accepts_groq_provider(self) -> None:
        payload = ChatRequest(question="How does Groq help latency?", provider="groq")
        self.assertEqual(payload.provider, "groq")

    def test_get_chat_provider_returns_groq_provider_when_configured(self) -> None:
        with (
            patch.object(settings, "groq_api_key", "test-key"),
            patch.object(settings, "groq_base_url", "https://api.groq.com/openai/v1"),
            patch.object(settings, "groq_chat_model", "llama-3.1-8b-instant"),
        ):
            provider = get_chat_provider("groq")

        self.assertIsInstance(provider, GroqChatProvider)
        self.assertEqual(provider.display_name, "groq:llama-3.1-8b-instant")

    def test_get_chat_provider_requires_key(self) -> None:
        with patch.object(settings, "groq_api_key", ""):
            with self.assertRaisesRegex(ValueError, "GROQ_API_KEY is required"):
                get_chat_provider("groq")

    def test_provider_status_helpers_reflect_groq_configuration(self) -> None:
        with patch.object(settings, "groq_api_key", ""):
            self.assertFalse(provider_routes._is_configured("groq"))
            self.assertEqual(
                provider_routes._missing_message("groq"),
                "GROQ_API_KEY is not set in the backend environment.",
            )

        with patch.object(settings, "groq_api_key", "test-key"):
            self.assertTrue(provider_routes._is_configured("groq"))
            self.assertIsNone(provider_routes._missing_message("groq"))


if __name__ == "__main__":
    unittest.main()
