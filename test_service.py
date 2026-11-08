import asyncio
import io
import json
import tempfile
import subprocess
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from pypdf import PdfWriter

import moodle_service as service
import delivery
import mcp_server
from session_lock import session_lock


def pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


@asynccontextmanager
async def fake_connection():
    yield None, None


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.downloads = Path(self.directory.name) / "downloads"
        self.patch = patch.object(service, "DOWNLOADS", self.downloads)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        lock = patch("session_lock.LOCK_PATH", Path(self.directory.name) / ".lock")
        lock.start()
        self.addCleanup(lock.stop)
        self.resource = {"id": "667630", "name": "APE01 TP1", "section_id": "20393", "section": "CM1"}
        self.file = service.file_entry(self.resource, service.scraper.BASE + "/pluginfile.php/842550/mod_resource/content/3/TP1.pdf")

    def response(self, body=None):
        return SimpleNamespace(status=200, ok=True, headers={"content-type": "application/pdf"},
                               body=AsyncMock(return_value=body if body is not None else pdf_bytes()), dispose=AsyncMock())

    async def test_download_and_existing_file(self):
        response = self.response()
        ctx = SimpleNamespace(request=SimpleNamespace(get=AsyncMock(return_value=response)))
        first = await service.save_file(ctx, 2798, self.file, True)
        self.assertEqual(first["pdf_pages"], 1)
        self.assertEqual(first["status"], "downloaded")
        self.assertEqual(Path(first["local_path"]).read_bytes(), pdf_bytes())
        second = await service.save_file(ctx, 2798, self.file)
        self.assertEqual(second["status"], "already_present")
        self.assertEqual(first["sha256"], second["sha256"])
        ctx.request.get.assert_awaited_once()

    async def test_mcp_destination_enqueues_verified_download(self):
        response = self.response()
        ctx = SimpleNamespace(request=SimpleNamespace(get=AsyncMock(return_value=response)))
        saved = await service.save_file(ctx, 2798, self.file)
        with (patch.object(service, "connection", fake_connection),
              patch.object(service, "inventory", AsyncMock(return_value=({"id": "2798"}, [], [], [self.file]))),
              patch.object(service, "save_file", AsyncMock(return_value=saved)),
              patch.object(delivery, "STATE", Path(self.directory.name) / ".delivery"),
              patch.object(delivery, "DOWNLOADS", self.downloads)):
            result = await service.download_file(2798, file_id=self.file["id"],
                                                destination_root="Documents", destination_folder="Uni/Analyse")
            self.assertEqual(result["delivery"]["status"], "queued")
            self.assertEqual(result["delivery"]["destination_folder"], "Uni/Analyse")
            self.assertTrue(Path(result["local_path"]).exists())

    async def test_html_and_invalid_pdf_are_not_saved(self):
        for body in (b"<html>login</html>", b"not a PDF"):
            response = self.response(body)
            ctx = SimpleNamespace(request=SimpleNamespace(get=AsyncMock(return_value=response)))
            with self.assertRaises(service.MoodleError):
                await service.save_file(ctx, 2798, self.file)
            self.assertFalse(service.local_path(2798, self.file).exists())
            self.assertFalse(list(self.downloads.rglob('.moodle-part-*')))

    async def test_interruption_is_retryable_and_no_partial_file_survives(self):
        response = self.response()
        ctx = SimpleNamespace(request=SimpleNamespace(get=AsyncMock(return_value=response)))
        response.body.side_effect = asyncio.TimeoutError("synthetic secret must not appear")
        with self.assertRaises(asyncio.TimeoutError):
            await service.save_file(ctx, 2798, self.file)
        response.body.side_effect = None
        with patch.object(service.os, "link", side_effect=OSError("interrupted publish")):
            with self.assertRaises(OSError):
                await service.save_file(ctx, 2798, self.file)
        self.assertFalse(service.local_path(2798, self.file).exists())
        self.assertFalse(list(self.downloads.rglob('.moodle-part-*')))
        self.assertEqual((await service.save_file(ctx, 2798, self.file))["status"], "downloaded")

    async def test_redirect_to_other_host_is_refused(self):
        response = self.response()
        response.status = 302
        response.headers["location"] = "https://other.example/private.pdf"
        ctx = SimpleNamespace(request=SimpleNamespace(get=AsyncMock(return_value=response)))
        with self.assertRaisesRegex(service.MoodleError, "hors du Moodle"):
            await service.save_file(ctx, 2798, self.file)
        ctx.request.get.assert_awaited_once()

    async def test_invalid_selection_and_empty_query_do_not_open_browser(self):
        with patch.object(service, "connection") as connection:
            with self.assertRaises(service.MoodleError):
                await service.download_file(2798, file_id="../../session.json")
            for query in ("", " ", "a" * 201):
                with self.assertRaises(service.MoodleError):
                    await service.search_files(2798, query)
            connection.assert_not_called()

    async def test_empty_search_and_invalid_course(self):
        with (patch.object(service, "connection", fake_connection),
              patch.object(service, "inventory", AsyncMock(return_value=({"id": "2798"}, [], [], [self.file])))):
            result = await service.search_files(2798, "no-match")
            self.assertEqual(result["items"], [])
            self.assertEqual(result["total"], 0)
        with patch.object(service, "courses_on_page", AsyncMock(return_value=[])):
            with self.assertRaises(service.MoodleError):
                await service.inventory(None, None, 999999)

    async def test_source_course_pagination_collects_each_page(self):
        paging = SimpleNamespace(count=AsyncMock(return_value=1), get_attribute=AsyncMock(return_value="1"))
        next_page = SimpleNamespace(count=AsyncMock(return_value=1),
                                    is_visible=AsyncMock(side_effect=[True, False]), click=AsyncMock())
        locators = [SimpleNamespace(first=paging), SimpleNamespace(first=next_page), SimpleNamespace(first=next_page)]
        one = {"url": "course-one", "name": "One"}
        two = {"url": "course-two", "name": "Two"}
        page = SimpleNamespace(goto=AsyncMock(), locator=MagicMock(side_effect=locators),
                               wait_for_function=AsyncMock(), wait_for_load_state=AsyncMock(),
                               evaluate=AsyncMock(side_effect=[[one], [one, two]]))
        self.assertEqual(await service.scraper.get_courses(page), [one, two])
        next_page.click.assert_awaited_once()

    async def test_missing_session_status(self):
        with patch.object(service.scraper, "STATE", Path(self.directory.name) / "missing.json"):
            result = await service.session_status()
        self.assertFalse(result["valid"])
        self.assertEqual(result["error"], "SESSION_EXPIRED")

    async def test_errors_never_echo_underlying_secrets(self):
        sentinel = "TEST-COOKIE-SECRET-NOT-REAL"
        with patch.object(service, "list_courses", AsyncMock(side_effect=RuntimeError(sentinel))):
            result = await mcp_server.list_moodle_courses()
        serialized = result.model_dump_json()
        self.assertNotIn(sentinel, serialized)
        self.assertTrue(result.isError)
        self.assertNotIn("traceback", serialized.lower())

    def test_stable_ids_safe_paths_and_symlink_refusal(self):
        same = service.file_entry(self.resource, self.file["url"] + "?forcedownload=1&sesskey=TEST")
        self.assertEqual(same["id"], self.file["id"])
        other = service.file_entry(self.resource, self.file["url"].replace("/3/", "/3/subfolder/"))
        self.assertNotEqual(service.local_path(2798, self.file), service.local_path(2798, other))
        file = dict(self.file, name="../../session.json")
        self.assertTrue(service.local_path(2798, file).is_relative_to(self.downloads.resolve()))
        path = service.local_path(2798, self.file)
        path.parent.mkdir(parents=True)
        path.symlink_to(Path(self.directory.name) / "outside.pdf")
        with self.assertRaises(service.MoodleError):
            service.local_path(2798, self.file)

    def test_pagination_and_concurrent_session_lock(self):
        result = service.paginate(list(range(6)), 2, 2)
        self.assertEqual(result["items"], [2, 3])
        self.assertEqual(result["next_offset"], 4)
        for offset, limit in ((-1, 1), (0, 0), (0, 101)):
            with self.assertRaises(service.MoodleError):
                service.paginate([], offset, limit)
        with session_lock():
            with self.assertRaisesRegex(RuntimeError, "MOODLE_BUSY"):
                with session_lock():
                    pass

    def test_tunnel_launcher_syntax_and_invalid_id(self):
        launcher = Path(__file__).parent / "tunnel.sh"
        self.assertEqual(subprocess.run(["bash", "-n", str(launcher)], capture_output=True).returncode, 0)
        invalid = subprocess.run(["bash", str(launcher), "init", "invalid"], capture_output=True)
        self.assertNotEqual(invalid.returncode, 0)


if __name__ == "__main__":
    unittest.main()
