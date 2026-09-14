"""Bounded VoiceOps/PBX adapter for FieldOps.

FieldOps never registers SIP, reads PBX/SIP credentials, or accepts an arbitrary
phone destination. VoiceOps owns the telephony execution plane. FieldOps may:

* read the sanitized ``voiceops.fieldops.telephony.v1`` contract;
* independently confirm the private PBX AMI control plane is reachable; and
* after normal FieldOps approval, request one callback to the preconfigured
  owner endpoint through the private VoiceOps runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import socket
from typing import Any, Mapping, Protocol
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .contracts import ActionRequest, ExecutionResult, VerificationResult
from .observations import ObservationRequest, ObservationResult, ObservationVerification

VOICEOPS_CONTRACT_VERSION = "voiceops.fieldops.telephony.v1"
OWNER_CALLBACK_TARGET = "voiceops.owner"


class TelephonyReadConfigurationError(RuntimeError):
    pass


class TelephonyReadClient(Protocol):
    def status(self) -> Mapping[str, Any]: ...


class VoiceOpsCallbackClient(TelephonyReadClient, Protocol):
    def request_owner_callback(
        self,
        *,
        correlation_id: str,
        reason: str,
        requested_by: str,
    ) -> Mapping[str, Any]: ...

    def receipt(self, correlation_id: str) -> Mapping[str, Any]: ...


def _private_or_loopback_literal(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(ip.is_private or ip.is_loopback)


def _ami_banner_probe(host: str, port: int, timeout_seconds: float) -> dict[str, Any]:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_seconds) as conn:
            conn.settimeout(timeout_seconds)
            raw = conn.recv(512)
    except OSError as exc:
        return {
            "reachable": False,
            "banner_valid": False,
            "error": type(exc).__name__,
        }
    banner = raw.decode("utf-8", "replace").splitlines()[0].strip() if raw else ""
    valid = banner.startswith("Asterisk Call Manager/")
    return {
        "reachable": bool(raw),
        "banner_valid": valid,
        "banner_family": "Asterisk Call Manager" if valid else "unexpected",
    }


@dataclass(frozen=True)
class LocalVoiceOpsRuntimeClient:
    """Consume the private persistent VoiceOps runtime over HTTP.

    ``base_url`` must be a private/loopback literal over plain HTTP. The runtime
    itself is designed to bind to loopback; the private-literal allowance keeps
    this adapter testable and permits an explicit private peer deployment without
    ever accepting a public hostname.
    """

    base_url: str
    pbx_ami_host: str
    pbx_ami_port: int = 7777
    timeout_seconds: float = 3.0
    bearer_token: str = ""

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url.rstrip("/"))
        if parsed.scheme != "http" or not parsed.hostname:
            raise TelephonyReadConfigurationError("VoiceOps runtime URL must be an http URL")
        if not _private_or_loopback_literal(parsed.hostname):
            raise TelephonyReadConfigurationError("VoiceOps runtime URL must stay on private/loopback networking")
        if parsed.path not in {"", "/"}:
            raise TelephonyReadConfigurationError("VoiceOps runtime URL must be a base URL without a path")
        if not _private_or_loopback_literal(self.pbx_ami_host):
            raise TelephonyReadConfigurationError("PBX AMI host must be a private/loopback literal")
        if not 1 <= int(self.pbx_ami_port) <= 65535:
            raise TelephonyReadConfigurationError("PBX AMI port must be between 1 and 65535")
        if self.timeout_seconds <= 0:
            raise TelephonyReadConfigurationError("timeout_seconds must be positive")

    def status(self) -> Mapping[str, Any]:
        contract = self._json("/v1/telephony/status")
        runtime = contract.get("runtime") if isinstance(contract.get("runtime"), Mapping) else {}
        contract_valid = contract.get("contract_version") == VOICEOPS_CONTRACT_VERSION
        ami = _ami_banner_probe(self.pbx_ami_host, self.pbx_ami_port, self.timeout_seconds)
        return {
            "ok": bool(
                contract_valid
                and runtime.get("ok")
                and ami.get("reachable")
                and ami.get("banner_valid")
            ),
            "contract": contract,
            "pbx_ami": ami,
            "execution_owner": "voiceops",
            "fieldops_registers_sip": False,
            "fieldops_reads_credentials": False,
        }

    def request_owner_callback(
        self,
        *,
        correlation_id: str,
        reason: str,
        requested_by: str,
    ) -> Mapping[str, Any]:
        return self._json(
            "/v1/callbacks",
            method="POST",
            payload={
                "correlation_id": correlation_id,
                "reason": reason,
                "requested_by": requested_by,
            },
        )

    def receipt(self, correlation_id: str) -> Mapping[str, Any]:
        safe_id = quote(correlation_id, safe="-_.~")
        return self._json(f"/v1/receipts/{safe_id}")

    def _json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(dict(payload)).encode("utf-8") if payload is not None else None
        headers = {"User-Agent": "InnerOS-FieldOps/1", "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        request = Request(
            self.base_url.rstrip("/") + path,
            data=body,
            headers=headers,
            method=method,
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 private literal validated above
            decoded = json.loads(response.read(128 * 1024).decode("utf-8"))
        if not isinstance(decoded, dict):
            raise TelephonyReadConfigurationError("VoiceOps runtime response must be a JSON object")
        return decoded


@dataclass(frozen=True)
class LocalVoiceOpsTelephonyReadClient:
    """Legacy read-only client kept for deployment compatibility.

    New deployments should use :class:`LocalVoiceOpsRuntimeClient`. This adapter
    still understands the older health endpoint and performs the same independent
    AMI banner probe, so a staged rollout never creates a false outage.
    """

    voiceops_health_url: str
    pbx_ami_host: str
    pbx_ami_port: int = 7777
    timeout_seconds: float = 3.0

    def __post_init__(self) -> None:
        parsed = urlparse(self.voiceops_health_url)
        if parsed.scheme != "http" or not parsed.hostname:
            raise TelephonyReadConfigurationError("VoiceOps health URL must be an http URL")
        if not _private_or_loopback_literal(parsed.hostname):
            raise TelephonyReadConfigurationError("VoiceOps health URL must stay on private/loopback networking")
        if not _private_or_loopback_literal(self.pbx_ami_host):
            raise TelephonyReadConfigurationError("PBX AMI host must be a private/loopback literal")
        if not 1 <= int(self.pbx_ami_port) <= 65535:
            raise TelephonyReadConfigurationError("PBX AMI port must be between 1 and 65535")
        if self.timeout_seconds <= 0:
            raise TelephonyReadConfigurationError("timeout_seconds must be positive")

    def status(self) -> Mapping[str, Any]:
        voiceops = self._voiceops_health()
        ami = _ami_banner_probe(self.pbx_ami_host, self.pbx_ami_port, self.timeout_seconds)
        return {
            "ok": bool(voiceops.get("ok") and ami.get("reachable") and ami.get("banner_valid")),
            "voiceops": voiceops,
            "pbx_ami": ami,
            "execution_owner": "voiceops",
            "fieldops_registers_sip": False,
            "fieldops_reads_credentials": False,
        }

    def _voiceops_health(self) -> dict[str, Any]:
        req = Request(self.voiceops_health_url, headers={"User-Agent": "InnerOS-FieldOps/1"})
        with urlopen(req, timeout=self.timeout_seconds) as response:  # noqa: S310 private literal validated above
            payload = json.loads(response.read(64 * 1024).decode("utf-8"))
        if not isinstance(payload, dict):
            raise TelephonyReadConfigurationError("VoiceOps health response must be a JSON object")
        return {
            "ok": bool(payload.get("ok")),
            "service": str(payload.get("service") or ""),
            "live_voice_enabled": bool(payload.get("live_voice_enabled")),
            "credential_configured": bool(payload.get("credential_configured")),
            "guardian_voice_bridge_enabled": bool(payload.get("guardian_voice_bridge_enabled")),
        }


class TelephonyStatusObserver:
    ALLOWED_TARGET = "voiceops.ucm"

    def __init__(self, client: TelephonyReadClient, observer_id: str = "voiceops-telephony-health"):
        self.client = client
        self.observer_id = observer_id

    def observe(self, request: ObservationRequest) -> ObservationResult:
        target = str(request.target_ref or "").strip().lower()
        if request.observation_type != "telephony.read_status" or target != self.ALLOWED_TARGET:
            return ObservationResult(
                correlation_id=request.correlation_id,
                observer=self.observer_id,
                success=False,
                details={"reason": "target_not_allowlisted", "target_ref": target},
            )
        status = dict(self.client.status())
        contract = status.get("contract") if isinstance(status.get("contract"), Mapping) else None
        ami = status.get("pbx_ami") if isinstance(status.get("pbx_ami"), Mapping) else {}
        if contract is not None:
            runtime = contract.get("runtime") if isinstance(contract.get("runtime"), Mapping) else {}
            owner = contract.get("owner_endpoint") if isinstance(contract.get("owner_endpoint"), Mapping) else {}
            details = {
                "target_ref": target,
                "contract_version": contract.get("contract_version"),
                "contract_state": contract.get("state"),
                "truth_label": contract.get("truth_label"),
                "voiceops_ok": bool(runtime.get("ok")),
                "voiceops_service": runtime.get("service"),
                "voiceops_runtime_version": runtime.get("runtime_version"),
                "owner_extension": owner.get("extension"),
                "owner_registered": bool(owner.get("registered")),
                "owner_status": owner.get("status"),
                "owner_address_present": bool(owner.get("address")),
                "callback_ready": contract.get("state") == "READY",
                "owner_confirmed_e2e_calling": bool(contract.get("owner_confirmed_e2e_calling")),
                "autonomous_pstn_enabled": bool(runtime.get("autonomous_pstn_enabled")),
                "public_sip_rtp": bool(runtime.get("public_sip_rtp")),
                "pbx_ami_reachable": bool(ami.get("reachable")),
                "pbx_ami_banner_valid": bool(ami.get("banner_valid")),
                "pbx_banner_family": ami.get("banner_family"),
                "execution_owner": "voiceops",
                "fieldops_registers_sip": False,
                "fieldops_reads_credentials": False,
                "evidence_ref": f"evidence://telephony/status/{request.correlation_id}",
            }
        else:
            voiceops = status.get("voiceops") if isinstance(status.get("voiceops"), Mapping) else {}
            details = {
                "target_ref": target,
                "voiceops_ok": bool(voiceops.get("ok")),
                "voiceops_service": voiceops.get("service"),
                "live_voice_enabled": bool(voiceops.get("live_voice_enabled")),
                "provider_credential_configured": bool(voiceops.get("credential_configured")),
                "pbx_ami_reachable": bool(ami.get("reachable")),
                "pbx_ami_banner_valid": bool(ami.get("banner_valid")),
                "pbx_banner_family": ami.get("banner_family"),
                "execution_owner": "voiceops",
                "fieldops_registers_sip": False,
                "fieldops_reads_credentials": False,
                "evidence_ref": f"evidence://telephony/health/{request.correlation_id}",
            }
        return ObservationResult(
            correlation_id=request.correlation_id,
            observer=self.observer_id,
            success=bool(status.get("ok")),
            details=details,
        )


class TelephonyStatusVerifier:
    def __init__(self, verifier_id: str = "voiceops-pbx-independent-readback"):
        self.verifier_id = verifier_id

    def verify(self, request: ObservationRequest, result: ObservationResult) -> ObservationVerification:
        details = result.details
        ownership_ok = (
            details.get("execution_owner") == "voiceops"
            and details.get("fieldops_registers_sip") is False
            and details.get("fieldops_reads_credentials") is False
        )
        if details.get("contract_version"):
            provider_ok = bool(
                details.get("contract_version") == VOICEOPS_CONTRACT_VERSION
                and details.get("voiceops_ok")
                and details.get("autonomous_pstn_enabled") is False
                and details.get("public_sip_rtp") is False
            )
        else:
            provider_ok = bool(details.get("voiceops_ok") and details.get("live_voice_enabled"))
        pbx_ok = bool(details.get("pbx_ami_reachable") and details.get("pbx_ami_banner_valid"))
        passed = bool(result.success and ownership_ok and provider_ok and pbx_ok)
        observed = {
            "voiceops_service": details.get("voiceops_service"),
            "voiceops_ok": bool(details.get("voiceops_ok")),
            "pbx_ami_reachable": bool(details.get("pbx_ami_reachable")),
            "pbx_ami_banner_valid": bool(details.get("pbx_ami_banner_valid")),
            "execution_owner": "voiceops",
            "fieldops_registers_sip": False,
            "fieldops_reads_credentials": False,
        }
        for key in (
            "contract_version",
            "contract_state",
            "owner_extension",
            "owner_registered",
            "owner_status",
            "callback_ready",
            "owner_confirmed_e2e_calling",
            "autonomous_pstn_enabled",
            "public_sip_rtp",
        ):
            if key in details:
                observed[key] = details.get(key)
        return ObservationVerification(
            correlation_id=request.correlation_id,
            verifier=self.verifier_id,
            passed=passed,
            observed_state=observed,
        )


class VoiceOpsOwnerCallbackExecutor:
    """Request one approved callback to the owner-selected endpoint in VoiceOps."""

    def __init__(self, client: VoiceOpsCallbackClient, executor_id: str = "voiceops-owner-callback") -> None:
        self.client = client
        self.executor_id = executor_id

    def execute(self, request: ActionRequest) -> ExecutionResult:
        if request.action_type != "telephony.request_owner_callback" or request.target_ref != OWNER_CALLBACK_TARGET:
            return ExecutionResult(
                correlation_id=request.correlation_id,
                executor=self.executor_id,
                success=False,
                details={"reason": "target_not_allowlisted"},
            )
        if "target_extension" in request.parameters or "phone_number" in request.parameters:
            return ExecutionResult(
                correlation_id=request.correlation_id,
                executor=self.executor_id,
                success=False,
                details={"reason": "destination_override_forbidden"},
            )
        reason = " ".join(str(request.parameters.get("reason") or "FieldOps requiere tu aprobación o atención.").split())[:600]
        receipt = dict(
            self.client.request_owner_callback(
                correlation_id=request.correlation_id,
                reason=reason,
                requested_by="fieldops",
            )
        )
        result = receipt.get("result") if isinstance(receipt.get("result"), Mapping) else {}
        status = str(result.get("status") or "")
        autonomous_pstn = bool(receipt.get("autonomous_pstn_enabled"))
        success = status in {"dispatched", "duplicate"} and not autonomous_pstn
        return ExecutionResult(
            correlation_id=request.correlation_id,
            executor=self.executor_id,
            success=success,
            details={
                "callback_status": status,
                "call_id": result.get("call_id"),
                "target_extension": result.get("target_extension"),
                "reason": result.get("reason"),
                "autonomous_pstn_enabled": autonomous_pstn,
                "evidence_ref": f"evidence://voiceops/call/{request.correlation_id}",
            },
        )


class VoiceOpsOwnerCallbackVerifier:
    """Independently read back VoiceOps receipt and current owner allowlist."""

    def __init__(self, client: VoiceOpsCallbackClient, verifier_id: str = "voiceops-call-receipt-readback") -> None:
        self.client = client
        self.verifier_id = verifier_id

    def verify(self, request: ActionRequest, execution: ExecutionResult) -> VerificationResult:
        try:
            receipt = dict(self.client.receipt(request.correlation_id))
            status = dict(self.client.status())
        except Exception as exc:
            return VerificationResult(
                correlation_id=request.correlation_id,
                verifier=self.verifier_id,
                passed=False,
                observed_state={"reason": f"voiceops_readback_failed:{type(exc).__name__}"},
            )
        result = receipt.get("result") if isinstance(receipt.get("result"), Mapping) else {}
        contract = status.get("contract") if isinstance(status.get("contract"), Mapping) else {}
        owner_rows = contract.get("owner_endpoints") if isinstance(contract.get("owner_endpoints"), list) else []
        owner_extensions = {
            str(row.get("extension"))
            for row in owner_rows
            if isinstance(row, Mapping) and row.get("extension")
        }
        call_id = result.get("call_id")
        target = str(result.get("target_extension") or "")
        callback_status = str(result.get("status") or "")
        autonomous_pstn = bool(receipt.get("autonomous_pstn_enabled"))
        passed = bool(
            execution.success
            and callback_status in {"dispatched", "duplicate"}
            and call_id
            and call_id == execution.details.get("call_id")
            and target in owner_extensions
            and not autonomous_pstn
        )
        return VerificationResult(
            correlation_id=request.correlation_id,
            verifier=self.verifier_id,
            passed=passed,
            observed_state={
                "callback_status": callback_status,
                "call_id": call_id,
                "target_extension": target,
                "owner_allowlisted": target in owner_extensions,
                "autonomous_pstn_enabled": autonomous_pstn,
                "contract_version": contract.get("contract_version"),
            },
        )
