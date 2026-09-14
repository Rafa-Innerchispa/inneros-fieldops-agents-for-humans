#!/usr/bin/env python3
"""Read-only edge sidecar for FieldOps.

Runs on the AMD edge node beside Physical Guardian and the dedicated Wi-Fi radio.
It exposes sanitized observations plus an ephemeral JPEG preview to the explicitly
allowlisted FieldOps primary node. It has no mutation endpoints and never stores
camera images.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import subprocess
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


MAX_JSON_BYTES = 256 * 1024
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
ALLOWED_CHANNELS = {2, 3}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_nmcli(line: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line.rstrip("\n"):
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def _run(argv: list[str], timeout: float = 8.0) -> str:
    completed = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"command_failed:{argv[0]}:{completed.returncode}")
    return completed.stdout


def _default_route() -> dict[str, object]:
    raw = _run(["ip", "route", "show", "default"], timeout=3.0).strip()
    first = raw.splitlines()[0] if raw else ""
    match = re.search(r"\bdev\s+(\S+)", first)
    return {"raw": first, "dev": match.group(1) if match else None}


def _scan_wifi(interface: str) -> dict[str, object]:
    before = _default_route()
    if before.get("dev") == interface:
        raise RuntimeError("dedicated_wifi_is_default_route")
    raw = _run(
        [
            "nmcli",
            "-t",
            "-f",
            "SSID,SECURITY,SIGNAL,CHAN,IN-USE",
            "device",
            "wifi",
            "list",
            "ifname",
            interface,
            "--rescan",
            "yes",
        ],
        timeout=12.0,
    )
    networks: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for line in raw.splitlines():
        fields = _split_nmcli(line)
        if len(fields) < 5:
            continue
        ssid, security, signal, channel, in_use = fields[:5]
        ssid = ssid.strip()
        if not ssid:
            continue
        key = (ssid, channel.strip(), signal.strip())
        if key in seen:
            continue
        seen.add(key)
        networks.append(
            {
                "ssid": ssid[:64],
                "security": security.strip()[:80],
                "signal": int(signal) if signal.strip().isdigit() else None,
                "channel": int(channel) if channel.strip().isdigit() else None,
                "in_use": in_use.strip() == "*",
            }
        )
    networks.sort(key=lambda item: int(item.get("signal") or 0), reverse=True)
    after = _default_route()
    route_ok = bool(
        before.get("dev")
        and before.get("dev") == after.get("dev")
        and after.get("dev") != interface
    )
    return {
        "ok": bool(networks) and route_ok,
        "interface": interface,
        "networks": networks[:20],
        "route_before": before,
        "route_after": after,
        "ethernet_route_intact": route_ok,
        "configuration_changed": False,
        "observed_at": utc_now(),
    }


def _guardian_json(base_url: str, path: str) -> dict[str, Any]:
    req = Request(base_url.rstrip("/") + path, headers={"User-Agent": "InnerOS-FieldOps-Edge/1"})
    with urlopen(req, timeout=4.0) as response:
        body = response.read(MAX_JSON_BYTES)
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("guardian_json_invalid")
    return payload


def _camera_jpeg(base_url: str, channel: int) -> tuple[bytes, str]:
    """Fetch an existing Physical Guardian snapshot without changing Guardian."""
    if channel not in ALLOWED_CHANNELS:
        raise ValueError("channel_not_allowlisted")
    status = _guardian_json(base_url, "/api/camera/status")
    guardian_ok = bool(status.get("ok")) and channel in set(status.get("channels") or [])
    if not guardian_ok:
        raise RuntimeError("guardian_camera_unavailable")
    req = Request(
        base_url.rstrip("/") + f"/api/camera/snapshot?channel={channel}",
        headers={"User-Agent": "InnerOS-FieldOps-Edge/1"},
    )
    with urlopen(req, timeout=5.0) as response:
        payload = response.read(MAX_SNAPSHOT_BYTES + 1)
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise RuntimeError("snapshot_too_large")
    jpeg_valid = payload.startswith(b"\xff\xd8") and payload.endswith(b"\xff\xd9")
    if not jpeg_valid or len(payload) <= 256:
        raise RuntimeError("snapshot_invalid_jpeg")
    return payload, utc_now()


def _camera_snapshot(base_url: str, channel: int) -> dict[str, object]:
    try:
        payload, captured_at = _camera_jpeg(base_url, channel)
    except RuntimeError as exc:
        if str(exc) != "guardian_camera_unavailable":
            raise
        return {
            "ok": False,
            "guardian_ok": False,
            "channel": channel,
            "jpeg_valid": False,
            "bytes": 0,
            "sha256": None,
            "captured_at": utc_now(),
        }
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "ok": True,
        "guardian_ok": True,
        "channel": channel,
        "jpeg_valid": True,
        "bytes": len(payload),
        "sha256": digest,
        "captured_at": captured_at,
        "image_returned": False,
        "credentials_exposed": False,
    }


class ReadOpsServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], *, allowed_clients: set[str], wifi_interface: str, guardian_url: str):
        self.allowed_clients = allowed_clients
        self.wifi_interface = wifi_interface
        self.guardian_url = guardian_url
        super().__init__(address, ReadOpsHandler)


class ReadOpsHandler(BaseHTTPRequestHandler):
    server: ReadOpsServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _authorized(self) -> bool:
        client = str(self.client_address[0] if self.client_address else "")
        return client in self.server.allowed_clients

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _jpeg(self, payload: bytes, *, channel: int, captured_at: str) -> None:
        digest = hashlib.sha256(payload).hexdigest()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-FieldOps-Camera-Channel", str(channel))
        self.send_header("X-FieldOps-Captured-At", captured_at)
        self.send_header("X-FieldOps-SHA256", digest)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "client_not_allowlisted"})
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/health":
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "mode": "read_only",
                        "camera": "physical_guardian_localhost",
                        "wifi_interface": self.server.wifi_interface,
                    },
                )
                return
            if parsed.path == "/camera/snapshot":
                raw = (parse_qs(parsed.query).get("channel") or ["0"])[0]
                channel = int(raw)
                payload = _camera_snapshot(self.server.guardian_url, channel)
                self._json(HTTPStatus.OK if payload.get("ok") else HTTPStatus.BAD_GATEWAY, payload)
                return
            if parsed.path == "/camera/preview":
                raw = (parse_qs(parsed.query).get("channel") or ["0"])[0]
                channel = int(raw)
                payload, captured_at = _camera_jpeg(self.server.guardian_url, channel)
                self._jpeg(payload, channel=channel, captured_at=captured_at)
                return
            if parsed.path == "/network/scan":
                payload = _scan_wifi(self.server.wifi_interface)
                self._json(HTTPStatus.OK if payload.get("ok") else HTTPStatus.CONFLICT, payload)
                return
        except (ValueError, RuntimeError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            self._json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "error": type(exc).__name__, "reason": str(exc)[:160]},
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("FIELDOPS_READOPS_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("FIELDOPS_READOPS_PORT", "18787")))
    args = parser.parse_args()
    allowed = {
        item.strip()
        for item in os.getenv("FIELDOPS_READOPS_ALLOWED_CLIENTS", "127.0.0.1").split(",")
        if item.strip()
    }
    wifi_interface = os.getenv("FIELDOPS_READOPS_WIFI_INTERFACE", "wlx3c64cf8a0de9").strip()
    guardian_url = os.getenv("FIELDOPS_GUARDIAN_LOCAL_URL", "http://127.0.0.1:8788").strip()
    server = ReadOpsServer(
        (args.host, args.port),
        allowed_clients=allowed,
        wifi_interface=wifi_interface,
        guardian_url=guardian_url,
    )
    print(f"FieldOps read-only edge sidecar listening on {args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
