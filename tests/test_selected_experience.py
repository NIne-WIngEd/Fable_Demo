import hashlib
import json
import unittest

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from fable_demo.selected.experience import KurrentExperienceLog, decode_event, encode_event, event_uuid, stream_name


def event_for(host: str) -> ExperienceEvent:
    scope = ProductHostScope.create(product_id="friday", host_instance_id=host,
        schema_version="1.0.0", encryption_domain=f"key-{host}")
    return ExperienceEvent.create(event_type="observation", scope=scope,
        occurred_at="2026-09-29T00:00:00Z", content_digest=hashlib.sha256(b"synthetic").hexdigest(),
        provenance=ProvenanceReference.create(provenance_type="derived_inference",
            source_reference_ids=("raw-a1",), derivation_activity_id="synthetic-ingest",
            responsible_component="synthetic-test"), retention_class="ordinary_experience",
        storage_tier="raw_buffer", payload_reference="raw-a1")


class CallRecorder:
    def append_to_stream(self, **kwargs):
        self.kwargs = kwargs


class SelectedExperienceContractTest(unittest.TestCase):
    def test_envelope_round_trip_and_cross_host_rejection(self):
        event = event_for("host-one")
        self.assertEqual(decode_event(encode_event(event), event.scope), event)
        self.assertNotIn("host-one", stream_name(event.scope))
        with self.assertRaisesRegex(ValueError, "host scope"):
            decode_event(encode_event(event), event_for("host-two").scope)
        corrupted = json.loads(encode_event(event))
        corrupted["content_digest"] = "0" * 64
        with self.assertRaises(Exception):
            decode_event(json.dumps(corrupted).encode(), event.scope)

    def test_kurrent_append_uses_expected_revision_and_stable_event_id(self):
        event = event_for("host-one")
        client = CallRecorder()
        log = KurrentExperienceLog(scope=event.scope, client=client)
        log.append(event, expected_revision=-1)
        from kurrentdbclient import StreamState
        self.assertEqual(client.kwargs["stream_name"], stream_name(event.scope))
        self.assertEqual(client.kwargs["current_version"], StreamState.NO_STREAM)
        sent = client.kwargs["events"][0]
        self.assertEqual(sent.id, event_uuid(event))
        self.assertEqual(decode_event(sent.data, event.scope), event)
        log.append(event, expected_revision=0)
        self.assertEqual(client.kwargs["current_version"], 0)
        with self.assertRaisesRegex(ValueError, "different host"):
            log.append(event_for("host-two"), expected_revision=0)


if __name__ == "__main__":
    unittest.main()
