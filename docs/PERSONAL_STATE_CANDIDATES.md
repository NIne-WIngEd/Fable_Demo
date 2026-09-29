# Personal-state candidate registry

FloRA's host, relationship, and assistant-self states are different subjects. The selected A.L.I.C.E. `ProjectionVersion` contract records each version's subject, source lineage, content digest, validity, generation, and predecessor. FloRA stores these candidate versions in XTDB; private content stays in the encrypted object plane.

`XTDBPersonalStateCandidates` accepts only the corresponding `owner_model`, `relationship_model`, or `self_model` projection. The owner subject must be the current host. It checks that cited claim versions are still current and that their source objects agree with KurrentDB Experience, or checks directly cited Experience events against their raw objects. The registry serializes revisions with an expected predecessor and rechecks source freshness on read. A correction can therefore make a candidate unreadable until a governed revision is made.

This is **candidate infrastructure**, not a personal model or a learning result. It accepts externally supplied content and does not infer a state, authenticate an owner, approve promotion, or feed a judgment model. `active` is rejected here. Episode-only sources await the selected episode plane. A later promotion boundary must check evidence, qualification, owner policy, and rollback before any candidate controls behavior. Outcome-driven updates and intervention tests remain open.

The synthetic selected-backend integration case registers all three subjects, revises the host candidate, rejects a stale predecessor, and rejects a read missing exact raw evidence. These checks qualify storage and lineage behavior only.
