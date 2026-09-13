# InnerOS FieldOps — Architecture

## Design principles

- Local-first, not local-only.
- Reuse existing InnerOS capabilities before creating new ones.
- Treat cloud providers as reusable capabilities, not product owners.
- Require explicit approval for risky or irreversible actions.
- Verify state after every important action.
- Preserve evidence sufficient to explain what happened.
- Keep tenant/customer boundaries server-authorized.
- Avoid exposing customer LAN devices directly to the public Internet.

## High-level architecture

```text
User / Event / Alert
        |
        v
Coordinating Agent
(Strands when used for AWS-facing builds)
        |
        v
InnerOS / Ralphi IA
        |
        +--> Resource Fabric / policy routing
        |
        +--> MCP / business tools
        |
        +--> Human Approval Gate
        |
        v
Executor Interface
   |        |         |          |
   v        v         v          v
Software   Local     Edge       Human
APIs       AMD       Node       Field Tech
                     |
                     v
              Physical Systems
              LAN / IoT / NVR /
              GPIO / relays etc.
        |
        v
Verification Interface
        |
        v
Audit Fabric / Evidence Receipt
        |
        +--> Human Time Returned
        +--> Notification / escalation
```

## AWS / Strands integration

Strands is the preferred AWS-facing agent layer when a future competition or deployment benefits from it.

The integration must remain thin:

- Strands coordinates the agent workflow.
- Bedrock may provide cloud model capability when policy allows.
- AgentCore may be added when it improves deployment or judging value.
- InnerOS remains responsible for governed routing, execution contracts, approval and evidence.
- Local AMD inference remains available through Resource Fabric.

Do not migrate the whole platform to AWS merely to increase the number of AWS logos in a diagram.

## InnerOS Edge Node

A Raspberry Pi or mini-PC can act as an edge executor inside a private network.

Suggested node identity: `inneros-edge-01`.

Responsibilities:

- health checks and device reachability;
- local device discovery;
- HTTP/MQTT/serial/GPIO/relay execution where authorized;
- camera/NVR/IoT reachability and service checks;
- post-action verification;
- evidence metadata generation;
- secure outbound connection to InnerOS.

The edge node is not intended for large-model inference. Reasoning stays in the registered local/cloud runtime; the edge node provides presence and execution inside the LAN.

Potential services:

```text
edge-agent
  device-discovery
  health-monitor
  physical-io
  evidence-collector
  mcp-bridge
  secure-transport
```

## Executor contract

Every executor should expose a common conceptual contract:

```text
plan(action, context) -> executable plan
authorize(plan, policy, approval?) -> allowed / denied
execute(plan) -> execution result
verify(expected_state) -> verification result
```

Implementations may include software APIs, local OS operations, edge nodes, physical adapters or human technician workflows.

## Verification contract

Execution success is not assumed from a successful command response.

Verification must observe the expected resulting state independently when feasible.

Examples:

- API says service restarted -> health endpoint returns healthy.
- Relay command sent -> sensor reports desired state.
- Camera service restarted -> stream/status probe succeeds.
- Work order sent -> downstream system contains expected record.

## Evidence receipt

An evidence receipt should capture at minimum:

```text
correlation_id
trace_id
actor / agent / model
route decision + reason
policy version
requested action
approval reference when required
executor
input evidence references
execution result
verification result
output evidence references / hashes
quality gate
HTR reference when applicable
```

Evidence semantics should remain compatible with the canonical InnerOS Audit Fabric rather than being reinvented in this repository.

## Approval model

High-impact actions must fail closed without a valid approval artifact.

Missing, pending, rejected or unauthorized approval must prevent downstream execution.

## Pre-existing components

This project intentionally consumes existing InnerOS capabilities rather than copying them:

- Ralphi IA MCP
- Resource Fabric
- local AMD inference
- human approval primitives
- Physical Guardian
- InnerOps Service Operations
- QuoteOps / Workforce where relevant
- Audit Fabric / Decision Evidence / Forensic Replay
- durable coordination and telemetry foundations

Future hackathon submissions must disclose these as pre-existing where required.
