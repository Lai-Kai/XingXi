import pytest
from pydantic import ValidationError

from deerflow.config.evidence_pack_config import EvidencePackAppConfig
from deerflow.utils.token_counting import count_text_tokens, estimate_text_tokens


def test_evidence_pack_config_defaults_to_network_free_counting() -> None:
    config = EvidencePackAppConfig()

    assert config.token_budget == 4000
    assert config.token_counting == "char"


def test_evidence_pack_config_rejects_inverted_quote_limits() -> None:
    with pytest.raises(ValidationError, match="min_quote_tokens"):
        EvidencePackAppConfig(min_quote_tokens=100, max_quote_tokens=10)


def test_public_token_counter_is_cjk_aware_and_deterministic() -> None:
    text = "木渎古桥 and bridge"

    assert count_text_tokens(text, strategy="char") == estimate_text_tokens(text)
    assert estimate_text_tokens("木渎古桥") == 4
    assert estimate_text_tokens(text) > 4
