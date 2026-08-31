"""Unit tests for Groq LLM provider integration and double-prefix routing rules."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.llm.client import _resolve_provider_name, complete, configured_providers
from app.llm.settings_store import DEFAULT_MODELS


def test_groq_default_models_present() -> None:
    """Verify exact six Groq models exist in settings store defaults."""
    expected_models = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "groq/compound",
        "groq/compound-mini",
        "qwen/qwen3.6-27b",
        "qwen/qwen3.8-27b",
    ]
    assert "groq" in DEFAULT_MODELS
    assert DEFAULT_MODELS["groq"] == expected_models


def test_groq_provider_resolution() -> None:
    """Verify Groq provider resolution across model strings."""
    assert _resolve_provider_name("groq/compound") == "groq"
    assert _resolve_provider_name("groq/groq/compound") == "groq"
    assert _resolve_provider_name("groq/openai/gpt-oss-120b") == "groq"
    assert _resolve_provider_name("groq/qwen/qwen3.6-27b") == "groq"


def test_groq_configured_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify configured_providers includes groq when key is present."""
    fake_settings = Settings.model_construct(
        groq_api_key=SecretStr("gsk_test_123456789")
    )
    with patch("app.llm.client.get_settings", return_value=fake_settings):
        provs = configured_providers()
        assert "groq" in provs


@pytest.mark.anyio
async def test_groq_double_prefix_and_call() -> None:
    """Verify Groq model call correctly formats wire model ID with groq/ prefix."""
    fake_settings = Settings.model_construct(
        groq_api_key=SecretStr("gsk_test_valid_key")
    )

    class FakeMessage:
        content = "OK"

    class FakeChoice:
        def __init__(self) -> None:
            self.message = FakeMessage()

    class FakeResponse:
        def __init__(self) -> None:
            self.choices = [FakeChoice()]
            self.model = "openai/gpt-oss-120b"

    mock_acompletion = AsyncMock(return_value=FakeResponse())

    with (
        patch("app.llm.client.get_settings", return_value=fake_settings),
        patch("app.llm.client.litellm.acompletion", mock_acompletion),
    ):
        res = await complete(
            [{"role": "user", "content": "Hello"}],
            model="openai/gpt-oss-120b",
        )
        assert res.text == "OK"
        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["model"] == "groq/openai/gpt-oss-120b"
        assert call_kwargs["api_key"] == "gsk_test_valid_key"
