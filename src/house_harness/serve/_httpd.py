"""Phase-1 HTTP skeleton — stdlib only (no extra deps) so the deployable artifact
comes up and `GET /health` is green from the very first deploy. This exists to make
"live in production" the *first* thing that works, not the last.

Endpoints:
- GET  /health  — open (deploy probe). Returns serve.app.health(): {status, mode}.
- POST /ask      — token-gated. Body {"q": "..."} -> serve.app.answer() -> envelope.
                   live + unwired -> 501 (honest); mock -> the mock envelope.

The production MCP server + richer HTTP layer supersede this module; the /health
contract (status + serve mode) stays stable so the deploy gate never regresses.
"""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from house_harness.obs import tracing as _tracing
from house_harness.serve import app as _app

logger = logging.getLogger(__name__)


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib API)
        if self.path.rstrip("/") in ("/health", ""):
            self._send(200, _app.health())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/ask":
            self._send(404, {"error": "not found"})
            return
        token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip() or None
        try:
            _app.require_token(token)
        except PermissionError:
            self._send(401, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            q = (json.loads(self.rfile.read(length) or b"{}") or {}).get("q", "")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid json"})
            return
        try:
            env = _app.answer(q)  # TODO: guards.redact on egress before returning
        except NotImplementedError as e:
            self._send(501, {"error": str(e)})  # live pipeline not wired yet — honest
            return
        self._send(200, env.model_dump(mode="json"))

    def log_message(self, format: str, *args: object) -> None:  # keep CI/logs quiet  # noqa: A002
        return


def run(ingest_on_boot: bool = False, corpus: Path | None = None, port: int | None = None) -> None:
    port = port or int(os.environ.get("APP_PORT", "8080"))
    logger.info("tracing %s", "on" if _tracing.init_tracing() else "off (no LANGSMITH_API_KEY)")
    if ingest_on_boot:
        if _app.serve_mode().value == "mock":
            logger.info("[mock] skipping ingest-on-boot (the skeleton serves canned envelopes)")
        else:
            from house_harness.pipeline.run import ingest_on_boot as _ingest

            corpus_dir = (
                str(corpus) if corpus else os.environ.get("HOUSE_HARNESS_CORPUS_DIR", "data")
            )
            try:
                if _ingest(corpus_dir):
                    _app.reset_state()  # reload the freshly-built ontology
            except Exception:  # noqa: BLE001 — a failed boot-ingest must not stop the server
                logger.exception("ingest-on-boot failed; serving with whatever is in the store")
    logger.info("house-harness serving on :%d (mode=%s)", port, _app.serve_mode().value)
    ThreadingHTTPServer(("0.0.0.0", port), _Handler).serve_forever()  # noqa: S104 — container binds all interfaces
