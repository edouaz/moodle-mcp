"""Read-only Moodle listings and one explicitly selected download."""
from i18n import translate as tr
import argparse
import asyncio
import json
import sys
import moodle_service as service
from moodle_service import public_url, select_one


async def run(args):
    offset, limit = getattr(args, "offset", 0), getattr(args, "limit", 50)
    if args.command == "session":
        result = await service.session_status()
    elif args.command == "courses":
        result = await service.list_courses(offset, limit)
    elif args.command == "files":
        result = await service.list_files(args.course, offset, limit)
    elif args.command == "search":
        result = await service.search_files(args.course, args.query, offset, limit)
    else:
        result = await service.download_file(args.course,
            file_id=getattr(args, "file_id", None), resource_id=args.resource,
            filename=args.file, include_text=getattr(args, "include_text", False))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("session", help=tr('Check the session without returning its contents'))
    courses = commands.add_parser("courses", help=tr('List courses without downloading files'))
    files = commands.add_parser("files", help=tr('Sections, resources and folder contents'))
    files.add_argument("--course", type=int, required=True)
    download = commands.add_parser("download", help=tr('One file, without overwriting existing files'))
    download.add_argument("--course", type=int, required=True)
    download.add_argument("--resource", type=int)
    download.add_argument("--file-id")
    download.add_argument("--include-text", action="store_true")
    download.add_argument("--file", help=tr('Exact filename within a folder'))
    search = commands.add_parser("search", help=tr('Search for a file by name'))
    search.add_argument("--course", type=int, required=True)
    search.add_argument("query")
    for listing in (courses, files, search):
        listing.add_argument("--offset", type=int, default=0)
        listing.add_argument("--limit", type=int, default=50)
    return root


if __name__ == "__main__":
    try:
        asyncio.run(run(parser().parse_args()))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as exc:
        # Playwright exceptions can embed authenticated URLs: show only the type.
        print(f"Technical error: {type(exc).__name__}. No failure is cached; you can retry.", file=sys.stderr)
        sys.exit(2)
