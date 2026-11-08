import hashlib
import json
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_mac


def job(body=b"PDF test", **overrides):
    return {"id": "a" * 32, "name": "TP.pdf", "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body), "destination_root": "Documents", "destination_folder": "Uni/Analyse", **overrides}


class SyncTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)

    def receive(self, value=None, body=b"PDF test"):
        return sync_mac.receive(value or job(), self.home, lambda _, output: output.write(body))

    def test_remote_shell_inputs_are_restricted(self):
        for host, path in [("-oProxyCommand=bad", "downloads"), ("user@host;id", "downloads"),
                           ("user@host", "$(id)"), ("user@host", "downloads;id")]:
            with self.assertRaises(ValueError):
                sync_mac.ssh_command(host, path, ["rpc"])

    def test_launch_agent_compatible_with_v1_paths_and_xml(self):
        destination = Path("/Users/Example Person/Downloads/Moodle & cours")
        value = sync_mac.agent("user@host", "project/downloads", destination, Path("/tmp/log"))
        decoded = plistlib.loads(plistlib.dumps(value))
        self.assertEqual(decoded["ProgramArguments"][-1], str(destination))
        self.assertEqual(decoded["StartInterval"], 30)

    def test_missing_folders_created_and_identical_retry_reused(self):
        first = self.receive()
        self.assertEqual(Path(first["final_path"]).read_bytes(), b"PDF test")
        self.assertEqual(Path(first["final_path"]), self.home / "Documents/Uni/Analyse/TP.pdf")
        self.assertEqual(first, self.receive())
        self.assertEqual(len(list((self.home / "Documents/Uni/Analyse").iterdir())), 1)

    def test_conflict_preserves_original_and_finds_identical_suffix(self):
        folder = self.home / "Documents/Uni/Analyse"
        folder.mkdir(parents=True)
        (folder / "TP.pdf").write_bytes(b"my annotated PDF")
        first = self.receive()
        self.assertEqual(Path(first["final_path"]).name, "TP (2).pdf")
        self.assertEqual((folder / "TP.pdf").read_bytes(), b"my annotated PDF")
        self.assertEqual(first, self.receive())

    def test_symlink_folder_and_traversal_are_refused(self):
        documents = self.home / "Documents"
        documents.mkdir()
        outside = self.home / "other"
        outside.mkdir()
        (documents / "Uni").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.receive()
        for folder in ("../other", "/tmp/outside", "Uni/../other", "Uni//Analyse"):
            with self.assertRaises(ValueError):
                self.receive(job(destination_folder=folder))
        self.assertEqual(list(outside.iterdir()), [])

    def test_incorrect_bytes_and_interruption_leave_no_final_file(self):
        with self.assertRaises(ValueError):
            self.receive(body=b"bad")
        def interrupted(_, output):
            output.write(b"part")
            raise OSError("network interrupted")
        with self.assertRaises(OSError):
            sync_mac.receive(job(), self.home, interrupted)
        self.assertEqual(list((self.home / "Documents/Uni/Analyse").iterdir()), [])
        self.receive()

    def test_inventory_caches_folders_without_symlinks_or_file_contents(self):
        (self.home / "Documents/Uni/Analyse").mkdir(parents=True)
        (self.home / "Documents/Uni/Analyse/secret.txt").write_text("private")
        (self.home / "Documents/.hidden").mkdir()
        (self.home / "Documents/link").symlink_to(self.home / "Documents/Uni")
        snapshot = sync_mac.inventory(self.home)
        self.assertEqual(snapshot["directories"]["Documents"], ["Uni", "Uni/Analyse"])
        self.assertNotIn("secret", json.dumps(snapshot))
        self.assertIn("Desktop", snapshot["errors"])

    def test_legacy_tree_flattened_without_losing_modified_or_unrelated_files(self):
        destination = self.home / "Downloads/Moodle"
        legacy = destination / "course-1/section/resource-2/hash/TP.pdf"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"local annotations")
        (destination / "TP.pdf").write_bytes(b"other file")
        (destination / "keep.txt").write_text("preserve")
        sync_mac.migrate_legacy(self.home, destination)
        self.assertFalse(legacy.exists())
        self.assertEqual((destination / "TP (2).pdf").read_bytes(), b"local annotations")
        self.assertEqual((destination / "TP.pdf").read_bytes(), b"other file")
        self.assertTrue((destination / "keep.txt").exists())
        self.assertFalse((destination / "course-1").exists())

    def test_lost_ack_is_durable_and_retried_after_restart(self):
        state_dir = self.home / "state"
        def fake_run(*args, **kwargs):
            kwargs["stdout"].write(b"PDF test")
        with (patch.object(sync_mac, "rpc", side_effect=[
                {"protocol": 2, "accepted_receipts": [], "jobs": [job()]}, OSError("SSH lost")]),
              patch.object(sync_mac.subprocess, "run", side_effect=fake_run)):
            with self.assertRaises(OSError):
                sync_mac.sync("user@host", "project/downloads", self.home / "Downloads/Moodle",
                              home=self.home, client_state=state_dir)
        self.assertEqual(len(json.loads((state_dir / "state.json").read_text())["receipts"]), 1)
        with patch.object(sync_mac, "rpc", return_value={"protocol": 2, "accepted_receipts": ["a" * 32], "jobs": []}) as rpc:
            self.assertEqual(sync_mac.sync("user@host", "project/downloads", self.home / "Downloads/Moodle",
                                          home=self.home, client_state=state_dir), 0)
            self.assertEqual(len(rpc.call_args.args[2]["receipts"]), 1)
        self.assertEqual(json.loads((state_dir / "state.json").read_text())["receipts"], [])


if __name__ == "__main__":
    unittest.main()
