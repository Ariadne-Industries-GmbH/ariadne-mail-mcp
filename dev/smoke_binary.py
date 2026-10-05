"""Exercise a packaged executable from a clean directory, without a Python runtime on PATH."""

# ruff: noqa: S101 - smoke-test assertions are intentional

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def check_stdio(executable: str, directory: str, env: dict[str, str]) -> None:
    server = StdioServerParameters(command=executable, args=["stdio"], env=env, cwd=directory)
    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = {tool.name for tool in (await session.list_tools()).tools}
        required = {
            "list_available_accounts",
            "list_folders",
            "move_email",
            "mark_email",
            "send_email_to_allowed_recipients",
        }
        assert required <= tools, tools
        assert not {"send_email", "delete_emails"} & tools, tools
        accounts = await session.call_tool("list_available_accounts", {})
        assert not accounts.isError


def main() -> None:
    executable = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix="email-binary-smoke-") as directory:
        env = {key: value for key, value in os.environ.items() if not key.startswith("MCP_EMAIL_SERVER_")}
        env.update(MCP_EMAIL_SERVER_CONFIG_PATH=str(Path(directory) / "config.toml"), GRADIO_ANALYTICS_ENABLED="False")
        # A frozen binary must locate its own resources and runtime.
        env["PATH"] = (
            os.environ.get("SYSTEMROOT", r"C:\Windows") + r"\System32" if sys.platform == "win32" else "/usr/bin:/bin"
        )
        asyncio.run(asyncio.wait_for(check_stdio(executable, directory, env), 90))
        config = Path(directory) / "config.toml"
        config.write_text('[[emails]]\n[emails.incoming]\npassword = "example-password"\n', encoding="utf-8")
        reset = subprocess.run(  # noqa: S603
            [executable, "reset", "--yes"], cwd=directory, env=env, capture_output=True, text=True, timeout=90
        )
        assert reset.returncode == 0, reset.stderr
        assert not config.exists(), "Binary reset left the active config on disk"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen(  # noqa: S603
                [executable, "ui", "--port", str(port), "--no-open-browser"],
                cwd=directory,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read().decode(errors="replace"))
                    try:
                        response = httpx.get(f"http://127.0.0.1:{port}/config", timeout=2)
                        if response.status_code == 200:
                            config = response.json()
                            assert config["title"] == "Ariadne Mail MCP"
                            print("Binary OK: MCP handshake, tools, reset and Gradio UI from a clean directory.")
                            return
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.5)
                raise TimeoutError("Binary UI did not become ready")
            finally:
                if sys.platform == "win32":
                    # A PyInstaller one-file executable starts a child process that keeps cwd open.
                    taskkill = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "taskkill.exe"
                    subprocess.run(  # noqa: S603
                        [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        check=True,
                        timeout=10,
                    )
                    process.wait(timeout=10)
                else:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()
