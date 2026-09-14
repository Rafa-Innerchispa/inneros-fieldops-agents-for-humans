# Demo Video Plan — maximum 5 minutes

Goal: prove end-to-end work, not narrate architecture for five minutes.

## 0:00–0:25 — Problem

Visual: service incident / FieldOps event.

Voiceover:

> Small technical-service companies lose hours every day coordinating work between messages, dashboards, devices and technicians. AI assistants can tell you what to do. FieldOps is built to actually do the work — safely — and prove that it worked.

## 0:25–0:50 — Product thesis

Visual: simple architecture.

> InnerOS FieldOps is a Strands-powered Professional Agent. It receives an operational goal, gathers context, routes work between cloud and local resources, requests approval when required, executes the action, independently verifies the result and produces an evidence receipt.

## 0:50–3:35 — Working demo

Visual: authenticated Judge Console at `/app/judge` or the LAN/service URL.

Scenario: operator signs in and opens the unified FieldOps console.

Show:

1. Login screen protects the public judge console.
2. Overview shows normalized runtime health: Agent/Strands, Edge Node/Pi, Home Assistant, PBX, Alarm, UniFi/RF.
3. `Read Solar` returns real Xmart/Pi01 telemetry and an Evidence Receipt.
4. `Scan Wi-Fi` returns real RF evidence with Ethernet route verification.
5. `Read Alarm` returns the Intelbras/Home Assistant panel state and zone summary without arming, disarming or exposing siren control.
6. `Read PBX` returns VoiceOps/PBX health and explicitly shows that VoiceOps owns SIP/RTP execution.
7. Open Judge Mode and show the governed security flow.
8. Denied approval path stops before executor invocation.
9. Approved path executes the bounded security fixture.
10. Independent verifier observes `healthy=true`.
11. Evidence Receipt appears.
12. Final result: `Resolved autonomously. No further action required.`

Narration should explicitly say:

> Notice that a successful command is not considered success. FieldOps verifies the resulting state separately, and read-only modules produce their own evidence receipts without pretending to control devices.

## 2:40–3:25 — Why Strands + AWS

Visual: Strands / Bedrock / InnerOS diagram.

> Strands is the coordinating agent layer. Amazon Bedrock can provide cloud intelligence, while InnerOS keeps execution governed and can route suitable reasoning to sovereign local infrastructure. AgentCore can host the AWS-facing agent without forcing the private operational network into the cloud.

## 3:25–4:05 — Physical / Edge extension

Visual: Raspberry Pi / building / cameras / IoT.

> The same execution contract extends beyond software. An InnerOS Edge Node can live inside a customer network and safely interact with cameras, gateways, sensors or other authorized devices. The agent never needs to expose those devices directly to the public Internet.

## 4:05–4:35 — Real-world impact

Visual: before/after human workflow.

> We built this from the operational reality of running a technical service business. The goal is not more automation for its own sake. The metric is Human Time Returned: how much repetitive coordination disappears while humans retain control over decisions that matter.

If showing the historical internal metric, label it clearly:

`Internal historical workflow evidence: ~120 min baseline -> ~10 min assisted. Not a universal benchmark.`

## 4:35–4:55 — Close

Visual: Evidence Receipt + final architecture.

> FieldOps doesn't just answer. It executes, verifies and proves. Cloud intelligence. Sovereign execution. Verified outcomes.

## Recording rules

- Keep under 5:00.
- Prefer 4:30–4:50.
- Show the working project for the majority of the video.
- Avoid long slides.
- Make login, approval denial and post-action verification visible.
- Show real Solar, Network, Alarm and PBX status before claiming the demo is ready.
- Never imply synthetic device data is a production customer system.
- Never imply FieldOps can originate arbitrary calls; phone execution remains in VoiceOps and must show a real PASS or an exact blocker.
- Do not expose IP addresses, credentials, customer names or private infrastructure.
- Video must be publicly playable on the platform accepted by Devpost.
