"""Explicit host-statement candidate lane on A.L.I.C.E.'s released Memory Core.

The full Fable Memory Formation Model is not implemented here. An owner supplies
a key for one statement; the candidate gate keeps it non-authoritative until a
separate confirmation promotes it. This compatibility lane is single-host.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import uuid

from .runtime import FableRuntime, _utc_now

_KEY = re.compile(r"^[a-z][a-z0-9._-]{0,95}$")
_NAMESPACE = uuid.UUID("ac6637b7-a83a-4c57-b407-1f9b9031e2e3")


class MemoryLane:
    def __init__(self, runtime: FableRuntime):
        self.runtime = runtime

    def _observation(self, logical_id: str):
        with self.runtime._stores() as (raw, ledger):
            self.runtime._append_missing(raw, ledger)
            for reference in raw.inspect():
                if reference.logical_record_id == logical_id:
                    return (self.runtime._unseal(raw.load_opaque_payload(reference.reference_id), logical_id),
                            reference, next(event for event in (ledger.load_event(item.event_id) for item in ledger.inspect())
                                            if event.payload_reference == reference.reference_id))
        raise KeyError(logical_id)

    def stage_host_statement(self, *, logical_id: str, key: str, category: str = "profile") -> dict:
        return self._stage(logical_id=logical_id, key=key, category=category, kind="statement")

    def stage_host_correction(self, *, logical_id: str, key: str, category: str = "profile") -> dict:
        return self._stage(logical_id=logical_id, key=key, category=category, kind="correction")

    def _stage(self, *, logical_id: str, key: str, category: str, kind: str) -> dict:
        from alice_memory.candidate_assessment import MemoryCandidateAssessmentAuthorization, assess_memory_candidate
        from alice_memory.formation import (MemoryCandidateCreateRequest, MemoryCandidateWriteAuthorization,
                                            load_memory_candidate, propose_memory_candidate,
                                            MemoryCandidateAlreadyExistsError)
        from alice_memory.sources import MemorySourceSpec
        from alice_memory.store import open_memory_store

        if not _KEY.fullmatch(key) or category not in {"profile", "goal", "project"}:
            raise ValueError("unsupported memory key or category")
        observation, reference, event = self._observation(logical_id)
        if observation.kind != kind or observation.subject != "host":
            raise ValueError("only explicit host statements or corrections enter this candidate lane")
        if kind == "correction" and len(event.parent_event_ids) != 1:
            raise ValueError("correction requires one linked source event")
        candidate_id = str(uuid.uuid5(_NAMESPACE, f"{logical_id}:{key}"))
        source = MemorySourceSpec(source_type="approved_manual_entry", source_ref=event.event_id,
                                  support_relation="supports", source_content_sha256=reference.content_digest,
                                  source_text_sha256=hashlib.sha256(observation.text.encode()).hexdigest(),
                                  source_date=observation.occurred_at)
        request = MemoryCandidateCreateRequest(candidate_id=candidate_id, content=observation.text,
            category=category, knowledge_status="rayan_statement", confidence=1.0,
            data_classification="PRIVATE", recorded_at=observation.occurred_at,
            valid_from=observation.occurred_at, time_precision="day",
            sources=(source,), origin="explicit_user", memory_key=f"demo.host.{key}",
            rayan_confirmed=False)
        with open_memory_store(self.runtime.vault) as connection:
            try:
                candidate = propose_memory_candidate(connection, request=request,
                    authorization=MemoryCandidateWriteAuthorization(actor="fable-demo-host", allowed=True,
                        reason="explicit host statement from sealed event"), proposed_at=observation.occurred_at)
            except MemoryCandidateAlreadyExistsError:
                candidate = load_memory_candidate(connection, candidate_id=candidate_id)
                if candidate.content_sha256 != hashlib.sha256(observation.text.encode()).hexdigest() or candidate.memory_key != request.memory_key:
                    raise ValueError("candidate identity was reused for changed content")
            assessment = assess_memory_candidate(connection, candidate_id=candidate_id,
                authorization=MemoryCandidateAssessmentAuthorization(actor="fable-demo-gate", allowed=True,
                    reason="deterministic assessment"), assessed_at=observation.occurred_at)
            candidate = load_memory_candidate(connection, candidate_id=candidate_id)
        return {"candidate_id": candidate_id, "state": candidate.candidate_state,
                "assessment": assessment.outcome, "reasons": assessment.reason_codes,
                "source_event_id": event.event_id}

    def confirm(self, candidate_id: str, *, target_memory_id: str | None = None) -> dict:
        from alice_memory.promotion import MemoryCandidatePromotionAuthorization, promote_memory_candidate
        from alice_memory.formation import load_memory_candidate
        from alice_memory.provenance import list_memory_sources
        from alice_memory.service import load_memory
        from alice_memory.store import open_memory_store
        from alice_memory.transition_promotion import (MemoryCandidateTransitionAuthorization,
                                                        promote_memory_candidate_with_transition)
        from .runtime import _utc_now

        with open_memory_store(self.runtime.vault) as connection:
            candidate = load_memory_candidate(connection, candidate_id=candidate_id)
            if candidate.origin != "explicit_user" or not candidate.memory_key or not candidate.memory_key.startswith("demo.host."):
                raise ValueError("only a staged explicit host candidate can use this confirmation path")
            sources = connection.execute("SELECT source_ref FROM memory_candidate_sources WHERE candidate_id = ?",
                                         (candidate_id,)).fetchall()
            if len(sources) != 1:
                raise ValueError("host candidate requires exactly one source event")
            with self.runtime._stores() as (_raw, ledger):
                self.runtime._append_missing(_raw, ledger)
                event = ledger.load_event(str(sources[0]["source_ref"]))
                if event.scope != self.runtime.scope:
                    raise ValueError("candidate source belongs to another host")
            if target_memory_id is None and event.event_type != "host-statement":
                raise ValueError("a host correction requires its target memory")
            if target_memory_id is not None and event.event_type != "host-correction":
                raise ValueError("only a linked host correction can replace a memory")
            if target_memory_id is not None:
                target = load_memory(connection, memory_id=target_memory_id)
                if target.memory_key != candidate.memory_key:
                    raise ValueError("correction target has a different memory key")
                if event.event_type != "host-correction" or len(event.parent_event_ids) != 1:
                    raise ValueError("candidate is not a linked host correction")
                if event.parent_event_ids[0] not in {item.source_ref for item in list_memory_sources(connection, memory_id=target_memory_id)}:
                    raise ValueError("correction target differs from its recorded parent")
                result = promote_memory_candidate_with_transition(connection, candidate_id=candidate_id,
                    authorization=MemoryCandidateTransitionAuthorization(actor="fable-demo-host", allowed=True,
                        candidate_id=candidate_id, target_memory_id=target_memory_id,
                        transition_type="correction", authorization_id=f"host-correct-{candidate_id}",
                        user_confirmed=True, reason="explicit demo host correction"), promoted_at=_utc_now())
                return {"candidate_id": candidate_id, "memory_id": result.memory.memory_id,
                        "replaced_memory_id": target_memory_id, "memory_key": result.memory.memory_key}
            result = promote_memory_candidate(connection, candidate_id=candidate_id,
                authorization=MemoryCandidatePromotionAuthorization(actor="fable-demo-host", allowed=True,
                    candidate_id=candidate_id, authorization_id=f"host-confirm-{candidate_id}",
                    user_confirmed=True, reason="explicit demo host confirmation"), promoted_at=_utc_now())
            return {"candidate_id": candidate_id, "memory_id": result.memory.memory_id,
                    "assessment": result.assessment_outcome, "memory_key": result.memory.memory_key}

    def current(self, *, key: str) -> list[dict]:
        from alice_memory.provenance import list_memory_sources
        from alice_memory.service import MemoryContentAccessAuthorization, load_memory_content
        from alice_memory.store import open_memory_store
        from alice_memory.temporal import resolve_memory_at

        if not _KEY.fullmatch(key):
            raise ValueError("invalid memory key")
        with open_memory_store(self.runtime.vault) as connection:
            state = resolve_memory_at(connection, memory_key=f"demo.host.{key}", at=_utc_now())
            auth = MemoryContentAccessAuthorization(actor="fable-demo-host", allowed=True,
                                                     reason="local demo memory inspection")
            return [{"memory_id": item.memory_id,
                     "text": load_memory_content(connection, memory_id=item.memory_id, authorization=auth),
                     "source_event_ids": [source.source_ref for source in list_memory_sources(connection, memory_id=item.memory_id)]}
                    for item in state.memories]

    def history(self, *, key: str) -> list[dict]:
        """Inspect provenance-linked current and superseded versions for one key."""
        from alice_memory.provenance import list_memory_sources
        from alice_memory.service import MemoryContentAccessAuthorization, load_memory_content
        from alice_memory.store import open_memory_store
        from alice_memory.temporal import list_memory_history

        if not _KEY.fullmatch(key):
            raise ValueError("invalid memory key")
        with open_memory_store(self.runtime.vault) as connection:
            records = list_memory_history(connection, memory_key=f"demo.host.{key}")
            auth = MemoryContentAccessAuthorization(actor="fable-demo-host", allowed=True,
                                                     reason="local demo history inspection")
            return [{"memory_id": item.memory_id, "validity_state": item.validity_state,
                     "recorded_at": item.recorded_at,
                     "text": load_memory_content(connection, memory_id=item.memory_id, authorization=auth),
                     "source_event_ids": [source.source_ref for source in list_memory_sources(connection, memory_id=item.memory_id)]}
                    for item in records]
