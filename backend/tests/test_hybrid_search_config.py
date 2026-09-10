import pytest
from pydantic import ValidationError

from deerflow.config.hybrid_search_config import HybridSearchConfig


def test_hybrid_search_config_has_bounded_timeout_and_rrf_constant() -> None:
    config = HybridSearchConfig(channel_timeout_seconds=2.5, rrf_k=40)

    assert config.channel_timeout_seconds == 2.5
    assert config.rrf_k == 40
    with pytest.raises(ValidationError):
        HybridSearchConfig(channel_timeout_seconds=0)
    with pytest.raises(ValidationError):
        HybridSearchConfig(rrf_k=0)
