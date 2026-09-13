# Devpost Submission Draft — AWS Agents for Humans

## Project name
InnerOS FieldOps

## Elevator pitch
AI agents that safely turn real-world needs into action, with human approval, physical execution, independent verification, and auditable evidence.

## Tagline
**The AI agent that doesn't just answer. It runs the operation.**

## Track
Professional Agents

## Who it is for
Small and mid-sized field-service and technical operations teams: security integrators, managed IT providers, maintenance companies, facilities teams, network installers, building-technology operators, and other service businesses where work crosses software, people, and physical infrastructure.

## Problem
Operational work is fragmented across messages, dashboards, device interfaces, technicians, and manual follow-up. The owner or operations manager becomes the glue between systems.

Most AI assistants stop at advice. They can say what should happen, but a human still has to open tools, execute actions, check whether they worked, preserve evidence, and decide what happens next.

## Solution
InnerOS FieldOps turns an operational objective into governed execution.

A Strands-based coordinating agent can:

1. understand an incident or request;
2. gather operational context;
3. choose a bounded FieldOps action;
4. request human approval when policy requires it;
5. execute through an allowlisted executor boundary;
6. independently verify the resulting state;
7. generate an Evidence Receipt;
8. close the incident or escalate only when human judgment is actually needed.

The core design principle is simple:

**A command returning success does not mean the problem is solved. The resulting state must be independently verified.**

## Why it matters
Field-service companies lose enormous amounts of human time to coordination rather than to the technical work itself. A simple incident can mean opening several systems, checking infrastructure, contacting someone, documenting the result, and updating the customer.

FieldOps moves repetitive coordination to the agent while preserving human authority over consequential actions.

InnerOS has historical internal evidence of a specific workflow moving from approximately 120 human minutes to approximately 10 assisted human minutes. This is context from one measured/internal workflow, not a universal performance claim.

## What makes it different

- It is designed to execute governed real-world work rather than only recommend actions.
- It requires post-action verification before accepting success.
- High-impact actions remain behind explicit human approval.
- It combines cloud-compatible agent orchestration with sovereign/local execution.
- It can operate inside private networks through InnerOS Edge Nodes such as Raspberry Pi or mini-PC systems.
- It produces Evidence Receipts instead of asking users to trust opaque autonomous actions.
- One governed execution model spans security, energy, facilities, networking, and other operational domains.
- Real integrations and synthetic demo fixtures are explicitly labeled rather than blended together.

## Architecture

```text
Human / Incident / Alert
          |
          v
     Strands Agent
          |
          v
 InnerOS / FieldOps
 context + policy + routing
          |
          +--> Human Approval Gate
          |
          v
   Governed Executor
          |
          +--> software/API
          +--> Edge Node
          +--> physical infrastructure
          |
          v
 Independent Verifier
          |
          v
    Evidence Receipt
          |
          v
 closeout or human escalation
```

## What the demo shows

### 1. Security Agent
A camera-service incident enters FieldOps. The agent proposes a bounded remediation. The action cannot execute until the human approves it. After execution, a separate verifier checks the resulting state. An Evidence Receipt records correlation ID, route, action, executor, verifier, and quality gate.

The execution fixture is deliberately safe and credential-free so judges can reproduce the governance loop without touching a production camera system.

### 2. Energy Agent — real physical evidence
A Raspberry Pi InnerOS Edge Node is physically connected to an **Xmart XSI-BB-120-3K-24-MPP** inverter. The system identified the PI30 protocol and reads real telemetry using read-only `QPI`/`QPIGS` queries.

The submission includes captured real evidence for output power, battery voltage/capacity, load, grid voltage, temperature, and PV state. When authorized local Home Assistant credentials are configured server-side, the judge console can refresh allowlisted local telemetry without exposing credentials to the browser.

### 3. Facility / Network Agent — real UniFi evidence
The submission includes sanitized real RF/network evidence from the local UniFi installation through Home Assistant diagnostics: AP state, channels, utilization, client distribution, and retry behavior. This demonstrates the same FieldOps model applied to infrastructure rather than to a single camera workflow.

