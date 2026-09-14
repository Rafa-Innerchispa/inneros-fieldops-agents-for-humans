# Universal Governed Actions

FieldOps has one mutation contract for every physical or operational domain:

`observe -> propose -> approve -> execute -> independently verify -> evidence receipt`

Read-only observations do not require approval. Every registered mutation does. Individual adapters cannot disable the approval gate because the central policy registry overwrites caller-provided approval flags.

## Current action matrix

| Domain | Action | Status | Approval | Executor / verifier truth |
| --- | --- | --- | --- | --- |
| Security | `camera.service_restart` | enabled synthetic judge target | required | bounded edge executor + independent state probe |
| Lighting | `dmx.set_scene` | **enabled real** | required | InnerOS AG-59 + AG-59 status readback |
| Lighting | `dmx.blackout` | **enabled real** | required | InnerOS AG-59 + `running=false` readback; stale last-scene name is not treated as failure |
| Facility / IoT | `homeassistant.scene_turn_on` | governed, blocked | required | enable only after FieldOps target allowlist + scene readback are bound |
| Facility / IoT | `homeassistant.entity_control` | governed, blocked | required | no arbitrary HA domain/service/entity calls |
| Telephony | `telephony.originate_call` | governed, blocked | required | SIP/AMI/CGI are verified; outbound route must be verified before enabling |
| Network | `network.apply_bounded_recovery` | governed, blocked | required | telemetry is real; arbitrary UniFi/RF mutation remains unavailable |
| Energy | `energy.apply_bounded_control` | governed, blocked | required | telemetry is real; inverter/load writes require proven bounded commands + independent telemetry verification |
| Alarm | `alarm.apply_state` | governed, blocked | required | presence/discovery only until a verified Intelbras write/readback path exists |
| Access | `access.apply_state` | governed, blocked | required | no unlock/open action without verified executor and independent physical readback |

Blocked does **not** mean read-only architecture. The action can be proposed and explicitly approved, but the execution stage fails closed until the required executor and verifier are installed and verified.

## Product runtime

`GovernedActionRuntime` is the shared execution service. Integrations register an executor/verifier pair by canonical action type. The runtime always resolves the central policy first and uses the common `run_action()` boundary.

`DMXExecutor` and `DMXVerifier` are the first real physical adapter pair. They accept only backend-advertised high-level scenes or blackout, require a private/local configured backend, and never expose raw DMX channels, universes, fixture addresses or arbitrary network destinations.

## Verification invariant

An executor ACK never closes a workflow. The verifier reads the resulting state independently. A successful command with failed readback produces `quality_gate=failed`.

The real AG-59 test on 2026-09-13 demonstrated why this matters: after blackout, the backend correctly reported `running=false` while retaining the previous scene name as last-scene telemetry. FieldOps therefore verifies blackout from physical inactivity state rather than assuming that a successful POST or a cleared scene name proves the outcome.
