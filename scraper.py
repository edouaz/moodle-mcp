"""
moodle-browser-scraper

A browser-session Moodle downloader.

First run:  opens Chromium, you log in manually, press Enter, and it downloads
            every file from your courses.
Next runs:  reuse the saved session in session.json.
Use --login-only to save the session without collecting courses.

It works through a real browser session (Playwright), so it handles institutional
SSO logins and JavaScript-rendered pages, and works even when the Moodle
web-services / mobile API is disabled.
"""

import argparse
import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from playwright.async_api import async_playwright
from session_lock import session_lock

# Flush every print immediately so we always see where we are if it dies
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass


def log(msg: str):
    print(msg, flush=True)


# Base URL of the campus Moodle. Override with the CAMPUS_BASE environment
# variable (e.g. CAMPUS_BASE=https://your.campus.edu) or edit this line.
from configuration import campus_base
BASE = campus_base()
OUT = Path(__file__).parent
# session.json stores YOUR login session (cookies). It is PERSONAL:
# do NOT share it. Each person must do their own login.
STATE = OUT / "session.json"

INVALID_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]')

MAX_FILE_MB = 300
PER_DOWNLOAD_TIMEOUT_MS = 60_000
PAGE_TIMEOUT_MS = 20_000
SKIP_VIDEO_CONTENT_TYPES = ("video/", "audio/")

NEW_FILES_LOG = OUT / "_new_files_log.md"

NEW_THIS_RUN = []  # list of (course, section, filename, size_kb)
CURRENT_COURSE = ""
CURRENT_SECTION = ""


def record_new_file(filename: str, size_kb: int):
    NEW_THIS_RUN.append((CURRENT_COURSE, CURRENT_SECTION, filename, size_kb))


def write_run_log(start_ts: datetime, end_ts: datetime):
    """Append this run's new downloads to the persistent log."""
    duration = (end_ts - start_ts).total_seconds()
    header = (
        f"\n## Run {start_ts:%Y-%m-%d %H:%M} "
        f"(duration {duration:.0f}s, {len(NEW_THIS_RUN)} new files)\n"
    )

    if not NEW_THIS_RUN:
        body = "_No new files this run._\n"
    else:
        by_course: dict[str, list[tuple[str, str, int]]] = {}
        for course, section, fname, kb in NEW_THIS_RUN:
            by_course.setdefault(course, []).append((section, fname, kb))

        lines = []
        for course in sorted(by_course):
            lines.append(f"\n### {course}")
            by_section: dict[str, list[tuple[str, int]]] = {}
            for section, fname, kb in by_course[course]:
                by_section.setdefault(section or "(no section)", []).append((fname, kb))
            for section in sorted(by_section):
                lines.append(f"\n**{section}**")
                for fname, kb in by_section[section]:
                    lines.append(f"- `{fname}` ({kb} KB)")
        body = "\n".join(lines) + "\n"

    is_new = not NEW_FILES_LOG.exists()
    with NEW_FILES_LOG.open("a", encoding="utf-8") as f:
        if is_new:
            f.write("# Log of new files discovered by the scraper\n\n")
            f.write(
                "Each run appends a section with the files that did NOT exist before. "
                "Useful to detect new uploads on the campus.\n"
            )
        f.write(header)
        f.write(body)
    log(f">> Log updated: {NEW_FILES_LOG}")


def safe_name(name: str, maxlen: int = 80) -> str:
    name = INVALID_CHARS.sub("_", name).strip().strip(".")
    return name[:maxlen] or "untitled"


def long_path(p: Path) -> Path:
    """Wrap Windows paths with the \\?\\ prefix to bypass the 260-char MAX_PATH limit."""
    if sys.platform != "win32":
        return p
    s = str(p.resolve())
    if s.startswith("\\\\?\\"):
        return Path(s)
    if s.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + s.lstrip("\\"))
    return Path("\\\\?\\" + s)


def shorten_filename(fname: str, max_total_path: int = 240, parent: Path = None) -> str:
    """If parent+fname would exceed MAX_PATH, truncate fname while keeping its extension."""
    if parent is None:
        return fname
    parent_len = len(str(parent.resolve())) + 1  # +1 for separator
    budget = max(40, max_total_path - parent_len)
    if len(fname) <= budget:
        return fname
    stem, dot, ext = fname.rpartition(".")
    if dot and len(ext) <= 8:
        keep = max(10, budget - len(ext) - 1)
        return stem[:keep] + "." + ext
    return fname[:budget]


def filename_from_url(url: str) -> str:
    path = urlparse(url).path
    return unquote(path.rsplit("/", 1)[-1]) or "file"