An Intelbras alarm is also discovered as an online real device. We do **not** claim alarm control in this submission because its exact panel protocol/model integration is still being validated.

## Judge console
The local no-dependency judge console exposes:

- Security, Energy, and Facility/Network operational cards;
- Judge Mode with approve/deny/failed-verification paths;
- the full observe → understand → approve → act → verify pipeline;
- Evidence Receipts;
- real-versus-captured evidence labels;
- read-only operations status refresh;
- technical trace and architecture surfaces.

Run it with:

```bash
python scripts/demo_web.py --host 127.0.0.1 --port 8765
```

## AWS / Strands usage

### Verified
- Real Strands Agents SDK integration.
- `strands.Agent` instantiation.
- Bounded FieldOps tools exposed through the Strands runtime.
- AgentCore-oriented entrypoint/config example.
- Optional Bedrock provider configuration path.

### Current AWS account limitation
During final testing the Bedrock Playground returned:

```text
ValidationException: Operation not allowed
```

We therefore do **not** claim a successful live Bedrock model invocation in this submission snapshot. FieldOps remains fully demonstrable through the verified Strands/local execution path, and Bedrock remains an optional cloud route once the account/service eligibility restriction is resolved.

This design is intentional: AWS provides cloud-compatible orchestration/model capability, while InnerOS preserves the governed local/private-network execution and verification boundary.

## Pre-existing technology disclosure
This project builds on pre-existing InnerOS technologies including Ralphi IA/MCP, local-model infrastructure, Resource Fabric, Home Assistant/edge integrations, Physical Guardian concepts, approval primitives, and audit/evidence foundations.

Hackathon-specific work includes the FieldOps workflow/product layer, Strands-facing orchestration, bounded demo execution, AWS configuration path, judge console, evidence presentation, and competition-specific documentation/integration.

See `docs/PREEXISTING_DISCLOSURE.md` for details.

## Built with
- Strands Agents SDK
- Python
- InnerOS
- MCP / operational integrations
- Raspberry Pi / InnerOS Edge Node
- Home Assistant
- UniFi
- local AMD/vLLM infrastructure
- optional Amazon Bedrock provider path
- AgentCore-oriented entrypoint

## Verification
Final pre-submission verification:

```text
python -m pytest -q                         19 passed, 1 skipped
python -m compileall -q src scripts agentcore   PASS
Judge console HTTP /                       200
Judge console HTTP /api/status             200
```

## Public repository
https://github.com/Rafa-Innerchispa/inneros-fieldops-agents-for-humans

## Devpost fields
- Project name: **InnerOS FieldOps**
- Track: **Professional Agents**
- AWS Builder ID: **@ralphi**
- Repository: `https://github.com/Rafa-Innerchispa/inneros-fieldops-agents-for-humans`
- Country of residence: **Ecuador**

## Testing instructions
Run the local credential-free demo to explore the complete governed workflow: request → AI analysis → human approval → bounded execution → independent verification → Evidence Receipt. The repository README includes setup and testing instructions. The judge console also exposes real captured Energy and UniFi operational evidence. AWS/Bedrock remains optional because the current account returned `ValidationException: Operation not allowed` during final testing.

## Submission checklist
- [x] Working Strands Agents implementation
- [x] Public repository
- [x] MIT license
- [x] README and testing instructions
- [x] Professional Agents track selected
- [x] AWS Builder ID: @ralphi
- [x] Devpost project created
- [x] Architecture asset exists in repository
- [x] Final Judge Console implemented and tested
- [x] Real solar evidence included
- [x] Real UniFi evidence included
- [ ] Upload final architecture/gallery media to Devpost
- [ ] Record/upload public YouTube or Vimeo demo video (maximum 5 minutes)
- [ ] Final Devpost review and Submit
- [ ] Optional builder.aws.com bonus post

## Repository lifecycle
This repository becomes a frozen hackathon snapshot after final submission. Reusable capabilities continue in the living InnerOS FieldOps product line; new product development must not continue by mutating the submitted competition snapshot.
