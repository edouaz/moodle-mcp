import argparse
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import scraper
import targeted
import moodle_service as service


class SelectionTests(unittest.TestCase):
    def test_ambiguous_or_missing_file_fails(self):
        for items in ([], [{"name": "TP.pdf"}, {"name": "TP.pdf"}]):
            with self.assertRaises(ValueError):
                targeted.select_one(items, "name", "TP.pdf")

    def test_listing_urls_remove_auth_parameters(self):
        self.assertEqual(targeted.public_url(scraper.BASE + "/mod/resource/view.php?id=42&sesskey=TEST"),
                         scraper.BASE + "/mod/resource/view.php?id=42")
        with self.assertRaises(ValueError):
            targeted.public_url("https://other.example/pluginfile.php/test.pdf")

    def test_explicit_commands_required(self):
        args = targeted.parser().parse_args(["download", "--course", "2798", "--resource", "667630"])
        self.assertEqual((args.course, args.resource), (2798, 667630))


class DownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_moodle_section_ignores_sidebar_duplicates(self):
        async with scraper.async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content('''
                    <nav><a href="https://example.org/mod/resource/view.php?id=7">Sidebar</a></nav>
                    <main><li class="section"><div class="section-item"><h3>CM1</h3>
                    <ul class="section"><li class="activity">
                    <a href="https://example.org/mod/resource/view.php?id=7">TP1</a>
                    </li></ul></div></li></main>''')
                with (patch.object(page, "goto", AsyncMock()),
                      patch.object(page, "wait_for_load_state", AsyncMock())):
                    resources = await scraper.get_course_resources(page, "unused")
                self.assertEqual(resources, [{"url": "https://example.org/mod/resource/view.php?id=7",
                                              "name": "TP1", "section": "CM1", "section_id": ""}])
            finally:
                await browser.close()

    async def test_html_failure_can_be_retried_and_never_overwrites(self):
        response = SimpleNamespace(ok=True, headers={"content-type": "text/html"},
                                   url=scraper.BASE + "/pluginfile.php/test.pdf",
                                   body=AsyncMock(return_value=b"%PDF-1.4\n%%EOF"), dispose=AsyncMock())
        ctx = SimpleNamespace(request=SimpleNamespace(get=AsyncMock(return_value=response)))
        with tempfile.TemporaryDirectory() as directory, patch.object(scraper, "log"), patch.object(scraper, "NEW_THIS_RUN", []):
            out = Path(directory)
            self.assertTrue((await scraper.download(ctx, response.url, out)).startswith("!!"))
            self.assertEqual(list(out.iterdir()), [])
            response.headers = {"content-type": "application/pdf"}
            self.assertTrue((await scraper.download(ctx, response.url, out)).startswith("++"))
            original = (out / "test.pdf").read_bytes()
            response.body.reset_mock()
            self.assertTrue((await scraper.download(ctx, response.url, out)).startswith("=="))
            response.body.assert_not_awaited()
            self.assertEqual((out / "test.pdf").read_bytes(), original)

    async def test_invalid_pdf_is_not_saved(self):
        response = SimpleNamespace(ok=True, headers={"content-type": "application/pdf"},
                                   url=scraper.BASE + "/pluginfile.php/test.pdf",
                                   body=AsyncMock(return_value=b"<html>Login</html>"), dispose=AsyncMock())
        ctx = SimpleNamespace(request=SimpleNamespace(get=AsyncMock(return_value=response)))
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue((await scraper.download(ctx, response.url, Path(directory))).startswith("!!"))
            self.assertEqual(list(Path(directory).iterdir()), [])

    async def test_folder_visits_all_files_and_retries_failures(self):
        with (patch.object(scraper, "find_files_on_mod_page", AsyncMock(return_value=["one.pdf", "two.pdf"])),
              patch.object(scraper, "download", AsyncMock(side_effect=["!! HTTP 503", "++ two.pdf", "++ one.pdf", "== two.pdf"])) as download,
              patch.object(scraper, "log")):
            for _ in range(2):
                await scraper.process_resource(None, None, scraper.BASE + "/mod/folder/view.php?id=1", "Folder", Path("unused"))
            self.assertEqual(download.await_count, 4)


class CommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        lock = patch("session_lock.LOCK_PATH", Path(directory.name) / ".lock")
        lock.start()
        self.addCleanup(lock.stop)

    async def check_command(self, command, authenticated=True):
        course = {"name": "LINFO1111 - Analyse", "url": scraper.BASE + "/course/view.php?id=2798"}
        resource = {"name": "TP1", "section": "CM1", "url": scraper.BASE + "/mod/resource/view.php?id=667630"}
        page = SimpleNamespace(set_default_timeout=MagicMock(), locator=MagicMock(return_value=SimpleNamespace(evaluate_all=AsyncMock(return_value=[]))))
        ctx = SimpleNamespace(new_page=AsyncMock(return_value=page))
        browser = SimpleNamespace(new_context=AsyncMock(return_value=ctx), close=AsyncMock())
        playwright = MagicMock()
        playwright.__aenter__ = AsyncMock(return_value=SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser))))
        with (tempfile.TemporaryDirectory() as directory,
              patch.object(scraper, "OUT", Path(directory)),
              patch.object(scraper, "async_playwright", return_value=playwright),
              patch.object(scraper, "STATE", SimpleNamespace(exists=lambda: True, __str__=lambda self: "test-session")),
              patch.object(scraper, "is_logged_in", AsyncMock(return_value=authenticated)),
              patch.object(scraper, "get_courses", AsyncMock(return_value=[course])) as courses,
              patch.object(scraper, "get_course_resources", AsyncMock(return_value=[resource])),
              patch.object(scraper, "find_files_on_mod_page", AsyncMock(return_value=[scraper.BASE + "/pluginfile.php/TP1.pdf"])),
              patch.object(service, "save_file", AsyncMock(return_value={"status": "downloaded"})) as download,
              patch("builtins.print")):
            args = argparse.Namespace(command=command, course=2798, resource=667630, file=None)
            if authenticated:
                await targeted.run(args)
                self.assertEqual(download.await_count, int(command == "download"))
                self.assertEqual(list(Path(directory).iterdir()), [])
            else:
                with self.assertRaises(service.MoodleError) as error:
                    await targeted.run(args)
                self.assertEqual(error.exception.code, "SESSION_EXPIRED")
                courses.assert_not_awaited()
                download.assert_not_awaited()
            browser.close.assert_awaited_once()

    async def test_list_commands_do_not_download(self):
        for command in ("courses", "files"):
            await self.check_command(command)

    async def test_targeted_download_calls_downloader_once(self):
        await self.check_command("download")

    async def test_expired_session_stops_without_prompt(self):
        await self.check_command("download", authenticated=False)


if __name__ == "__main__":
    unittest.main()
