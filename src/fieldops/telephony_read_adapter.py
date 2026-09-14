"""Read-only VoiceOps/PBX health adapter for FieldOps.

This module deliberately does not register a SIP account, originate calls, read
SIP credentials, or mutate the PBX. VoiceOps owns the telephony execution plane.
FieldOps only checks the existing VoiceOps health surface and independently
confirms that the private PBX AMI control plane is reachable.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import socket
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .observations import ObservationRequest, ObservationResult, ObservationVerification


class TelephonyReadConfigurationError(RuntimeError):
    pass


class TelephonyReadClient(Protocol):
    def status(self) -> Mapping[str, Any]: ...


def _private_or_loopback_literal(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(ip.is_private or ip.is_loopback)


@dataclass(frozen=True)
class LocalVoiceOpsTelephonyReadClient:
    """Query the existing VoiceOps service and independently probe PBX AMI.

    The AMI probe reads only the initial Asterisk banner. It never authenticates
    and therefore needs no PBX secret. The VoiceOps HTTP endpoint must remain on
    loopback/private networking.
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
        ami = self._ami_banner_probe()
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
        with urlopen(req, timeout=self.timeout_seconds) as response:
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

    def _ami_banner_probe(self) -> dict[str, Any]:
        try:
            with socket.create_connection(
                (self.pbx_ami_host, int(self.pbx_ami_port)), timeout=self.timeout_seconds
            ) as conn:
                conn.settimeout(self.timeout_seconds)
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
        voiceops = status.get("voiceops") if isinstance(status.get("voiceops"), Mapping) else {}
        ami = status.get("pbx_ami") if isinstance(status.get("pbx_ami"), Mapping) else {}
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
        provider_ok = bool(details.get("voiceops_ok") and details.get("live_voice_enabled"))
        pbx_ok = bool(details.get("pbx_ami_reachable") and details.get("pbx_ami_banner_valid"))
        passed = bool(result.success and ownership_ok and provider_ok and pbx_ok)
        return ObservationVerification(
            correlation_id=request.correlation_id,
            verifier=self.verifier_id,
            passed=passed,
            observed_state={
                "voiceops_service": details.get("voiceops_service"),
                "voiceops_ok": bool(details.get("voiceops_ok")),
                "live_voice_enabled": bool(details.get("live_voice_enabled")),
                "pbx_ami_reachable": bool(details.get("pbx_ami_reachable")),
                "pbx_ami_banner_valid": bool(details.get("pbx_ami_banner_valid")),
                "execution_owner": "voiceops",
                "fieldops_registers_sip": False,
                "fieldops_reads_credentials": False,
            },
        )
