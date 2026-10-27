"""Example knowledge tool: explicit scope/key lookup, no inferred applicability."""
import json
import sqlite3
from pathlib import Path

from .values import dumps


def _connect(database):
    path = Path(database).absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=10)
    db.execute("""CREATE TABLE IF NOT EXISTS knowledge (
        scope TEXT NOT NULL, key TEXT NOT NULL, record TEXT NOT NULL,
        PRIMARY KEY(scope,key))""")
    return db


def lookup(database, scope, key):
    db = _connect(database)
    try:
        row = db.execute("SELECT record FROM knowledge WHERE scope=? AND key=?", (scope, key)).fetchone()
        return {"found": row is not None, "record": json.loads(row[0]) if row else None}
    finally:
        db.close()


def remember(database, scope, key, value, source, exceptions=None):
    if not scope or not key or not source:
        raise ValueError("scope, key and source must be explicit")
    record = dict(scope=scope, key=key, value=value, source=source, exceptions=exceptions or [])
    db = _connect(database)
    try:
        with db:
            # Lock before checking so two conflicting writers cannot both succeed.
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT record FROM knowledge WHERE scope=? AND key=?", (scope, key)).fetchone()
            if existing and json.loads(existing[0]) != record:
                raise ValueError("conflicting knowledge: use a new scope/key or review the existing rule")
            db.execute("INSERT OR IGNORE INTO knowledge VALUES (?,?,?)", (scope, key, dumps(record)))
    finally:
        db.close()
    return record
