"""SQLite checkpoints and events committed together; revision checks prevent races."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from .values import dumps


class Conflict(RuntimeError):
    pass


class Store:
    def __init__(self, path):
        self.path = str(Path(path).absolute())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, event TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def create(self, state):
        run_id = uuid.uuid4().hex
        state.update(id=run_id, revision=0)
        with self.connect() as db:
            db.execute("INSERT INTO runs VALUES (?, 0, ?)", (run_id, dumps(state)))
            db.execute("INSERT INTO events(run_id,revision,event) VALUES (?,0,?)",
                       (run_id, dumps({"type": "created"})))
        return state

    def load(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def save(self, state, event):
        revision = state["revision"]
        updated = dict(state, revision=revision + 1)
        with self.connect() as db:
            count = db.execute("UPDATE runs SET revision=?, state=? WHERE id=? AND revision=?",
                               (revision + 1, dumps(updated), state["id"], revision)).rowcount
            if count != 1:
                raise Conflict("run changed in another executor; reload before continuing")
            db.execute("INSERT INTO events(run_id,revision,event) VALUES (?,?,?)",
                       (state["id"], revision + 1, dumps(event)))
        state["revision"] = revision + 1
        return state

    def events(self, run_id):
        with self.connect() as db:
            rows = db.execute("SELECT revision,event,created_at FROM events WHERE run_id=? ORDER BY seq",
                              (run_id,)).fetchall()
        return [dict(revision=r, event=json.loads(e), created_at=t) for r, e, t in rows]
