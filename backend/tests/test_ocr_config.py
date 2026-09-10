from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow.config.app_config import AppConfig
from deerflow.config.model_config import ModelConfig
from deerflow.config.sandbox_config import SandboxConfig


def test_enabled_ocr_rejects_a_model_without_vision_support():
    with pytest.raises(ValidationError, match="must support vision"):
        AppConfig(
            sandbox=SandboxConfig(use="test"),
            models=[
                ModelConfig(
                    name="text-only",
                    use="langchain_openai.ChatOpenAI",
                    model="text-model",
                    supports_vision=False,
                )
            ],
            ocr={"enabled": True, "model_name": "text-only"},
        )
