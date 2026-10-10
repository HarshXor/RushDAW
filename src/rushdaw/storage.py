"""Project storage for RushDAW.

Layout (default home ``~/.rushdaw``, override with ``RUSHDAW_HOME``)::

    ~/.rushdaw/
        db.sql                         SQLite: only the important metadata
        file/<project_id>/rev-0001.rushdaw   full project snapshot per revision

The SQLite database keeps *metadata only* (project name, tempo, timestamps,
revision numbers, messages, file name, size, checksum).  The heavy project
content (tracks, notes, FX, embedded audio) lives in the ``.rushdaw`` files.
"""
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    bpm           REAL NOT NULL DEFAULT 120,
    sig           INTEGER NOT NULL DEFAULT 4,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    head_revision INTEGER NOT NULL DEFAULT 0,
    deleted_at    REAL
);
CREATE TABLE IF NOT EXISTS revisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    number      INTEGER NOT NULL,
    message     TEXT NOT NULL DEFAULT '',
    file_name   TEXT NOT NULL,
    size        INTEGER NOT NULL,
    sha256      TEXT NOT NULL,
    track_count INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL,
    UNIQUE (project_id, number)
);
CREATE INDEX IF NOT EXISTS idx_revisions_project ON revisions(project_id, number);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
SCHEMA_VERSION = "1"
_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class StorageError(Exception):
    """Raised for invalid input (maps to HTTP 400/404)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def default_home():
    return os.path.abspath(os.path.expanduser(os.environ.get("RUSHDAW_HOME") or "~/.rushdaw"))


class Storage:
    def __init__(self, home=None):
        self.home = os.path.abspath(home or default_home())
        self.files_dir = os.path.join(self.home, "file")
        self.db_path = os.path.join(self.home, "db.sql")
        os.makedirs(self.files_dir, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)", (SCHEMA_VERSION,))

    # ------------------------------------------------------------ helpers
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @staticmethod
    def _check_id(project_id):
        if not isinstance(project_id, str) or not _ID_RE.match(project_id):
            raise StorageError("invalid project id", 400)
        return project_id

    def _project_dir(self, project_id):
        path = os.path.join(self.files_dir, self._check_id(project_id))
        if os.path.dirname(path) != self.files_dir:  # defence in depth against traversal
            raise StorageError("invalid project path", 400)
        return path

    @staticmethod
    def _row(r):
        return dict(r) if r is not None else None

    @staticmethod
    def _clean_name(name, fallback="Untitled"):
        name = (name or "").strip()[:120]
        return name or fallback

    @staticmethod
    def _parse_project(data):
        try:
            obj = json.loads(data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data)
        except (ValueError, UnicodeDecodeError) as e:
            raise StorageError(f"invalid .rushdaw JSON: {e}")
        if not isinstance(obj, dict) or obj.get("app") != "rushdaw" or not isinstance(obj.get("project"), dict):
            raise StorageError("not a RushDAW project file")
        return obj

    # ------------------------------------------------------------ projects
    def list_projects(self, deleted=False):
        """Active projects (default) or the soft-deleted ones (trash)."""
        where = "p.deleted_at IS NOT NULL" if deleted else "p.deleted_at IS NULL"
        with self._connect() as db:
            rows = db.execute(
                """SELECT p.*, (SELECT COUNT(*) FROM revisions r WHERE r.project_id = p.id) AS revision_count,
                          (SELECT size FROM revisions r WHERE r.project_id = p.id AND r.number = p.head_revision) AS size
                   FROM projects p WHERE """ + where + " ORDER BY p.updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_project(self, project_id, include_deleted=False):
        self._check_id(project_id)
        with self._connect() as db:
            p = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if p is None or (p["deleted_at"] is not None and not include_deleted):
                raise StorageError("project not found", 404)
            revs = db.execute(
                "SELECT number, message, file_name, size, sha256, track_count, created_at FROM revisions "
                "WHERE project_id = ? ORDER BY number DESC", (project_id,)).fetchall()
        out = dict(p)
        out["revisions"] = [dict(r) for r in revs]
        return out

    def create_project(self, name, bpm=120, sig=4):
        pid = uuid.uuid4().hex
        now = time.time()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO projects(id, name, bpm, sig, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (pid, self._clean_name(name), float(bpm or 120), int(sig or 4), now, now))
        os.makedirs(self._project_dir(pid), exist_ok=True)
        return self.get_project(pid)

    def rename_project(self, project_id, name):
        self.get_project(project_id)
        with self._lock, self._connect() as db:
            db.execute("UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                       (self._clean_name(name), time.time(), project_id))
        return self.get_project(project_id)

    def delete_project(self, project_id):
        """Soft delete: hidden from the list, files and history are kept on disk."""
        self.get_project(project_id)
        with self._lock, self._connect() as db:
            db.execute("UPDATE projects SET deleted_at = ? WHERE id = ?", (time.time(), project_id))
        return {"id": project_id, "deleted": True}

    def restore_project(self, project_id):
        self.get_project(project_id, include_deleted=True)
        with self._lock, self._connect() as db:
            db.execute("UPDATE projects SET deleted_at = NULL WHERE id = ?", (project_id,))
        return self.get_project(project_id)

    # ------------------------------------------------------------ revisions
    def save_revision(self, project_id, data, message=""):
        """Store ``data`` (.rushdaw JSON bytes) as the next revision of the project."""
        self.get_project(project_id)
        obj = self._parse_project(data)
        proj = obj["project"]
        raw = data if isinstance(data, (bytes, bytearray)) else data.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        pdir = self._project_dir(project_id)
        os.makedirs(pdir, exist_ok=True)
        with self._lock, self._connect() as db:
            head = db.execute("SELECT head_revision FROM projects WHERE id = ?", (project_id,)).fetchone()[0]
            number = head + 1
            file_name = f"rev-{number:04d}.rushdaw"
            path = os.path.join(pdir, file_name)
            tmp = path + ".tmp"
            with open(tmp, "wb") as f:  # atomic write: never leaves a half-written revision
                f.write(raw)
            os.replace(tmp, path)
            now = time.time()
            db.execute(
                "INSERT INTO revisions(project_id, number, message, file_name, size, sha256, track_count, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (project_id, number, (message or "").strip()[:200] or f"Revision {number}", file_name, len(raw), digest,
                 len(proj.get("tracks") or []), now))
            db.execute(
                "UPDATE projects SET head_revision = ?, updated_at = ?, name = ?, bpm = ?, sig = ? WHERE id = ?",
                (number, now, self._clean_name(proj.get("title"), "Untitled"), float(proj.get("bpm") or 120),
                 int(proj.get("sig") or 4), project_id))
        return {"project_id": project_id, "number": number, "size": len(raw), "sha256": digest, "file_name": file_name}

    def read_revision(self, project_id, number=None):
        p = self.get_project(project_id)
        if not p["revisions"]:
            raise StorageError("project has no saved revision yet", 404)
        if number is None:
            number = p["head_revision"]
        rev = next((r for r in p["revisions"] if r["number"] == int(number)), None)
        if rev is None:
            raise StorageError("revision not found", 404)
        path = os.path.join(self._project_dir(project_id), rev["file_name"])
        if not os.path.isfile(path):
            raise StorageError("revision file missing on disk", 404)
        with open(path, "rb") as f:
            return f.read(), rev, p

    def restore_revision(self, project_id, number):
        data, rev, _ = self.read_revision(project_id, number)
        return self.save_revision(project_id, data, f"Restored from revision {rev['number']}")

    def import_project(self, data, name=None):
        obj = self._parse_project(data)
        p = self.create_project(name or obj["project"].get("title") or "Imported", obj["project"].get("bpm") or 120,
                                obj["project"].get("sig") or 4)
        self.save_revision(p["id"], data, "Imported")
        return self.get_project(p["id"])
