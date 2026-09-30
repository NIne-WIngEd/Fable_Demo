# Selected Temporal restart gate

The earlier local Temporal dev-server tests use in-memory persistence. They demonstrate activity retry with selected index adapters but cannot demonstrate a workflow surviving a server restart.

The Docker gate now adds actual Temporal Server **1.32.0** with its PostgreSQL **16.14** history/visibility persistence. PostgreSQL is Temporal's backing store; it does not replace XTDB Claims, Kurrent Experience or the other selected memory planes. The server, schema bootstrap and namespace setup follow the [official Temporal SQL deployment example](https://github.com/temporalio/samples-server/blob/main/compose/docker-compose-postgres.yml) and [schema initialization flow](https://github.com/temporalio/samples-server/blob/main/compose/scripts/setup-postgres.sh). This is a single-node integration configuration, not a consumer deployment or production migration system.

The synthetic probe:

1. Runs one activity and records its invocation in XTDB.
2. Waits for a signal after Temporal has recorded the activity completion.
3. Stops the worker process, then restarts the Temporal server and its PostgreSQL service.
4. Opens the same workflow from a new client/worker and checks the persisted completion history.
5. Sends the signal and runs the pending second activity.
6. Requires one invocation of each activity. A completed first activity must not run again during replay.

Probe material is a fictional marker. This checks orchestration continuity, not learned memory, native judgment, complete cross-plane recovery or the correctness of index cleanup. Real cleanup adapters retain their separate integration checks.

The persistent probe passed at `5cc36c6754df5e6dcdf99d0581a3f042fcd73077`
in [run 36755050656](https://github.com/NIne-WIngEd/FloRA/actions/runs/36755050656),
core job `110023050041`. The workflow restarted both PostgreSQL and Temporal,
then recovered and resumed the existing waiting workflow without repeating its
completed first activity. This receipt qualifies that exact probe and
implementation; a later change needs its own run.

`scripts/temporal_schema_setup.sh` initializes fresh CI volumes. Restarts retain the existing databases. It is not a general schema-upgrade, backup/restore, failover or key-custody tool. All fixture credentials are confined to this local Docker integration setup.
