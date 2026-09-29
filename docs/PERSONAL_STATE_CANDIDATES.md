# Personal-state candidate registry

FloRA's host, relationship, and assistant-self states are different subjects. The selected A.L.I.C.E. `ProjectionVersion` contract records each version's subject, source lineage, content digest, validity, generation, and predecessor. FloRA stores these candidate versions in XTDB; private content stays in the encrypted object plane.

`XTDBPersonalStateCandidates` accepts only the corresponding `owner_model`, `relationship_model`, or `self_model` projection. The owner subject must be the current host. It checks that cited claim versions are still current and that their source objects agree with KurrentDB Experience, or checks directly cited Experience events against their raw objects. The registry serializes revisions with an expected predecessor and rechecks source freshness on read. A correction can therefore make a candidate unreadable until a governed revision is made.

Activation is a separate XTDB head. A matching `state_activation_approval` Experience event carries an exact private request bound to the candidate's version and digest. A trusted product-supplied `StateApprovalVerifier` must independently authenticate and authorize that event. Activation uses an expected previous active version; reads recheck the current sources, exact approval payload, and verifier. A candidate is never active merely because it was registered.

This is **infrastructure**, not a personal model or a learning result. It accepts externally supplied content, and FloRA does not yet provide a production owner-authentication adapter or an activation policy. The integration verifier is synthetic. No judgment model consumes the active state yet. Episode-only sources await the selected episode plane. Model qualification, outcome-driven updates, rollback governance, and behavioral intervention tests remain open.

The synthetic selected-backend integration case registers all three subjects, revises the host candidate, rejects a stale predecessor and missing raw evidence, and checks an exact activation approval. These checks qualify storage and lineage behavior only.
