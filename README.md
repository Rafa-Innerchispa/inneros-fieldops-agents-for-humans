# InnerOS FieldOps

**Cloud intelligence. Sovereign execution. Verified outcomes.**

InnerOS FieldOps is an AI operations agent for the physical world, built for the AWS **Agents for Humans** hackathon. It turns an operational objective into a governed workflow that can request human approval, execute a bounded action, independently verify the result, and return an auditable Evidence Receipt.

## Thesis

Most agents stop at recommendations. FieldOps closes the loop:

```text
objective / incident
  -> context
  -> agent decision
  -> bounded action proposal
  -> human approval when required
  -> execution
  -> independent verification
  -> evidence receipt
```

The human should be interrupted for judgment, not routine coordination.

## What is implemented

The hackathon snapshot contains:

- an actual Strands Agents SDK runtime that instantiates a `strands.Agent` and exposes bounded FieldOps tools;
- provider-neutral action, approval, execution, verification, and evidence contracts;
- fail-closed approval handling for consequential actions;
- independent post-action verification;
- Evidence Receipts with correlation, route, action, executor, verifier, and quality gate;
- an AgentCore-oriented entrypoint/config example without committed secrets;
- a judge-facing web console with Security, Energy, and Facility/Network views;
- real Xmart solar evidence from an InnerOS Raspberry Pi Edge Node using read-only PI30 `QPI`/`QPIGS` queries;
- real UniFi RF evidence from the local Home Assistant/UniFi integration;
- an allowlisted read-only Home Assistant adapter that can show live local telemetry when server-side credentials are configured;
- explicit `LIVE REAL` vs `CAPTURED REAL` labeling so recorded evidence is never presented as live telemetry;
- credential-free synthetic execution fixtures for approval, execution-failure, and verification-failure paths;
- architecture, pre-existing-code disclosure, and edge-node documentation.

The Intelbras alarm is currently discovered as a real online network device. This snapshot **does not claim alarm control** because its panel protocol/model integration has not yet been proven.

## Run the demo

Create the environment:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test,strands]"
```

Run the final Strands-backed judge console:

```bash
python scripts/demo_web_strands.py --host 127.0.0.1 --port 8777
```

Open `http://127.0.0.1:8777`.

The console demonstrates:

1. **Observe** an operational incident.
2. **Understand** and select a bounded FieldOps action through a real `strands.Agent` runtime.
3. **Human Approval** for consequential execution.
4. **Act** through the governed executor boundary.
5. **Independent Verification** before success is accepted.
6. **Evidence Receipt** proving what happened.

It also shows the real Energy and Facility/Network evidence included with this submission. When authorized local Home Assistant credentials are supplied server-side, `/api/status` can refresh allowlisted local telemetry without exposing those credentials to the browser.

Run credential-free scenarios directly:

```bash
python scripts/demo_synthetic.py
python scripts/demo_synthetic.py --scenario denied
python scripts/demo_synthetic.py --scenario failed-execution
python scripts/demo_synthetic.py --scenario failed-verification
python scripts/demo_strands.py --scenario happy
```

## Verification

Final pre-submission verification on 2026-09-13:

```text
python -m pytest -q                         22 passed
python -m compileall -q src                 PASS
Judge Console /                             PASS
Judge Console /api/demo?scenario=happy      PASS
Strands runtime                             active=true
Bounded tool                                execute_fieldops_demo -> success
Independent verification                    PASS
Evidence Receipt quality gate               PASS
```

## Real-world evidence

### Energy Agent

The InnerOS Edge Node reads an **Xmart XSI-BB-120-3K-24-MPP** inverter over USB using the PI30 protocol. Only read-only `QPI`/`QPIGS` queries are used. A captured real sample in `docs/evidence/inneros_pi01_xmart_live_telemetry_20260913.json` includes output power, battery voltage/capacity, load, grid voltage, temperature, and PV values.

### Facility / Network Agent

`docs/evidence/unifi_rf_snapshot_20260913.json` contains sanitized real UniFi RF evidence captured through Home Assistant diagnostics. It includes AP/channel/utilization/client information and a real camera retry-rate problem. No Wi-Fi credentials are stored and no RF settings are changed by the demo.

### Security Agent

The hackathon execution scenario uses a safe bounded camera-service fixture so approval, execution, and independent verification can be demonstrated without risking a production camera system. Existing InnerOS/Physical Guardian capabilities are disclosed as pre-existing technology rather than presented as new hackathon code.

## AWS / Strands truth boundary

Strands Agents is genuinely integrated and tested. The final judge console is mediated by a real `strands.Agent` instance and bounded Strands tool. The repository also contains an optional Bedrock provider configuration path and AgentCore-oriented entrypoint.

During final testing, the current AWS account returned:

```text
ValidationException: Operation not allowed
```

in the Bedrock Playground. We therefore **do not claim a successful live Bedrock inference** in this snapshot unless a later bounded smoke test succeeds before submission. The credential-free/local Strands demo remains complete, while Bedrock stays an optional cloud route once the account/service eligibility restriction is resolved.

AWS is a capability, not the owner of the product architecture. InnerOS retains the governed execution, local/private-network access, and verification boundary.

## Architecture

```text
Human / Event / Alert
        |
        v
   Strands Agent
        |
        v
InnerOS / FieldOps policy + context
        |
        +--> Human Approval Gate
        +--> Local / cloud routing
        |
        v
Governed Executor
        |
        +--> software/API
        +--> InnerOS Edge Node
        +--> physical infrastructure
        |
        v
Independent Verifier
        |
        v
Evidence Receipt
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/assets/fieldops-architecture.svg`](docs/assets/fieldops-architecture.svg).

## Pre-existing technology disclosure

InnerOS, Ralphi IA/MCP, local-model infrastructure, Resource Fabric, Home Assistant integrations, Physical Guardian concepts, approval/audit foundations, and other operational infrastructure predate this hackathon.

Hackathon-specific work includes the FieldOps product/workflow layer, Strands-facing orchestration, bounded demo execution, judge console, evidence presentation, AWS configuration path, documentation, and competition-specific integration work.

See [`docs/PREEXISTING_DISCLOSURE.md`](docs/PREEXISTING_DISCLOSURE.md).

## Safety

- No secrets are committed.
- No arbitrary model shell or arbitrary public network execution is exposed.
- Consequential actions fail closed without approval.
- A command response is never accepted as proof of success without verification.
- Solar access is read-only.
- UniFi RF data is read-only in this snapshot.
- Real and synthetic/captured evidence are explicitly labeled.

## Submission snapshot lifecycle

This repository is the reproducible **hackathon submission snapshot**. After final Devpost submission, the exact submitted SHA will be tagged and this repository will be frozen for feature development. Reusable FieldOps capabilities continue in the living InnerOS product line rather than mutating the competition snapshot.

## License

MIT.
