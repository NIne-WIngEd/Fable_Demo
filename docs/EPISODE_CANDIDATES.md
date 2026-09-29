# Episode candidate boundary

A.L.I.C.E.'s `EpisodeRecord` keeps an autobiography distinct from raw Experience and canonical Claims. FloRA can register a supplied candidate without deciding where an episode starts, what it means, or whether it should be accepted. The learned formation producer belongs to the separate MFM workstream.

`XTDBEpisodeCandidates` persists immutable candidate generations and a serialized thread head on the selected XTDB plane. Its summary and full content remain in the encrypted object plane. Before writing or reading, it verifies every cited Experience event through KurrentDB replay and original encrypted bytes. It verifies every cited Claim version against XTDB's current head and raw sources. Corrections or quarantine invalidate a candidate at read time. A generation must cite its exact predecessor and cannot silently overwrite another thread.

This registry admits only `candidate` state and currently accepts direct Experience and current Claim sources. Candidate-to-candidate lineage, learned boundaries, narratives, acceptance policy, activation, rollback, graph projection of episodes, and episode use in context await separate qualifications. Synthetic test content only checks persistence and revocation behavior; it is not an MFM output.
