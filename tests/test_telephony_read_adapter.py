from __future__ import annotations

import pytest

from src.fieldops.observations import ObservationRequest
from src.fieldops.telephony_read_adapter import (
    LocalVoiceOpsTelephonyReadClient,
    TelephonyReadConfigurationError,
    TelephonyStatusObserver,
    TelephonyStatusVerifier,
)


class FakeTelephonyReadClient:
    def __init__(self, *, provider_ok: bool = True, pbx_ok: bool = True):
        self.provider_ok = provider_ok
        self.pbx_ok = pbx_ok

    def status(self):
        return {
            "ok": self.provider_ok and self.pbx_ok,
            "voiceops": {
                "ok": self.provider_ok,
                "service": "inneros-voiceops",
                "live_voice_enabled": self.provider_ok,
                "credential_configured": True,
            },
            "pbx_ami": {
                "reachable": self.pbx_ok,
                "banner_valid": self.pbx_ok,
                "banner_family": "Asterisk Call Manager" if self.pbx_ok else "unexpected",
            },
            "execution_owner": "voiceops",
            "fieldops_registers_sip": False,
            "fieldops_reads_credentials": False,
        }


def request(target: str = "voiceops.ucm") -> ObservationRequest:
    return ObservationRequest(
        correlation_id="telephony-read-001",
        observation_type="telephony.read_status",
        target_ref=target,
    )


def test_telephony_status_passes_only_when_voiceops_and_pbx_are_healthy():
    observer = TelephonyStatusObserver(FakeTelephonyReadClient())
    verifier = TelephonyStatusVerifier()
    result = observer.observe(request())
    verification = verifier.verify(request(), result)
    assert result.success is True
    assert verification.passed is True
    assert verification.observed_state["voiceops_ok"] is True
    assert verification.observed_state["pbx_ami_reachable"] is True
    assert verification.observed_state["execution_owner"] == "voiceops"
    assert verification.observed_state["fieldops_registers_sip"] is False
    assert verification.observed_state["fieldops_reads_credentials"] is False


def test_telephony_status_fails_closed_when_pbx_is_unreachable():
    observer = TelephonyStatusObserver(FakeTelephonyReadClient(pbx_ok=False))
    verifier = TelephonyStatusVerifier()
    result = observer.observe(request())
    verification = verifier.verify(request(), result)
    assert result.success is False
    assert verification.passed is False


def test_telephony_observer_rejects_non_allowlisted_target():
    observer = TelephonyStatusObserver(FakeTelephonyReadClient())
    result = observer.observe(request("voiceops.other"))
    assert result.success is False
    assert result.details["reason"] == "target_not_allowlisted"


@pytest.mark.parametrize(
    "health_url,ami_host",
    [
        ("https://127.0.0.1:8791/healthz", "192.168.1.6"),
        ("http://example.com/healthz", "192.168.1.6"),
        ("http://127.0.0.1:8791/healthz", "8.8.8.8"),
    ],
)
def test_telephony_client_rejects_non_private_or_non_http_configuration(health_url, ami_host):
    with pytest.raises(TelephonyReadConfigurationError):
        LocalVoiceOpsTelephonyReadClient(
            voiceops_health_url=health_url,
            pbx_ami_host=ami_host,
        )