async def is_logged_in(page) -> bool:
    await page.goto(f"{BASE}/my/courses.php", wait_until="domcontentloaded")
    current, campus = urlparse(page.url), urlparse(BASE)
    # Moodle can show /my/courses.php to guests, so the URL alone is insufficient.
    return (
        current.netloc == campus.netloc
        and current.path.startswith(campus.path.rstrip("/") + "/my/")
        and await page.locator('a[href*="/login/logout.php"]').count() > 0
    )


async def get_courses(page):
    await page.goto(f"{BASE}/my/courses.php", wait_until="networkidle")
    script = (
        """() => {
            const links = Array.from(document.querySelectorAll('a[href*="/course/view.php?id="]'));
            const seen = new Map();
            for (const a of links) {
                const url = a.href.split('#')[0];
                const text = (a.textContent || '').trim();
                if (!text || text.length < 2) continue;
                if (!seen.has(url)) seen.set(url, text);
            }
            return Array.from(seen, ([url, name]) => ({url, name}));
        }"""
    )
    courses = {}
    paging = page.locator('[data-region="paging-bar"]').first
    while True:
        if await paging.count():
            await page.wait_for_function("""() => document.querySelector('[data-region="paging-bar"]').dataset.lastPageNumber !== '0'""", timeout=PAGE_TIMEOUT_MS)
        for course in await page.evaluate(script):
            courses[course["url"]] = course
        next_page = page.locator('[data-region="paging-bar"] [data-control="next"]:not(.disabled) a').first
        if not await next_page.count() or not await next_page.is_visible():
            break
        number = await paging.get_attribute("data-active-page-number")
        await next_page.click()
        await page.wait_for_function("""previous => document.querySelector('[data-region="paging-bar"]').dataset.activePageNumber !== previous""", arg=number, timeout=PAGE_TIMEOUT_MS)
        await page.wait_for_load_state("networkidle")
    return list(courses.values())


async def get_course_resources(page, course_url):
    await page.goto(course_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    # small settle delay for lazy-loaded sections, but don't wait for networkidle
    try:
        await page.wait_for_load_state("load", timeout=8000)
    except Exception:
        pass
    resources = await page.evaluate(
        """() => {
            const out = [];
            const seen = new Set();
            const root = document.querySelector('[role="main"], main') || document;
            const selectors = [
                'a[href*="/mod/resource/view.php"]',
                'a[href*="/mod/folder/view.php"]',
                'a[href*="/mod/url/view.php"]',
                'a[href*="pluginfile.php"]',
            ];
            for (const sel of selectors) {
                for (const a of root.querySelectorAll(sel)) {
                    const url = a.href;
                    if (seen.has(url)) continue;
                    seen.add(url);
                    // try to find a section heading above
                    let section = '';
                    let section_id = '';
                    let p = a.closest('li.section, .course-section') || a.closest('.activity');
                    if (p) {
                        const h = p.querySelector('.sectionname, h2, h3, h4');
                        if (h) section = h.textContent.trim();
                        const link = p.querySelector('a[href*="/course/section.php?id="]');
                        section_id = link ? new URL(link.href).searchParams.get('id') : p.id;
                    }
                    out.push({
                        url,
                        name: (a.textContent || '').trim() || 'file',
                        section,
                        section_id,
                    });
                }
            }
            return out;
        }"""
    )
    return resources


PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK\x03\x04"
OFFICE_MAGICS = (b"PK\x03\x04", b"\xd0\xcf\x11\xe0")  # docx/xlsx/pptx vs. legacy doc/xls/ppt


def looks_like_html(body: bytes) -> bool:
    head = body[:512].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


async def find_files_on_mod_page(page, ctx, url: str):
    """Look for downloadable file URLs in a mod/resource or mod/folder page.

    Order:
      1. HEAD/GET the URL itself - Moodle often 303-redirects straight to the file.
      2. Open the page and scan a/iframe/embed/object/meta-refresh for pluginfile.php.
      3. Try url + &redirect=1 trick.
    """
    # 1. HEAD first so we don't accidentally download a huge body just to inspect redirects
    try:
        resp = await asyncio.wait_for(
            ctx.request.fetch(url, method="HEAD", max_redirects=10, timeout=PAGE_TIMEOUT_MS),
            timeout=PAGE_TIMEOUT_MS / 1000 + 5,
        )
        final = resp.url
        ctype = resp.headers.get("content-type", "").lower()
        if "pluginfile.php" in final:
            return [final]
        if not ctype.startswith("text/html"):
            return [url]  # the URL itself serves a file directly
    except Exception:
        pass

    # 2. Render the page and scrape every plausible element
    try:
        await asyncio.wait_for(
            page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS),
            timeout=PAGE_TIMEOUT_MS / 1000 + 5,
        )
    except Exception:
        return []

    links = await page.evaluate(
        """() => {
            const out = new Set();
            const collect = (sel, attr) => {
                document.querySelectorAll(sel).forEach(el => {
                    const v = el.getAttribute(attr);
                    if (v && v.includes('pluginfile.php')) {
                        try { out.add(new URL(v, location.href).href); } catch(e) {}
                    }
                });
            };
            collect('a[href*="pluginfile.php"]', 'href');
            collect('iframe[src*="pluginfile.php"]', 'src');
            collect('embed[src*="pluginfile.php"]', 'src');
            collect('object[data*="pluginfile.php"]', 'data');
            collect('source[src*="pluginfile.php"]', 'src');
            // meta refresh
            const meta = document.querySelector('meta[http-equiv="refresh" i]');
            if (meta) {
                const m = /url=([^;]+)/i.exec(meta.getAttribute('content') || '');
                if (m && m[1].includes('pluginfile.php')) {
                    try { out.add(new URL(m[1], location.href).href); } catch(e) {}
                }
            }
            return Array.from(out);
        }"""
    )
    if links:
        return links

    # also peek inside same-origin iframes
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            sub = await frame.evaluate(
                """() => Array.from(document.querySelectorAll('a[href*="pluginfile.php"], embed[src*="pluginfile.php"], iframe[src*="pluginfile.php"]'))
                    .map(el => el.href || el.src).filter(Boolean)"""
            )
            links.extend(sub)
        except Exception:
            continue

    return links


