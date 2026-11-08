"""Shared CLI/MCP operations. Moodle text is untrusted data, never instructions."""
import asyncio
import hashlib
import logging
import os
import re
import tempfile
from contextlib import asynccontextmanager
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pypdf import PdfReader

import scraper
import delivery
from session_lock import session_lock

ROOT = Path(__file__).resolve().parent
DOWNLOADS = ROOT / "downloads"
RECONNECT = f"cd {ROOT} && .venv/bin/python scraper.py --login-only"
FILE_ID = re.compile(r"([1-9][0-9]*):([0-9a-f]{24})\Z")
logging.getLogger("pypdf").setLevel(logging.CRITICAL)


class MoodleError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def public_url(url):
    parts, base = urlparse(url), urlparse(scraper.BASE)
    if (parts.scheme, parts.netloc) != (base.scheme, base.netloc):
        raise MoodleError("UNSAFE_LINK", "Lien hors du Moodle configure refuse.")
    query = parse_qs(parts.query)
    return urlunparse(parts._replace(query=urlencode({k: query[k][0] for k in ("id", "forcedownload") if k in query}), fragment=""))


def select_one(items, key, value):
    matches = [item for item in items if str(item[key]) == str(value)]
    if len(matches) != 1:
        raise MoodleError("INVALID_ID", "Selection absente ou ambigue; utilisez les identifiants de la liste.")
    return matches[0]


def paginate(items, offset=0, limit=50):
    if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 100:
        raise MoodleError("INVALID_PAGE", "offset doit etre positif ou nul et limit compris entre 1 et 100.")
    end = offset + limit
    return {"items": items[offset:end], "total": len(items), "offset": offset,
            "next_offset": end if end < len(items) else None,
            "content_trust": "untrusted_moodle_data"}


def file_entry(resource, url):
    url = public_url(url)
    if "/pluginfile.php/" not in urlparse(url).path:
        raise MoodleError("UNSUPPORTED_FILE", "Lien de fichier Moodle standard introuvable.")
    digest = hashlib.sha256(urlparse(url).path.encode()).hexdigest()[:24]
    return {"kind": "file", "id": f"{resource['id']}:{digest}",
            "resource_id": resource["id"], "section_id": resource["section_id"],
            "section": resource["section"], "name": scraper.filename_from_url(url),
            "resource_name": resource["name"], "url": url}


def local_path(course_id, file):
    # Fixed root and identifiers prevent Moodle filenames from selecting local paths.
    root = DOWNLOADS.resolve()
    match = FILE_ID.fullmatch(file["id"])
    if not match:
        raise MoodleError("INVALID_ID", "Identifiant fichier local invalide.")
    path = root / f"course-{int(course_id)}" / scraper.safe_name(file["section_id"] or "general") / f"resource-{int(file['resource_id'])}" / match[2] / scraper.safe_name(file["name"], maxlen=180)
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise MoodleError("UNSAFE_PATH", "Chemin de stockage non autorise.")
    return path


def verify_file(path, include_text=False):
    if path.is_symlink() or not path.is_file():
        raise MoodleError("INVALID_FILE", "Fichier local absent ou non autorise.")
    with path.open("rb") as head:
        prefix = head.read(1024)
    if scraper.looks_like_html(prefix):
        raise MoodleError("HTML_INSTEAD_OF_FILE", "Page HTML recue; reconnectez Moodle puis reessayez.")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    result = {"bytes": path.stat().st_size, "sha256": digest}
    if path.suffix.lower() == ".pdf":
        if not prefix.startswith(b"%PDF-"):
            raise MoodleError("INVALID_PDF", "Signature PDF absente; fichier refuse.")
        try:
            reader = PdfReader(path, strict=True)
            result["pdf_pages"] = len(reader.pages)
            if not reader.pages:
                raise ValueError("Empty PDF")
            if include_text:
                text = ""
                processed = 0
                for page in reader.pages:
                    processed += 1
                    text += (page.extract_text() or "") + "\n"
                    if len(text) > 12000:
                        break
                result["text"] = text[:12000]
                result["text_truncated"] = len(text) > 12000 or processed < len(reader.pages)
        except Exception:
            raise MoodleError("INVALID_PDF", "Le PDF ne peut pas etre lu; fichier refuse.") from None
    return result


