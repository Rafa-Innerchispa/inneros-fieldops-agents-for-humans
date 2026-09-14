# Universal Governed Actions

FieldOps has one mutation contract for every physical or operational domain:

`observe -> propose -> approve -> execute -> independently verify -> evidence receipt`

Read-only observations do not require approval. Every registered mutation does. Individual adapters cannot disable the approval gate because the central policy registry overwrites caller-provided approval flags.

## Current action matrix

| Domain | Action | Status | Approval | Executor / verifier truth |
| --- | --- | --- | --- | --- |
| Security | `camera.service_restart` | enabled synthetic judge target | required | bounded edge executor + independent state probe; real camera restart is not claimed yet |
| Lighting | `dmx.set_scene` | **enabled real** | required | bounded local DMX engine + independent status readback |
| Lighting | `dmx.blackout` | **enabled real** | required | bounded local DMX engine + `running=false` readback; stale last-scene name is not treated as failure |
| Facility / IoT | `homeassistant.entity_control` | **enabled real** | required | canonical InnerOS Home Assistant client; server allowlist; exact light on/off only; independent HA state readback |
| Facility / IoT | `homeassistant.scene_turn_on` | governed, blocked | required | enable only after a per-scene allowlist + resulting-state verifier are bound |
| Telephony | `telephony.originate_call` | governed, blocked | required | SIP/AMI/CGI control planes exist; outbound route verification is handled in the VoiceOps workstream before FieldOps can bind it |
| Network | `network.apply_bounded_recovery` | governed, blocked | required | telemetry is real; arbitrary UniFi/RF mutation remains unavailable |
| Energy | `energy.apply_bounded_control` | governed, blocked | required | telemetry is real; inverter/load writes require proven bounded commands + independent telemetry verification |
| Alarm | `alarm.apply_state` | governed, blocked | required | alarm status/discovery may exist, but critical writes are not enabled by FieldOps until separately verified |
| Access | `access.apply_state` | governed, blocked | required | no unlock/open action without verified executor and independent physical readback |

Blocked does **not** mean read-only architecture. The action can be proposed and explicitly approved, but the execution stage fails closed until the required executor and verifier are installed and verified.

## Product runtime

`GovernedActionRuntime` is the shared execution service. Integrations register an executor/verifier pair by canonical action type. The runtime always resolves the central policy first and uses the common `run_action()` boundary.

Real adapter pairs now include:

- `DMXExecutor` + `DMXVerifier`: backend-advertised high-level scenes and blackout only. Raw DMX channels, universes, fixture addresses and arbitrary network destinations are not exposed.
- `HomeAssistantEntityExecutor` + `HomeAssistantEntityVerifier`: exact `on`/`off` state for a server-configured allowlist of noncritical `light.*` entities. The adapter reuses the canonical InnerOS Home Assistant client, so the HA credential remains in the server-side InnerOS runtime and is never copied into this repository or browser payload.

`build_product_runtime()` binds only adapters that are genuinely configured. An `enabled_real` policy without a runtime binding cannot execute.

## Operator Console

Port 8777 now serves the **FieldOps Operator Console** as the primary surface. The hackathon-specific Strands judge evidence view remains available at `/judge` as secondary evidence rather than being the product itself.

The operator HTTP surface exposes:

- `GET /api/actions` — current policy + runtime binding truth.
- `GET /api/status` — runtime status and read-only InnerOS context.
- `POST /api/propose` — creates a governed proposal; it cannot bypass central approval policy.
- `POST /api/execute` — physical execution path, restricted to an explicitly enabled direct loopback operator request. Public/judge traffic cannot use this endpoint to mutate physical devices.

This keeps the public hackathon surface inspectable without accidentally publishing a home-control API.

## Verification invariant

An executor ACK never closes a workflow. The verifier reads the resulting state independently. A successful command with failed readback produces `quality_gate=failed`.

The real DMX test on 2026-09-13 demonstrated why this matters: after blackout, the backend correctly reported `running=false` while retaining the previous scene name as last-scene telemetry. FieldOps therefore verifies blackout from physical inactivity state rather than assuming that a successful POST or a cleared scene name proves the outcome.

The Home Assistant adapter follows the same rule: a successful service call is insufficient; the target entity must independently read back the requested `on` or `off` state.
