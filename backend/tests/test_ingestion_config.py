import pytest
from pydantic import ValidationError

from deerflow.config.ingestion_config import IngestionConfig


def test_ingestion_config_has_safe_local_defaults():
    config = IngestionConfig()

    assert config.max_concurrent_jobs == 2
    assert config.lease_seconds == 60
    assert config.recovery_grace_seconds == 10


@pytest.mark.parametrize(
    "values",
    [
        {"max_concurrent_jobs": 0},
        {"lease_seconds": 9},
        {"recovery_grace_seconds": -1},
    ],
)
def test_ingestion_config_rejects_unsafe_limits(values):
    with pytest.raises(ValidationError):
        IngestionConfig.model_validate(values)
