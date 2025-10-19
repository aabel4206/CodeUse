import threading
from functools import partial
from pathlib import Path
from typing import Generator, Tuple

import pytest
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
import time
import uvicorn

from tool.executor.main import app as executor_app


@pytest.fixture(scope="session")
def test_page_server() -> Generator[Tuple[str, int], None, None]:
    """Serve the static test page on an ephemeral port for Playwright-driven tests."""

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args):
            return

    handler = partial(
        QuietHandler,
        directory=str(Path(__file__).resolve().parents[1] / "tool" / "executor" / "test_page"),
    )

    # Bind to an ephemeral port on loopback.
    with TCPServer(("127.0.0.1", 0), handler, bind_and_activate=False) as httpd:
        httpd.allow_reuse_address = True
        httpd.server_bind()
        httpd.server_activate()

        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield (f"http://127.0.0.1:{port}", port)
        finally:
            httpd.shutdown()
            thread.join()


@pytest.fixture(scope="session")
def test_page_url(test_page_server: Tuple[str, int]) -> str:
    """Return the base URL for the served test page."""
    base_url, _ = test_page_server
    return f"{base_url}/index.html"


@pytest.fixture(scope="session")
def executor_server_url(test_page_server: Tuple[str, int]) -> Generator[str, None, None]:
    """Run the executor FastAPI app on an ephemeral port for integration tests."""
    config = uvicorn.Config(
        executor_app,
        host="127.0.0.1",
        port=0,
        log_level="error",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    while not getattr(server, "started", False):
        time.sleep(0.05)

    sockets = getattr(server, "servers", [])[0].sockets
    port = sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
