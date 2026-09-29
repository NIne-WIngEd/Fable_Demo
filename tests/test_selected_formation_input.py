import hashlib
import tempfile
import unittest

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from fable_demo.selected.formation_input import formation_input
from fable_demo.selected.object_store import EncryptedObjectPlane, LocalObjectBackend


class SelectedFormationInputTest(unittest.TestCase):
    def test_only_verified_same_host_experience_enters_context(self):
        with tempfile.TemporaryDirectory() as directory:
            scope = ProductHostScope.create(product_id="friday", host_instance_id="fictional-a",
                schema_version="1.0.0", encryption_domain="key-a")
            objects = EncryptedObjectPlane(scope=scope, key=b"a" * 32,
                backend=LocalObjectBackend(directory))
            raw = objects.put(b"synthetic observation")
            event = ExperienceEvent.create(event_type="observation", scope=scope,
                occurred_at="2026-09-29T00:00:00Z", content_digest=raw.plaintext_sha256,
                provenance=ProvenanceReference.create(provenance_type="derived_inference",
                    source_reference_ids=(raw.object_id,), derivation_activity_id="synthetic-ingest",
                    responsible_component="synthetic-test"),
                retention_class="ordinary_experience", storage_tier="raw_buffer",
                payload_reference=raw.object_id)
            packet = formation_input(events=[event], references={raw.object_id: raw},
                modalities={event.event_id: "text"}, objects=objects, authority_namespace_id="host-claims")
            self.assertEqual(packet.experience_refs, (event.event_id,))
            self.assertEqual(packet.evidence[0].role, "historical_experience")
            with self.assertRaisesRegex(ValueError, "missing"):
                formation_input(events=[event], references={}, objects=objects,
                    modalities={event.event_id: "text"}, authority_namespace_id="host-claims")
            wrong = ExperienceEvent.create(event_type="observation", scope=scope,
                occurred_at="2026-09-29T00:00:00Z", content_digest=hashlib.sha256(b"wrong").hexdigest(),
                provenance=event.provenance, retention_class="ordinary_experience",
                storage_tier="raw_buffer", payload_reference=raw.object_id)
            with self.assertRaisesRegex(ValueError, "digest"):
                formation_input(events=[wrong], references={raw.object_id: raw},
                    modalities={wrong.event_id: "text"}, objects=objects, authority_namespace_id="host-claims")


if __name__ == "__main__":
    unittest.main()
