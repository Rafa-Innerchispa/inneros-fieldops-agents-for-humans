"""Factory for the real FieldOps operator runtime.

Only adapters that are actually configured and bounded are registered. A policy
may exist in the catalog while its executor remains unbound; execution then fails
closed in :class:`GovernedActionRuntime`.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping

from .dmx_adapter import DMXClient, DMXExecutor, DMXVerifier, LocalDMXHTTPClient
from .ha_adapter import (
    HomeAssistantBindingConfig,
    HomeAssistantClient,
    HomeAssistantConfigurationError,
    HomeAssistantEntityExecutor,
    HomeAssistantEntityVerifier,
    load_canonical_ha_client,
)
from .runtime import GovernedActionRuntime


@dataclass(frozen=True)
class ProductRuntimeBundle:
    runtime: GovernedActionRuntime
    bindings: tuple[str, ...]
    errors: tuple[str, ...]
    ha_allowlist: tuple[str, ...]

    def status_payload(self) -> dict[str, object]:
        return {
            "route": self.runtime.route,
            "route_reason": self.runtime.route_reason,
            "bound_actions": list(self.bindings),
            "binding_errors": list(self.errors),
            "ha_allowlisted_targets": list(self.ha_allowlist),
        }


def build_product_runtime(
    env: Mapping[str, str] | None = None,
    *,
    ha_client: HomeAssistantClient | None = None,
    dmx_client: DMXClient | None = None,
) -> ProductRuntimeBundle:
    source = env or os.environ
    runtime = GovernedActionRuntime(route="inneros-local", route_reason="local_first_bounded_execution")
    errors: list[str] = []
    ha_allowlist: tuple[str, ...] = ()

    # Home Assistant: credentials remain inside the canonical InnerOS module.
    try:
        ha_config = HomeAssistantBindingConfig.from_env(source)
        resolved_ha = ha_client or load_canonical_ha_client(source.get("FIELDOPS_INNEROS_PLATFORM_ROOT"))
        runtime.register(
            "homeassistant.entity_control",
            executor=HomeAssistantEntityExecutor(resolved_ha, ha_config),
            verifier=HomeAssistantEntityVerifier(resolved_ha, ha_config),
        )
        ha_allowlist = tuple(sorted(ha_config.allowed_lights))
    except HomeAssistantConfigurationError as exc:
        errors.append(f"homeassistant:{exc}")

    # DMX: only an explicit private/local backend endpoint is accepted.
    try:
        resolved_dmx = dmx_client
        if resolved_dmx is None and source.get("FIELDOPS_DMX_ENGINE_URL"):
            resolved_dmx = LocalDMXHTTPClient(source.get("FIELDOPS_DMX_ENGINE_URL"))
        if resolved_dmx is not None:
            executor = DMXExecutor(resolved_dmx)
            verifier = DMXVerifier(resolved_dmx)
            runtime.register("dmx.set_scene", executor=executor, verifier=verifier)
            runtime.register("dmx.blackout", executor=executor, verifier=verifier)
        else:
            errors.append("dmx:FIELDOPS_DMX_ENGINE_URL is not configured")
    except Exception as exc:
        errors.append(f"dmx:{type(exc).__name__}")

    return ProductRuntimeBundle(
        runtime=runtime,
        bindings=runtime.bound_actions(),
        errors=tuple(errors),
        ha_allowlist=ha_allowlist,
    )
