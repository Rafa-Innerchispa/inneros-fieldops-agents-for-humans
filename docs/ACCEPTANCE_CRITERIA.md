# MVP Acceptance Criteria

FieldOps is not considered operational merely because an agent prints a plausible answer.

## P0 — must pass

- [ ] Clean install from repository instructions.
- [ ] `pytest` passes locally.
- [ ] Synthetic E2E demo runs without cloud credentials.
- [ ] A risky action cannot execute without approval.
- [ ] A rejected approval produces no execution side effect.
- [ ] Execution failure cannot be reported as resolved.
- [ ] Verification failure cannot be reported as resolved.
- [ ] Successful workflow returns a structured Evidence Receipt.
- [ ] Evidence receipt contains correlation/trace identity, action, approval reference when required, executor, execution result and verification result.
- [ ] No customer data, LAN addresses, credentials or secrets are committed.

## P1 — AWS/Strands

- [ ] Strands adapter invokes the same provider-neutral FieldOps workflow.
- [ ] Core tests remain independent from AWS/network access.
- [ ] Bedrock provider is configurable rather than hard-coded.
- [ ] One real Bedrock-backed agent run succeeds.
- [ ] Agent tool calls cannot bypass approval or verification policy.
- [ ] AWS setup is reproducible from documentation.

## P1 — InnerOS integration

- [ ] MCP adapter uses a narrow allowlisted capability surface.
- [ ] Resource Fabric records/controls model/provider routing.
- [ ] Existing Audit Fabric semantics are reused rather than duplicated.
- [ ] Real executor and verifier are separate interfaces.
- [ ] Integration failure fails closed.

## P2 — Edge / Physical

- [ ] Raspberry Pi / mini-PC can register as an edge executor.
- [ ] Edge communication is outbound-first or otherwise securely brokered.
- [ ] Device actions are allowlisted.
- [ ] Independent post-action observation verifies physical/digital state.
- [ ] Evidence metadata can be returned to InnerOS.

## Demo-ready gate

A demo is ready when a non-developer can observe this sequence without explanation:

```text
Problem detected
-> agent understands operational context
-> action proposed
-> approval requested only if needed
-> action executed
-> resulting state independently verified
-> evidence produced
-> human receives outcome or escalation
```

The demo should finish with a human-readable result such as:

> Resolved autonomously. Verified healthy. No action required.

or, when the system cannot prove success:

> Not resolved. Verification failed. Human intervention required.

## Submission-ready gate

For a future hackathon submission additionally require:

- public repository and appropriate license;
- pre-existing work disclosure compliant with that event's rules;
- architecture image, not only Mermaid source;
- short end-to-end video showing the working system;
- setup instructions tested from a clean environment;
- explicit explanation of what was built during the eligibility window;
- no claims unsupported by evidence.

Historical metrics such as 120 -> 10 minutes may only be used with their correct evidence/disclosure. They must not be presented as canonical verified HTR when the canonical verification contract has not been satisfied.
