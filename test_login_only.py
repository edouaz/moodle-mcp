"""Check the login-only boundary without network, real sessions or credentials."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import scraper


class LoginOnlyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        lock = patch("session_lock.LOCK_PATH", Path(directory.name) / ".lock")
        lock.start()
        self.addCleanup(lock.stop)

    async def test_guest_course_page_is_not_authenticated(self):
        for url, logout_links, expected in (
            (scraper.BASE + "/my/courses.php", 0, False),
            (scraper.BASE + "/my/courses.php", 1, True),
            (scraper.BASE + "/login/index.php", 1, False),
            ("https://sso.example.org/my/courses.php", 1, False),
        ):
            with self.subTest(url=url, logout_links=logout_links):
                page = SimpleNamespace(url=url, goto=AsyncMock(),
                                       locator=MagicMock(return_value=SimpleNamespace(
                                           count=AsyncMock(return_value=logout_links))))
                self.assertEqual(await scraper.is_logged_in(page), expected)

    async def test_login_supports_moodle_subdirectory(self):
        page = SimpleNamespace(url="https://campus.example.edu/moodle/my/courses.php",
                               goto=AsyncMock(), locator=MagicMock(return_value=SimpleNamespace(
                                   count=AsyncMock(return_value=1))))
        with patch.object(scraper, "BASE", "https://campus.example.edu/moodle"):
            self.assertTrue(await scraper.is_logged_in(page))

    async def run_login(self, checks, existing=False):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "session.json"
            if existing:
                state.touch()
            page = SimpleNamespace(goto=AsyncMock())
            context = SimpleNamespace(new_page=AsyncMock(return_value=page),
                                      storage_state=AsyncMock())
            browser = SimpleNamespace(new_context=AsyncMock(return_value=context),
                                      close=AsyncMock())
            playwright = MagicMock()
            playwright.__aenter__ = AsyncMock(return_value=SimpleNamespace(
                chromium=SimpleNamespace(launch=AsyncMock(return_value=browser))))
            with (patch.object(scraper, "STATE", state),
                  patch.object(scraper, "OUT", Path(directory)),
                  patch.object(scraper, "async_playwright", return_value=playwright),
                  patch.object(scraper, "is_logged_in", AsyncMock(side_effect=checks)),
                  patch.object(scraper, "get_courses", AsyncMock()) as courses,
                  patch.object(scraper, "process_resource", AsyncMock()) as resources,
                  patch.object(scraper, "download", AsyncMock()) as download,
                  patch.object(scraper, "write_run_log") as run_log,
                  patch.object(scraper, "log"),
                  patch("builtins.input", return_value="") as prompt):
                if checks[-1]:
                    await scraper.main(login_only=True)
                    context.storage_state.assert_awaited_once_with(path=str(state))
                    self.assertEqual(state.stat().st_mode & 0o777, 0o600)
                else:
                    with self.assertRaisesRegex(RuntimeError, "Login not confirmed"):
                        await scraper.main(login_only=True)
                    context.storage_state.assert_not_awaited()
                    self.assertFalse(state.exists())
                courses.assert_not_awaited()
                resources.assert_not_awaited()
                download.assert_not_awaited()
                run_log.assert_not_called()
                browser.close.assert_awaited_once()
                self.assertEqual(prompt.call_count, int(not checks[0]))
                self.assertEqual(browser.new_context.call_args.kwargs,
                                 {"storage_state": str(state) if existing else None,
                                  "accept_downloads": False})

    async def test_first_login(self):
        await self.run_login([False, True])

    async def test_existing_session(self):
        await self.run_login([True], existing=True)

    async def test_expired_session(self):
        await self.run_login([False, True], existing=True)

    async def test_unfinished_login(self):
        await self.run_login([False, False])


if __name__ == "__main__":
    unittest.main()
