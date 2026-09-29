"""Fictional adapter contracts only; no model, tokenizer or baseline quality."""
from dataclasses import replace
import hashlib

from cognitive_kernel.contracts import ProductHostScope, ProvenanceReference
from cognitive_kernel.experience import ExperienceEvent
from flora.comparator import (
    BaselineConfiguration, EmbeddingBatch, MemoryConfiguration, ProviderConfiguration,
    ProviderResponse, TokenCount, encoded, sha,
)
from flora.comparison_run import ArmBinding, HistorySnapshot, PairedRunPlan, SourceMaterial
from flora.evaluation_protocol import ARMS, EvaluationCase, EvaluationProtocol


def configuration():
    return BaselineConfiguration(ProviderConfiguration("fixture-provider", "fixture-feature", "fixture-snapshot",
        ("fixture-snapshot",), "https://fixture.invalid/generate", b'{"temperature":0}', "1" * 64, "2" * 64),
        MemoryConfiguration("3" * 64, "4" * 64, "5" * 64, "6" * 64, 2, 256, 32, 16, 60, 128, 1),
        b"Use authorized evidence, preserve chronology and uncertainty, and distinguish corrections from original statements.")


class FixtureCompiler:
    artifact_sha256 = "2" * 64
    def compile(self, *, configuration, semantic_input, response_token_budget):
        return encoded({"model": configuration.requested_model_id,
                        "input": semantic_input.decode(), "maximum_output_tokens": response_token_budget})


class FixtureByteCounter:
    """A byte-count stand-in used solely to test budget mechanics."""
    def count(self, content):
        return TokenCount(sha(content), "5" * 64, "6" * 64, len(content))


class FixtureEmbeddings:
    async def embed(self, content):
        # Two arbitrary positive numbers; not trained or called semantic quality.
        return EmbeddingBatch(tuple(sha(value) for value in content), "3" * 64, "4" * 64,
                              tuple((float(len(value) + 1), 1.0) for value in content))


def inputs(host="fixture-host", *, actual_sources=None):
    scope = ProductHostScope.create(product_id="friday", host_instance_id=host,
                                     schema_version="1.0.0", encryption_domain="key-" + host)
    if actual_sources is None:
        sources = []
        for index, plaintext in enumerate((b"Fictional host prefers calm planning for a project.",
                                          b"Correction: the project needs a concise plan this time.")):
            event = ExperienceEvent.create(event_type="observation" if index == 0 else "correction", scope=scope,
                occurred_at=f"2020-01-0{index + 1}T12:00:00Z", content_digest=sha(plaintext),
                provenance=ProvenanceReference.create(provenance_type="generated_reconstruction",
                    source_reference_ids=("fictional-source-" + str(index),),
                    derivation_activity_id="comparator-contract-fixture", responsible_component="synthetic-test"),
                retention_class="ordinary_experience", storage_tier="raw_buffer",
                parent_event_ids=() if not index else (sources[0].event.event_id,),
                payload_reference="fixture-object-" + str(index))
            sources.append(SourceMaterial(event, plaintext))
    else:
        sources = actual_sources
        scope = sources[0].event.scope
    histories = {("case", "before"): HistorySnapshot(scope, tuple(sources[:1])),
                 ("case", "after"): HistorySnapshot(scope, tuple(sources))}
    question = b"How should the fictional host plan this project?"
    case = EvaluationCase("case", host, "relevant_correction", "heldout",
        histories[("case", "before")].digest(), histories[("case", "after")].digest(), "7" * 64, sources[-1].event.event_id)
    protocol = EvaluationProtocol("fixture-comparator-protocol", "8" * 64, "2026-09-29T00:00:00Z",
        "fixture-feature", 32, 10000, (case,), "9" * 64, "a" * 64, "b" * 64, "c" * 64, ("other-host",))
    config = configuration()
    bindings = {arm: ArmBinding(config.producer_component, config.provider.digest(), config.digest(),
                                "source-memory-without-native-update") for arm in ARMS}
    plan = PairedRunPlan(protocol, bindings, 20000, 20000, 1, {"case": sha(question)})
    return histories, question, plan


def signed_response(request, marker, signing_key, *, returned_model="fixture-snapshot"):
    output = b"Supplied fictional output. No model inference occurred."
    response = ProviderResponse(request.configuration.digest(), sha(request.payload), "fixture-request",
        returned_model, encoded({"output": output.decode(), "usage": {"input": len(request.payload), "output": 9}}),
        output, len(request.payload), 9, marker, b"unsigned")
    return replace(response, proof=signing_key.sign(encoded(response.observation())))
