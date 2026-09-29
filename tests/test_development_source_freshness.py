"""Current original-use grants must precede each derived-source plaintext read."""
import unittest
from flora.selected.development_sources import RegisteredDevelopmentSourceGuard
import test_governed_development as helpers


class DevelopmentSourceFreshnessTest(unittest.TestCase):
    def setUp(self):
        self.f = helpers.GovernedDevelopmentContractTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        f=self.f
        self.guard=RegisteredDevelopmentSourceGuard(f.scope,f.namespace,f.registry,f.policy)

    def check(self, evidence=(), claims=()):
        f=self.f
        return self.guard.check(source_evidence_ids=evidence,source_claim_version_ids=claims,
            source_records=tuple(evidence)+tuple(claims),**f.inputs())

    def test_one_original_read_revoking_a_later_source_never_opens_later_plaintext(self):
        f=self.f
        opened,original=[],f.objects.get
        expected={f.source_one.payload_reference:f.source_one.event_id,
                  f.source_two.payload_reference:f.source_two.event_id}
        victim=[]
        def revoke_other(raw):
            content=original(raw)
            opened.append(raw.object_id)
            if len(opened)==1:
                other=next(item for item in expected if item!=raw.object_id)
                victim.append(other)
                f.policy.allowed.discard((expected[other],"personal_judgment"))
            return content
        f.objects.get=revoke_other
        with self.assertRaisesRegex(ValueError,"authority changed before raw read"):
            self.check(evidence=(f.source_one.event_id,f.source_two.event_id))
        self.assertEqual(len(opened),1)
        self.assertNotIn(victim[0],opened)

    def claim(self):
        f=self.f
        relation="fictional-live-claim-relation"
        version="fictional-live-claim-v1"
        f.claims.versions[version]={"claim_id":"fictional-live-claim","claim_version_id":version,
            "adjudication_state":"accepted","evidence_relation_ids":[relation],
            "envelope":{"scope":f.scope.metadata_record(),"authority_namespace_id":f.namespace,
                        "source_records":[f.source_one.event_id]}}
        f.claims.relations[relation]={"evidence_record_id":f.source_one.event_id,
            "target_record_id":version,"target_record_type":"claim_version"}
        f.claims.current["fictional-live-claim"]={"claim_id":"fictional-live-claim",
            "current_claim_version_id":version,"projection_id":"fictional-live-projection",
            "validity_state":"current","deletion_state":"active","conflict_state":"none",
            "adjudication_state":"accepted"}
        return version

    def test_claim_reader_live_denial_is_checked_before_second_plaintext_open(self):
        f=self.f
        version=self.claim()
        original_load,original_get=f.claims.load_current,f.objects.get
        current_reads,opened=[],[]
        def deny_at_claim_reader(claim_id):
            current_reads.append(claim_id)
            if len(current_reads)==2:
                f.policy.allowed.discard((f.source_one.event_id,"personal_judgment"))
            return original_load(claim_id)
        f.claims.load_current=deny_at_claim_reader
        f.objects.get=lambda raw:(opened.append(raw.object_id),original_get(raw))[1]
        with self.assertRaisesRegex(PermissionError,"not permitted before raw read"):
            self.check(claims=(version,))
        self.assertEqual(opened,[f.source_one.payload_reference])

    def test_claim_reader_denial_during_raw_read_never_returns_a_packet(self):
        f=self.f
        version=self.claim()
        original=f.objects.get
        opened=[]
        def revoke_on_claim_read(raw):
            content=original(raw)
            opened.append(raw.object_id)
            if len(opened)==2:
                f.policy.allowed.discard((f.source_one.event_id,"personal_judgment"))
            return content
        f.objects.get=revoke_on_claim_read
        with self.assertRaisesRegex(PermissionError,"permission changed during raw read"):
            self.check(claims=(version,))
        self.assertEqual(opened,[f.source_one.payload_reference]*2)

    def test_original_cipher_lookup_denial_prevents_plaintext_get(self):
        f=self.f
        backend_get=f.objects.backend.get_object
        original_get=f.objects.get
        opened=[]
        def deny_on_cipher(namespace,object_id):
            ciphertext=backend_get(namespace,object_id)
            if object_id==f.source_one.payload_reference:
                f.policy.allowed.discard((f.source_one.event_id,"personal_judgment"))
            return ciphertext
        f.objects.backend.get_object=deny_on_cipher
        f.objects.get=lambda raw:(opened.append(raw.object_id),original_get(raw))[1]
        with self.assertRaisesRegex(ValueError,"authority changed during read"):
            self.check(evidence=(f.source_one.event_id,))
        self.assertEqual(opened,[])
