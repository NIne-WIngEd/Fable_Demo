"""Real embedded LadybugDB checks for exact graph index behavior."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ladybug

from cognitive_kernel.contracts import ProductHostScope
from flora.selected.graph_recollection import LadybugEvidenceGraph
from flora.selected.source_native import (
    CurrentEvidencePacket, CurrentSourceManifest, SourceManifestItem, VerifiedSource,
)


class _Authority:
    def __init__(self, scope):
        self.scope = scope
        self.current = "v1"
        self.deleted = False

    def load_version(self, version):
        return {"evidence_relation_ids": ["r1"]}

    def load_evidence_relation(self, relation):
        return {"relation_type": "support"}

    def load_current(self, claim):
        return {"current_claim_version_id": self.current,
                "projection_id": "p1", "deletion_state": (
                    "pending" if self.deleted else "active")}


class _Scoped:
    def __init__(self, scope):
        self.scope = scope


class SelectedGraphTest(unittest.TestCase):
    def test_current_query_rechecks_authority_and_shared_database_scope(self):
        host = ProductHostScope.create(
            product_id="friday", host_instance_id="synthetic-host-one",
            schema_version="1.0.0", encryption_domain="synthetic-one")
        other = ProductHostScope.create(
            product_id="friday", host_instance_id="synthetic-host-two",
            schema_version="1.0.0", encryption_domain="synthetic-two")
        with tempfile.TemporaryDirectory() as directory:
            conn = ladybug.Connection(ladybug.Database(str(Path(directory) / "graph")))
            graph = LadybugEvidenceGraph(scope=host, connection=conn)
            another = LadybugEvidenceGraph(scope=other, connection=conn)
            graph.ensure_schema()
            another.ensure_schema()
            source = CurrentEvidencePacket(
                "c1", "v1", "p1", (VerifiedSource("e1", "r1", "a" * 64,
                                                    b"synthetic"),))
            first = _Authority(host)
            second = _Authority(other)
            manifest = CurrentSourceManifest("c1", "v1", "p1",
                (SourceManifestItem("e1", "r1", "a" * 64),))
            with patch("flora.selected.graph_recollection.read_current_sources",
                       return_value=source), patch(
                    "flora.selected.graph_recollection.read_current_source_manifest",
                    return_value=manifest):
                graph.project_current(claim_id="c1", authority=first,
                                      log=_Scoped(host), objects=_Scoped(host),
                                      references={})
                another.project_current(claim_id="c1", authority=second,
                                        log=_Scoped(other), objects=_Scoped(other),
                                        references={})
                self.assertEqual(len(graph.related_current(
                    source_event_id="e1", authority=first, log=_Scoped(host),
                    objects=_Scoped(host), references={})), 1)
                first.deleted = True
                self.assertEqual(graph.prune_noncurrent(
                    claim_id="c1", authority=first), 1)
                self.assertEqual(len(another.related_current(
                    source_event_id="e1", authority=second,
                    log=_Scoped(other), objects=_Scoped(other), references={})), 1)


if __name__ == "__main__":
    unittest.main()
