"""Pure request/response helpers for the real FieldOps Operator API."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping
from uuid import uuid4

from .contracts import ActionRequest, ApprovalArtifact, ApprovalStatus
from .governance import action_catalog_payload
from .observations import (
    ObservationAdapterNotBound,
    ObservationRequest,
    ObservationUnavailable,
    UnknownObservationPolicy,
    observation_catalog_payload,
)
from .product_runtime import ProductRuntimeBundle
from .runtime import ActionAdapterNotBound
from .workflow import ActionUnavailable, ApprovalDenied, ApprovalRequired, UnknownActionPolicy


class OperatorRequestError(ValueError):
    pass


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise OperatorRequestError(f"{field_name} must be an object")
    return value


def action_request_from_payload(payload: Mapping[str, Any]) -> ActionRequest:
    action_type = str(payload.get("action_type") or "").strip()
    target_ref = str(payload.get("target_ref") or "").strip()
    if not action_type:
        raise OperatorRequestError("action_type is required")
    if not target_ref:
        raise OperatorRequestError("target_ref is required")
    correlation_id = str(payload.get("correlation_id") or f"fieldops-{uuid4().hex[:16]}")
    parameters = dict(_mapping(payload.get("parameters"), "parameters"))
    expected_state = dict(_mapping(payload.get("expected_state"), "expected_state"))
    return ActionRequest(
        correlation_id=correlation_id,
        action_type=action_type,
        target_ref=target_ref,
        parameters=parameters,
        expected_state=expected_state,
        # Central governance overwrites this. Keeping False proves callers cannot
        # grant themselves a bypass through the HTTP surface.
        requires_approval=False,
    )


def observation_request_from_payload(payload: Mapping[str, Any]) -> ObservationRequest:
    observation_type = str(payload.get("observation_type") or "").strip()
    target_ref = str(payload.get("target_ref") or "").strip()
    if not observation_type:
        raise OperatorRequestError("observation_type is required")
    if not target_ref:
        raise OperatorRequestError("target_ref is required")
    correlation_id = str(payload.get("correlation_id") or f"fieldops-read-{uuid4().hex[:16]}")
    parameters = dict(_mapping(payload.get("parameters"), "parameters"))
    return ObservationRequest(
        correlation_id=correlation_id,
        observation_type=observation_type,
        target_ref=target_ref,
        parameters=parameters,
    )


def approval_from_payload(payload: Mapping[str, Any]) -> ApprovalArtifact:
    raw = _mapping(payload.get("approval"), "approval")
    status_text = str(raw.get("status") or "pending").strip().lower()
    try:
        status = ApprovalStatus(status_text)
    except ValueError as exc:
        raise OperatorRequestError("approval.status is invalid") from exc
    approval_id = str(raw.get("approval_id") or "").strip() or None
    approver_id = str(raw.get("approver_id") or "").strip() or None
    evidence_ref = str(raw.get("evidence_ref") or "").strip() or None
    policy_version = str(raw.get("policy_version") or "").strip() or None
    return ApprovalArtifact(
        status=status,
        approval_id=approval_id,
        approver_id=approver_id,
        policy_version=policy_version,
        evidence_ref=evidence_ref,
    )


def catalog_response(bundle: ProductRuntimeBundle) -> dict[str, object]:
    rows = []
    bound = set(bundle.bindings)
    for item in action_catalog_payload():
        row = dict(item)
        row["runtime_bound"] = item["action_type"] in bound
        rows.append(row)

    observation_rows = []
    observation_bound = set(bundle.observation_bindings)
    for item in observation_catalog_payload():
        row = dict(item)
        row["runtime_bound"] = item["observation_type"] in observation_bound
        observation_rows.append(row)

    return {
        "ok": True,
        "runtime": bundle.status_payload(),
        "actions": rows,
        "observations": observation_rows,
    }


def propose_response(bundle: ProductRuntimeBundle, payload: Mapping[str, Any]) -> dict[str, object]:
    try:
        request = action_request_from_payload(payload)
        proposal = bundle.runtime.proposal(request)
        return {
            "ok": True,
            "request": asdict(request),
            "proposal": asdict(proposal),
            "runtime_bound": bundle.runtime.is_bound(proposal.action_type),
        }
    except (OperatorRequestError, UnknownActionPolicy) as exc:
        return {"ok": False, "error": exc.__class__.__name__, "message": str(exc)}


def observe_response(bundle: ProductRuntimeBundle, payload: Mapping[str, Any]) -> dict[str, object]:
    try:
        request = observation_request_from_payload(payload)
        receipt = bundle.observations.observe(request)
        return {
            "ok": receipt.quality_gate == "passed",
            "status": "observed" if receipt.quality_gate == "passed" else "verification_failed",
            "request": asdict(request),
            "receipt": asdict(receipt),
        }
    except (
        OperatorRequestError,
        UnknownObservationPolicy,
        ObservationUnavailable,
        ObservationAdapterNotBound,
    ) as exc:
        return {
            "ok": False,
            "status": "blocked",
            "error": exc.__class__.__name__,
            "message": str(exc),
        }


def execute_response(bundle: ProductRuntimeBundle, payload: Mapping[str, Any]) -> dict[str, object]:
    try:
        request = action_request_from_payload(payload)
        approval = approval_from_payload(payload)
        proposal = bundle.runtime.proposal(request)
        receipt = bundle.runtime.execute(request=request, approval=approval)
        return {
            "ok": receipt.quality_gate == "passed",
            "status": "completed" if receipt.quality_gate == "passed" else "verification_failed",
            "proposal": asdict(proposal),
            "receipt": asdict(receipt),
        }
    except (
        OperatorRequestError,
        UnknownActionPolicy,
        ApprovalRequired,
        ApprovalDenied,
        ActionUnavailable,
        ActionAdapterNotBound,
    ) as exc:
        return {
            "ok": False,
            "status": "blocked",
            "error": exc.__class__.__name__,
            "message": str(exc),
        }
