import threading
from functools import partial
from pathlib import Path
from typing import Generator, Tuple

import pytest
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
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

