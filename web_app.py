"""HTTP entry point: serves the workbench UI and the /v1 JSON API.

Routing is declarative (see ROUTES): each entry maps method + path pattern to
a handler taking (manager, body, query, params). Adding an endpoint means
adding one line here plus a handler in api_service.py.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, unquote, urlparse

import auto_refresh
from api_service import (
    create_alias,
    delete_alias,
    disable_alias,
    enable_alias,
    error_response,
    export_aliases_csv,
    get_mail_message,
    import_session,
    list_aliases,
    list_mail_folders,
    list_mail_messages,
    ok_response,
    refresh_session,
    require_api_key,
    session_status,
)
from hme import HmeError
from icloud_web_session import ICloudSessionManager


def create_manager_from_env(env: Mapping[str, str] | None = None) -> ICloudSessionManager:
    env = os.environ if env is None else env
    return ICloudSessionManager(
        state_dir=env.get("HME_STATE_DIR", "state"),
        config_path=env.get("ICLOUD_HME_CONFIG", "hme-config.json"),
    )


MANAGER = create_manager_from_env()

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _read_static(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def render_index() -> str:
    return _read_static("index.html")


def health_payload() -> dict[str, Any]:
    return ok_response({"status": "ok"})


def is_api_path(path: str) -> bool:
    return urlparse(path).path.startswith("/v1/")


# ---------- /v1 route handlers ----------

Handler = Callable[[Any, dict[str, Any], dict[str, str], dict[str, str]], dict[str, Any]]


def _h_session_status(manager, body, query, params):
    return session_status(manager)


def _h_session_refresh(manager, body, query, params):
    return refresh_session(manager)


def _h_session_import(manager, body, query, params):
    return import_session(manager, body)


def _h_auto_refresh_get(manager, body, query, params):
    return ok_response(auto_refresh.status(manager))


def _h_auto_refresh_update(manager, body, query, params):
    return ok_response(auto_refresh.update(body, manager))


def _h_auto_refresh_run(manager, body, query, params):
    return ok_response(auto_refresh.run_once(manager))


def _h_aliases_list(manager, body, query, params):
    return list_aliases(manager.get_client())


def _h_aliases_export(manager, body, query, params):
    return ok_response(export_aliases_csv(manager.get_client()))


def _h_aliases_create(manager, body, query, params):
    return create_alias(manager.get_client(), body)


def _h_alias_disable(manager, body, query, params):
    return disable_alias(manager.get_client(), unquote(params["anonymousId"]))


def _h_alias_enable(manager, body, query, params):
    return enable_alias(manager.get_client(), unquote(params["anonymousId"]))


def _h_alias_delete(manager, body, query, params):
    return delete_alias(manager.get_client(), unquote(params["anonymousId"]))


def _h_mail_folders(manager, body, query, params):
    return list_mail_folders(manager.get_mail_client())


def _h_mail_messages(manager, body, query, params):
    return list_mail_messages(manager.get_mail_client(), query)


def _h_mail_message(manager, body, query, params):
    return get_mail_message(manager.get_mail_client(), unquote(params["guid"]))


ROUTES: tuple[tuple[str, re.Pattern[str], Handler], ...] = (
    ("GET", re.compile(r"^/v1/session/status$"), _h_session_status),
    ("POST", re.compile(r"^/v1/session/refresh$"), _h_session_refresh),
    ("POST", re.compile(r"^/v1/session/import$"), _h_session_import),
    ("GET", re.compile(r"^/v1/auto-refresh$"), _h_auto_refresh_get),
    ("POST", re.compile(r"^/v1/auto-refresh$"), _h_auto_refresh_update),
    ("POST", re.compile(r"^/v1/auto-refresh/run$"), _h_auto_refresh_run),
    ("GET", re.compile(r"^/v1/aliases$"), _h_aliases_list),
    ("GET", re.compile(r"^/v1/aliases/export\.csv$"), _h_aliases_export),
    ("POST", re.compile(r"^/v1/aliases$"), _h_aliases_create),
    ("POST", re.compile(r"^/v1/aliases/(?P<anonymousId>[^/]+)/disable$"), _h_alias_disable),
    ("POST", re.compile(r"^/v1/aliases/(?P<anonymousId>[^/]+)/enable$"), _h_alias_enable),
    ("POST", re.compile(r"^/v1/aliases/(?P<anonymousId>[^/]+)/delete$"), _h_alias_delete),
    ("GET", re.compile(r"^/v1/mail/folders$"), _h_mail_folders),
    ("GET", re.compile(r"^/v1/mail/messages$"), _h_mail_messages),
    ("GET", re.compile(r"^/v1/mail/messages/(?P<guid>[^/]+)$"), _h_mail_message),
)


def dispatch_private_api(
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
    manager: ICloudSessionManager,
    api_key: str | None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    parsed = urlparse(path)
    query = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
    try:
        require_api_key(headers, api_key)
        for route_method, pattern, handler in ROUTES:
            if route_method != method:
                continue
            match = pattern.match(parsed.path)
            if match is None:
                continue
            payload = _json_body(body) if method == "POST" else {}
            return HTTPStatus.OK, handler(manager, payload, query, match.groupdict())
        return HTTPStatus.NOT_FOUND, error_response("NOT_FOUND", "not found")
    except PermissionError as exc:
        return HTTPStatus.UNAUTHORIZED, error_response("UNAUTHORIZED", str(exc))
    except (ValueError, json.JSONDecodeError) as exc:
        return HTTPStatus.BAD_REQUEST, error_response("BAD_REQUEST", str(exc))
    except HmeError as exc:
        code, status = _hme_error_code_and_status(str(exc))
        return status, error_response(code, str(exc))
    except OSError as exc:
        return HTTPStatus.INTERNAL_SERVER_ERROR, error_response("STORAGE_ERROR", str(exc))


def _json_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _hme_error_code_and_status(message: str) -> tuple[str, HTTPStatus]:
    if "尚未匯入" in message or "Missing required config" in message or "Config file not found" in message:
        return "SESSION_MISSING", HTTPStatus.CONFLICT
    # 421 means the (mail) session is no longer valid, same as 401/403;
    # keep in sync with auto_refresh._AUTH_ERROR_MARKERS.
    if any(marker in message for marker in ("HTTP 401", "HTTP 403", "HTTP 421")):
        return "SESSION_EXPIRED", HTTPStatus.CONFLICT
    return "ICLOUD_ERROR", HTTPStatus.BAD_GATEWAY


class HmeWebHandler(BaseHTTPRequestHandler):
    server_version = "HmeWeb/0.2"

    def do_GET(self) -> None:
        try:
            if self.path == "/health":
                self._json(health_payload())
                return
            if is_api_path(self.path):
                status, payload = dispatch_private_api(
                    "GET",
                    self.path,
                    self.headers,
                    b"",
                    MANAGER,
                    os.environ.get("HME_API_KEY"),
                )
                self._json(payload, status=status)
                return
            if self.path == "/" or self.path.startswith("/?"):
                self._html(render_index())
                return
            if self.path.startswith("/static/"):
                self._serve_static(self.path[len("/static/"):])
                return
            if self.path == "/favicon.ico":
                self._send(HTTPStatus.NO_CONTENT, b"", "text/plain")
                return
            self._json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)
        except HmeError as exc:
            self._json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        try:
            if is_api_path(self.path):
                status, payload = dispatch_private_api(
                    "POST",
                    self.path,
                    self.headers,
                    self._read_body(),
                    MANAGER,
                    os.environ.get("HME_API_KEY"),
                )
                self._json(payload, status=status)
                return
            self._json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)
        except (HmeError, ValueError, json.JSONDecodeError) as exc:
            self._json({"ok": False, "error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), format % args))

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length)

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _html(self, content: str) -> None:
        self._send(HTTPStatus.OK, content.encode("utf-8"), "text/html; charset=utf-8")

    STATIC_CONTENT_TYPES = {
        "app.css": "text/css; charset=utf-8",
        "app.js": "text/javascript; charset=utf-8",
        "logo.svg": "image/svg+xml",
    }

    def _serve_static(self, name: str) -> None:
        content_type = self.STATIC_CONTENT_TYPES.get(name)
        if content_type is None:  # whitelist only; blocks path traversal
            self._json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        self._send(HTTPStatus.OK, _read_static(name).encode("utf-8"), content_type)

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def create_server(host: str, port: int) -> HTTPServer:
    # Threading keeps the UI responsive while a slow Apple request is in flight.
    server = ThreadingHTTPServer((host, port), HmeWebHandler)
    server.daemon_threads = True
    return server


def run(host: str, port: int) -> None:
    server = create_server(host, port)
    auto_refresh.start_worker(MANAGER)
    print(f"Listening on http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        auto_refresh.stop_worker()
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Local web UI for iCloud Hide My Email")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=int(os.environ.get("PORT", "8000")), type=int)
    args = parser.parse_args()
    run(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
