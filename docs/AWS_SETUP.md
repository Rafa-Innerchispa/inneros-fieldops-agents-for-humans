# AWS / Strands Setup

This project is designed to run locally without AWS credentials. AWS integration is an optional capability layer for hackathons or deployments where AWS adds value.

## Minimal AWS path

The smallest useful AWS integration is:

```text
Strands Agent
  -> Amazon Bedrock model provider
  -> FieldOps tools
  -> InnerOS / MCP execution boundary
```

Strands runs inside the application process. Bedrock is the default provider, but the same FieldOps workflow can run with local or other providers.

## Local-first development

Local development should remain credential-free where possible:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pytest
python scripts/demo_synthetic.py
```

The core workflow must pass without AWS.

## Strands development dependency

When enabling the Strands adapter:

```bash
pip install 'strands-agents[bedrock]'
```

Recommended implementation rule:

- import Strands lazily/optionally;
- fail with an actionable configuration error when the optional dependency is unavailable;
- never make core FieldOps tests depend on network access;
- keep secrets outside the repository.

## AWS credentials

Use one of the normal AWS credential mechanisms:

- AWS CLI profile / shared credentials file;
- environment variables;
- IAM role when running on AWS;
- Bedrock-supported API credential mechanism when appropriate.

Never commit keys or tokens.

Expected environment examples:

```text
AWS_REGION=us-west-2
FIELDOPS_MODEL_PROVIDER=bedrock
FIELDOPS_BEDROCK_MODEL_ID=<approved-model-id>
```

A `.env.example` may list variable names but must contain no secrets.

## Bedrock permissions

The runtime identity must be allowed to invoke the selected Amazon Bedrock model. Keep IAM permissions least-privilege and scoped to the capabilities actually used.

## AgentCore deployment (optional)

AgentCore is an enhancement, not a prerequisite for FieldOps.

Current AWS tooling supports a Python + Strands + Bedrock project with CodeZip deployment, avoiding a Docker requirement for the first deployment.

Conceptual command shape:

```bash
agentcore create \
  --project-name InnerOSFieldOps \
  --name FieldOpsAgent \
  --language Python \
  --framework Strands \
  --model-provider Bedrock \
  --memory none \
  --build CodeZip
```

Do not run cloud deployment from automation until credentials, permissions, region, cost policy and owner approval are confirmed.

## Target architecture

```text
Amazon Bedrock / optional AgentCore
        |
     Strands
        |
 FieldOps tools
        |
 InnerOS / MCP / Resource Fabric
        |
 approval -> executor -> verifier
        |
 Evidence Receipt / Audit Fabric
```

AWS coordinates or provides model capacity. InnerOS remains the governed execution boundary.

## Readiness gate

AWS integration is considered ready only when all of these are true:

1. local FieldOps tests pass without AWS;
2. Strands adapter can call the same provider-neutral workflow;
3. no secrets are committed;
4. Bedrock invocation succeeds with an explicitly selected model;
5. tool calls preserve approval and verification guarantees;
6. one end-to-end demo produces a valid Evidence Receipt;
7. cloud cost and routing decisions are observable;
8. AgentCore deployment, if used, is proven separately from local functionality.

## Hackathon strategy

For future AWS-focused competitions, show real AWS usage but avoid migrating unrelated InnerOS infrastructure merely for sponsor optics. The strongest story is hybrid:

**Cloud intelligence. Sovereign execution. Verified outcomes.**
