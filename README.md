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
- an authenticated judge-facing web console with Security/Camera, Solar/Energy, Network/Facility, Alarm/Security Panel, and Telephony/PBX modules;
- real Xmart solar evidence from an InnerOS Raspberry Pi Edge Node using read-only PI30 `QPI`/`QPIGS` queries;
- real UniFi RF evidence from the local Home Assistant/UniFi integration;
- real read-only Intelbras/Home Assistant alarm panel and zone status;
- read-only VoiceOps/PBX health evidence; FieldOps does not register SIP, read SIP credentials, or originate arbitrary calls;
- an allowlisted read-only Home Assistant adapter that can show live local telemetry when server-side credentials are configured;
- explicit `LIVE REAL` vs `CAPTURED REAL` labeling so recorded evidence is never presented as live telemetry;
- credential-free synthetic execution fixtures for approval, execution-failure, and verification-failure paths;
- architecture, pre-existing-code disclosure, and edge-node documentation.

This snapshot **does not claim alarm control**. Arm/disarm/panic/siren/PGM remain outside FieldOps until a bounded executor plus independent readback is proven.

## Judge testing instructions

The final judge build is deployed at:

**https://inneros.creatorcore.ai/app/judge**

Use the judge credentials provided privately by the project owner. Credentials are configured server-side and are intentionally not committed to Git or published in this README.

Recommended evaluation flow:

1. **Sign in** and confirm the unified status strip plus the five operational modules: Security/Camera, Solar/Energy, Network/Facility, Alarm/Security Panel, and Telephony/PBX.
2. Run **Read Solar**. Review Xmart/Pi01 telemetry, source label, timestamp/freshness, verification result, and Evidence Receipt. The inverter path is read-only.
3. Run **Scan Wi-Fi**. Review sanitized RF/network evidence and confirm that Ethernet route integrity is verified before and after the scan. No RF mutation is performed.
4. Run **Read Alarm**. Review the real Home Assistant/Intelbras panel state and zone summary. FieldOps intentionally exposes no arm/disarm/panic/siren/PGM control in this submission.
5. Run **Read PBX**. Review VoiceOps/Grandstream PBX control-plane health. FieldOps does not register SIP, read SIP secrets, or originate arbitrary calls. Audible owner-side call confirmation is not claimed while the current VoiceOps endpoints remain unavailable.
6. Open the **Security / Judge** workflow and run the **deny** path. Confirm that the executor remains blocked when human approval is denied.
7. Run the **approved** Security path and follow the governed sequence: `OBSERVE -> ANALYZE -> APPROVE -> EXECUTE -> VERIFY -> EVIDENCE`.
8. Inspect the **Evidence Receipt** and final quality gate. A successful command ACK is not accepted as success; FieldOps requires independent state verification.
9. Review source labels throughout the console. `REAL`, `CAPTURED REAL`, and `SYNTHETIC` evidence are explicitly distinguished.
10. **Log out** and confirm the authenticated boundary. Public unauthenticated observations fail closed by design.

### Local reproduction

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

Set `FIELDOPS_JUDGE_USERNAME`, `FIELDOPS_JUDGE_PASSWORD`, and `FIELDOPS_JUDGE_SESSION_SECRET` outside Git before exposing the console publicly.

Credential-free synthetic scenarios remain available for reproducible approval and failure-path testing:

```bash
python scripts/demo_synthetic.py
python scripts/demo_synthetic.py --scenario denied
python scripts/demo_synthetic.py --scenario failed-execution
python scripts/demo_synthetic.py --scenario failed-verification
python scripts/demo_strands.py --scenario happy
```

The repository also contains an AgentCore-oriented entrypoint and optional Amazon Bedrock provider configuration. Live Bedrock inference is **not claimed** in the final submission because the AWS account returned `ValidationException: Operation not allowed` during final testing. The working judge build uses the real Strands Agents SDK runtime with local/private InnerOS execution and independent verification.

## Verification

Final pre-submission verification on 2026-09-14:

```text
python -m pytest -q                              71 passed
python -m compileall -q src scripts agentcore   PASS
git diff --check                                PASS
Judge Console login/logout                      PASS
Judge Console /app/judge                        PASS
Public unauthenticated observation              FAIL-CLOSED
Authenticated Solar observation                 PASS
Authenticated Wi-Fi observation                 PASS
Authenticated Alarm observation                 PASS
Authenticated PBX observation                   PASS
Security denial path                            PASS
Security approved path                          PASS
Bounded execution                               PASS
Independent verification                        PASS
Evidence Receipt quality gate                   PASS
```

## Real-world evidence

### Energy Agent

The InnerOS Edge Node reads an **Xmart XSI-BB-120-3K-24-MPP** inverter over USB using the PI30 protocol. Only read-only `QPI`/`QPIGS` queries are used. A captured real sample in `docs/evidence/inneros_pi01_xmart_live_telemetry_20260913.json` includes output power, battery voltage/capacity, load, grid voltage, temperature, and PV values.

### Facility / Network Agent

`docs/evidence/unifi_rf_snapshot_20260913.json` contains sanitized real UniFi RF evidence captured through Home Assistant diagnostics. It includes AP/channel/utilization/client information and a real camera retry-rate problem. No Wi-Fi credentials are stored and no RF settings are changed by the demo.

### Alarm / Security Panel

The console reads `alarm_control_panel.panel_home_ralphi_panel_home_ralphi` and the `binary_sensor.panel_home_ralphi_zona_*` zone projection through the existing Home Assistant/Intelbras Guardian path. It reports panel state, zone count, and open-zone count as read-only evidence. It does not expose arm/disarm/siren/PGM.

### Telephony / PBX

The console reads VoiceOps health and an independent Asterisk/Grandstream PBX AMI banner probe. It shows whether the control plane is reachable, while live SIP/RTP, Zoiper registration, TTS audio, and owner-visible calls remain owned by VoiceOps.

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
