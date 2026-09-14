"""Universal governance registry for every FieldOps action that can mutate reality.

The registry is the source of truth for approval, execution readiness, verifier
requirements and safe-return metadata. Integrations are not allowed to weaken
these rules by constructing an ActionRequest with a friendlier flag.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .contracts import ActionRequest


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionAvailability(str, Enum):
    ENABLED_REAL = "enabled_real"
    ENABLED_SYNTHETIC = "enabled_synthetic"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ActionPolicy:
    action_type: str
    domain: str
    description: str
    risk: RiskLevel
    requires_approval: bool
    availability: ActionAvailability
    executor_id: str
    verifier_id: str
    reversible: bool = False
    safe_return_action: str | None = None
    truth_note: str = ""

    @property
    def executable(self) -> bool:
        return self.availability in {
            ActionAvailability.ENABLED_REAL,
            ActionAvailability.ENABLED_SYNTHETIC,
        }


@dataclass(frozen=True)
class ActionProposal:
    correlation_id: str
    action_type: str
    target_ref: str
    domain: str
    description: str
    risk: str
    requires_approval: bool
    availability: str
    executable: bool
    executor_id: str
    verifier_id: str
    reversible: bool
    safe_return_action: str | None
    truth_note: str


class UnknownActionPolicy(RuntimeError):
    pass


class ActionUnavailable(RuntimeError):
    pass


# Mutations only. Read-only observations deliberately do not live here and do
# not require approval.
_ACTIONS = {
    "camera.service_restart": ActionPolicy(
        action_type="camera.service_restart",
        domain="security",
        description="Restart an allowlisted camera/service target.",
        risk=RiskLevel.MEDIUM,
        requires_approval=True,
        availability=ActionAvailability.ENABLED_SYNTHETIC,
        executor_id="inneros-edge-01",
        verifier_id="synthetic-state-probe",
        truth_note="Judge workflow uses a safe synthetic target; the governance contract is production-shaped.",
    ),
    "dmx.set_scene": ActionPolicy(
        action_type="dmx.set_scene",
        domain="lighting",
        description="Apply an allowlisted high-level DMX scene through InnerOS AG-59.",
        risk=RiskLevel.LOW,
        requires_approval=True,
        availability=ActionAvailability.ENABLED_REAL,
        executor_id="inneros-ag59",
        verifier_id="inneros-ag59-status",
        reversible=True,
        safe_return_action="dmx.blackout",
        truth_note="Real high-level scene execution is verified; raw channels/universes remain unavailable.",
    ),
    "dmx.blackout": ActionPolicy(
        action_type="dmx.blackout",
        domain="lighting",
        description="Return the DMX installation to bounded blackout.",
        risk=RiskLevel.LOW,
        requires_approval=True,
        availability=ActionAvailability.ENABLED_REAL,
        executor_id="inneros-ag59",
        verifier_id="inneros-ag59-status",
        reversible=True,
        truth_note="Backend ACK is real; verifier treats running=false as blackout while last-scene telemetry may remain stale.",
    ),
    "homeassistant.scene_turn_on": ActionPolicy(
        action_type="homeassistant.scene_turn_on",
        domain="facility_iot",
        description="Activate an explicitly allowlisted Home Assistant scene.",
        risk=RiskLevel.LOW,
        requires_approval=True,
        availability=ActionAvailability.BLOCKED,
        executor_id="inneros-ha-service-bridge",
        verifier_id="homeassistant-state-readback",
        reversible=True,
        truth_note="Bridge exists in InnerOS; FieldOps target allowlist and per-scene verifier must be bound before execution.",
    ),
    "homeassistant.entity_control": ActionPolicy(
        action_type="homeassistant.entity_control",
        domain="facility_iot",
        description="Change one explicitly allowlisted light/switch entity.",
        risk=RiskLevel.MEDIUM,
        requires_approval=True,
        availability=ActionAvailability.BLOCKED,
        executor_id="inneros-ha-service-bridge",
        verifier_id="homeassistant-state-readback",
        reversible=True,
        truth_note="No arbitrary entity/service calls are accepted until an explicit FieldOps allowlist is bound.",
    ),
    "telephony.originate_call": ActionPolicy(
        action_type="telephony.originate_call",
        domain="telephony",
        description="Originate a bounded outbound call through the verified PBX route.",
        risk=RiskLevel.MEDIUM,
        requires_approval=True,
        availability=ActionAvailability.BLOCKED,
        executor_id="voiceops-ucm-originate",
        verifier_id="voiceops-call-state",
        reversible=True,
        safe_return_action="telephony.hangup_call",
        truth_note="SIP/AMI/CGI control planes are verified, but outbound route verification is still required before enabling calls.",
    ),
    "network.apply_bounded_recovery": ActionPolicy(
        action_type="network.apply_bounded_recovery",
        domain="network",
        description="Apply a predeclared UniFi recovery operation to an allowlisted target.",
        risk=RiskLevel.HIGH,
        requires_approval=True,
        availability=ActionAvailability.BLOCKED,
        executor_id="inneros-network-ops",
        verifier_id="unifi-state-readback",
        reversible=True,
        truth_note="Network telemetry is real; arbitrary RF/network mutation remains disabled until a bounded recovery action is verified.",
    ),
    "energy.apply_bounded_control": ActionPolicy(
        action_type="energy.apply_bounded_control",
        domain="energy",
        description="Apply an explicitly allowlisted inverter/load control operation.",
        risk=RiskLevel.HIGH,
        requires_approval=True,
        availability=ActionAvailability.BLOCKED,
        executor_id="inneros-energy-control",
        verifier_id="energy-telemetry-readback",
        reversible=True,
        truth_note="Energy telemetry is available; inverter writes stay blocked until command semantics and independent telemetry verification are proven.",
    ),
    "alarm.apply_state": ActionPolicy(
        action_type="alarm.apply_state",
        domain="alarm",
        description="Change alarm state through a bounded, verified Intelbras operation.",
        risk=RiskLevel.CRITICAL,
        requires_approval=True,
        availability=ActionAvailability.BLOCKED,
        executor_id="inneros-alarm-control",
        verifier_id="alarm-state-readback",
        reversible=True,
        truth_note="Presence/discovery exists; arm/disarm/panic/siren/PGM execution is not yet claimed.",
    ),
    "access.apply_state": ActionPolicy(
        action_type="access.apply_state",
        domain="access",
        description="Change an allowlisted physical access point state.",
        risk=RiskLevel.CRITICAL,
        requires_approval=True,
        availability=ActionAvailability.BLOCKED,
        executor_id="inneros-access-control",
        verifier_id="access-state-readback",
        reversible=True,
        truth_note="No production unlock/open action is enabled without a verified executor plus independent readback.",
    ),
}

# Backward-compatible wire aliases are canonicalized before execution. They do
# not inherit old approval semantics.
_ALIASES = {"service_restart": "camera.service_restart"}

READ_ONLY_CAPABILITIES = {
    "energy.telemetry": "Observe inverter, battery, load and PV state.",
    "network.telemetry": "Observe UniFi clients, AP state and RF conditions.",
    "camera.telemetry": "Observe camera/service health.",
    "telephony.telemetry": "Observe PBX/control-plane reachability and call state.",
    "alarm.telemetry": "Observe alarm presence/state when available.",
    "facility.telemetry": "Observe Home Assistant entities and facility state.",
}


def action_policy(action_type: str) -> ActionPolicy:
    canonical = _ALIASES.get(action_type, action_type)
    try:
        return _ACTIONS[canonical]
    except KeyError as exc:
        raise UnknownActionPolicy(f"No FieldOps mutation policy registered for {action_type!r}") from exc


def list_action_policies() -> tuple[ActionPolicy, ...]:
    return tuple(_ACTIONS.values())


def bind_request_to_policy(request: ActionRequest) -> tuple[ActionRequest, ActionPolicy]:
    """Canonicalize a request and impose central approval policy.

    This function intentionally does not reject blocked executors. A blocked action
    may still be proposed and explicitly approved; execution is what remains gated.
    """

    policy = action_policy(request.action_type)
    return (
        replace(
            request,
            action_type=policy.action_type,
            requires_approval=policy.requires_approval,
        ),
        policy,
    )


def governed_request(request: ActionRequest) -> tuple[ActionRequest, ActionPolicy]:
    """Backward-compatible alias for policy binding."""

    return bind_request_to_policy(request)


def propose_action(request: ActionRequest) -> ActionProposal:
    governed, policy = bind_request_to_policy(request)
    return ActionProposal(
        correlation_id=governed.correlation_id,
        action_type=policy.action_type,
        target_ref=governed.target_ref,
        domain=policy.domain,
        description=policy.description,
        risk=policy.risk.value,
        requires_approval=policy.requires_approval,
        availability=policy.availability.value,
        executable=policy.executable,
        executor_id=policy.executor_id,
        verifier_id=policy.verifier_id,
        reversible=policy.reversible,
        safe_return_action=policy.safe_return_action,
        truth_note=policy.truth_note,
    )


def action_catalog_payload() -> list[dict[str, object]]:
    return [
        {
            "action_type": item.action_type,
            "domain": item.domain,
            "description": item.description,
            "risk": item.risk.value,
            "requires_approval": item.requires_approval,
            "availability": item.availability.value,
            "executor_id": item.executor_id,
            "verifier_id": item.verifier_id,
            "reversible": item.reversible,
            "safe_return_action": item.safe_return_action,
            "truth_note": item.truth_note,
        }
        for item in list_action_policies()
    ]
