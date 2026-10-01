# Selected integration partition

Independent native-pilot and history-route cases run in separate CI jobs so one
slow case cannot consume the cap before the next case starts. The completed f3c
native-pilot job passed its first case in 1947.869 seconds, then reached the job
cap without another completed case. A retained history-route case took 3518.312
seconds, leaving about 31 seconds for the next case. These are whole-case suite
times, not paired-response timing receipts.

The runner and workflow assign the current 43 discovered physical cases exactly
once across 12 integration shards, plus the separate contracts job.

| Shard | Cases | Assignment |
| --- | ---: | --- |
| `core` | 28 | Existing general integration cases and restart probes |
| `transport` | 2 | Comparator memory and provider attempt ledger |
| `native-comparison` | 1 | Actual native paired comparison |
| `native-pilot-before-tail` | 1 | Before, accepted tail and unrelated correction |
| `native-pilot-outcome-audit` | 1 | Outcome audit, unknown tail and withdrawal |
| `native-pilot-typed-phase` | 1 | Typed phase snapshot and grant-proof join |
| `native-pilot-withdrawal` | 1 | Cipher-read withdrawal blocks later private reads |
| `lineage` | 2 | Existing native lineage cases |
| `readers` | 2 | Owned native readers and physical writer deadline |
| `history` | 2 | Coordinator and preregistration history |
| `history-routes-retained` | 1 | Retained before route through replacement and withdrawal |
| `history-routes-native` | 1 | Distinct actual native invocations on all phase routes |

The six individual assignments use exact discovered test identities. A new
native-pilot or history-route method is rejected until it receives an explicit
assignment; missing configured cases and duplicate discovered identities are
also rejected before execution. Other new integration modules retain the
existing core assignment. The regression checks the actual discovered suite
and matrix parity without executing backend cases.

Every job retains its 60-minute cap. Ordinary test bodies, selected services,
the transport failure observer, core persistence/restart probes, the standalone
10000 ms response budget and native 60000 ms response budget remain unchanged.
Discovery verifies coverage only.
Each newly isolated physical case still needs a completed exact-commit receipt;
parallel infrastructure checks do not establish model qualification or response
latency.
