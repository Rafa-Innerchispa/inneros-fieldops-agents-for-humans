"""Governed read-only observations for FieldOps.

Reads do not require human approval because they cannot mutate the physical
system, but they still pass through a central policy, bounded observer,
independent verifier and evidence receipt. This keeps read truth as explicit as
mutation truth without pretending that reading a sensor is a dangerous action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol


class ObservationAvailability(str, Enum):
    ENABLED_REAL = "enabled_real"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ObservationPolicy:
    observation_type: str
    domain: str
    description: str
    availability: ObservationAvailability
    observer_id: str
    verifier_id: str
    truth_note: str = ""

    @property
    def observable(self) -> bool:
        return self.availability == ObservationAvailability.ENABLED_REAL


@dataclass(frozen=True)
class ObservationRequest:
    correlation_id: str
    observation_type: str
    target_ref: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    policy_version: str = "fieldops-v1"


@dataclass(frozen=True)
class ObservationResult:
    correlation_id: str
    observer: str
    success: bool
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ObservationVerification:
    correlation_id: str
    verifier: str
    passed: bool
    observed_state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ObservationReceipt:
    correlation_id: str
    route: str
    route_reason: str
    policy_version: str
    requested_observation: str
    target_ref: str
    observer: str
    verifier: str
    read_success: bool
    verification_passed: bool
    quality_gate: str
    evidence_refs: tuple[str, ...] = ()
    read_details: Mapping[str, Any] = field(default_factory=dict)
    observed_state: Mapping[str, Any] = field(default_factory=dict)
    governance_domain: str = ""
    observation_availability: str = ""
    requires_approval: bool = False


class Observer(Protocol):
    def observe(self, request: ObservationRequest) -> ObservationResult: ...


class ObservationVerifier(Protocol):
    def verify(
        self, request: ObservationRequest, result: ObservationResult
    ) -> ObservationVerification: ...


class UnknownObservationPolicy(RuntimeError):
    pass


class ObservationUnavailable(RuntimeError):
    pass


class ObservationAdapterNotBound(RuntimeError):
    pass


_OBSERVATIONS = {
    "energy.read_status": ObservationPolicy(
        observation_type="energy.read_status",
        domain="energy",
        description="Read live inverter/battery/grid state without changing inverter configuration.",
        availability=ObservationAvailability.ENABLED_REAL,
        observer_id="inneros-ha-solar-telemetry",
        verifier_id="solar-telemetry-consistency",
        truth_note="Reads the existing PI30/Xmart telemetry exposed through the canonical Home Assistant bridge; no inverter write path is present.",
    ),
    "camera.capture_evidence": ObservationPolicy(
        observation_type="camera.capture_evidence",
        domain="security",
        description="Request a fresh allowlisted Dahua snapshot through the existing Physical Guardian runtime and retain only evidence metadata.",
        availability=ObservationAvailability.ENABLED_REAL,
        observer_id="physical-guardian-snapshot",
        verifier_id="jpeg-evidence-verifier",
        truth_note="Reuses the live Physical Guardian camera path. FieldOps receives JPEG validity, size and SHA-256 evidence metadata, not camera credentials.",
    ),
    "network.scan_wifi": ObservationPolicy(
        observation_type="network.scan_wifi",
        domain="network",
        description="Scan RF conditions from the dedicated AMD Wi-Fi adapter without changing AP or client configuration.",
        availability=ObservationAvailability.ENABLED_REAL,
        observer_id="inneros-peer-wifi-scan",
        verifier_id="ethernet-route-readback",
        truth_note="The dedicated Wi-Fi radio scans only; the verifier requires the production default route to remain on Ethernet before and after the scan.",
    ),
    "telephony.read_status": ObservationPolicy(
        observation_type="telephony.read_status",
        domain="telephony",
        description="Read VoiceOps and PBX control-plane health without registering SIP or originating a call.",
        availability=ObservationAvailability.ENABLED_REAL,
        observer_id="voiceops-telephony-health",
        verifier_id="voiceops-pbx-independent-readback",
        truth_note="VoiceOps remains the sole owner of SIP/RTP execution. FieldOps checks the existing VoiceOps health surface and independently verifies private PBX AMI reachability without reading telephony credentials.",
    ),
    "alarm.read_status": ObservationPolicy(
        observation_type="alarm.read_status",
        domain="alarm",
        description="Read the Intelbras alarm panel and zone presence without arming, disarming, triggering siren, or changing panel state.",
        availability=ObservationAvailability.ENABLED_REAL,
        observer_id="inneros-ha-intelbras-alarm-read",
        verifier_id="alarm-read-only-state-verifier",
        truth_note="Reads the existing Home Assistant/Intelbras Guardian projection only. FieldOps does not expose arm/disarm/panic/siren/PGM control.",
    ),
}


def observation_policy(observation_type: str) -> ObservationPolicy:
    try:
        return _OBSERVATIONS[observation_type]
    except KeyError as exc:
        raise UnknownObservationPolicy(
            f"No FieldOps observation policy registered for {observation_type!r}"
        ) from exc


def observation_catalog_payload() -> list[dict[str, object]]:
    return [
        {
            "observation_type": item.observation_type,
            "domain": item.domain,
            "description": item.description,
            "availability": item.availability.value,
            "observer_id": item.observer_id,
            "verifier_id": item.verifier_id,
            "requires_approval": False,
            "truth_note": item.truth_note,
        }
        for item in _OBSERVATIONS.values()
    ]


class GovernedObservationRuntime:
    def __init__(self, route: str = "inneros-local", route_reason: str = "local_first_read_only"):
        self.route = route
        self.route_reason = route_reason
        self._bindings: dict[str, tuple[Observer, ObservationVerifier]] = {}

    def register(
        self,
        observation_type: str,
        *,
        observer: Observer,
        verifier: ObservationVerifier,
    ) -> None:
        policy = observation_policy(observation_type)
        if not policy.observable:
            raise ObservationUnavailable(f"{observation_type} is not enabled for real observation")
        self._bindings[observation_type] = (observer, verifier)

    def is_bound(self, observation_type: str) -> bool:
        return observation_type in self._bindings

    def bound_observations(self) -> tuple[str, ...]:
        return tuple(sorted(self._bindings))

    def observe(self, request: ObservationRequest) -> ObservationReceipt:
        policy = observation_policy(request.observation_type)
        if not policy.observable:
            raise ObservationUnavailable(f"{request.observation_type} is not available")
        try:
            observer, verifier = self._bindings[policy.observation_type]
        except KeyError as exc:
            raise ObservationAdapterNotBound(
                f"No real observer is bound for {policy.observation_type}"
            ) from exc

        result = observer.observe(request)
        verification = verifier.verify(request, result)
        quality_gate = "passed" if result.success and verification.passed else "failed"
        evidence_refs: list[str] = []
        ref = result.details.get("evidence_ref") if isinstance(result.details, Mapping) else None
        if ref:
            evidence_refs.append(str(ref))
        return ObservationReceipt(
            correlation_id=request.correlation_id,
            route=self.route,
            route_reason=self.route_reason,
            policy_version=request.policy_version,
            requested_observation=policy.observation_type,
            target_ref=request.target_ref,
            observer=policy.observer_id,
            verifier=policy.verifier_id,
            read_success=result.success,
            verification_passed=verification.passed,
            quality_gate=quality_gate,
            evidence_refs=tuple(evidence_refs),
            read_details=result.details,
            observed_state=verification.observed_state,
            governance_domain=policy.domain,
            observation_availability=policy.availability.value,
            requires_approval=False,
        )
