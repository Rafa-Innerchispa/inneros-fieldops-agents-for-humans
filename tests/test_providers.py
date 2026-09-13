import pytest

from src.fieldops.providers import ProviderConfigError, load_provider_config


def test_local_provider_config_is_default_and_secret_free():
    config = load_provider_config({})

    assert config.provider == "local"
    assert config.model_id == "inneros-local-default"
    assert config.endpoint == "http://127.0.0.1:8000/v1"
    assert config.region is None


def test_bedrock_provider_requires_model_id_without_credentials():
    with pytest.raises(ProviderConfigError):
        load_provider_config({"FIELDOPS_MODEL_PROVIDER": "bedrock"})


def test_bedrock_provider_loads_non_secret_routing_metadata():
    config = load_provider_config(
        {
            "FIELDOPS_MODEL_PROVIDER": "bedrock",
            "FIELDOPS_BEDROCK_MODEL_ID": "anthropic.claude-test",
            "AWS_REGION": "us-east-1",
        }
    )

    assert config.provider == "bedrock"
    assert config.model_id == "anthropic.claude-test"
    assert config.region == "us-east-1"
    assert config.strands_enabled is True
    assert config.endpoint is None
