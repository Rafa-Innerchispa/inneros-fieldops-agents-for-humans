# InnerOS FieldOps — Agents for Humans Hackathon

**Cloud intelligence. Sovereign execution. Verified outcomes.**

InnerOS FieldOps is a Professional Agent built for the AWS Agents for Humans Hackathon. It uses Strands Agents to coordinate real operational work, while InnerOS and MCP tools execute approved actions against business and physical infrastructure, verify results, and produce evidence receipts.

## Hackathon scope

This repository is the hackathon-specific layer created during the submission period. It integrates Strands Agents and AWS-facing orchestration with pre-existing InnerOS components.

Pre-existing components reused and disclosed:
- InnerOS / Ralphi IA operational runtime
- MCP tools and connectors
- Local-first inference infrastructure
- Human approval gates
- Physical Guardian / field operations capabilities
- Existing evidence and audit primitives

New work for this hackathon:
- Strands Agents orchestration layer
- Professional Agent workflow for FieldOps
- AWS integration where it improves judging value
- End-to-end incident -> action -> verification -> evidence flow
- Hackathon-specific architecture, tests, demo and documentation

## Core flow

1. Receive a real operational objective or incident.
2. Gather context through MCP and InnerOS tools.
3. Reason using the Strands Agent.
4. Execute only actions allowed by policy.
5. Request human approval when required.
6. Verify the resulting state.
7. Produce a tamper-evident evidence receipt.
8. Surface to the human only when a real decision is needed.

## Target track

**Professional Agents**

## Status

Active development for the Agents for Humans Hackathon.
