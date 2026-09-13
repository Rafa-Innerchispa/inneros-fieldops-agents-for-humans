# Devpost Submission Draft — Agents for Humans

## Project name
InnerOS FieldOps

## Tagline
The AI operations agent that does the work, verifies the outcome, and only interrupts a human when judgment is actually required.

## Track
Professional Agents

## Who it is for
Small and mid-sized field-service and technical operations teams: security integrators, managed IT providers, maintenance companies, facilities teams, network installers, building technology operators and other service businesses where work crosses software, people and physical infrastructure.

## Problem
Operational work is fragmented across tickets, WhatsApp, email, dashboards, device interfaces, technician messages and manual follow-up. The owner or operations manager becomes the glue between systems.

Most AI assistants stop at advice. They can say what should happen, but a human still has to open tools, execute actions, check whether they worked, capture evidence and decide what to do next.

## Solution
InnerOS FieldOps turns an operational objective into governed execution.

A coordinating agent built with Strands Agents can:

1. understand an incident or request;
2. gather context through InnerOS/MCP tools;
3. decide where work should run using policy-aware routing;
4. request human approval only when policy requires it;
5. execute through a bounded executor;
6. independently verify the resulting state;
7. generate an Evidence Receipt;
8. notify the human only if intervention or judgment is genuinely needed.

The core design principle is simple:

**A command returning success does not mean the problem is solved. The resulting state must be verified.**

## Why it matters
For field-service companies, the hidden cost is coordination. A simple incident may require opening several systems, chasing a technician, checking a device, documenting what happened and updating the customer.

FieldOps moves repetitive coordination to the agent while preserving human authority over sensitive actions.

InnerOS already measures Human Time Returned on operational workflows. One internal workflow previously measured approximately 120 human minutes baseline versus approximately 10 assisted human minutes. This is internal evidence from a specific workflow, not a universal performance claim.

## What makes it different

- Executes real work instead of only recommending actions.
- Verifies post-action state independently.
- Keeps high-impact actions behind explicit human approval.
- Supports local-first / cloud-hybrid routing.
- Can execute inside private networks through an InnerOS Edge Node such as a Raspberry Pi or mini-PC.
- Produces evidence instead of asking users to trust an opaque autonomous action.
- Connects business operations and physical infrastructure through one governed execution model.

## Architecture

```text
Incident / Goal
      |
      v
Strands Agent
      |
      v
InnerOS / Ralphi IA
      |
      +--> Resource Fabric (local/cloud routing)
      +--> MCP context/tools
      +--> Human Approval Gate
      |
      v
FieldOps Executor
      |
      +--> Software APIs
      +--> InnerOS Edge Node
      +--> Physical Guardian / local devices
      +--> Human field technician
      |
      v
Independent Verification
      |
      v
Evidence Receipt / Audit Fabric
      |
      v
Resolved silently OR human escalation
```

## AWS usage

FieldOps is provider-neutral at its execution boundary. For the AWS build:

- Strands Agents provides the agent orchestration layer.
- Amazon Bedrock is the cloud model provider when policy permits.
- Amazon Bedrock AgentCore is an optional deployment target that can strengthen the Technical Implementation score.
- AWS does not replace InnerOS. It provides cloud intelligence/orchestration while InnerOS maintains governed execution and local/private-network access.

## Demo scenario

A camera gateway is reported unhealthy.

1. The Strands agent receives the incident.
2. It retrieves site/device context.
3. Policy determines the remediation is allowed only with explicit approval.
4. Human approves the restart.
5. FieldOps executes the restart through the edge executor.
6. A separate verifier probes the service state.
7. The system produces an Evidence Receipt showing route, policy, approval, executor, action result and verification.
8. The human receives `Resolved autonomously. No further action required.`

A second demo branch shows that pending/rejected approval prevents execution entirely.

## Pre-existing technology disclosure

This project builds on pre-existing InnerOS technologies, including Ralphi IA, MCP integrations, local inference infrastructure, Resource Fabric, Physical Guardian concepts, human approval primitives and audit/evidence foundations.

Hackathon-specific work includes the Strands-facing orchestration layer, FieldOps workflow, AWS integration, demo, documentation and competition-specific presentation.

See `docs/PREEXISTING_DISCLOSURE.md` for details.

## Built with

- Strands Agents SDK
- Amazon Bedrock
- Amazon Bedrock AgentCore (optional deployment)
- Python
- InnerOS
- MCP
- Resource Fabric
- local AMD/vLLM inference
- Raspberry Pi / edge execution architecture
- InnerOS Audit Fabric / Evidence Receipts

## Public repository

https://github.com/Rafa-Innerchispa/inneros-fieldops-agents-for-humans

## Submission checklist

Required by Devpost:

- [ ] Working Strands Agents implementation
- [x] Public repository
- [x] MIT license
- [x] README
- [ ] Final architecture diagram image/PDF upload
- [ ] Demo video, maximum 5 minutes
- [ ] AWS Builder ID
- [ ] Devpost project created
- [ ] Professional Agents track selected
- [ ] Country of residence: Ecuador
- [ ] Test instructions finalized
- [ ] Optional live demo
- [ ] Optional builder.aws.com post
