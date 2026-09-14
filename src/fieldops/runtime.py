"""Product runtime for the universal FieldOps governed-action contract."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import ActionRequest, ApprovalArtifact, EvidenceReceipt, Executor, Verifier
from .governance import ActionProposal, action_policy, propose_action
from .workflow import run_action


class ActionAdapterNotBound(RuntimeError):
    pass


@dataclass(frozen=True)
class ActionBinding:
    executor: Executor
    verifier: Verifier


class GovernedActionRuntime:
    """One runtime for every FieldOps mutation domain.

    Integrations register bounded executor/verifier pairs. Proposal and approval
    semantics always come from the central registry; adapters cannot override them.
    """

    def __init__(self, *, route: str = "local-edge", route_reason: str = "local_first"):
        self.route = route
        self.route_reason = route_reason
        self._bindings: dict[str, ActionBinding] = {}

    def register(self, action_type: str, *, executor: Executor, verifier: Verifier) -> None:
        policy = action_policy(action_type)
        self._bindings[policy.action_type] = ActionBinding(executor=executor, verifier=verifier)

    def proposal(self, request: ActionRequest) -> ActionProposal:
        return propose_action(request)

    def is_bound(self, action_type: str) -> bool:
        policy = action_policy(action_type)
        return policy.action_type in self._bindings

    def execute(self, *, request: ActionRequest, approval: ApprovalArtifact) -> EvidenceReceipt:
        policy = action_policy(request.action_type)
        binding = self._bindings.get(policy.action_type)
        if binding is None:
            raise ActionAdapterNotBound(
                f"No executor/verifier binding is installed for {policy.action_type!r}"
            )
        return run_action(
            request=request,
            approval=approval,
            executor=binding.executor,
            verifier=binding.verifier,
            route=self.route,
            route_reason=self.route_reason,
        )

    def bound_actions(self) -> tuple[str, ...]:
        return tuple(sorted(self._bindings))
