# Raspberry Pi runbook — InnerOS Edge Node

This is a future deployment runbook. The current FieldOps core does not require Raspberry Pi hardware.

## Recommended role

The Raspberry Pi is an edge executor/verifier inside a private customer or lab LAN. It should not host the primary large language model.

Suggested hostname: `inneros-edge-01`.

## Base OS

Use Raspberry Pi OS Lite 64-bit. Enable SSH during imaging. Prefer Ethernet and a reserved DHCP lease or managed static address.

## Initial packages

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y git curl python3 python3-venv ca-certificates
```

Containerization may be added later, but the first edge agent should remain simple enough to diagnose without Docker being another failure domain.

## Security defaults

- No customer device credentials in Git.
- Secrets remain local/server-side and referenced by secure identifiers.
- Prefer outbound secure connectivity from the edge node rather than inbound Internet exposure.
- Maintain a target allowlist.
- No arbitrary URL execution.
- Bounded actions only.
- Risky/irreversible actions require approval.
- Log correlation_id and evidence references for state changes.
- Support dry-run for new adapters.

## Candidate adapters

- HTTP health/service probes
- MQTT
- GPIO/relay
- serial/RS485/Modbus with appropriate hardware
- camera/NVR reachability and vendor APIs
- DMX through a supported interface
- local service/systemd operations where explicitly allowlisted

## Edge API concept

```text
GET  /health
GET  /v1/targets/{ref}/state
POST /v1/actions/plan
POST /v1/actions/execute
POST /v1/actions/verify
GET  /v1/evidence/{correlation_id}
```

The API must use authenticated requests, replay protection/idempotency for state changes and a strict target/action allowlist.

## First lab milestone

1. Install OS and SSH.
2. Register node as `inneros-edge-01`.
3. Run edge-agent health endpoint.
4. Connect one harmless synthetic/local service target.
5. Execute a bounded restart/toggle action.
6. Verify state independently.
7. Return evidence receipt to InnerOS.
8. Only then add cameras, GPIO, relays, DMX or customer systems.
