# InnerOS Edge Node

## Purpose

An InnerOS Edge Node provides controlled execution and verification inside a private LAN or physical site. A Raspberry Pi is a good low-cost reference platform for small installations; a mini-PC can serve larger sites.

The node is intentionally not the primary LLM runtime. It provides **eyes, hands and local presence** while reasoning is handled through InnerOS Resource Fabric.

## Reference hardware

- Raspberry Pi capable of running a current 64-bit Raspberry Pi OS
- reliable storage
- Ethernet preferred
- optional adapters depending on site: GPIO relay, USB-RS485, MQTT devices, DMX interface, sensors

## Suggested base system

- Raspberry Pi OS Lite 64-bit
- SSH enabled
- fixed/reserved LAN address through DHCP reservation where practical
- outbound-only secure connection to the InnerOS control plane where possible
- no direct public exposure of device-management ports

Suggested hostname:

`inneros-edge-01`

## Responsibilities

- device/service reachability checks
- local discovery where policy permits
- bounded HTTP actions against allowlisted targets
- MQTT publish/subscribe adapters
- GPIO/relay actions
- serial/RS485 adapters
- camera/NVR health probes
- post-action state verification
- local evidence buffering when the control plane is temporarily unavailable
- reporting executor identity, timestamps and results

## Security model

- least privilege
- target allowlists
- no arbitrary URL execution
- no embedded customer credentials in source code
- secrets remain server-side or in an appropriate protected node secret store
- signed/authenticated control-plane requests
- idempotency for state-changing actions
- timeout and bounded retries
- risky actions require upstream approval
- independent verification after execution

## Conceptual API

```text
GET  /health
GET  /capabilities
POST /v1/plan
POST /v1/execute
POST /v1/verify
GET  /v1/evidence/{correlation_id}
```

This is a design contract, not a claim that the endpoints are already implemented.

## Example action envelope

```json
{
  "correlation_id": "incident-123",
  "action_type": "service_restart",
  "target_ref": "camera-gateway-01",
  "parameters": {},
  "policy_version": "fieldops-v1",
  "approval_ref": null,
  "expected_state": {
    "service_healthy": true
  }
}
```

## Example evidence result

```json
{
  "correlation_id": "incident-123",
  "executor": "inneros-edge-01",
  "execution": "local",
  "action_result": "success",
  "verification": "pass",
  "observed_state": {
    "service_healthy": true
  }
}
```

## FieldOps demo value

The edge node lets a future demo prove that an agent can cross the digital-to-physical boundary:

```text
incident -> agent -> governed decision -> edge execution -> observed verification -> evidence
```

That is materially different from a chatbot recommending that a human perform the same action.
