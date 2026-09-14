"""Factory for the real FieldOps operator runtime.

Only adapters that are actually configured and bounded are registered. Mutation
and observation capabilities share the same product bundle but keep different
safety semantics: reads never require approval; mutations do.
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
from .observations import GovernedObservationRuntime
from .read_adapters import (
    AlarmStatusObserver,
    AlarmStatusVerifier,
    CameraEvidenceObserver,
    CameraEvidenceVerifier,
    EdgeReadClient,
    NetworkScanObserver,
    NetworkScanVerifier,
    ReadAdapterConfigurationError,
    RemoteReadOpsHTTPClient,
    SolarStatusObserver,
    SolarStatusVerifier,
)
from .runtime import GovernedActionRuntime
from .telephony_read_adapter import (
    LocalVoiceOpsRuntimeClient,
    LocalVoiceOpsTelephonyReadClient,
    TelephonyReadClient,
    TelephonyReadConfigurationError,
    TelephonyStatusObserver,
    TelephonyStatusVerifier,
    VoiceOpsCallbackClient,
    VoiceOpsOwnerCallbackExecutor,
    VoiceOpsOwnerCallbackVerifier,
)


@dataclass(frozen=True)
class ProductRuntimeBundle:
    runtime: GovernedActionRuntime
    observations: GovernedObservationRuntime
    bindings: tuple[str, ...]
    observation_bindings: tuple[str, ...]
    errors: tuple[str, ...]
    ha_allowlist: tuple[str, ...]

    def status_payload(self) -> dict[str, object]:
        return {
            "route": self.runtime.route,
            "route_reason": self.runtime.route_reason,
            "bound_actions": list(self.bindings),
            "bound_observations": list(self.observation_bindings),
            "binding_errors": list(self.errors),
            "ha_allowlisted_targets": list(self.ha_allowlist),
        }


def build_product_runtime(
    env: Mapping[str, str] | None = None,
    *,
    ha_client: HomeAssistantClient | None = None,
    dmx_client: DMXClient | None = None,
    edge_client: EdgeReadClient | None = None,
    telephony_read_client: TelephonyReadClient | None = None,
    telephony_callback_client: VoiceOpsCallbackClient | None = None,
) -> ProductRuntimeBundle:
    source = env or os.environ
    runtime = GovernedActionRuntime(route="inneros-local", route_reason="local_first_bounded_execution")
    observations = GovernedObservationRuntime(
        route="inneros-local",
        route_reason="local_first_read_only_observation",
    )
    errors: list[str] = []
    ha_allowlist: tuple[str, ...] = ()

    # Canonical HA client is reused for both safe solar observation and bounded
    # light control. Solar reads do not depend on the mutation allowlist.
    resolved_ha: HomeAssistantClient | None = None
    try:
        resolved_ha = ha_client or load_canonical_ha_client(source.get("FIELDOPS_INNEROS_PLATFORM_ROOT"))
        observations.register(
            "energy.read_status",
            observer=SolarStatusObserver(resolved_ha),
            verifier=SolarStatusVerifier(),
        )
        observations.register(
            "alarm.read_status",
            observer=AlarmStatusObserver(
                resolved_ha,
                panel_entity_id=str(source.get("FIELDOPS_ALARM_ENTITY") or "").strip() or None,
                zone_prefix=str(source.get("FIELDOPS_ALARM_ZONE_PREFIX") or "").strip() or None,
            ),
            verifier=AlarmStatusVerifier(),
        )
    except HomeAssistantConfigurationError as exc:
        errors.append(f"homeassistant-read:{exc}")

    try:
        ha_config = HomeAssistantBindingConfig.from_env(source)
        if resolved_ha is None:
            resolved_ha = ha_client or load_canonical_ha_client(source.get("FIELDOPS_INNEROS_PLATFORM_ROOT"))
        runtime.register(
            "homeassistant.entity_control",
            executor=HomeAssistantEntityExecutor(resolved_ha, ha_config),
            verifier=HomeAssistantEntityVerifier(resolved_ha, ha_config),
        )
        ha_allowlist = tuple(sorted(ha_config.allowed_lights))
    except HomeAssistantConfigurationError as exc:
        errors.append(f"homeassistant:{exc}")

    # Physical Guardian + Wi-Fi read sidecar. It exposes only sanitized
    # observation metadata from the AMD edge node; camera credentials stay there.
    try:
        resolved_edge = edge_client
        if resolved_edge is None:
            edge_url = str(source.get("FIELDOPS_READOPS_EDGE_URL") or "").strip()
            if edge_url:
                resolved_edge = RemoteReadOpsHTTPClient(edge_url)
        if resolved_edge is not None:
            observations.register(
                "camera.capture_evidence",
                observer=CameraEvidenceObserver(resolved_edge),
                verifier=CameraEvidenceVerifier(),
            )
            observations.register(
                "network.scan_wifi",
                observer=NetworkScanObserver(resolved_edge),
                verifier=NetworkScanVerifier(),
            )
        else:
            errors.append("readops:FIELDOPS_READOPS_EDGE_URL is not configured")
    except (ReadAdapterConfigurationError, ValueError) as exc:
        errors.append(f"readops:{exc}")

    # VoiceOps owns SIP/RTP/PBX credentials. FieldOps consumes only the private
    # runtime contract and may request one governed owner callback after normal
    # approval. The legacy health path remains available for staged rollback.
    try:
        resolved_telephony = telephony_read_client
        resolved_callback = telephony_callback_client
        if resolved_telephony is None or resolved_callback is None:
            runtime_url = str(source.get("FIELDOPS_VOICEOPS_RUNTIME_URL") or "").strip()
            ami_host = str(source.get("FIELDOPS_TELEPHONY_AMI_HOST") or "").strip()
            if runtime_url and ami_host:
                voiceops_runtime = LocalVoiceOpsRuntimeClient(
                    base_url=runtime_url,
                    pbx_ami_host=ami_host,
                    pbx_ami_port=int(str(source.get("FIELDOPS_TELEPHONY_AMI_PORT") or "7777")),
                    bearer_token=str(source.get("FIELDOPS_VOICEOPS_RUNTIME_TOKEN") or "").strip(),
                )
                if resolved_telephony is None:
                    resolved_telephony = voiceops_runtime
                if resolved_callback is None:
                    resolved_callback = voiceops_runtime
            elif resolved_telephony is None:
                health_url = str(source.get("FIELDOPS_VOICEOPS_HEALTH_URL") or "").strip()
                if health_url and ami_host:
                    resolved_telephony = LocalVoiceOpsTelephonyReadClient(
                        voiceops_health_url=health_url,
                        pbx_ami_host=ami_host,
                        pbx_ami_port=int(str(source.get("FIELDOPS_TELEPHONY_AMI_PORT") or "7777")),
                    )
        if resolved_telephony is not None:
            observations.register(
                "telephony.read_status",
                observer=TelephonyStatusObserver(resolved_telephony),
                verifier=TelephonyStatusVerifier(),
            )
        else:
            errors.append(
                "telephony:FIELDOPS_VOICEOPS_RUNTIME_URL or legacy health URL plus AMI host are not configured"
            )
        if resolved_callback is not None:
            runtime.register(
                "telephony.request_owner_callback",
                executor=VoiceOpsOwnerCallbackExecutor(resolved_callback),
                verifier=VoiceOpsOwnerCallbackVerifier(resolved_callback),
            )
    except (TelephonyReadConfigurationError, ValueError) as exc:
        errors.append(f"telephony:{exc}")

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
        observations=observations,
        bindings=runtime.bound_actions(),
        observation_bindings=observations.bound_observations(),
        errors=tuple(errors),
        ha_allowlist=ha_allowlist,
    )