async def save_file(ctx, course_id, file, include_text=False):
    path = local_path(course_id, file)
    if path.exists():
        return {"status": "already_present", "local_path": str(path), **verify_file(path, include_text)}
    # No redirect may send the saved session toward an unrelated host.
    url = file["url"]
    response = None
    temporary = None
    try:
        for _ in range(6):
            response = await ctx.request.get(public_url(url), max_redirects=0, timeout=30000)
            if response.status in (301, 302, 303, 307, 308):
                from urllib.parse import urljoin
                url = public_url(urljoin(url, response.headers.get("location", "")))
                await response.dispose()
                response = None
                continue
            break
        if response is None or not response.ok:
            raise MoodleError("DOWNLOAD_FAILED", "Reponse HTTP en echec; la meme demande peut etre reessayee.")
        ctype = response.headers.get("content-type", "").lower()
        if "html" in ctype:
            raise MoodleError("HTML_INSTEAD_OF_FILE", "Page HTML recue au lieu du fichier. Reconnexion : " + RECONNECT)
        size = response.headers.get("content-length", "")
        if size.isdigit() and int(size) > 20 * 1024 * 1024:
            raise MoodleError("FILE_TOO_LARGE", "Limite personnelle : 20 Mio par fichier.")
        body = await response.body()
        if len(body) > 20 * 1024 * 1024:
            raise MoodleError("FILE_TOO_LARGE", "Limite personnelle : 20 Mio par fichier.")
        if not body or scraper.looks_like_html(body):
            raise MoodleError("INVALID_FILE", "Fichier vide ou HTML; aucun fichier enregistre, reessayez apres reconnexion.")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Publish only a complete, validated file; never leave a partial final file.
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".moodle-part-", suffix=path.suffix, delete=False) as output:
            temporary = Path(output.name)
            output.write(body)
        metadata = verify_file(temporary, include_text)
        try:
            os.link(temporary, path)
            status = "downloaded"
        except FileExistsError:
            metadata = verify_file(path, include_text)
            status = "already_present"
        return {"status": status, "local_path": str(path), **metadata}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if response is not None:
            await response.dispose()


@asynccontextmanager
async def connection():
    try:
        with session_lock():
            async with asyncio.timeout(100):
                if not scraper.STATE.exists():
                    raise MoodleError("SESSION_EXPIRED", "Session absente. Reconnexion : " + RECONNECT)
                async with scraper.async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    try:
                        ctx = await browser.new_context(storage_state=str(scraper.STATE), accept_downloads=False)
                        page = await ctx.new_page()
                        page.set_default_timeout(20000)
                        if not await scraper.is_logged_in(page):
                            raise MoodleError("SESSION_EXPIRED", "Session invite ou expiree. Reconnexion : " + RECONNECT)
                        yield page, ctx
                    finally:
                        await browser.close()
    except MoodleError:
        raise
    except RuntimeError as exc:
        if str(exc).startswith("MOODLE_BUSY:"):
            raise MoodleError("MOODLE_BUSY", "Une operation Moodle est deja en cours; reessayez.") from None
        raise MoodleError("MOODLE_FAILED", "Operation Moodle interrompue; vous pouvez reessayer.") from None
    except Exception:
        # Third-party errors may contain credentials, URLs or cookie values.
        raise MoodleError("MOODLE_FAILED", "Operation Moodle en echec ou trop longue; reessayez ou reconnectez la session.") from None


async def courses_on_page(page):
    courses = await scraper.get_courses(page)
    return sorted([{"id": parse_qs(urlparse(public_url(c["url"])).query)["id"][0],
                    "name": unescape(c["name"]), "url": public_url(c["url"])} for c in courses], key=lambda c: int(c["id"]))


