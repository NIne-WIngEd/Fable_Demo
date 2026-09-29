#!/bin/sh
# Fresh-volume CI bootstrap, following temporalio/samples-server SQL schema flow.
# Normal service restart retains these databases; this is not a migration tool.
set -eu
: "${POSTGRES_SEEDS:?required}"
: "${POSTGRES_USER:?required}"
: "${SQL_PASSWORD:?required}"

for temporal_database in temporal temporal_visibility; do
    temporal_schema=temporal
    if [ "$temporal_database" = temporal_visibility ]; then
        temporal_schema=visibility
    fi
    temporal-sql-tool --plugin postgres12 --ep "$POSTGRES_SEEDS" -p 5432 -u "$POSTGRES_USER" \
        --db "$temporal_database" create
    temporal-sql-tool --plugin postgres12 --ep "$POSTGRES_SEEDS" -p 5432 -u "$POSTGRES_USER" \
        --db "$temporal_database" setup-schema -v 0.0
    temporal-sql-tool --plugin postgres12 --ep "$POSTGRES_SEEDS" -p 5432 -u "$POSTGRES_USER" \
        --db "$temporal_database" update-schema \
        -d "/etc/temporal/schema/postgresql/v12/$temporal_schema/versioned"
done
