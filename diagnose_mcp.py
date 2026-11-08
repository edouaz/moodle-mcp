"""Real stdio MCP check; --live opts into Moodle reads and --download one PDF."""
import argparse
import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(line_buffering=True)

async def diagnose(live=False, download=False):
    parameters = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).parent / "mcp_server.py")])
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=110)) as client:
            initialized = await client.initialize()
            tools = (await client.list_tools()).tools
            print(json.dumps({"transport": "local_stdio", "server": initialized.serverInfo.name,
                              "tools": [t.name for t in tools], "chatgpt_tested": False}))
            if not live:
                return

            async def call(name, arguments):
                result = await client.call_tool(name, arguments)
                data = result.structuredContent
                if result.isError:
                    print(json.dumps({"failed_tool": name, "result": data}, ensure_ascii=False))
                    raise RuntimeError("MCP tool failed")
                return data

            status = await call("check_moodle_session", {})
            print("SESSION", json.dumps(status, ensure_ascii=False))
            if not status["valid"]:
                return
            courses = await call("list_moodle_courses", {})
            print("COURSES", json.dumps(courses, ensure_ascii=False))
            offset, items = 0, []
            while offset is not None:
                page = await call("list_moodle_files", {"course_id": 2798, "offset": offset, "limit": 100})
                items.extend(page["items"])
                offset = page["next_offset"]
            print("INVENTORY", json.dumps({"total": len(items), "sections": sum(i["kind"] == "section" for i in items),
                                          "files": sum(i["kind"] == "file" for i in items)}))
            found = await call("search_moodle_files", {"course_id": 2798, "query": "APE01_TP1"})
            print("SEARCH", json.dumps(found, ensure_ascii=False))
            empty = await call("search_moodle_files", {"course_id": 2798, "query": "no-such-file-18b652ec"})
            assert empty["total"] == 0
            invalid = await client.call_tool("list_moodle_files", {"course_id": 999999999})
            assert invalid.isError and invalid.structuredContent["error"]["code"] == "INVALID_ID"
            if download:
                exercises = [file for file in found["items"] if file["name"] == "LINFO1111_2026_APE01_TP1.pdf"]
                assert len(exercises) == 1
                arguments = {"course_id": 2798, "file_id": exercises[0]["id"], "include_text": True}
                result = await call("download_moodle_file", arguments)
                print("DOWNLOAD", json.dumps({k: v for k, v in result.items() if k != "text"}, ensure_ascii=False))
                assert result["pdf_pages"] > 0 and result["text"] and not result["file_bytes_transferred_to_chatgpt"]
                again = await call("download_moodle_file", arguments)
                assert again["status"] == "already_present" and again["sha256"] == result["sha256"]
                print("EXISTING_FILE_OK")
            print("LOCAL_MCP_LIVE_OK (pas un test via tunnel ou ChatGPT)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(diagnose(args.live, args.download))
    except Exception:
        print("Diagnostic interrompu; voir l'erreur structuree precedente, aucun detail secret affiche.", file=sys.stderr)
        sys.exit(1)