async def inventory(page, ctx, course_id, resource_id=None):
    course = select_one(await courses_on_page(page), "id", course_id)
    resources = await scraper.get_course_resources(page, course["url"])
    sections = await page.locator('li.section, .course-section').evaluate_all('''ss => ss.map(s => ({
        kind: 'section', id: s.querySelector('a[href*="/course/section.php?id="]')?.href
            ? new URL(s.querySelector('a[href*="/course/section.php?id="]').href).searchParams.get('id') : s.id,
        name: s.querySelector('.sectionname,h2,h3,h4')?.textContent.trim() || ''
    }))''')
    modules, files = [], []
    for resource in resources:
        if not any(p in resource["url"] for p in ("/mod/resource/", "/mod/folder/")):
            continue
        resource["url"] = public_url(resource["url"])
        resource["id"] = parse_qs(urlparse(resource["url"]).query)["id"][0]
        resource["section_id"] = resource.get("section_id") or next((s["id"] for s in sections if s["name"] == resource["section"]), "general")
        resource["kind"] = "folder" if "/mod/folder/" in resource["url"] else "resource"
        modules.append(resource)
    if resource_id is not None:
        modules = [select_one(modules, "id", resource_id)]
    for resource in modules:
        links = await scraper.find_files_on_mod_page(page, ctx, resource["url"])
        # Empty folders are valid; a non-folder without a file is an explicit failure.
        if not links and resource["kind"] != "folder":
            raise MoodleError("RESOURCE_UNAVAILABLE", "Ressource inaccessible ou session expiree; reconnectez puis reessayez.")
        files.extend(file_entry(resource, link) for link in dict.fromkeys(links))
    if not await scraper.is_logged_in(page):
        raise MoodleError("SESSION_EXPIRED", "Session expiree pendant la lecture. Reconnexion : " + RECONNECT)
    return course, sections, modules, sorted(files, key=lambda f: f["id"])


async def session_status():
    try:
        async with connection():
            return {"valid": True, "content_trust": "untrusted_moodle_data"}
    except MoodleError as exc:
        if exc.code == "SESSION_EXPIRED":
            return {"valid": False, "error": exc.code, "reconnect_command": RECONNECT}
        raise


async def list_courses(offset=0, limit=50):
    paginate([], offset, limit)
    async with connection() as (page, _):
        return paginate(await courses_on_page(page), offset, limit)


async def list_files(course_id, offset=0, limit=50):
    paginate([], offset, limit)
    async with connection() as (page, ctx):
        course, sections, modules, files = await inventory(page, ctx, course_id)
        return {"course": course, **paginate(sections + modules + files, offset, limit)}


async def search_files(course_id, query, offset=0, limit=50):
    if not query.strip() or len(query) > 200:
        raise MoodleError("INVALID_QUERY", "Recherche vide ou trop longue (maximum 200 caracteres).")
    paginate([], offset, limit)
    async with connection() as (page, ctx):
        course, _, _, files = await inventory(page, ctx, course_id)
        matches = [f for f in files if query.casefold() in (f["name"] + " " + f["resource_name"]).casefold()]
        return {"course": course, **paginate(matches, offset, limit)}


async def download_file(course_id, file_id=None, resource_id=None, filename=None, include_text=False,
                        destination_root=None, destination_folder="Moodle"):
    if destination_root is not None:
        delivery.destination(destination_root, destination_folder)
    if file_id:
        match = FILE_ID.fullmatch(file_id)
        if not match:
            raise MoodleError("INVALID_ID", "Identifiant fichier invalide; utilisez la recherche ou la liste.")
        resource_id = int(match[1])
    if resource_id is None:
        raise MoodleError("INVALID_ID", "Un identifiant fichier ou ressource est requis.")
    async with connection() as (page, ctx):
        course, _, _, files = await inventory(page, ctx, course_id, resource_id)
        if file_id:
            file = select_one(files, "id", file_id)
        elif filename:
            file = select_one(files, "name", filename)
        elif len(files) == 1:
            file = files[0]
        else:
            raise MoodleError("INVALID_ID", "Plusieurs fichiers ou aucun : choisissez un identifiant fichier de la liste.")
        result = await save_file(ctx, course_id, file, include_text)
        transfer = None
        if destination_root is not None:
            job = delivery.enqueue(Path(result["local_path"]), destination_root, destination_folder)
            transfer = {k: job[k] for k in ("id", "status", "destination_root", "destination_folder")}
        return {"course": course, "file": file, **result,
                "delivery": transfer,
                "content_trust": "untrusted_moodle_data", "file_bytes_transferred_to_chatgpt": False,
                "transfer_note": "Fichier sur le serveur MCP. Si delivery est renseigne, transfert en attente du client Mac version 2; verifier get_mac_delivery_status pour la reception et le chemin final. La copie VPS est nettoyee apres accuse SHA-256. Aucun fichier joint ChatGPT."}
