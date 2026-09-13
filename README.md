# InnerOS FieldOps

**Cloud intelligence. Sovereign execution. Verified outcomes.**

InnerOS FieldOps is a reusable governed execution layer for AI agents that need to do real operational work across software, field-service workflows and physical infrastructure.

It originated while evaluating the AWS **Agents for Humans** hackathon. The project is intentionally preserved beyond that event as reusable InnerOS R&D rather than being discarded or frozen as a one-off submission.

## Thesis

Most agents stop at recommendations. FieldOps closes the loop:

```text
objective / incident
  -> context
  -> reasoning
  -> bounded action proposal
  -> policy + human approval when required
  -> execution
  -> independent verification
  -> evidence receipt
  -> closeout or escalation
```

The human should be interrupted for judgment, not routine coordination.

## Current implementation

The repository now contains a provider-neutral Python core with:

- action, approval, execution, verification and evidence contracts;
- fail-closed approval handling for risky actions;
- mandatory post-action verification;
- a safe synthetic Edge Node executor and independent verifier;
- a runnable synthetic camera-gateway recovery scenario;
- a Strands-shaped adapter boundary without requiring AWS credentials;
- tests covering blocked approvals, successful verified execution, unknown targets and the Strands-facing boundary;
- architecture, roadmap, pre-existing-code disclosure and Raspberry Pi Edge Node runbook.

Run the synthetic demo after cloning:

```bash
python scripts/demo_synthetic.py
```

Run tests:

```bash
python -m pytest
```

## Architecture

```text
Agent / Event
    |
    v
Strands or other orchestrator
    |
    v
InnerOS / Ralphi IA
    |
    +--> Resource Fabric / model routing
    +--> MCP / operational context
    +--> Human Approval Gate
    |
    v
FieldOps governed execution boundary
    |
    +--> software/API executor
    +--> InnerOS Edge Node (Raspberry Pi / mini-PC)
    +--> Physical Guardian
    +--> human field technician
    |
    v
Independent verification
    |
    v
Audit Fabric / Evidence Receipt / HTR
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the complete design.

## Raspberry Pi / Edge

A Raspberry Pi can become `inneros-edge-01`: a permanent execution and verification node inside a private LAN. It can provide health probes, MQTT, GPIO/relay, serial/Modbus, camera/NVR checks and other bounded adapters without exposing customer devices directly to the Internet.

The Raspberry Pi is not intended to run the primary large language model. Reasoning stays in the registered InnerOS local/cloud runtime; the edge node provides physical presence.

See [`docs/RASPBERRY_PI_RUNBOOK.md`](docs/RASPBERRY_PI_RUNBOOK.md).

## AWS / Strands

Strands remains a valuable optional orchestration layer for AWS-facing deployments or future competitions. The reusable FieldOps core does not require AWS credentials and does not give a model unrestricted shell/network access.

See [`docs/STRANDS_ADAPTER.md`](docs/STRANDS_ADAPTER.md).

## Pre-existing InnerOS capabilities

FieldOps is designed to consume, not duplicate:

- InnerOS / Ralphi IA
- MCP tools/connectors
- Resource Fabric
- local AMD inference
- Physical Guardian
- InnerOps Service Operations / Workforce / QuoteOps where relevant
- approval primitives
- Audit Fabric / Decision Evidence / Forensic Replay
- Human Time Returned telemetry

Future hackathon submissions must disclose reused components according to the event rules.

## Safety boundary

No production customer systems are touched by the synthetic demo. Risky actions fail closed without explicit approval, and a successful command response is never treated as proof that the desired state exists.

## License

MIT.
