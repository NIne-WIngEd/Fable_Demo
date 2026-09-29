# Governed proposal-to-Claim admission

`selected/formation_admission.py` connects recorded, externally supplied MFM proposals to the selected XTDB Claim authority. It builds no MFM and supplies no semantic interpretation or adjudicator.

- Recover the exact encrypted proposal, canonical value, delivered input and registered original evidence.
- Require an external interpretation and independently authenticated adjudication of that exact candidate. Source authentication alone cannot approve its meaning.
- Keep generated evidence and its parent closure inside an explicitly isolated fictional-world authority. A derived child cannot turn a synthetic ancestor into real owner testimony.
- Commit the candidate, adjudication, conflict resolution, Claim identity/version, evidence relations, current projection, namespace sequence and retry receipt in one native XTDB transaction.
- Preserve Claim identity through exact correction, and prevent a conflicting value from bypassing the occupied semantic property by choosing a different Claim ID.

Kurrent event positions and Claim store sequences are separate. Once this controller owns a namespace, legacy piecemeal Claim writes are refused, including at transaction time. An exact admitted retry returns its original immutable receipt; it does not reactivate historical authority.

This slice supports host Claim/preference additions and exact current correction revisions. Other conflict operations, governed Claim quarantine and complete derived influence removal remain open. The earlier `quarantine_claim` path is explicitly refused for controlled namespaces because its event-position ordering is incompatible. Registered source permission revocation stops later source use but is not complete deletion.

Seven deterministic boundary tests pass. A real KurrentDB/XTDB/Qdrant/LadybugDB integration case is included and awaits the selected-backend gate. Neither supplied fixture proposals nor authenticated fixture adjudications establish learned formation quality.
