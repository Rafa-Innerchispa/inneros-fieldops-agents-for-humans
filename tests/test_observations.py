from src.fieldops.observations import GovernedObservationRuntime, ObservationRequest
from src.fieldops.read_adapters import (
    CameraEvidenceObserver,
    CameraEvidenceVerifier,
    NetworkScanObserver,
    NetworkScanVerifier,
    SolarStatusObserver,
    SolarStatusVerifier,
)


class FakeSolarHA:
    def configured(self):
        return True

    def get_state(self, entity_id):
        states = {
            "sensor.inneros_pi01_solar_status": {
                "state": "online",
                "attributes": {
                    "safety": "read_only_queries_only",
                    "device_model": "Xmart XSI-BB-120-3K-24-MPP",
                    "protocol": "PI30",
                    "updated_at": "2026-09-14T06:25:06+00:00",
                    "telemetry": {
                        "battery_capacity_percent": 100,
                        "output_load_percent": 21,
                        "inverter_heat_sink_temperature_c": 39,
                        "pv_charging_power_w": 0,
                    },
                    "mode_inferred": {"grid_present": True, "output_present": True},
                },
            },
            "sensor.inneros_pi01_solar_battery_voltage": {"state": "28.8", "attributes": {}},
            "sensor.inneros_pi01_solar_output_power": {"state": "534", "attributes": {}},
            "sensor.inneros_pi01_solar_grid_voltage": {"state": "125.4", "attributes": {}},
            "sensor.inneros_pi01_solar_mode": {"state": "utility_present_backup_float", "attributes": {}},
        }
        entity = states.get(entity_id)
        return {"ok": bool(entity), "entity": entity} if entity else {"ok": False}

    def call_service(self, *args, **kwargs):
        raise AssertionError("read-only solar observation must never call a HA service")


class FakeEdge:
    def camera_snapshot(self, channel):
        return {
            "ok": True,
            "guardian_ok": True,
            "channel": channel,
            "jpeg_valid": True,
            "bytes": 42000,
            "sha256": "a" * 64,
            "captured_at": "2026-09-14T06:30:00+00:00",
        }

    def wifi_scan(self):
        return {
            "ok": True,
            "interface": "wlx3c64cf8a0de9",
            "networks": [
                {"ssid": "RafaHome5G", "signal": 80, "channel": 149, "security": "WPA2", "in_use": False}
            ],
            "route_before": {"dev": "enp3s0"},
            "route_after": {"dev": "enp3s0"},
            "ethernet_route_intact": True,
        }


def test_solar_observation_is_read_only_verified_and_receipted():
    runtime = GovernedObservationRuntime()
    runtime.register(
        "energy.read_status",
        observer=SolarStatusObserver(FakeSolarHA()),
        verifier=SolarStatusVerifier(),
    )
    receipt = runtime.observe(
        ObservationRequest(
            correlation_id="solar-001",
            observation_type="energy.read_status",
            target_ref="solar.pi01",
        )
    )
    assert receipt.requires_approval is False
    assert receipt.quality_gate == "passed"
    assert receipt.verification_passed is True
    assert receipt.observed_state["mode"] == "utility_present_backup_float"
    assert receipt.observed_state["read_only"] is True


def test_camera_snapshot_receipt_contains_hash_not_image():
    runtime = GovernedObservationRuntime()
    runtime.register(
        "camera.capture_evidence",
        observer=CameraEvidenceObserver(FakeEdge()),
        verifier=CameraEvidenceVerifier(),
    )
    receipt = runtime.observe(
        ObservationRequest(
            correlation_id="camera-001",
            observation_type="camera.capture_evidence",
            target_ref="camera.dahua.ch2",
        )
    )
    assert receipt.quality_gate == "passed"
    assert receipt.observed_state["jpeg_valid"] is True
    assert receipt.observed_state["image_returned_to_fieldops"] is False
    assert receipt.evidence_refs == ("evidence://camera/sha256/" + "a" * 64,)


def test_wifi_scan_requires_ethernet_route_to_remain_intact():
    runtime = GovernedObservationRuntime()
    runtime.register(
        "network.scan_wifi",
        observer=NetworkScanObserver(FakeEdge()),
        verifier=NetworkScanVerifier(),
    )
    receipt = runtime.observe(
        ObservationRequest(
            correlation_id="wifi-001",
            observation_type="network.scan_wifi",
            target_ref="wifi.amd-dedicated",
        )
    )
    assert receipt.quality_gate == "passed"
    assert receipt.observed_state["ethernet_route_intact"] is True
    assert receipt.observed_state["network_count"] == 1
    assert receipt.observed_state["configuration_changed"] is False


def test_wifi_scan_fails_closed_if_route_changes():
    class UnsafeEdge(FakeEdge):
        def wifi_scan(self):
            result = dict(super().wifi_scan())
            result["route_after"] = {"dev": "wlx3c64cf8a0de9"}
            result["ethernet_route_intact"] = False
            return result

    runtime = GovernedObservationRuntime()
    runtime.register(
        "network.scan_wifi",
        observer=NetworkScanObserver(UnsafeEdge()),
        verifier=NetworkScanVerifier(),
    )
    receipt = runtime.observe(
        ObservationRequest(
            correlation_id="wifi-unsafe",
            observation_type="network.scan_wifi",
            target_ref="wifi.amd-dedicated",
        )
    )
    assert receipt.quality_gate == "failed"
    assert receipt.verification_passed is False
