import hashlib
import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import delivery
import sync_mac


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for attr, value in (("STATE", self.root / ".delivery"), ("DOWNLOADS", self.root / "downloads")):
            patched = patch.object(delivery, attr, value)
            patched.start()
            self.addCleanup(patched.stop)
        lock = patch("session_lock.LOCK_PATH", self.root / ".moodle.lock")
        lock.start()
        self.addCleanup(lock.stop)
        self.source = delivery.DOWNLOADS / "course-1/section/resource-2/hash/TP.pdf"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"PDF test")
        self.client = "b" * 32

    def exchange(self, **kwargs):
        return delivery.exchange({"client_id": self.client, **kwargs})

    def receipt(self, job):
        return {"id": job["id"], "sha256": job["sha256"], "final_path": "/Users/me/Documents/Uni/TP.pdf"}

    def test_cache_root_alias_accepts_canonical_source_but_rejects_file_symlink(self):
        alias = self.root / "alias"
        alias.symlink_to(delivery.DOWNLOADS, target_is_directory=True)
        with patch.object(delivery, "DOWNLOADS", alias):
            queued = delivery.enqueue(self.source.resolve())
            self.assertEqual(queued["source"], "course-1/section/resource-2/hash/TP.pdf")
            link = alias / "link.pdf"
            link.symlink_to(self.source)
            with self.assertRaises(delivery.DeliveryError):
                delivery.enqueue(link)

    def test_offline_queue_persists_and_duplicate_pending_request_reuses_job(self):
        first = delivery.enqueue(self.source, "Documents", "Uni")
        second = delivery.enqueue(self.source, "Documents", "Uni")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(delivery.status()["counts"], {"queued": 1})
        self.assertTrue(self.source.exists())

    def test_ack_validated_before_cleanup_and_lost_reply_is_idempotent(self):
        first = delivery.enqueue(self.source)
        bad = dict(self.receipt(first), sha256="0" * 64)
        self.assertEqual(self.exchange(receipts=[bad])["accepted_receipts"], [])
        self.assertTrue(self.source.exists())
        accepted = self.exchange(receipts=[self.receipt(first)])
        self.assertEqual(accepted["accepted_receipts"], [first["id"]])
        self.assertFalse(self.source.exists())
        self.assertFalse((delivery.STATE / "payloads" / first["sha256"]).exists())
        self.assertEqual(self.exchange(receipts=[self.receipt(first)])["accepted_receipts"], [first["id"]])
        self.assertEqual(delivery.status(first["id"])["jobs"][0]["status"], "delivered")

    def test_same_file_for_two_destinations_retained_until_both_ack(self):
        first = delivery.enqueue(self.source)
        second = delivery.enqueue(self.source, "Desktop", "")
        self.exchange(receipts=[self.receipt(first)])
        self.assertTrue(self.source.exists())
        self.exchange(receipts=[self.receipt(second)])
        self.assertFalse(self.source.exists())

    def test_failure_keeps_bytes_and_updated_source_is_never_deleted(self):
        first = delivery.enqueue(self.source)
        self.exchange(failures=[{"id": first["id"], "error": "Access denied"}])
        self.assertTrue(self.source.exists())
        self.assertEqual(delivery.status(first["id"])["jobs"][0]["last_error"], "Access denied")
        self.source.write_bytes(b"new content")
        self.exchange(receipts=[self.receipt(first)])
        self.assertEqual(self.source.read_bytes(), b"new content")

    def test_cached_folder_listing_pagination_search_and_other_mac_refused(self):
        self.exchange(snapshot={"roots": {"Documents": "/Users/me/Documents"},
                                "directories": {"Documents": ["Uni", "Uni/Analyse", "Uni/Algebre"]},
                                "scanned_at": "yesterday"})
        self.assertEqual(delivery.list_folders()["items"], ["Uni"])
        self.assertEqual(delivery.list_folders(folder="Uni", limit=1)["next_offset"], 1)
        self.assertEqual(delivery.list_folders(query="analyse")["items"], ["Uni/Analyse"])
        with self.assertRaises(delivery.DeliveryError):
            delivery.exchange({"client_id": "c" * 32})

    def test_invalid_destination_refused_before_enqueuing(self):
        for root, folder in [("Library", ""), ("Documents", "../Desktop"),
                             ("Downloads", "/absolute"), ("Desktop", "a//b")]:
            with self.assertRaises(delivery.DeliveryError):
                delivery.enqueue(self.source, root, folder)

    def test_legacy_cache_is_queued_on_first_client_exchange(self):
        response = self.exchange()
        self.assertEqual(len(response["jobs"]), 1)
        self.assertEqual(response["jobs"][0]["destination_folder"], "Moodle")
        self.assertEqual(len(self.exchange()["jobs"]), 1)

    def test_server_and_client_full_flow_with_real_bytes_and_receipt(self):
        value = delivery.enqueue(self.source, "Documents", "Uni/Analyse")
        mac_home = self.root / "mac"
        def rpc(host, remote, payload):
            return delivery.exchange(payload)
        def fetch(args, **kwargs):
            with delivery.database() as db:
                row = db.execute("SELECT sha256 FROM jobs WHERE id=?", (value["id"],)).fetchone()
            kwargs["stdout"].write((delivery.STATE / "payloads" / row["sha256"]).read_bytes())
        # Do not create another job by adopting this synthetic source.
        with delivery.database() as db:
            delivery.set_setting(db, "legacy_adopted", True)
        with patch.object(sync_mac, "rpc", side_effect=rpc), patch.object(sync_mac.subprocess, "run", side_effect=fetch):
            self.assertEqual(sync_mac.sync("user@host", "project/downloads", mac_home / "Downloads/Moodle",
                                          home=mac_home, client_state=mac_home / "state"), 0)
        target = mac_home / "Documents/Uni/Analyse/TP.pdf"
        self.assertEqual(target.read_bytes(), b"PDF test")
        self.assertFalse(self.source.exists())
        result = delivery.status(value["id"])["jobs"][0]
        self.assertEqual(result["status"], "delivered")
        self.assertEqual(result["final_path"], str(target))

    def test_standalone_ssh_helper_protocol_export_and_ack(self):
        server = self.root / "standalone"
        server.mkdir()
        for name in ("delivery.py", "session_lock.py"):
            shutil.copyfile(Path(__file__).parent / name, server / name)
        source = server / "downloads/course-1/section/resource-2/hash/TP.pdf"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"real protocol bytes")
        def rpc(payload):
            completed = subprocess.run([sys.executable, str(server / "delivery.py"), "rpc"],
                                       input=json.dumps(payload).encode(), capture_output=True, check=True, timeout=10)
            return json.loads(completed.stdout)
        response = rpc({"client_id": self.client})
        value = response["jobs"][0]
        def fetch(job_id, output):
            subprocess.run([sys.executable, str(server / "delivery.py"), "export", job_id],
                           stdout=output, check=True, timeout=10)
        (self.root / "mac").mkdir()
        receipt = sync_mac.receive(value, self.root / "mac", fetch)
        self.assertEqual(Path(receipt["final_path"]).read_bytes(), b"real protocol bytes")
        self.assertEqual(rpc({"client_id": self.client, "receipts": [receipt]})["accepted_receipts"], [value["id"]])
        self.assertFalse(source.exists())

    def test_blocked_jobs_do_not_starve_new_downloads(self):
        first = delivery.enqueue(self.source)
        self.exchange(failures=[{"id": first["id"], "error": "permission denied"}])
        second = delivery.enqueue(self.source, "Documents", "new folder")
        self.assertEqual(self.exchange()["jobs"][0]["id"], second["id"])

    def test_cleanup_is_deferred_while_moodle_is_busy(self):
        first = delivery.enqueue(self.source)
        # Finish legacy adoption before simulating another browser operation.
        self.exchange()
        with delivery.session_lock():
            self.exchange(receipts=[self.receipt(first)])
            self.assertTrue(self.source.exists())
        self.exchange()
        self.assertFalse(self.source.exists())


if __name__ == "__main__":
    unittest.main()
