"""Persistent, private Mac delivery queue and its SSH-only protocol (stdlib only)."""
from i18n import translate as tr
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid

from session_lock import session_lock

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".delivery"
DOWNLOADS = ROOT / "downloads"
ROOTS = ("Documents", "Desktop", "Downloads")
MAX_BYTES = 20 * 1024 * 1024


class DeliveryError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def destination(root, folder):
    if root not in ROOTS:
        raise DeliveryError("INVALID_DESTINATION", tr('Choose Documents, Desktop or Downloads.'))
    if not isinstance(folder, str) or len(folder) > 1000:
        raise DeliveryError("INVALID_DESTINATION", tr('Subfolder path is too long.'))
    parts = folder.split("/") if folder else []
    if any(not p or p in (".", "..") or p.startswith(".") or len(p.encode()) > 200
           or any(ord(c) < 32 or c in "\\:" for c in p) for p in parts):
        raise DeliveryError("INVALID_DESTINATION", tr('Use a relative path without .., hidden folders or control characters.'))
    return root, folder


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def database():
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(STATE / "queue.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
                name TEXT NOT NULL, source TEXT NOT NULL, destination_root TEXT NOT NULL,
                destination_folder TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
                created_at TEXT NOT NULL, delivered_at TEXT, final_path TEXT,
                last_error TEXT, attempts INTEGER NOT NULL DEFAULT 0);
        """)
        with db:
            db.execute("BEGIN IMMEDIATE")
            yield db
    finally:
        db.close()


def setting(db, key):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def set_setting(db, key, value):
    db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))


def source_path(relative):
    path = DOWNLOADS / relative
    if path.is_symlink() or not path.resolve().is_relative_to(DOWNLOADS.resolve()):
        raise DeliveryError("UNSAFE_PATH", tr('Source file is outside the Moodle cache.'))
    return path


def enqueue(path, root="Downloads", folder="Moodle"):
    destination(root, folder)
    path = Path(path)
    if path.is_symlink():
        raise DeliveryError("UNSAFE_PATH", tr('Source file symlinks are not allowed.'))
    try:
        relative = str(path.resolve().relative_to(DOWNLOADS.resolve()))
    except ValueError:
        raise DeliveryError("UNSAFE_PATH", tr('Source file is outside the Moodle cache.')) from None
    path = source_path(relative)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise DeliveryError("INVALID_FILE", tr('Source file is missing or too large.'))
    sha = digest(path)
    with database() as db:
        existing = db.execute("""SELECT * FROM jobs WHERE sha256=? AND name=?
            AND destination_root=? AND destination_folder=? AND status='queued'""",
            (sha, path.name, root, folder)).fetchone()
        if existing:
            return dict(existing)
        payloads = STATE / "payloads"
        payloads.mkdir(mode=0o700, exist_ok=True)
        blob = payloads / sha
        if not blob.exists():
            with tempfile.NamedTemporaryFile(dir=payloads, delete=False) as output:
                temporary = Path(output.name)
                try:
                    with path.open("rb") as stream:
                        shutil.copyfileobj(stream, output)
                    output.flush()
                    os.fsync(output.fileno())
                    if digest(temporary) != sha:
                        raise DeliveryError("FILE_CHANGED", tr('The file changed while being queued.'))
                    os.replace(temporary, blob)
                finally:
                    temporary.unlink(missing_ok=True)
        job_id = uuid.uuid4().hex
        db.execute("""INSERT INTO jobs
            (id,sha256,bytes,name,source,destination_root,destination_folder,created_at)
            VALUES (?,?,?,?,?,?,?,?)""", (job_id, sha, path.stat().st_size, path.name,
                                        relative, root, folder, now()))
        return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def cleanup():
    # Keep the browser/cache and queue lock order consistent with download_file.
    try:
        with session_lock(), database() as db:
            rows = db.execute("SELECT DISTINCT sha256,source FROM jobs WHERE status='delivered'").fetchall()
            for row in rows:
                pending = db.execute("SELECT 1 FROM jobs WHERE sha256=? AND status='queued'", (row["sha256"],)).fetchone()
                if pending:
                    continue
                path = source_path(row["source"])
                if path.is_file() and digest(path) == row["sha256"]:
                    path.unlink()
                    parent = path.parent
                    while parent != DOWNLOADS:
                        try:
                            parent.rmdir()
                        except OSError:
                            break
                        parent = parent.parent
                (STATE / "payloads" / row["sha256"]).unlink(missing_ok=True)
    except RuntimeError:
        pass  # Moodle is busy; the next exchange retries cleanup.


def adopt_legacy():
    with database() as db:
        if setting(db, "legacy_adopted"):
            return
    try:
        with session_lock():
            for path in sorted(DOWNLOADS.glob("course-*/*/resource-*/*/*")):
                if path.is_file() and not path.is_symlink() and not path.name.startswith("."):
                    with database() as db:
                        known = db.execute("SELECT 1 FROM jobs WHERE source=? AND sha256=?",
                                           (str(path.relative_to(DOWNLOADS)), digest(path))).fetchone()
                    if not known:
                        enqueue(path)
            with database() as db:
                set_setting(db, "legacy_adopted", True)
    except RuntimeError:
        pass


def exchange(data):
    client_id = data.get("client_id", "")
    if not re.fullmatch(r"[0-9a-f]{32}", client_id):
        raise DeliveryError("INVALID_CLIENT", tr('Invalid Mac client ID.'))
    accepted = []
    with database() as db:
        bound = setting(db, "client_id")
        if bound and bound != client_id:
            raise DeliveryError("OTHER_MAC", tr('The queue is already paired with another Mac.'))
        set_setting(db, "client_id", client_id)
        set_setting(db, "last_seen_at", now())
        snapshot = data.get("snapshot")
        if snapshot is not None:
            if not isinstance(snapshot, dict) or len(json.dumps(snapshot)) > 2_000_000:
                raise DeliveryError("INVALID_SNAPSHOT", tr('Folder inventory is too large or invalid.'))
            set_setting(db, "snapshot", snapshot)
        for receipt in data.get("receipts", [])[:100]:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (receipt.get("id"),)).fetchone()
            if not row or row["sha256"] != receipt.get("sha256"):
                continue
            final_path = receipt.get("final_path", "")
            if not isinstance(final_path, str) or not final_path.startswith("/") or len(final_path) > 3000:
                continue
            db.execute("""UPDATE jobs SET status='delivered',delivered_at=COALESCE(delivered_at,?),
                final_path=?,last_error=NULL WHERE id=?""", (now(), final_path, row["id"]))
            accepted.append(row["id"])
        for failure in data.get("failures", [])[:100]:
            db.execute("UPDATE jobs SET last_error=?,attempts=attempts+1 WHERE id=? AND status='queued'",
                       (str(failure.get("error", tr('Local error')))[:500], failure.get("id")))
    adopt_legacy()
    cleanup()
    with database() as db:
        jobs = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY attempts,created_at,id LIMIT 20").fetchall()
        return {"protocol": 2, "accepted_receipts": accepted,
                "jobs": [{k: row[k] for k in ("id", "name", "bytes", "sha256", "destination_root", "destination_folder")} for row in jobs]}


def list_folders(root="Documents", folder="", query="", offset=0, limit=50):
    destination(root, folder)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise DeliveryError("INVALID_PAGE", tr('Invalid pagination (limit must be 1..100).'))
    with database() as db:
        snapshot = setting(db, "snapshot") or {}
        seen = setting(db, "last_seen_at")
    directories = snapshot.get("directories", {}).get(root, [])
    if query:
        items = [p for p in directories if query.casefold() in p.casefold()
                 and (not folder or p.startswith(folder + "/"))]
    else:
        items = [p for p in directories if str(PurePosixPath(p).parent) == (folder or ".")]
    end = offset + limit
    return {"root": root, "root_path": snapshot.get("roots", {}).get(root), "folder": folder,
            "items": items[offset:end], "total": len(items), "next_offset": end if end < len(items) else None,
            "last_seen_at": seen, "snapshot_at": snapshot.get("scanned_at"),
            "snapshot_limits": snapshot.get("limits", {}), "access_errors": snapshot.get("errors", {}),
            "note": tr('Last known folder inventory; it may be out of date. Missing folders are created on delivery.'),
            "content_trust": "untrusted_mac_paths"}


def status(job_id=None):
    with database() as db:
        seen = setting(db, "last_seen_at")
        rows = db.execute("SELECT * FROM jobs WHERE id=?" if job_id else
                          "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 50",
                          (job_id,) if job_id else ()).fetchall()
        counts = dict(db.execute("SELECT status,count(*) FROM jobs GROUP BY status").fetchall())
    return {"last_seen_at": seen, "counts": counts,
            "jobs": [{k: row[k] for k in ("id", "name", "status", "destination_root", "destination_folder",
                     "created_at", "delivered_at", "final_path", "last_error", "attempts")} for row in rows],
            "note": tr('delivered means SHA-256 verified receipt on the Mac; queued is waiting for the next connection.')}


def export(job_id):
    with database() as db:
        row = db.execute("SELECT sha256 FROM jobs WHERE id=? AND status='queued'", (job_id,)).fetchone()
    if not row:
        raise DeliveryError("INVALID_JOB", tr('Transfer is missing or already delivered.'))
    blob = STATE / "payloads" / row["sha256"]
    with blob.open("rb") as stream:
        shutil.copyfileobj(stream, sys.stdout.buffer)


if __name__ == "__main__":
    os.umask(0o077)
    try:
        if sys.argv[1:] == ["rpc"]:
            data = json.loads(sys.stdin.buffer.read(3_000_001))
            print(json.dumps(exchange(data), ensure_ascii=False))
        elif len(sys.argv) == 3 and sys.argv[1] == "export" and re.fullmatch(r"[0-9a-f]{32}", sys.argv[2]):
            export(sys.argv[2])
        else:
            raise DeliveryError("INVALID_COMMAND", tr('Use rpc or export JOB_ID over SSH.'))
    except Exception as exc:
        print(f"Transfer failed: {exc.code if isinstance(exc, DeliveryError) else type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
