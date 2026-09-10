from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EvidencePackAppConfig(BaseModel):
    """Prompt-facing evidence pack limits."""

    token_budget: int = Field(default=4000, ge=128, le=100_000)
    max_items: int = Field(default=12, ge=1, le=100)
    max_quote_tokens: int = Field(default=512, ge=1, le=20_000)
    min_quote_tokens: int = Field(default=24, ge=1, le=2_000)
    token_counting: Literal["tiktoken", "char"] = "char"

    @model_validator(mode="after")
    def validate_quote_limits(self) -> "EvidencePackAppConfig":
        if self.min_quote_tokens > self.max_quote_tokens:
            raise ValueError("min_quote_tokens must not exceed max_quote_tokens")
        return self
