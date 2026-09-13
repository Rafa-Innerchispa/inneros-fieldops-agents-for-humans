# InnerOS FieldOps — Reusable Roadmap

The current Agents for Humans submission was paused because the deadline conflicted with travel and higher-priority active hackathons. The project itself remains active reusable R&D.

## P0 — reusable foundation

- [ ] Reconcile the physical server checkout with GitHub `main`.
- [ ] Establish short-lived development branch/worktree.
- [ ] Add Python package structure.
- [ ] Define provider-neutral agent/orchestrator interface.
- [ ] Define executor interface.
- [ ] Define verification interface.
- [ ] Define approval artifact contract.
- [ ] Define evidence receipt schema compatible with InnerOS Audit Fabric.
- [ ] Add synthetic field incident fixture.
- [ ] Add E2E test: request -> decision -> approval policy -> action -> verification -> evidence.
- [x] Document product vision.
- [x] Document architecture.
- [x] Document pre-existing component boundary.

## P1 — Strands / AWS adapter

- [ ] Implement minimal Strands Agent.
- [ ] Wrap InnerOS/MCP capabilities as bounded tools.
- [ ] Add optional Bedrock model provider.
- [ ] Evaluate AgentCore deployment only when useful or required.
- [ ] Preserve route/evidence metadata for AWS and local execution.
- [ ] Add tests that do not require AWS credentials.

## P1 — InnerOS Edge Node

- [ ] Define EdgeNode protocol/API.
- [ ] Create Raspberry Pi OS Lite bootstrap documentation.
- [ ] Add health-check executor.
- [ ] Add HTTP executor with explicit target allowlist.
- [ ] Add MQTT adapter example.
- [ ] Add optional GPIO/relay adapter.
- [ ] Add edge verification and evidence reporting.
- [ ] Define secure outbound identity/tunnel model.
- [ ] Register edge node through canonical InnerOS capability/runtime registry.

## P1 — Physical Guardian integration

- [ ] Reuse existing Physical Guardian physical I/O adapter.
- [ ] Map FieldOps action plans to bounded Physical Guardian actions.
- [ ] Preserve approval requirements.
- [ ] Return independent verification to FieldOps.
- [ ] Generate compatible evidence references.

## P2 — product/demo experience

- [ ] Build a single operational timeline rather than another dashboard.
- [ ] Show incident -> reasoning -> approval -> execution -> verification -> evidence.
- [ ] Show routing reason: local/cloud/edge.
- [ ] Show Human Time Returned only with truthful provenance.
- [ ] Add a live physical-state demo when hardware is available.
- [ ] Prepare public demo deployment only for competitions that need it.

## Future hackathon packaging checklist

When reusing this project for another event:

1. Read the event rules first.
2. Identify mandatory sponsor technology.
3. Create only the event-specific delta.
4. Disclose all pre-existing InnerOS components.
5. Keep generic improvements reusable.
6. Freeze the submitted state by exact SHA/tag.
7. Record tests and live evidence.
8. Do not claim integrations that were not actually verified.

## Strong demo sequence

1. Realistic customer/building incident arrives.
2. Agent gathers context through tools.
3. Resource Fabric selects an allowed execution route.
4. A safe action executes automatically or a risky action requests approval.
5. Edge/software executor changes real or synthetic state.
6. Verification independently confirms the outcome.
7. Evidence receipt is produced.
8. Human sees only the resolved outcome or the decision that genuinely requires them.

## Definition of done for reusable v1

A synthetic, tenant-safe E2E must prove:

```text
request
 -> route
 -> decision
 -> approval gate
 -> execution
 -> independent verification
 -> evidence receipt
 -> quality gate
```

No production infrastructure or customer data is required to prove v1.
