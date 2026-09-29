from pathlib import Path
import tempfile
import unittest

from fable_demo.formation_context import assemble_formation_context, build_formation_manifest, bind_model_proposals
from fable_demo.memory_lane import MemoryLane
from fable_demo.runtime import FableRuntime


class FormationContextTest(unittest.TestCase):
    def test_correction_packet_reopens_with_parent_and_confirmed_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = FableRuntime.initialize(Path(directory) / "host")
            first = runtime.record(kind="statement", subject="host", text="I like calls.",
                                   occurred_at="2025-01-01T10:00:00Z")
            candidate = MemoryLane(runtime).stage_host_statement(logical_id=first["logical_id"], key="meetings")
            MemoryLane(runtime).confirm(candidate["candidate_id"])
            correction = runtime.record(kind="correction", subject="host", text="I prefer written briefs.",
                                        relates_to=first["logical_id"], occurred_at="2025-02-01T10:00:00Z")
            packet = assemble_formation_context(FableRuntime(runtime.vault), logical_id=correction["logical_id"],
                                                host_keys=("meetings",))
            self.assertEqual(packet["observation"]["event_id"], correction["event_id"])
            self.assertEqual(packet["parent_observation"]["event_id"], first["event_id"])
            self.assertEqual(packet["selected_current_host_claims"]["meetings"][0]["text"], "I like calls.")
            self.assertEqual(packet["formation_manifest"]["experience_refs"], [correction["event_id"]])
            self.assertEqual(packet["formation_manifest"]["evidence"][0]["subject_ref"], runtime.scope.host_instance_id)
            self.assertEqual(packet["formation_manifest"]["evidence"][0]["role"], "historical_experience")
            self.assertEqual(len(packet["formation_digest"]), 64)
            self.assertEqual(len(packet["packet_sha256"]), 64)

    def test_model_bundle_is_bound_to_actual_host_evidence_without_promotion(self):
        from dataclasses import replace
        from cognitive_kernel.canonical import CognitiveKernelContractError
        from cognitive_kernel.formation_contracts import FormationProposal, MemoryProposalBundle

        with tempfile.TemporaryDirectory() as directory:
            runtime = FableRuntime.initialize(Path(directory) / "host")
            observation = runtime.record(kind="observation", subject="relationship", text="We missed a meeting.")
            manifest = build_formation_manifest(runtime, logical_id=observation["logical_id"])
            proposal = FormationProposal(proposal_id="proposal-1", kind="relationship_norm",
                domain="relationship", subject_ref=f"relationship-{runtime.scope.host_instance_id}",
                value_ref="private-value-1", evidence_refs=(observation["event_id"],),
                epistemic_status="uncertain")
            bundle = MemoryProposalBundle(scope=runtime.scope, authority_namespace_id=runtime.scope.host_instance_id,
                bundle_id="bundle-1", experience_refs=manifest.experience_refs,
                context_digest=manifest.content_digest(), model_artifact_digest="a" * 64,
                inference_run_id="run-1", proposals=(proposal,))
            receipt = bind_model_proposals(runtime, logical_id=observation["logical_id"], host_keys=(), bundle=bundle)
            self.assertEqual(receipt["authority"], "none; proposals need a separate deterministic gate")
            self.assertEqual(MemoryLane(runtime).current(key="relationship"), [])
            with self.assertRaisesRegex(CognitiveKernelContractError, "matching evidence"):
                bind_model_proposals(runtime, logical_id=observation["logical_id"], host_keys=(),
                    bundle=replace(bundle, proposals=(replace(proposal, epistemic_status="owner_statement"),)))
            with self.assertRaisesRegex(CognitiveKernelContractError, "absent"):
                bind_model_proposals(runtime, logical_id=observation["logical_id"], host_keys=(),
                    bundle=replace(bundle, proposals=(replace(proposal, evidence_refs=("invented-source",)),)))
            other = FableRuntime.initialize(Path(directory) / "other")
            other_event = other.record(kind="observation", subject="relationship", text="Different host.")
            with self.assertRaisesRegex(CognitiveKernelContractError, "scope"):
                bind_model_proposals(other, logical_id=other_event["logical_id"], host_keys=(), bundle=bundle)


if __name__ == "__main__":
    unittest.main()
