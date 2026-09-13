"""Read-only InnerOS context and operations telemetry adapters for FieldOps demos.

The adapter deliberately avoids mutation. It can read a small allowlisted set of
Home Assistant entities when local credentials are supplied through environment
variables. If live Home Assistant access is unavailable, it falls back to
sanitized, committed evidence captured from the real InnerOS installation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import socket
from typing import Mapping
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_COORDINATION_ROOTS = (
    "/home/rlopez/data/ai_coordination/HUB",
    "/home/rlopez/inneros/inneros_core/platform",
)

SOLAR_ENTITIES = {
    "status": "sensor.inneros_pi01_solar_status",
    "output_power_w": "sensor.inneros_pi01_solar_output_power",
    "battery_voltage_v": "sensor.inneros_pi01_solar_battery_voltage",
    "battery_capacity_percent": "sensor.inneros_pi01_solar_battery_capacity",
    "load_percent": "sensor.inneros_pi01_solar_load",
    "pv_voltage_v": "sensor.inneros_pi01_solar_pv_voltage",
    "temperature_c": "sensor.inneros_pi01_solar_temperature",
    "grid_voltage_v": "sensor.inneros_pi01_solar_grid_voltage",
    "mode": "sensor.inneros_pi01_solar_mode",
}

FACILITY_ENTITIES = {
    "wifi_24_clients_primary": "sensor.rafahome2_4g_clients",
    "wifi_24_clients_secondary": "sensor.rafah2_4ghz_clients",
    "wifi_5_clients": "sensor.rafahome5g_clients",
    "u7_living_state": "sensor.u7_lite_state",
    "u7_living_memory_percent": "sensor.u7_living_memory_utilization",
    "alarm_intelbras_presence": "device_tracker.alarma_interbras",
}


def _split_roots(value: str) -> list[str]:
    return [item for item in (part.strip() for part in value.split(":")) if item]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_allowed_local_url(value: str) -> bool:
    """Only permit loopback/private/local Home Assistant endpoints."""

    try:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local") or host.endswith(".localdomain"):
            return True
        try:
            return ipaddress.ip_address(host).is_private
        except ValueError:
            return False
    except Exception:
        return False


def _coerce_state(value: object) -> object:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _ha_entity(base_url: str, token: str, entity_id: str, timeout: float = 1.5) -> dict[str, object] | None:
    request = Request(
        f"{base_url.rstrip('/')}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is restricted to private/local hosts
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return None
    return {
        "entity_id": entity_id,
        "state": _coerce_state(body.get("state")),
        "last_updated": body.get("last_updated"),
    }


def _live_homeassistant_snapshot(env: Mapping[str, str]) -> dict[str, object] | None:
    base_url = (env.get("FIELDOPS_HA_URL") or env.get("HOME_ASSISTANT_URL") or "").strip()
    token = (env.get("FIELDOPS_HA_TOKEN") or env.get("HOME_ASSISTANT_TOKEN") or "").strip()
    if not base_url or not token or not _is_allowed_local_url(base_url):
        return None

    solar_raw = {key: _ha_entity(base_url, token, entity_id) for key, entity_id in SOLAR_ENTITIES.items()}
    facility_raw = {key: _ha_entity(base_url, token, entity_id) for key, entity_id in FACILITY_ENTITIES.items()}
    if not any(solar_raw.values()) and not any(facility_raw.values()):
        return None

    solar = {
        key: (row or {}).get("state")
        for key, row in solar_raw.items()
    }
    facility = {
        key: (row or {}).get("state")
        for key, row in facility_raw.items()
    }
    clients_24 = sum(
        int(value or 0)
        for key, value in facility.items()
        if key in {"wifi_24_clients_primary", "wifi_24_clients_secondary"} and isinstance(value, (int, float))
    )
    facility["wifi_24_clients_total"] = clients_24

    timestamps = [
        str(row.get("last_updated"))
        for row in [*solar_raw.values(), *facility_raw.values()]
        if isinstance(row, dict) and row.get("last_updated")
    ]
    return {
        "source": "home_assistant_local",
        "evidence_mode": "LIVE REAL",
        "live": True,
        "timestamp": max(timestamps) if timestamps else datetime.now(timezone.utc).isoformat(),
        "energy": solar,
        "facilities": facility,
    }


def _captured_operations_snapshot() -> dict[str, object]:
    root = _repo_root()
    solar_path = root / "docs" / "evidence" / "inneros_pi01_xmart_live_telemetry_20260913.json"
    wifi_path = root / "docs" / "evidence" / "unifi_rf_snapshot_20260913.json"

    energy: dict[str, object] = {}
    facilities: dict[str, object] = {}
    timestamps: list[str] = []

    if solar_path.exists():
        try:
            solar = json.loads(solar_path.read_text(encoding="utf-8"))
            sample = solar.get("sample_telemetry") or {}
            energy = {
                "status": ((solar.get("home_assistant") or {}).get("status_entity") or {}).get("state", "online"),
                "output_power_w": sample.get("ac_output_active_power_w"),
                "battery_voltage_v": sample.get("battery_voltage_v"),
                "battery_capacity_percent": sample.get("battery_capacity_percent"),
                "load_percent": sample.get("output_load_percent"),
                "pv_voltage_v": sample.get("pv_input_voltage_v"),
                "pv_charging_power_w": sample.get("pv_charging_power_w"),
                "temperature_c": sample.get("inverter_heat_sink_temperature_c"),
                "grid_voltage_v": sample.get("grid_voltage_v"),
                "protocol": solar.get("protocol"),
            }
            if solar.get("timestamp_utc"):
                timestamps.append(str(solar["timestamp_utc"]))
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    if wifi_path.exists():
        try:
            wifi = json.loads(wifi_path.read_text(encoding="utf-8"))
            facilities = wifi.get("facilities") or {}
            if wifi.get("timestamp_utc"):
                timestamps.append(str(wifi["timestamp_utc"]))
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    return {
        "source": "committed_real_evidence",
        "evidence_mode": "CAPTURED REAL",
        "live": False,
        "timestamp": max(timestamps) if timestamps else None,
        "energy": energy,
        "facilities": facilities,
    }


def read_operations_snapshot(source: Mapping[str, str] | None = None) -> dict[str, object]:
    """Return live local telemetry when configured, otherwise real captured evidence."""

    env = source or os.environ
    return _live_homeassistant_snapshot(env) or _captured_operations_snapshot()


def read_inneros_context_snapshot(
    source: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return non-secret, read-only runtime context for evidence."""

    env = source or os.environ
    roots = _split_roots(env.get("FIELDOPS_INNEROS_COORDINATION_ROOTS", ""))
    if not roots:
        roots = list(DEFAULT_COORDINATION_ROOTS)
    live_status_path = env.get("FIELDOPS_INNEROS_STATUS_PATH", "").strip()
    live_status_preview = None
    live_status_exists = False
    if live_status_path:
        path = Path(live_status_path)
        live_status_exists = path.exists()
        if live_status_exists and path.is_file():
            live_status_preview = path.read_text(encoding="utf-8", errors="replace")[:1200]

    operations = read_operations_snapshot(env)
    return {
        "adapter": "inneros-readonly-v2",
        "arbitrary_shell": False,
        "arbitrary_network": False,
        "governed_action_boundary": "fieldops.workflow.run_action",
        "hostname": socket.gethostname(),
        "mcp_profile": env.get("FIELDOPS_INNEROS_MCP_PROFILE", "not-configured"),
        "mcp_url_configured": bool(env.get("FIELDOPS_INNEROS_MCP_URL")),
        "mutation_allowed": False,
        "operations": operations,
        "read_only": True,
        "roots": [
            {
                "path": root,
                "exists": Path(root).exists(),
            }
            for root in roots
        ],
        "status_path": live_status_path or None,
        "status_path_exists": live_status_exists,
        "status_preview": live_status_preview,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
