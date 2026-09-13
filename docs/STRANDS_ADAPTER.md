# Strands adapter plan

InnerOS FieldOps is intentionally orchestrator-neutral. A Strands adapter should translate agent intent into the bounded FieldOps contracts instead of giving the model direct access to arbitrary shell, network or physical operations.

## Proposed Strands tools

- `get_customer_context(ref)` -> sanitized operational context from InnerOS/MCP.
- `get_system_state(target_ref)` -> current state/evidence references.
- `propose_action(target_ref, objective)` -> bounded ActionRequest candidate.
- `request_human_approval(action)` -> external approval artifact; never synthesize APPROVED.
- `execute_field_action(action, approval)` -> FieldOps governed execution boundary.
- `verify_outcome(correlation_id)` -> independent resulting-state observation.
- `get_evidence_receipt(correlation_id)` -> auditable receipt/reference.
- `create_work_order(...)` -> optional Service Operations handoff when remote remediation is impossible.

## Security boundary

The Strands model must never receive an unrestricted shell or arbitrary URL execution tool. It selects from bounded capabilities whose policy and authorization are enforced outside the model.

## Model routing

Strands can use Bedrock when an AWS-facing deployment requires it. InnerOS Resource Fabric may use the registered local AMD runtime for private/local reasoning. Route evidence should record the actual selected provider/model/location and reason rather than hardcoding it.

## AgentCore

AgentCore is optional. Add it only when it improves deployment, observability or a competition requirement. The reusable FieldOps core must not depend on AgentCore to function.

## Implementation order

1. Keep synthetic adapter green.
2. Add a Strands dependency behind an optional extra.
3. Implement tool wrappers around provider-neutral FieldOps contracts.
4. Add a mock MCP context provider.
5. Run deterministic tests without AWS credentials.
6. Add Bedrock/AgentCore live path only with credentials and an explicit test environment.
7. Record live evidence separately from synthetic evidence.
