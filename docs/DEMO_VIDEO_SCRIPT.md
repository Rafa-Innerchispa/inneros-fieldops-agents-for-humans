# Demo Video Plan — maximum 5 minutes

Goal: prove end-to-end work, not narrate architecture for five minutes.

## 0:00–0:25 — Problem

Visual: service incident / FieldOps event.

Voiceover:

> Small technical-service companies lose hours every day coordinating work between messages, dashboards, devices and technicians. AI assistants can tell you what to do. FieldOps is built to actually do the work — safely — and prove that it worked.

## 0:25–0:50 — Product thesis

Visual: simple architecture.

> InnerOS FieldOps is a Strands-powered Professional Agent. It receives an operational goal, gathers context, routes work between cloud and local resources, requests approval when required, executes the action, independently verifies the result and produces an evidence receipt.

## 0:50–2:40 — Working demo

Visual: terminal or compact UI.

Scenario: synthetic camera gateway is unhealthy.

Show:

1. Incident enters FieldOps.
2. Current state is unhealthy.
3. Agent proposes `service_restart`.
4. Policy reports `approval_required`.
5. First run with pending/rejected approval stops before executor invocation.
6. Approve the action.
7. Executor performs the action.
8. Independent verifier observes `healthy=true`.
9. Evidence Receipt appears.
10. Final result: `Resolved autonomously. No further action required.`

Narration should explicitly say:

> Notice that a successful command is not considered success. FieldOps verifies the resulting state separately.

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
- Make approval denial and post-action verification visible.
- Never imply synthetic device data is a production customer system.
- Do not expose IP addresses, credentials, customer names or private infrastructure.
- Video must be publicly playable on the platform accepted by Devpost.
