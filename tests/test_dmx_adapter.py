from src.fieldops.contracts import ActionRequest, ApprovalArtifact, ApprovalStatus
from src.fieldops.dmx_adapter import DMXExecutor, DMXVerifier
from src.fieldops.workflow import run_action


class FakeDMXClient:
    def __init__(self):
        self.running = False
        self.current_effect = None
        self.scene_calls = []
        self.blackout_calls = 0
        self.supported_scenes = ["aurora_verde_demo", "rainbow", "blackout"]

    def status(self):
        return {
            "ok": True,
            "status": "online",
            "running": self.running,
            "current_effect": self.current_effect,
            "supported_scenes": list(self.supported_scenes),
        }

    def set_scene(self, scene, speed=1.0):
        self.scene_calls.append((scene, speed))
        self.current_effect = scene
        self.running = True
        return {"ok": True}

    def blackout(self):
        self.blackout_calls += 1
        self.running = False
        # Deliberately retain current_effect to mirror the real backend behavior.
        return {"ok": True}


def approval(ref):
    return ApprovalArtifact(
        status=ApprovalStatus.APPROVED,
        approval_id=ref,
        approver_id="owner",
        policy_version="fieldops-v1",
        evidence_ref=f"evidence://approval/{ref}",
    )


def test_real_shaped_dmx_scene_runs_through_universal_governance_and_verifies():
    client = FakeDMXClient()
    receipt = run_action(
        request=ActionRequest(
            correlation_id="dmx-scene-001",
            action_type="dmx.set_scene",
            target_ref="ag59",
            parameters={"scene": "aurora_verde_demo"},
            requires_approval=False,
        ),
        approval=approval("dmx-scene-001"),
        executor=DMXExecutor(client),
        verifier=DMXVerifier(client),
        route="local-edge",
        route_reason="physical_device_locality",
    )

    assert client.scene_calls == [("aurora_verde_demo", 1.0)]
    assert receipt.action_success is True
    assert receipt.verification_passed is True
    assert receipt.quality_gate == "passed"
    assert receipt.governance_domain == "lighting"
    assert receipt.safe_return_action == "dmx.blackout"


def test_dmx_scene_not_advertised_never_mutates():
    client = FakeDMXClient()
    receipt = run_action(
        request=ActionRequest(
            correlation_id="dmx-bad-scene",
            action_type="dmx.set_scene",
            target_ref="ag59",
            parameters={"scene": "channel_1_full"},
        ),
        approval=approval("dmx-bad-scene"),
        executor=DMXExecutor(client),
        verifier=DMXVerifier(client),
        route="local-edge",
        route_reason="test",
    )

    assert client.scene_calls == []
    assert receipt.action_success is False
    assert receipt.quality_gate == "failed"


def test_dmx_blackout_verifies_running_false_even_if_last_scene_is_stale():
    client = FakeDMXClient()
    client.current_effect = "aurora_verde_demo"
    client.running = True
    receipt = run_action(
        request=ActionRequest(
            correlation_id="dmx-blackout-001",
            action_type="dmx.blackout",
            target_ref="ag59",
        ),
        approval=approval("dmx-blackout-001"),
        executor=DMXExecutor(client),
        verifier=DMXVerifier(client),
        route="local-edge",
        route_reason="safe_return",
    )

    assert client.blackout_calls == 1
    assert receipt.verification_passed is True
    assert receipt.observed_state["running"] is False
    assert receipt.observed_state["current_scene"] == "aurora_verde_demo"


def test_executor_ack_is_not_enough_when_readback_disagrees():
    class LyingClient(FakeDMXClient):
        def set_scene(self, scene, speed=1.0):
            self.scene_calls.append((scene, speed))
            return {"ok": True}

    client = LyingClient()
    receipt = run_action(
        request=ActionRequest(
            correlation_id="dmx-readback-fail",
            action_type="dmx.set_scene",
            target_ref="ag59",
            parameters={"scene": "aurora_verde_demo"},
        ),
        approval=approval("dmx-readback-fail"),
        executor=DMXExecutor(client),
        verifier=DMXVerifier(client),
        route="local-edge",
        route_reason="test",
    )

    assert receipt.action_success is True
    assert receipt.verification_passed is False
    assert receipt.quality_gate == "failed"
