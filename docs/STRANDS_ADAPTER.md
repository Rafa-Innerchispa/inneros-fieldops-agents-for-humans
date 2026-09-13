# Strands / AWS Adapter

InnerOS FieldOps is intentionally orchestrator-neutral. Strands translates agent
intent into bounded FieldOps contracts instead of giving the model direct access
to arbitrary shell, network or physical operations.

## Implemented runtime

The repository now has two Strands-facing layers:

1. `src.fieldops.strands_adapter.execute_field_action(...)` remains a
   dependency-free bounded function that wraps the governed FieldOps workflow.
2. `src.fieldops.strands_runtime.build_fieldops_agent(...)` imports the actual
   Strands Agents SDK, instantiates `strands.Agent` and exposes FieldOps tools.
3. `scripts/demo_strands.py` proves direct tool invocation through
   `agent.tool.execute_fieldops_demo(...)`.

This keeps the reusable FieldOps core green without AWS credentials, while still
providing real SDK evidence for the hackathon submission path.

## Current Strands tools

- `execute_fieldops_demo(scenario)` runs the credential-free approved synthetic
  scenario and returns an Evidence Receipt JSON payload.
- `read_inneros_readonly_context()` returns non-secret InnerOS runtime context
  and explicitly reports that mutation is not allowed.

Future production tools should preserve the same boundary:

- `get_customer_context(ref)` -> sanitized operational context from InnerOS/MCP.
- `get_system_state(target_ref)` -> current state/evidence references.
- `propose_action(target_ref, objective)` -> bounded ActionRequest candidate.
- `request_human_approval(action)` -> external approval artifact; never synthesize APPROVED.
- `execute_field_action(action, approval)` -> FieldOps governed execution boundary.
- `verify_outcome(correlation_id)` -> independent resulting-state observation.
- `get_evidence_receipt(correlation_id)` -> auditable receipt/reference.
- `create_work_order(...)` -> optional Service Operations handoff when remote remediation is impossible.

## Security boundary

The Strands model must never receive an unrestricted shell or arbitrary URL
execution tool. It selects from bounded capabilities whose policy and
authorization are enforced outside the model.

## Model routing

Strands can use Bedrock when an AWS-facing deployment requires it. InnerOS
Resource Fabric may use the registered local AMD runtime for private/local
reasoning. Route evidence should record the actual selected
provider/model/location and reason rather than hardcoding it.

## Bedrock readiness

Live Bedrock invocation remains optional and owner-approved. Required non-secret
configuration is documented in `.env.example`; secrets must come from the runtime
environment, AWS SSO, instance profiles or IAM roles, never from the repository.

Minimum owner action for a live Bedrock run:

```bash
export FIELDOPS_MODEL_PROVIDER=bedrock
export FIELDOPS_BEDROCK_MODEL_ID=<approved-bedrock-model-id>
export AWS_REGION=us-west-2
aws sts get-caller-identity
python scripts/demo_strands.py --scenario happy
```

Without `FIELDOPS_BEDROCK_MODEL_ID`, the Bedrock provider fails closed before any
network/model call.

## AgentCore

AgentCore is optional. `agentcore/fieldops_agent.py` exposes a deployable
entrypoint that creates the same Strands Agent used locally.
`agentcore/agentcore.example.json` is a secret-free configuration template for
the deployment owner. Add live AgentCore deployment only when it improves
deployment, observability or a competition requirement.

## InnerOS context

`src.fieldops.inneros_adapter` exposes read-only runtime context only. It never
performs mutation and reports that governed action requests must pass through the
FieldOps approval boundary.

## Implementation order

1. Keep synthetic adapter green.
2. Keep the actual Strands SDK runtime green.
3. Keep deterministic tests passing without AWS credentials.
4. Add Bedrock/AgentCore live path only with credentials and an explicit test environment.
5. Record live evidence separately from synthetic evidence.
