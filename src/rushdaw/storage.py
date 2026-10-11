"""Project storage for RushDAW.

Layout (default home ``~/.rushdaw``, override with ``RUSHDAW_HOME``)::

    ~/.rushdaw/
        db.sql                         SQLite: only the important metadata
        file/<project_id>/rev-0001.rushdaw   full project snapshot per revision

The SQLite database keeps *metadata only* (project name, tempo, timestamps,
revision numbers, messages, file name, size, checksum).  The heavy project
content (tracks, notes, FX, embedded audio) lives in the ``.rushdaw`` files.
"""
import base64
import contextlib
import datetime
import hashlib
import io
import json
import os
import re
import sqlite3
import threading
import time
import uuid
import zipfile

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
CREATE TABLE IF NOT EXISTS master_presets (
    name        TEXT PRIMARY KEY COLLATE NOCASE,
    params      TEXT NOT NULL,              -- JSON: full mastering parameter set (small)
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
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
            # mute / solo state of each revision (what Download renders), added later -> migrate older databases
            if "mix" not in {r[1] for r in db.execute("PRAGMA table_info(revisions)")}:
                db.execute("ALTER TABLE revisions ADD COLUMN mix TEXT")
            # live mute / solo from the editor (unsaved): always what Play / Download use; cleared by the next save
            if "live_mix" not in {r[1] for r in db.execute("PRAGMA table_info(projects)")}:
                db.execute("ALTER TABLE projects ADD COLUMN live_mix TEXT")

    # ------------------------------------------------------------ helpers
    @contextlib.contextmanager
    def _connect(self):
        """Transaction + guaranteed close (sqlite3's own context manager only commits)."""
        db = sqlite3.connect(self.db_path, timeout=30)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            with db:
                yield db
        finally:
            db.close()

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
    def mix_summary(proj):
        """Which layers a render of this project plays: muted = silent; if any layer is soloed only soloed ones play."""
        tracks = [t for t in (proj.get("tracks") or []) if isinstance(t, dict)]
        any_solo = any(t.get("solo") for t in tracks)
        name = lambda t: str(t.get("name") or "Track")
        return {"solo": [name(t) for t in tracks if t.get("solo")], "mute": [name(t) for t in tracks if t.get("mute")],
                "audible": [name(t) for t in tracks if not t.get("mute") and (not any_solo or t.get("solo"))]}

    @staticmethod
    def apply_live_mix(proj, live):
        """Put the editor's latest mute / solo (live mix, matched by track id) onto a project document."""
        if not live:
            return proj
        by_id = {str(x.get("id")): x for x in live if isinstance(x, dict)}
        for t in proj.get("tracks") or []:
            x = by_id.get(str(t.get("id")))
            if x is not None:
                t["mute"], t["solo"] = bool(x.get("mute")), bool(x.get("solo"))
        return proj

    def set_live_mix(self, project_id, tracks):
        """Store the editor's current mute / solo of every layer (no new revision)."""
        self.get_project(project_id)
        if not isinstance(tracks, list) or len(tracks) > 500:
            raise StorageError("tracks must be a list")
        clean = [{"id": str(t.get("id"))[:64], "name": str(t.get("name") or "Track")[:120], "mute": bool(t.get("mute")),
                  "solo": bool(t.get("solo"))} for t in tracks if isinstance(t, dict) and t.get("id") is not None]
        with self._lock, self._connect() as db:
            db.execute("UPDATE projects SET live_mix = ? WHERE id = ?", (json.dumps(clean), project_id))
        return {"project_id": project_id, "mix": self.mix_summary({"tracks": clean})}

    def live_mix(self, project_id):
        with self._connect() as db:
            r = db.execute("SELECT live_mix FROM projects WHERE id = ?", (project_id,)).fetchone()
        try:
            return json.loads(r[0]) if r and r[0] else None
        except ValueError:
            return None

    def _backfill_mix(self, project_id, number):
        """Revisions saved before the 'mix' column existed: compute it once from the revision file and store it."""
        try:
            with self._connect() as db:
                row = db.execute("SELECT file_name FROM revisions WHERE project_id = ? AND number = ?", (project_id, number)).fetchone()
            if not row:
                return None
            with open(os.path.join(self._project_dir(project_id), row["file_name"]), "rb") as f:
                mix = self.mix_summary(self._parse_project(f.read())["project"])
            with self._lock, self._connect() as db:
                db.execute("UPDATE revisions SET mix = ? WHERE project_id = ? AND number = ?", (json.dumps(mix), project_id, number))
            return mix
        except (OSError, StorageError, ValueError):
            return None

    @staticmethod
    def _parse_project(data):
        try:
            obj = json.loads(data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data)
        except (ValueError, UnicodeDecodeError) as e:
            raise StorageError(f"invalid .rushdaw JSON: {e}")
        if not isinstance(obj, dict) or obj.get("app") != "rushdaw" or not isinstance(obj.get("project"), dict):
            raise StorageError("not a RushDAW project file")
        return obj

    # ------------------------------------------------------------ user master presets
    # Small JSON blobs (19 numbers) -> they live in SQLite; validation is done by the caller (model.clean_*).
    def list_master_presets(self):
        with self._connect() as db:
            rows = db.execute("SELECT name, params, created_at, updated_at FROM master_presets ORDER BY name COLLATE NOCASE").fetchall()
        return [{"name": r["name"], "params": json.loads(r["params"]), "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows]

    def get_master_preset(self, name):
        with self._connect() as db:
            r = db.execute("SELECT name, params, created_at, updated_at FROM master_presets WHERE name = ?", (name,)).fetchone()
        if r is None:
            raise StorageError(f"master preset '{name}' not found", 404)
        return {"name": r["name"], "params": json.loads(r["params"]), "created_at": r["created_at"], "updated_at": r["updated_at"]}

    def master_preset_exists(self, name):
        with self._connect() as db:
            return db.execute("SELECT 1 FROM master_presets WHERE name = ?", (name,)).fetchone() is not None

    def save_master_preset(self, name, params, overwrite=True):
        now = time.time()
        with self._lock, self._connect() as db:
            old = db.execute("SELECT created_at FROM master_presets WHERE name = ?", (name,)).fetchone()
            if old is not None and not overwrite:
                raise StorageError(f"master preset '{name}' already exists", 409)
            blob = json.dumps(params, sort_keys=True)
            if old is None:  # plain INSERT/UPDATE (no UPSERT -> works with old SQLite builds too)
                db.execute("INSERT INTO master_presets(name, params, created_at, updated_at) VALUES(?, ?, ?, ?)", (name, blob, now, now))
            else:
                db.execute("UPDATE master_presets SET name = ?, params = ?, updated_at = ? WHERE name = ?", (name, blob, now, name))
        return self.get_master_preset(name)

    def delete_master_preset(self, name):
        with self._lock, self._connect() as db:
            n = db.execute("DELETE FROM master_presets WHERE name = ?", (name,)).rowcount
        if not n:
            raise StorageError(f"master preset '{name}' not found", 404)
        return {"deleted": name}

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
                "SELECT number, message, file_name, size, sha256, track_count, created_at, mix FROM revisions "
                "WHERE project_id = ? ORDER BY number DESC", (project_id,)).fetchall()
        out = dict(p)
        try:
            out["live_mix"] = json.loads(out["live_mix"]) if out.get("live_mix") else None
        except ValueError:
            out["live_mix"] = None
        out["revisions"] = []
        for r in revs:
            d = dict(r)
            try:
                d["mix"] = json.loads(d["mix"]) if d.get("mix") else None
            except ValueError:
                d["mix"] = None
            out["revisions"].append(d)
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
                "INSERT INTO revisions(project_id, number, message, file_name, size, sha256, track_count, created_at, mix) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (project_id, number, (message or "").strip()[:200] or f"Revision {number}", file_name, len(raw), digest,
                 len(proj.get("tracks") or []), now, json.dumps(self.mix_summary(proj))))
            db.execute(
                "UPDATE projects SET head_revision = ?, updated_at = ?, name = ?, bpm = ?, sig = ?, live_mix = NULL WHERE id = ?",
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
        """Import a .rushdaw file (JSON, audio embedded) or an exported project package (.zip with
        project.rushdaw + audio/ files) as a new project."""
        if is_package(data):
            data = unpack_package(data)
        obj = self._parse_project(data)
        if name and name.strip():  # the chosen name wins (the saved revision's title becomes the project name)
            obj["project"]["title"] = self._clean_name(name)
            data = json.dumps(obj).encode("utf-8")
        p = self.create_project(obj["project"].get("title") or "Imported", obj["project"].get("bpm") or 120,
                                obj["project"].get("sig") or 4)
        self.save_revision(p["id"], data, "Imported")
        return self.get_project(p["id"])

    # ------------------------------------------------------------ export package
    def export_package(self, project_id, number=None):
        """Project package (.zip) of a saved revision: project.rushdaw + audio/ files. Returns (bytes, file name)."""
        data, rev, p = self.read_revision(project_id, number)
        live = self.live_mix(project_id) if number is None or int(number) == p["head_revision"] else None
        if live:  # the latest mute / solo from the editor (not saved yet) goes with the latest revision
            obj = self._parse_project(data)
            self.apply_live_mix(obj["project"], live)
            data = json.dumps(obj).encode()
        return build_package(data), f"{safe_file_name(p['name'])}-rev{rev['number']}.rushdaw.zip"

    # ------------------------------------------------------------ listing (search / filter / pagination)
    SORTS = {"updated": "p.updated_at", "created": "p.created_at", "name": "p.name COLLATE NOCASE", "bpm": "p.bpm",
             "revisions": "revision_count"}

    def query_projects(self, q="", deleted=False, date_field="updated", date_from=None, date_to=None,
                       bpm_min=None, bpm_max=None, sort="updated", order="desc", page=1, per_page=24):
        """Server-side project listing: text search (name + revision notes), date range on created/updated,
        BPM range, sorting and pagination. Dates are 'YYYY-MM-DD' (local time, both ends inclusive) or epoch seconds."""
        where, args = ["p.deleted_at IS NOT NULL" if deleted else "p.deleted_at IS NULL"], []
        q = (q or "").strip()
        if q:
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            where.append("(p.name LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM revisions r WHERE r.project_id = p.id "
                         "AND r.message LIKE ? ESCAPE '\\'))")
            args += [like, like]
        col = {"updated": "p.updated_at", "created": "p.created_at"}.get(date_field)
        if col is None:
            raise StorageError("date_field must be 'updated' or 'created'")
        if date_from not in (None, ""):
            where.append(f"{col} >= ?"); args.append(_to_epoch(date_from, end=False))
        if date_to not in (None, ""):
            where.append(f"{col} <= ?"); args.append(_to_epoch(date_to, end=True))
        if bpm_min not in (None, ""):
            where.append("p.bpm >= ?"); args.append(float(bpm_min))
        if bpm_max not in (None, ""):
            where.append("p.bpm <= ?"); args.append(float(bpm_max))
        sort_sql = self.SORTS.get(sort)
        if sort_sql is None:
            raise StorageError("sort must be one of: " + ", ".join(self.SORTS))
        direction = "ASC" if str(order).lower() == "asc" else "DESC"
        page, per_page = max(1, int(page or 1)), min(100, max(1, int(per_page or 24)))
        base = " FROM projects p WHERE " + " AND ".join(where)
        with self._connect() as db:
            total = db.execute("SELECT COUNT(*)" + base, args).fetchone()[0]
            rows = db.execute(
                """SELECT p.*, (SELECT COUNT(*) FROM revisions r WHERE r.project_id = p.id) AS revision_count,
                          (SELECT size FROM revisions r WHERE r.project_id = p.id AND r.number = p.head_revision) AS size,
                          (SELECT mix FROM revisions r WHERE r.project_id = p.id AND r.number = p.head_revision) AS mix"""
                + base + f" ORDER BY {sort_sql} {direction}, p.updated_at DESC LIMIT ? OFFSET ?",
                args + [per_page, (page - 1) * per_page]).fetchall()
        pages = max(1, -(-total // per_page))
        projects = []
        for r in rows:
            d = dict(r)
            try:
                d["mix"] = json.loads(d["mix"]) if d.get("mix") else None
            except ValueError:
                d["mix"] = None
            if d["mix"] is None and d.get("head_revision"):
                d["mix"] = self._backfill_mix(d["id"], d["head_revision"])
            live, raw = None, d.pop("live_mix", None)
            try:
                live = json.loads(raw) if raw else None
            except ValueError:
                pass
            d["mix_unsaved"] = bool(live)
            if live:
                d["mix"] = self.mix_summary({"tracks": live})
            projects.append(d)
        return {"projects": projects, "total": total, "page": page, "per_page": per_page, "pages": pages}


def _to_epoch(v, end=False):
    if isinstance(v, (int, float)) or re.fullmatch(r"\d+(\.\d+)?", str(v)):
        return float(v)
    try:
        d = datetime.datetime.strptime(str(v)[:10], "%Y-%m-%d")
    except ValueError:
        raise StorageError(f"invalid date '{v}' (use YYYY-MM-DD)")
    if end:
        d += datetime.timedelta(days=1)
        return time.mktime(d.timetuple()) - 0.001
    return time.mktime(d.timetuple())


# ---------------------------------------------------------------- project packages (.zip)
# Export = one zip that can be imported again in one go:
#     <name>.rushdaw.zip
#       project.rushdaw        the project (JSON); audio entries point to files instead of embedding them
#       audio/<id>-<name>.wav  every recorded / imported audio file used by the project
#       README.txt             what this is
PACKAGE_PROJECT = "project.rushdaw"
MAX_PACKAGE_UNCOMPRESSED = 2 * 1024 * 1024 * 1024  # zip-bomb guard


def safe_file_name(name, fallback="project"):
    n = re.sub(r"[^\w\- .()]+", "_", str(name or "")).strip(" ._")[:80]
    return n or fallback


def _audio_ext(raw):
    if raw[:4] == b"RIFF":
        return ".wav"
    if raw[:3] == b"ID3" or raw[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    if raw[:4] == b"OggS":
        return ".ogg"
    if raw[:4] == b"fLaC":
        return ".flac"
    return ".bin"


def is_package(data):
    return isinstance(data, (bytes, bytearray)) and data[:4] == b"PK\x03\x04"


def build_package(data):
    """.rushdaw bytes (audio embedded as base64) -> zip bytes (project.rushdaw + audio/ files)."""
    obj = Storage._parse_project(data)
    audio_out, files, used = {}, [], set()
    for aid, a in (obj.get("audio") or {}).items():
        if not isinstance(a, dict) or "wav" not in a:
            continue
        raw = base64.b64decode(a["wav"])
        base = safe_file_name(f"{aid}-{a.get('name') or 'audio'}".rsplit(".", 1)[0], aid)
        fname = f"audio/{base}{_audio_ext(raw)}"
        while fname in used:
            fname = fname.replace("audio/", "audio/_", 1)
        used.add(fname)
        files.append((fname, raw))
        audio_out[aid] = {"name": a.get("name") or "", "file": fname}
    obj["audio"] = audio_out
    obj["package"] = {"format": 1, "exported_at": time.time()}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(PACKAGE_PROJECT, json.dumps(obj))
        for fname, raw in files:
            z.writestr(zipfile.ZipInfo(fname, time.localtime()[:6]), raw, compress_type=zipfile.ZIP_STORED)  # audio: already dense
        z.writestr("README.txt", "RushDAW project package.\nImport this .zip in RushDAW (Projects > Import) - the project and\n"
                                 f"all its audio files ({len(files)}) come back in one go.\nproject.rushdaw = the project, "
                                 "audio/ = recorded and imported audio used by it.\n")
    return buf.getvalue()


def unpack_package(data):
    """Project package zip -> .rushdaw bytes with the audio embedded again (the internal storage format)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(bytes(data)))
    except zipfile.BadZipFile as e:
        raise StorageError(f"invalid project package: {e}")
    with z:
        if sum(i.file_size for i in z.infolist()) > MAX_PACKAGE_UNCOMPRESSED:
            raise StorageError("project package is too large")
        names = z.namelist()
        proj_name = PACKAGE_PROJECT if PACKAGE_PROJECT in names else next(
            (n for n in names if n.lower().endswith(".rushdaw") and "/" not in n.strip("/")), None) or next(
            (n for n in names if n.lower().endswith(".rushdaw")), None)
        if proj_name is None:
            raise StorageError("no project.rushdaw found in the package")
        obj = Storage._parse_project(z.read(proj_name))
        root = proj_name.rsplit("/", 1)[0] + "/" if "/" in proj_name else ""
        audio = {}
        for aid, a in (obj.get("audio") or {}).items():
            if not isinstance(a, dict):
                continue
            if "wav" in a:  # already embedded
                audio[aid] = a
                continue
            f = str(a.get("file") or "")
            cand = [root + f, f] + [n for n in names if n.endswith("/" + f.rsplit("/", 1)[-1])]
            hit = next((c for c in cand if c in names), None)
            if hit is None:
                raise StorageError(f"audio file '{f}' is missing from the package")
            audio[aid] = {"name": a.get("name") or "", "wav": base64.b64encode(z.read(hit)).decode("ascii")}
        obj["audio"] = audio
        obj.pop("package", None)
    return json.dumps(obj).encode("utf-8")

