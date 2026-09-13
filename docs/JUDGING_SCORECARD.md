# Agents for Humans — Internal Judging Scorecard

Official judging uses five equally weighted criteria, each scored on a 5-point scale.

Do not submit until the evidence below supports a credible score.

## 1. Technological Implementation

Target: 4.5–5/5

Evidence required:

- real Strands Agents SDK usage in the working path;
- non-trivial tool/action orchestration;
- approval gates enforced in code;
- independent post-action verification;
- Evidence Receipt generated;
- tests pass;
- Bedrock invocation proven if feasible;
- AgentCore deployment or live demo if feasible without destabilizing the build.

Main risk: Strands exists only as a decorative import while the demo bypasses it.

## 2. Design

Target: 4.5/5

Evidence required:

- one coherent incident-to-resolution experience;
- human sees decisions, approvals and final outcome rather than internal plumbing;
- clear states: investigating, approval required, executing, verifying, resolved/escalated;
- no requirement to operate five dashboards.

Main risk: terminal-only engineering demo with no understandable product story.

## 3. Potential Impact

Target: 5/5

Evidence required:

- specific audience: field-service / technical operations SMBs;
- credible operational pain: fragmented coordination and verification;
- PC Doctor operational context as motivation without exposing customer data;
- Human Time Returned as the product metric;
- historical 120->10 example labeled internal and non-universal.

Main risk: generic claims about "saving time with AI."

## 4. Creativity & Originality

Target: 5/5

Differentiators to demonstrate:

- digital-to-physical execution;
- independent verification rather than trusting command success;
- local/cloud hybrid routing;
- edge node inside private networks;
- Evidence Receipt;
- agent interrupts humans only for judgment/approval;
- one execution contract across APIs, edge devices and human technicians.

Main risk: presenting FieldOps as another AIOps or ticket-triage agent.

## 5. Presentation

Target: 4.5–5/5

Evidence required:

- working demo dominates video;
- problem, audience and importance explained within first minute;
- approval-denied path visible;
- successful execute->verify->evidence path visible;
- architecture readable in seconds;
- close with one memorable thesis.

Recommended close:

**FieldOps doesn't just answer. It executes, verifies and proves.**

## Go / No-Go threshold

A hackathon submission is worth the remaining time if:

- Strands is genuinely in the execution path;
- local E2E demo passes reliably;
- repository/setup are reproducible;
- architecture diagram can be produced;
- video can be recorded without emergency debugging;
- AWS Builder ID is available;
- submission can be completed with margin before deadline.

If those conditions are not met, preserve the project for the next competition rather than shipping a misleading or fragile demo.
