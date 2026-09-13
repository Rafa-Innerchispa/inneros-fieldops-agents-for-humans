from src.fieldops.demo_runner import run_demo
from src.fieldops.providers import ProviderConfigError, load_provider_config


def test_demo_happy_path_returns_evidence_receipt():
    result = run_demo("happy", load_provider_config({}))

    assert result["status"] == "ok"
    assert result["receipt"]["quality_gate"] == "passed"
    assert result["provider"]["provider"] == "local"


def test_bedrock_cli_override_requires_model_configuration():
    try:
        load_provider_config({"FIELDOPS_MODEL_PROVIDER": "bedrock"})
        assert False, "expected ProviderConfigError"
    except ProviderConfigError as exc:
        assert "FIELDOPS_BEDROCK_MODEL_ID" in str(exc)
