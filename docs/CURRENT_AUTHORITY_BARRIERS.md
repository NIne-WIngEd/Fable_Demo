# Current authority during private reads

Permission checks surround the actual ciphertext fetch, before authenticated
decryption, as well as the final plaintext return. Withdrawal during a slow
backend read cannot be noticed only after the private material has been opened.
These checks prevent further reads; they cannot recall material already disclosed.

The shared personal-artifact reader and native runtime reader copy the supplied
object plane and wrap its backend. They preserve the actual host key, scope and
encrypted object implementation. Nested readers retain both current gates; they
do not mutate the production object plane. Reference recovery uses the same
boundary. Enrolled owner-proof lookup receives a guarded view of those objects.

Comparison artifact recovery also checks its exact registered metadata and
current purpose immediately around the encrypted fetch. Generic recorded-event
recovery rejects comparison, provider-attempt, phase-snapshot and experiment-
manifest artifacts before private I/O. Those controls have dedicated registered
readers, including the sealed assessment path for blind identity keys.

Native context and result recovery carry the independently authorized phase
history through their inner private reads. Passive recovery never registers a
missing index; authenticated reconciliation is a separate write operation.

Nine personal-artifact tests include withdrawal during ciphertext fetch,
reference recovery and nested authority gates. Runtime, lineage and comparison
contract checks cover the corresponding selected interfaces. These are
mechanical checks; the expanded real-backend gate remains separate. They prove
neither model competence nor a FloRA behavioral advantage.
