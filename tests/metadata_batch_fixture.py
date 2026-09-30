"""Finite SQL shape recorder for tests; never a physical XTDB substitute."""
from copy import deepcopy
import re
from types import SimpleNamespace


class _Cursor:
    def __init__(self, rows):
        names = tuple(rows[0]) if rows else ()
        self.description = [SimpleNamespace(name=name) for name in names]
        self.rows = [tuple(row[name] for name in names) for row in rows]
    def fetchall(self):
        return self.rows


def install_current_metadata_batch(connection):
    """Extend an explicitly controlled row recorder, preserving its identity."""
    original = connection.execute
    if getattr(connection, "_flora_metadata_batch_recorder", False):
        return
    def execute(sql, parameters):
        if not sql.startswith("SELECT * FROM (SELECT '") or ") AS flora_current_metadata_fence LIMIT" not in sql:
            return original(sql, parameters)
        connection.calls.append((sql, parameters))
        clauses = re.findall(r"SELECT '([^']+)' AS fence_kind, _id, scope_digest, "
            r"(\w+) AS fence_sha256, record_json FROM (\w+)( FOR VALID_TIME ALL)? "
            r"WHERE scope_digest = %s AND _id IN \(([^)]+)\)", sql)
        if not clauses:
            raise AssertionError("unrecognized finite terminal metadata SQL shape")
        limit_match = re.search(r" AS flora_current_metadata_fence LIMIT ([1-9][0-9]*)$", sql)
        if limit_match is None:
            raise AssertionError("finite metadata LIMIT must be an XTDB-compatible integer literal")
        row_limit = int(limit_match.group(1))
        offset, values = 0, []
        expected_rows = 0
        for tag, column, table, temporal, placeholders in clauses:
            count = placeholders.count("%s")
            expected_rows += count
            scope, keys = parameters[offset], parameters[offset + 1:offset + 1 + count]
            offset += 1 + count
            for (name, key), row in connection.rows.items():
                if name == table and key in keys and row["scope_digest"] == scope:
                    values.append({"fence_kind": tag, "_id": row["_id"], "scope_digest": row["scope_digest"],
                        "fence_sha256": row[column], "record_json": row["record_json"]})
        if offset != len(parameters) or row_limit != expected_rows + 1:
            raise AssertionError("finite metadata query parameter count changed")
        return _Cursor(deepcopy(values[:row_limit]))
    connection.execute = execute
    connection._flora_metadata_batch_recorder = True