async def download(ctx, url, outdir: Path, name_hint: str = ""):
    try:
        resp = await asyncio.wait_for(
            ctx.request.get(url, max_redirects=10, timeout=PER_DOWNLOAD_TIMEOUT_MS),
            timeout=PER_DOWNLOAD_TIMEOUT_MS / 1000,
        )
    except asyncio.TimeoutError:
        return f"!! timeout (>{PER_DOWNLOAD_TIMEOUT_MS//1000}s)"
    except Exception as e:
        return f"!! request failed: {type(e).__name__}"
    if not resp.ok:
        return f"!! HTTP {resp.status}"

    headers = resp.headers
    ctype = headers.get("content-type", "").lower()
    clen = headers.get("content-length")
    size_mb = (int(clen) / (1024 * 1024)) if clen and clen.isdigit() else None

    if any(ctype.startswith(v) for v in SKIP_VIDEO_CONTENT_TYPES):
        return f".. skipped (video/audio: {ctype.split(';')[0]})"
    if size_mb and size_mb > MAX_FILE_MB:
        return f".. skipped (too big: {size_mb:.1f} MB)"

    cd = headers.get("content-disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
    fname = unquote(m.group(1)) if m else filename_from_url(resp.url)
    if not fname or fname in ("view.php", "file"):
        fname = safe_name(name_hint) or "file"
    fname = safe_name(fname)

    if "text/html" in ctype and not fname.endswith(".html"):
        return f"!! HTML page instead of file (session expired?): {fname}"

    fname = shorten_filename(fname, parent=outdir)
    fpath = outdir / fname
    fpath_lp = long_path(fpath)
    if fpath_lp.exists():
        try: await resp.dispose()
        except Exception: pass
        return f"== {fname} (already)"

    size_hint = f" (~{int(clen)//1024} KB)" if clen and clen.isdigit() else ""
    log(f"         downloading {fname[:60]}{size_hint}...")
    try:
        body = await asyncio.wait_for(resp.body(), timeout=PER_DOWNLOAD_TIMEOUT_MS / 1000)
    except asyncio.TimeoutError:
        try: await resp.dispose()
        except Exception: pass
        return f"!! body timeout: {fname}"
    except Exception as e:
        try: await resp.dispose()
        except Exception: pass
        return f"!! body read failed: {type(e).__name__}"
    finally:
        try: await resp.dispose()
        except Exception: pass

    # Validate: did we actually get the file, or a login/error HTML page?
    if looks_like_html(body) and not fname.endswith(".html"):
        return f"!! got HTML instead of file (session expired?): {fname}"

    if fname.lower().endswith(".pdf") and not body.startswith(PDF_MAGIC):
        # try to find %PDF within first 1KB (some servers prepend BOM)
        idx = body[:1024].find(PDF_MAGIC)
        if idx > 0:
            body = body[idx:]
        else:
            return f"!! invalid PDF (no %PDF header): {fname} [{len(body)} bytes, ctype={ctype}]"

    if fname.lower().endswith((".docx", ".xlsx", ".pptx", ".zip")) and not body.startswith(OFFICE_MAGICS):
        return f"!! invalid archive header: {fname}"

    long_path(outdir).mkdir(parents=True, exist_ok=True)
    try:
        with fpath_lp.open("xb") as output:
            output.write(body)
    except FileExistsError:
        return f"== {fname} (already; not overwritten)"
    kb = len(body) // 1024
    record_new_file(fname, kb)
    log(f">> Saved: {fpath}")
    return f"++ {fname} ({kb} KB)"


async def process_resource(page, ctx, target_url: str, name: str, section_dir: Path):
    if "/mod/resource/view.php" in target_url or "/mod/folder/view.php" in target_url:
        plugin_links = await find_files_on_mod_page(page, ctx, target_url)
        if plugin_links:
            for pl in plugin_links:
                msg = await download(ctx, pl, section_dir, name)
                log(f"      {msg}")
                if "/mod/folder/" not in target_url and msg.startswith(("++", "==")):
                    break  # got it, no need to try more links
        else:
            msg = await download(ctx, target_url, section_dir, name)
            log(f"      {msg}  (via mod-url fallback)")
    elif "pluginfile.php" in target_url:
        msg = await download(ctx, target_url, section_dir, name)
        log(f"      {msg}")
    else:
        log(f"      .. skipped (not a downloadable)")


async def _main_inner(login_only=False):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            storage_state=str(STATE) if STATE.exists() else None,
            accept_downloads=not login_only,
        )
        page = await ctx.new_page()

        logged_in = await is_logged_in(page)
        if not logged_in:
            log("\n>> No saved session (or it has expired).")
            log(">> Log in using the browser window that just opened.")
            log(">> When you can see your course list, come back here and press Enter.\n")
            await page.goto(f"{BASE}/login/index.php")
            input("Press Enter once you are inside the campus: ")
            if not await is_logged_in(page):
                await browser.close()
                raise RuntimeError("Login not confirmed. No session saved; run again after logging in.")

        if login_only or not logged_in:
            # Create the session privately before Playwright writes any cookies.
            STATE.touch(mode=0o600, exist_ok=True)
            STATE.chmod(0o600)
            await ctx.storage_state(path=str(STATE))
            log(f">> Session saved to {STATE}")

        if login_only:
            log(">> Login only: no course downloads.")
            await browser.close()
            return

        courses = await get_courses(page)
        log(f"\n>> Found {len(courses)} courses:")
        for c in courses:
            log(f"   - {c['name']}")

        global CURRENT_COURSE, CURRENT_SECTION
        for course in courses:
            cname = safe_name(course["name"])
            cdir = OUT / cname
            cdir.mkdir(parents=True, exist_ok=True)
            log(f"\n>> [{cname}]")
            CURRENT_COURSE = cname

            try:
                resources = await get_course_resources(page, course["url"])
            except Exception as e:
                log(f"   !! could not read the course: {type(e).__name__}")
                continue

            log(f"   {len(resources)} resources found")

            for idx, r in enumerate(resources, 1):
                target_url = r["url"]
                section_dir = cdir / safe_name(r["section"]) if r["section"] else cdir
                section_dir.mkdir(parents=True, exist_ok=True)
                CURRENT_SECTION = r["section"] or ""
                log(f"   [{idx}/{len(resources)}] {r['name'][:70]}")

                try:
                    # hard cap per resource: 4 min, then we move on no matter what
                    await asyncio.wait_for(
                        process_resource(page, ctx, target_url, r["name"], section_dir),
                        timeout=240,
                    )
                except asyncio.TimeoutError:
                    log(f"      !! hard timeout (>4min), skipped")
                except Exception as e:
                    log(f"      !! error: {type(e).__name__}")

                # free up tab memory between resources
                try:
                    await page.goto("about:blank", timeout=5000)
                except Exception:
                    pass

        await browser.close()


async def main(login_only=False):
    OUT.mkdir(parents=True, exist_ok=True)
    start_ts = datetime.now()
    try:
        with session_lock():
            await _main_inner(login_only=login_only)
    finally:
        if not login_only:
            write_run_log(start_ts, datetime.now())
            log(f">> New files this run: {len(NEW_THIS_RUN)}")
        log(">> Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login-only", action="store_true",
                        help="Save the browser session and exit without collecting courses.")
    args = parser.parse_args()
    try:
        asyncio.run(main(login_only=args.login_only))
    except KeyboardInterrupt:
        log("\nCancelled.")
        sys.exit(1)
    except Exception as exc:
        log(f"\n!! The script stopped: {type(exc).__name__}. You can retry; no failure is permanently skipped.")
        sys.exit(2)
