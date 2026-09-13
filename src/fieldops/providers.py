"""Provider configuration for local-first FieldOps routing.

This module contains metadata and validation only. It does not create network
clients, read secrets, or require AWS/Strands packages. Live Bedrock invocation
belongs in an explicit adapter with owner-approved credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


class ProviderConfigError(ValueError):
    """Raised when a requested provider is missing non-secret configuration."""


@dataclass(frozen=True)
class ModelProviderConfig:
    provider: str
    model_id: str
    route: str
    route_reason: str
    region: str | None = None
    endpoint: str | None = None
    strands_enabled: bool = False

    def to_env_overlay(self) -> dict[str, str]:
        """Return non-secret env values useful for deterministic CLI overrides."""

        values = {
            "FIELDOPS_MODEL_PROVIDER": self.provider,
            "FIELDOPS_ROUTE": self.route,
            "FIELDOPS_ROUTE_REASON": self.route_reason,
            "FIELDOPS_STRANDS_ENABLED": "1" if self.strands_enabled else "0",
        }
        if self.model_id:
            if self.provider == "bedrock":
                values["FIELDOPS_BEDROCK_MODEL_ID"] = self.model_id
            else:
                values["FIELDOPS_LOCAL_MODEL_ID"] = self.model_id
        if self.region:
            values["AWS_REGION"] = self.region
        if self.endpoint:
            values["FIELDOPS_LOCAL_ENDPOINT"] = self.endpoint
        return values


def _env(source: Mapping[str, str] | None, key: str, default: str = "") -> str:
    if source is not None and key in source:
        return source[key].strip()
    return os.getenv(key, default).strip()


def load_provider_config(source: Mapping[str, str] | None = None) -> ModelProviderConfig:
    """Load local or Bedrock routing metadata without loading credentials."""

    provider = _env(source, "FIELDOPS_MODEL_PROVIDER", "local").lower()
    route = _env(source, "FIELDOPS_ROUTE", "local-edge")
    route_reason = _env(source, "FIELDOPS_ROUTE_REASON", "privacy_and_device_locality")
    strands_enabled = _env(source, "FIELDOPS_STRANDS_ENABLED", "0") in {"1", "true", "yes"}

    if provider == "local":
        return ModelProviderConfig(
            provider="local",
            model_id=_env(source, "FIELDOPS_LOCAL_MODEL_ID", "inneros-local-default"),
            endpoint=_env(source, "FIELDOPS_LOCAL_ENDPOINT", "http://127.0.0.1:8000/v1"),
            route=route,
            route_reason=route_reason,
            strands_enabled=strands_enabled,
        )
    if provider == "bedrock":
        model_id = _env(source, "FIELDOPS_BEDROCK_MODEL_ID")
        region = _env(source, "AWS_REGION", "us-west-2")
        if not model_id:
            raise ProviderConfigError(
                "FIELDOPS_BEDROCK_MODEL_ID is required when FIELDOPS_MODEL_PROVIDER=bedrock"
            )
        return ModelProviderConfig(
            provider="bedrock",
            model_id=model_id,
            region=region,
            route=route,
            route_reason="aws_bedrock_optional_orchestration",
            strands_enabled=True,
        )
    raise ProviderConfigError(f"Unsupported FIELDOPS_MODEL_PROVIDER: {provider}")
