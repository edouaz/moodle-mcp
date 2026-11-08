"""Real MCP subprocess initialization/discovery; no Moodle requests."""
import sys
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_discover_and_safe_errors(self):
        parameters = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).parent / "mcp_server.py")])
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                info = await client.initialize()
                self.assertEqual(info.serverInfo.name, "Moodle personnel")
                tools = (await client.list_tools()).tools
                self.assertEqual(len(tools), 7)
                for tool in tools:
                    self.assertIsNotNone(tool.outputSchema)
                    self.assertFalse(tool.annotations.destructiveHint)
                    self.assertTrue(tool.annotations.openWorldHint)
                    self.assertEqual(tool.annotations.readOnlyHint, tool.name != "download_moodle_file")
                    self.assertNotIn("url", tool.inputSchema["properties"])
                    self.assertNotIn("path", tool.inputSchema["properties"])
                empty = await client.call_tool("search_moodle_files", {"course_id": 2798, "query": ""})
                self.assertTrue(empty.isError)
                self.assertEqual(empty.structuredContent["error"]["code"], "INVALID_QUERY")
                invalid = await client.call_tool("download_moodle_file", {"course_id": 2798, "file_id": "../../session.json"})
                self.assertTrue(invalid.isError)
                self.assertEqual(invalid.structuredContent["error"]["code"], "INVALID_ID")


if __name__ == "__main__":
    unittest.main()
