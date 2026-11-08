"""Mac client v2: cached folder inventory, queued SSH delivery and verified receipts."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import stat
import subprocess
import sys
import uuid

LABEL = "fr.edouard.moodle-downloads"
ROOTS = ("Documents", "Desktop", "Downloads")
MAX_BYTES = 20 * 1024 * 1024


def write_json(path, value):
    temporary = path.with_suffix(".new")
    with temporary.open("w") as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def ssh_command(host, remote_path, action):
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.@-]*", host):
        raise ValueError("Hote SSH invalide.")
    if not re.fullmatch(r"[a-zA-Z0-9_/.-]+", remote_path) or remote_path.startswith("-"):
        raise ValueError("Chemin distant invalide.")
    # Keep --remote-path compatible with the old Mac LaunchAgent's downloads path.
    helper = str(Path(remote_path.rstrip("/")).parent / "delivery.py")
    remote = " ".join(shlex.quote(p) for p in ["python3", helper, *action])
    return ["/usr/bin/ssh", "-oBatchMode=yes", "-oConnectTimeout=10",
            "-oStrictHostKeyChecking=yes", host, remote]


def rpc(host, remote_path, payload):
    result = subprocess.run(ssh_command(host, remote_path, ["rpc"]),
                            input=json.dumps(payload).encode(), stdout=subprocess.PIPE,
                            check=True, timeout=120)
    value = json.loads(result.stdout)
    if value.get("protocol") != 2:
        raise ValueError("Le serveur n'utilise pas le protocole de transfert v2.")
    return value


def file_hash(stream):
    stream.seek(0)
    return hashlib.file_digest(stream, "sha256").hexdigest()


def path_hash(path):
    with path.open("rb") as stream:
        return file_hash(stream)


def inventory(home):
    directories, errors, roots = {}, {}, {}
    limited = []
    remaining_bytes = 1_000_000
    for name in ROOTS:
        root = home / name
        roots[name] = str(root)
        directories[name] = []
        if not root.is_dir():
            errors[name] = "Dossier racine absent ou inaccessible"
            continue
        def onerror(error):
            errors[name] = "Inventaire partiel : acces refuse ou dossier disparu"
        for current, children, _ in os.walk(root, followlinks=False, onerror=onerror):
            children[:] = sorted(c for c in children if not c.startswith(".")
                                 and not (Path(current) / c).is_symlink()
                                 and not c.endswith((".app", ".bundle", ".photoslibrary")))
            relative = Path(current).relative_to(root)
            if len(relative.parts) >= 12:
                if children:
                    limited.append(name)
                children[:] = []
                continue
            for child in children:
                item = str(relative / child)
                remaining_bytes -= len(item.encode()) + 12
                if remaining_bytes < 0:
                    limited.append(name)
                    break
                directories[name].append(item)
            if remaining_bytes < 0:
                break
            if len(directories[name]) > 5000:
                directories[name] = directories[name][:5000]
                limited.append(name)
                break
    return {"roots": roots, "directories": directories, "errors": errors,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "limits": {"max_depth": 12, "max_directories_per_root": 5000,
                       "truncated_roots": sorted(set(limited))}}


@contextmanager
def destination_directory(home, root, folder):
    if root not in ROOTS or not isinstance(folder, str) or len(folder) > 1000:
        raise ValueError("Destination invalide.")
    parts = folder.split("/") if folder else []
    if any(not p or p in (".", "..") or p.startswith(".") or len(p.encode()) > 200
           or any(ord(c) < 32 or c in "\\:" for c in p) for p in parts):
        raise ValueError("Sous-dossier invalide.")
    base = home / root
    base.mkdir(mode=0o700, exist_ok=True)
    descriptor = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            next_descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        yield descriptor, base.joinpath(*parts)
    finally:
        os.close(descriptor)


def validate_job(job):
    name = job["name"]
    if not re.fullmatch(r"[0-9a-f]{32}", job["id"]) or not re.fullmatch(r"[0-9a-f]{64}", job["sha256"]):
        raise ValueError("Identifiant ou empreinte invalide.")
    if not name or name.startswith(".") or len(name.encode()) > 230 or any(ord(c) < 32 or c in "/\\:" for c in name):
        raise ValueError("Nom de fichier invalide.")
    if type(job["bytes"]) is not int or not 0 < job["bytes"] <= MAX_BYTES:
        raise ValueError("Taille de fichier invalide.")


def publish(directory_fd, temporary, name, sha):
    stem, suffix = Path(name).stem, Path(name).suffix
    for index in range(10000):
        candidate = name if index == 0 else f"{stem} ({index + 1}){suffix}"
        try:
            os.link(temporary, candidate, src_dir_fd=directory_fd, dst_dir_fd=directory_fd,
                    follow_symlinks=False)
            try:
                os.fsync(directory_fd)
            except OSError as exc:
                if exc.errno != errno.EINVAL:
                    raise
            return candidate
        except FileExistsError:
            try:
                descriptor = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                     dir_fd=directory_fd)
            except OSError:
                continue
            with os.fdopen(descriptor, "rb") as stream:
                if stat.S_ISREG(os.fstat(stream.fileno()).st_mode) and file_hash(stream) == sha:
                    return candidate
    raise ValueError("Trop de conflits de noms dans ce dossier.")


def receive(job, home, fetch):
    validate_job(job)
    with destination_directory(home, job["destination_root"], job["destination_folder"]) as (directory_fd, folder):
        temporary = f".moodle-part-{job['id']}"
        # A leftover from an interrupted attempt is safe to discard under this client's lock.
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        descriptor = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory_fd)
        try:
            with os.fdopen(descriptor, "w+b") as output:
                fetch(job["id"], output)
                output.flush()
                if os.fstat(output.fileno()).st_size != job["bytes"] or file_hash(output) != job["sha256"]:
                    raise ValueError("Taille ou SHA-256 incorrect; copie VPS conservee.")
                os.fsync(output.fileno())
            candidate = publish(directory_fd, temporary, job["name"], job["sha256"])
            final = folder / candidate
            # Do not acknowledge if the directory was moved/deleted during the copy.
            if final.is_symlink() or not final.resolve().is_relative_to((home / job["destination_root"]).resolve()) or path_hash(final) != job["sha256"]:
                raise ValueError("Destination modifiee pendant le transfert; copie VPS conservee.")
            return {"id": job["id"], "sha256": job["sha256"], "final_path": str(final)}
        finally:
            os.unlink(temporary, dir_fd=directory_fd)


def migrate_legacy(home, destination):
    # Only the exact hierarchy produced by the v1 client; preserve other local files.
    for source in sorted(destination.glob("course-*/*/resource-*/*/*")):
        if not source.is_file() or source.is_symlink() or source.name.startswith("."):
            continue
        if any(parent.is_symlink() for parent in source.parents if parent.is_relative_to(destination)):
            continue
        job = {"id": uuid.uuid4().hex, "name": source.name, "sha256": path_hash(source),
               "bytes": source.stat().st_size, "destination_root": "Downloads", "destination_folder": "Moodle"}
        def fetch(_, output):
            with source.open("rb") as stream:
                import shutil
                shutil.copyfileobj(stream, output)
        receipt = receive(job, home, fetch)
        if path_hash(source) == job["sha256"] and path_hash(Path(receipt["final_path"])) == job["sha256"]:
            source.unlink()
            parent = source.parent
            while parent != destination:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent


def sync(host, remote_path, destination, *, home=None, client_state=None):
    home = home or Path.home()
    client_state = client_state or home / "Library/Application Support/MoodleSync"
    client_state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (client_state / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        state_path = client_state / "state.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {"client_id": uuid.uuid4().hex, "receipts": []}
        write_json(state_path, state)
        # Flatten the old layout once, only on this machine.
        if not state.get("legacy_migrated"):
            migrate_legacy(home, destination)
            state["legacy_migrated"] = True
            write_json(state_path, state)
        snapshot = inventory(home)
        response = rpc(host, remote_path, {"client_id": state["client_id"], "snapshot": snapshot,
                                           "receipts": state["receipts"]})
        accepted = set(response["accepted_receipts"])
        state["receipts"] = [r for r in state["receipts"] if r["id"] not in accepted]
        write_json(state_path, state)
        failures = []
        def fetch(job_id, output):
            subprocess.run(ssh_command(host, remote_path, ["export", job_id]), stdout=output,
                           check=True, timeout=300)
        for job in response["jobs"]:
            if any(r["id"] == job["id"] for r in state["receipts"]):
                continue
            try:
                receipt = receive(job, home, fetch)
                state["receipts"].append(receipt)
                write_json(state_path, state)  # survives an SSH failure before acknowledgement
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                failures.append({"id": job["id"], "error": str(exc)[:500]})
        if state["receipts"] or failures:
            response = rpc(host, remote_path, {"client_id": state["client_id"],
                                               "receipts": state["receipts"], "failures": failures})
            accepted = set(response["accepted_receipts"])
            state["receipts"] = [r for r in state["receipts"] if r["id"] not in accepted]
            write_json(state_path, state)
        return 1 if failures else 0


def agent(host, remote_path, destination, log):
    return {"Label": LABEL,
            "ProgramArguments": [sys.executable, str(Path(__file__).resolve()), "once",
                                 "--host", host, "--remote-path", remote_path,
                                 "--destination", str(destination)],
            "StartInterval": 30, "RunAtLoad": True, "ProcessType": "Background",
            "StandardOutPath": str(log), "StandardErrorPath": str(log), "Umask": 0o077}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["once", "install", "status", "uninstall"])
    parser.add_argument("--host", help="Hote SSH ou alias configure dans ~/.ssh/config")
    parser.add_argument("--remote-path", default="project/moodle-mcp/downloads")
    parser.add_argument("--destination", type=Path, default=Path.home() / "Downloads/Moodle",
                        help="Ancien dossier v1 a aplatir; les nouveaux depots sont choisis par le MCP.")
    args = parser.parse_args()
    if args.action in ("once", "install") and not args.host:
        parser.error("--host est requis (ex. etudiant@vps.example.org).")
    destination = args.destination.expanduser().resolve()
    if args.action == "once":
        return sync(args.host, args.remote_path, destination)
    if sys.platform != "darwin":
        parser.error("install/status/uninstall s'executent sur le Mac.")
    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{LABEL}"
    plist = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    if args.action == "status":
        return subprocess.run(["/bin/launchctl", "print", target], check=False).returncode
    if args.action == "uninstall":
        subprocess.run(["/bin/launchctl", "bootout", target], check=False, capture_output=True)
        plist.unlink(missing_ok=True)
        print("Synchronisation retiree; documents conserves.")
        return 0
    if sync(args.host, args.remote_path, destination):
        print("Certains depots ont echoue; ils restent en attente sur le VPS.", file=sys.stderr)
    log = Path.home() / "Library/Logs" / f"{LABEL}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    plist.parent.mkdir(parents=True, exist_ok=True)
    with plist.open("wb") as output:
        plistlib.dump(agent(args.host, args.remote_path, destination, log), output)
    subprocess.run(["/bin/launchctl", "bootout", target], check=False, capture_output=True)
    subprocess.run(["/bin/launchctl", "bootstrap", domain, str(plist)], check=True)
    print("Client v2 actif : depots verifies, inventaire des dossiers et file hors ligne, toutes les 30 secondes.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"Synchronisation en echec : {exc}", file=sys.stderr)
        sys.exit(1)
