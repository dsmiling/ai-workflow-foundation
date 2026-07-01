import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from aiwf import cli_acp as cli_acp_module

from aiwf.cli_acp import (
    AcpSessionScope,
    CliAcpClient,
    SessionRegistry,
    resolve_spawn_argv,
)


class CliAcpParseTests(unittest.TestCase):
    def test_resolve_spawn_argv_cursor_windows(self) -> None:
        with patch.object(cli_acp_module.os, "name", "nt"), patch.dict(
            "os.environ",
            {"LOCALAPPDATA": str(Path.home() / "AppData" / "Local")},
            clear=False,
        ):
            ps1 = Path.home() / "AppData" / "Local" / "cursor-agent" / "cursor-agent.ps1"
            if ps1.exists():
                argv = resolve_spawn_argv("cursor-agent-acp", Path.cwd())
                self.assertIn("acp", argv)
                self.assertTrue(any("powershell" in part.lower() for part in argv))

    def test_resolve_spawn_argv_uses_scope_workspace(self) -> None:
        workspace = Path("G:/demo/.aiwf/assist/assist_demo")
        with patch.dict(
            "os.environ",
            {"AIWF_CURSOR_WORKSPACE": "G:/other/unity-project"},
            clear=False,
        ):
            argv = resolve_spawn_argv("cursor-agent-acp", workspace)
        joined = " ".join(argv)
        self.assertIn(str(workspace.resolve()), joined)

    def test_session_registry_serializes_scope(self) -> None:
        SessionRegistry.reset()
        registry = SessionRegistry.get()
        calls: list[str] = []

        class FakeClient:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs
                self._chat_id = None
                self._proc = MagicMock()
                self._proc.poll.return_value = None

            def start_session(self) -> None:
                calls.append("start")

            def create_chat(self) -> str:
                self._chat_id = "chat-123"
                return "chat-123"

            def load_chat(self, chat_id: str) -> None:
                self._chat_id = chat_id

            @property
            def chat_id(self):
                return self._chat_id

            def close(self) -> None:
                calls.append("close")

        scope = AcpSessionScope(
            provider_id="cursor-agent-acp",
            scope_key="wf:test",
            workspace=Path("."),
        )
        with patch("aiwf.cli_acp.CliAcpClient", FakeClient):
            c1 = registry.acquire(scope)
            self.assertIsNotNone(c1)
            c2 = registry.acquire(scope)
            self.assertIs(c1, c2)
            registry.release_scope("wf:test")
        SessionRegistry.reset()


class CliAcpClientDispatchTests(unittest.TestCase):
    def test_dispatch_session_update_chunk(self) -> None:
        client = CliAcpClient(
            provider_id="cursor-agent-acp",
            workspace=Path("."),
            scope_key="test",
            timeout=5,
        )
        client._dispatch_message(
            {
                "method": "session/update",
                "params": {
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"text": "hello"},
                    }
                },
            }
        )
        self.assertEqual(client._stream_buffer, ["hello"])

    def test_format_rpc_error_includes_details(self) -> None:
        client = CliAcpClient(
            provider_id="cursor-agent-acp",
            workspace=Path("."),
            scope_key="test",
            timeout=5,
        )
        client._stderr_tail.append("provider stderr detail")

        message = client._format_rpc_error(
            {
                "code": -32603,
                "message": "Internal error",
                "data": {"reason": "session failed"},
            }
        )

        self.assertIn("Internal error", message)
        self.assertIn("code=-32603", message)
        self.assertIn("session failed", message)
        self.assertIn("provider stderr detail", message)

    def test_dispatch_permission_auto_allow(self) -> None:
        client = CliAcpClient(
            provider_id="cursor-agent-acp",
            workspace=Path("."),
            scope_key="test",
            timeout=5,
        )
        client._proc = MagicMock()
        client._proc.stdin = MagicMock()
        client._dispatch_message(
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "session/request_permission",
                "params": {},
            }
        )
        client._proc.stdin.write.assert_called()


if __name__ == "__main__":
    unittest.main()
