"""Real read-only adapters for FieldOps observations.

The adapters intentionally reuse existing InnerOS surfaces instead of creating
parallel device clients:
- solar status comes from the canonical Home Assistant bridge populated by the
  PI30/Xmart reader;
- camera and Wi-Fi reads come from a tiny read-only edge sidecar on the AMD node,
  where Physical Guardian and the dedicated Wi-Fi radio already live.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
from typing import Any, Mapping, Protocol
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .ha_adapter import HomeAssistantClient
from .observations import (
    ObservationRequest,
    ObservationResult,
    ObservationVerification,
)


class ReadAdapterConfigurationError(RuntimeError):
    pass


class EdgeReadClient(Protocol):
    def camera_snapshot(self, channel: int) -> Mapping[str, Any]: ...
    def wifi_scan(self) -> Mapping[str, Any]: ...


def _entity_payload(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    if not raw.get("ok"):
        return {}
    entity = raw.get("entity")
    return entity if isinstance(entity, Mapping) else {}


class SolarStatusObserver:
    STATUS_ENTITY = "sensor.inneros_pi01_solar_status"
    BATTERY_ENTITY = "sensor.inneros_pi01_solar_battery_voltage"
    POWER_ENTITY = "sensor.inneros_pi01_solar_output_power"
    GRID_ENTITY = "sensor.inneros_pi01_solar_grid_voltage"
    MODE_ENTITY = "sensor.inneros_pi01_solar_mode"
    ALLOWED_TARGETS = {"solar.pi01", "inneros-pi01-solar"}

    def __init__(self, client: HomeAssistantClient, observer_id: str = "inneros-ha-solar-telemetry"):
        self.client = client
        self.observer_id = observer_id

    def observe(self, request: ObservationRequest) -> ObservationResult:
        target = str(request.target_ref or "").strip().lower()
        if request.observation_type != "energy.read_status" or target not in self.ALLOWED_TARGETS:
            return ObservationResult(
                correlation_id=request.correlation_id,
                observer=self.observer_id,
                success=False,
                details={"reason": "target_not_allowlisted", "target_ref": target},
            )
        status = _entity_payload(dict(self.client.get_state(self.STATUS_ENTITY)))
        battery = _entity_payload(dict(self.client.get_state(self.BATTERY_ENTITY)))
        power = _entity_payload(dict(self.client.get_state(self.POWER_ENTITY)))
        grid = _entity_payload(dict(self.client.get_state(self.GRID_ENTITY)))
        mode = _entity_payload(dict(self.client.get_state(self.MODE_ENTITY)))
        attrs = status.get("attributes") if isinstance(status.get("attributes"), Mapping) else {}
        telemetry = attrs.get("telemetry") if isinstance(attrs.get("telemetry"), Mapping) else {}
        mode_inferred = attrs.get("mode_inferred") if isinstance(attrs.get("mode_inferred"), Mapping) else {}
        details = {
            "target_ref": target,
            "status": status.get("state"),
            "battery_voltage_v": battery.get("state"),
            "output_power_w": power.get("state"),
            "grid_voltage_v": grid.get("state"),
            "mode": mode.get("state"),
            "battery_capacity_percent": telemetry.get("battery_capacity_percent"),
            "output_load_percent": telemetry.get("output_load_percent"),
            "temperature_c": telemetry.get("inverter_heat_sink_temperature_c"),
            "pv_charging_power_w": telemetry.get("pv_charging_power_w"),
            "grid_present": mode_inferred.get("grid_present"),
            "output_present": mode_inferred.get("output_present"),
            "safety": attrs.get("safety"),
            "device_model": attrs.get("device_model"),
            "protocol": attrs.get("protocol"),
            "updated_at": attrs.get("updated_at"),
            "evidence_ref": f"evidence://energy/ha/{request.correlation_id}",
        }
        success = bool(status and str(status.get("state")).lower() == "online")
        return ObservationResult(
            correlation_id=request.correlation_id,
            observer=self.observer_id,
            success=success,
            details=details,
        )


class SolarStatusVerifier:
    def __init__(self, verifier_id: str = "solar-telemetry-consistency"):
        self.verifier_id = verifier_id

    def verify(self, request: ObservationRequest, result: ObservationResult) -> ObservationVerification:
        details = result.details
        status_ok = str(details.get("status") or "").lower() == "online"
        safety_ok = details.get("safety") == "read_only_queries_only"
        telemetry_ok = all(
            details.get(key) not in (None, "")
            for key in ("battery_voltage_v", "output_power_w", "grid_voltage_v", "mode")
        )
        passed = bool(result.success and status_ok and safety_ok and telemetry_ok)
        return ObservationVerification(
            correlation_id=request.correlation_id,
            verifier=self.verifier_id,
            passed=passed,
            observed_state={
                "status": details.get("status"),
                "mode": details.get("mode"),
                "battery_voltage_v": details.get("battery_voltage_v"),
                "output_power_w": details.get("output_power_w"),
                "grid_voltage_v": details.get("grid_voltage_v"),
                "read_only": safety_ok,
                "telemetry_complete": telemetry_ok,
            },
        )


@dataclass(frozen=True)
class RemoteReadOpsHTTPClient:
    base_url: str
    timeout_seconds: float = 6.0

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ReadAdapterConfigurationError("FIELDOPS_READOPS_EDGE_URL must be an http URL")
        host = parsed.hostname.lower()
        if host == "localhost":
            return
        try:
            ip = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ReadAdapterConfigurationError("read-ops edge URL must use a literal private/loopback IP") from exc
        if not (ip.is_private or ip.is_loopback):
            raise ReadAdapterConfigurationError("read-ops edge URL must stay on private/loopback networking")

    def _get(self, path: str, query: Mapping[str, object] | None = None) -> Mapping[str, Any]:
        suffix = path
        if query:
            suffix += "?" + urlencode({key: str(value) for key, value in query.items()})
        req = Request(self.base_url.rstrip("/") + suffix, headers={"User-Agent": "InnerOS-FieldOps/1"})
        with urlopen(req, timeout=self.timeout_seconds) as response:
            body = response.read(256 * 1024)
        decoded = json.loads(body.decode("utf-8"))
        if not isinstance(decoded, Mapping):
            raise ReadAdapterConfigurationError("edge read response must be a JSON object")
        return decoded

    def camera_snapshot(self, channel: int) -> Mapping[str, Any]:
        return self._get("/camera/snapshot", {"channel": channel})

    def wifi_scan(self) -> Mapping[str, Any]:
        return self._get("/network/scan")


class CameraEvidenceObserver:
    TARGETS = {"camera.dahua.ch2": 2, "camera.dahua.ch3": 3}

    def __init__(self, client: EdgeReadClient, observer_id: str = "physical-guardian-snapshot"):
        self.client = client
        self.observer_id = observer_id

    def observe(self, request: ObservationRequest) -> ObservationResult:
        target = str(request.target_ref or "").strip().lower()
        channel = self.TARGETS.get(target)
        if request.observation_type != "camera.capture_evidence" or channel is None:
            return ObservationResult(
                correlation_id=request.correlation_id,
                observer=self.observer_id,
                success=False,
                details={"reason": "target_not_allowlisted", "target_ref": target},
            )
        result = dict(self.client.camera_snapshot(channel))
        details = {
            "target_ref": target,
            "channel": channel,
            "jpeg_valid": bool(result.get("jpeg_valid")),
            "bytes": result.get("bytes"),
            "sha256": result.get("sha256"),
            "captured_at": result.get("captured_at"),
            "guardian_ok": bool(result.get("guardian_ok")),
            "image_returned_to_fieldops": False,
            "credentials_exposed": False,
        }
        if details["sha256"]:
            details["evidence_ref"] = f"evidence://camera/sha256/{details['sha256']}"
        return ObservationResult(
            correlation_id=request.correlation_id,
            observer=self.observer_id,
            success=bool(result.get("ok")),
            details=details,
        )


class CameraEvidenceVerifier:
    def __init__(self, verifier_id: str = "jpeg-evidence-verifier"):
        self.verifier_id = verifier_id

    def verify(self, request: ObservationRequest, result: ObservationResult) -> ObservationVerification:
        details = result.details
        digest = str(details.get("sha256") or "")
        bytes_count = int(details.get("bytes") or 0)
        passed = bool(
            result.success
            and details.get("guardian_ok")
            and details.get("jpeg_valid")
            and bytes_count > 256
            and len(digest) == 64
        )
        return ObservationVerification(
            correlation_id=request.correlation_id,
            verifier=self.verifier_id,
            passed=passed,
            observed_state={
                "channel": details.get("channel"),
                "jpeg_valid": bool(details.get("jpeg_valid")),
                "bytes": bytes_count,
                "sha256": digest,
                "captured_at": details.get("captured_at"),
                "image_returned_to_fieldops": False,
            },
        )


class NetworkScanObserver:
    ALLOWED_TARGET = "wifi.amd-dedicated"

    def __init__(self, client: EdgeReadClient, observer_id: str = "inneros-peer-wifi-scan"):
        self.client = client
        self.observer_id = observer_id

    def observe(self, request: ObservationRequest) -> ObservationResult:
        target = str(request.target_ref or "").strip().lower()
        if request.observation_type != "network.scan_wifi" or target != self.ALLOWED_TARGET:
            return ObservationResult(
                correlation_id=request.correlation_id,
                observer=self.observer_id,
                success=False,
                details={"reason": "target_not_allowlisted", "target_ref": target},
            )
        result = dict(self.client.wifi_scan())
        details = {
            "target_ref": target,
            "interface": result.get("interface"),
            "networks": result.get("networks") if isinstance(result.get("networks"), list) else [],
            "route_before": result.get("route_before"),
            "route_after": result.get("route_after"),
            "ethernet_route_intact": bool(result.get("ethernet_route_intact")),
            "configuration_changed": False,
            "evidence_ref": f"evidence://network/rf-scan/{request.correlation_id}",
        }
        return ObservationResult(
            correlation_id=request.correlation_id,
            observer=self.observer_id,
            success=bool(result.get("ok")),
            details=details,
        )


class NetworkScanVerifier:
    def __init__(self, verifier_id: str = "ethernet-route-readback"):
        self.verifier_id = verifier_id

    def verify(self, request: ObservationRequest, result: ObservationResult) -> ObservationVerification:
        details = result.details
        networks = details.get("networks") if isinstance(details.get("networks"), list) else []
        route_ok = bool(details.get("ethernet_route_intact"))
        interface = str(details.get("interface") or "")
        passed = bool(result.success and route_ok and interface.startswith("wl") and networks)
        return ObservationVerification(
            correlation_id=request.correlation_id,
            verifier=self.verifier_id,
            passed=passed,
            observed_state={
                "interface": interface,
                "network_count": len(networks),
                "ethernet_route_intact": route_ok,
                "route_before": details.get("route_before"),
                "route_after": details.get("route_after"),
                "configuration_changed": False,
            },
        )
