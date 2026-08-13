import unittest
import tempfile
from http import HTTPStatus
from http.server import HTTPServer, ThreadingHTTPServer
from pathlib import Path

import auto_refresh
from web_app import (
    _hme_error_code_and_status,
    create_manager_from_env,
    create_server,
    dispatch_private_api,
    health_payload,
    is_api_path,
    render_index,
)


class FakeManager:
    def __init__(self):
        self.config_path = "hme-config.json"
        self.metadata_path = "state/hme-session.json"
        self.state_dir = "state"
        self.metadata = None

    def status(self):
        return {"metadataDetected": True}

    def check(self):
        return {"sessionValid": True, "needsReauth": False}

    def get_client(self):
        return FakeClient()

    def get_mail_client(self):
        return FakeMailClient()

    def reload(self):
        self.metadata = None


class FakeClient:
    def list_aliases(self):
        return [{"hme": "a@icloud.com", "anonymousId": "id1"}]

    def create_alias(self, label, note=""):
        return {"hme": "new@icloud.com", "label": label, "note": note}

    def deactivate_alias(self, anonymous_id):
        return {"anonymousId": anonymous_id, "isActive": False}

    def activate_alias(self, anonymous_id):
        return {"anonymousId": anonymous_id, "isActive": True}

    def delete_alias(self, anonymous_id):
        return {"anonymousId": anonymous_id, "deleted": True}


class FakeMailClient:
    def list_folders(self):
        return [{"guid": "folder-1", "name": "Inbox", "role": "INBOX", "unreadCount": 1, "totalCount": 3}]

    def inbox_folder(self):
        return self.list_folders()[0]

    def list_messages(self, folder_guid, limit=20, offset=0):
        return {
            "folder": folder_guid,
            "offset": offset,
            "total": 1,
            "messages": [{"guid": "msg 1", "from": "a@b.c", "subject": "hi", "limit": limit}],
        }

    def get_message(self, guid):
        return {"guid": guid, "subject": "hi", "textBody": "code 123456"}


class WebAppTests(unittest.TestCase):
    def test_create_manager_from_env_uses_container_paths(self):
        manager = create_manager_from_env(
            {
                "ICLOUD_HME_CONFIG": "/data/hme-config.json",
                "HME_STATE_DIR": "/data/state",
            }
        )

        self.assertEqual(manager.config_path.as_posix(), "/data/hme-config.json")
        self.assertEqual(manager.state_dir.as_posix(), "/data/state")

    def test_health_payload_uses_stable_api_envelope(self):
        payload = health_payload()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"], {"status": "ok"})
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["meta"]["service"], "hme-manager")

    def test_expired_icloud_session_is_not_api_key_unauthorized(self):
        code, status = _hme_error_code_and_status("HTTP 401: Invalid global session")

        self.assertEqual(code, "SESSION_EXPIRED")
        self.assertEqual(status, HTTPStatus.CONFLICT)

    def test_mail_421_maps_to_session_expired(self):
        code, status = _hme_error_code_and_status('HTTP 421: {"error": 2, "reason": "Invalid global session"}')

        self.assertEqual(code, "SESSION_EXPIRED")
        self.assertEqual(status, HTTPStatus.CONFLICT)

    def test_render_index_markup_and_static_assets(self):
        html = render_index()

        # links the extracted static assets instead of inlining CSS/JS
        self.assertIn('href="/static/app.css"', html)
        self.assertIn('src="/static/app.js"', html)
        self.assertNotIn("<style>", html)
        # main logic stays external; only a tiny inline theme bootstrap is allowed
        self.assertLessEqual(html.count("<script"), 2)

        # workbench shell: sidebar nav with four views
        for view in ("aliases", "inbox", "builder", "session"):
            self.assertIn(f'data-view="{view}"', html)
        # builder hooks
        self.assertIn("endpointList", html)
        for endpoint in ("list", "create", "status", "refresh", "disable", "enable", "delete",
                         "mailFolders", "mailMessages", "mailMessage"):
            self.assertIn(f'data-endpoint="{endpoint}"', html)
        self.assertIn('id="requestPreview"', html)
        self.assertIn('id="responsePreview"', html)
        self.assertIn('id="actualOutput"', html)
        self.assertIn("request-actions", html)
        self.assertIn('<button id="sendBtn" type="button" class="primary">送出</button>', html)
        self.assertNotIn("送出目前 API", html)
        # aliases + session hooks
        self.assertIn('data-alias-tab="source"', html)
        self.assertIn("createAliasForm", html)
        self.assertIn('id="exportCsvBtn"', html)
        self.assertIn("Mail / ForwardTo", html)
        self.assertIn('id="sessionRegion"', html)
        self.assertIn("refreshSessionBtn", html)
        self.assertNotIn('id="loginBtn"', html)
        # inbox view hooks
        self.assertIn('id="view-inbox"', html)
        self.assertIn('id="mailFolderSelect"', html)
        self.assertIn('id="mailList"', html)
        self.assertIn('id="mailReader"', html)
        self.assertIn('id="refreshMailBtn"', html)
        # toast container for visible operation feedback
        self.assertIn('id="toasts"', html)
        # auto-refresh UI restored
        self.assertIn("autoRefreshEnabled", html)
        self.assertIn("autoRefreshInterval", html)
        self.assertIn('id="autoRefreshEnabled" type="checkbox" checked', html)
        self.assertIn('id="autoRefreshInterval" type="number" min="300" step="60" value="600"', html)
        self.assertIn("auto-refresh-actions", html)
        # manual import UI present, covering both regions
        self.assertIn("importCurl", html)
        self.assertIn("手動匯入 Session", html)
        self.assertIn("https://www.icloud.com/icloudplus/", html)
        self.assertIn("https://www.icloud.com.cn/icloudplus/", html)
        self.assertIn("list?clientBuildNumber", html)
        self.assertIn("Copy as cURL (bash)", html)
        # api key modal
        self.assertIn('id="apiKeyModal"', html)
        self.assertIn('id="modalApiKeyInput"', html)
        # logo / favicon, theme toggle, author link
        self.assertIn('rel="icon"', html)
        self.assertIn("/static/logo.svg", html)
        self.assertIn('<a class="brand-name" href="https://github.com/banana2556/hme-manager"', html)
        self.assertIn('id="themeToggle"', html)
        self.assertLess(html.index('id="themeToggle"'), html.index('id="logoutBtn"'))
        self.assertIn('id="status" class="sr-only"', html)
        self.assertNotIn('class="status-chip"', html)
        self.assertIn('id="sessionMiniStatus"', html)
        self.assertIn('class="logout-label"', html)
        self.assertIn("github.com/banana2556", html)
        # no baked-in default secret in the served page
        self.assertNotIn("dev-secret", html)

    def test_logo_svg_served_as_svg(self):
        from web_app import HmeWebHandler, _read_static

        self.assertEqual(HmeWebHandler.STATIC_CONTENT_TYPES.get("logo.svg"), "image/svg+xml")
        self.assertIn("<svg", _read_static("logo.svg"))

    def test_app_js_has_logic_and_targets_v1(self):
        from web_app import _read_static

        app_js = _read_static("app.js")
        for fn in ("renderSessionInfo", "syncCurlFromRequestEditor", "filterAliases",
                   "runSelectedOperation", "runAliasAction", "showView", "loadAutoRefresh",
                   "submitImportSession", "loadMailFolders", "loadMailMessages",
                   "openMailMessage", "extractVerificationCode", "exportAliasesCsv",
                   "toast", "copyText", "regionLabel"):
            self.assertIn(fn, app_js)
        self.assertIn('data-action="toggle-alias"', app_js)
        self.assertIn('data-action="delete-alias"', app_js)
        self.assertIn('data-action="copy-alias"', app_js)
        self.assertNotIn("/v1/auth/", app_js)
        self.assertIn("/v1/auto-refresh", app_js)
        self.assertIn("/v1/session/import", app_js)
        self.assertIn("/v1/mail/folders", app_js)
        self.assertIn("/v1/mail/messages", app_js)
        self.assertIn("/v1/aliases/export.csv", app_js)
        self.assertIn("hme-api-key", app_js)
        self.assertIn("toggleTheme", app_js)
        self.assertIn("hme-theme", app_js)
        self.assertIn("setAutoRefreshMini", app_js)
        self.assertIn("sessionIndicatorEl.className = `session-indicator ${stateKind}`", app_js)
        self.assertNotIn("dev-secret", app_js)
        # html mail bodies must be sandboxed
        self.assertIn('sandbox=""', app_js)

    def test_render_index_contains_api_key_modal(self):
        html = render_index()
        self.assertIn('id="apiKeyModal"', html)
        self.assertIn('id="modalApiKeyInput"', html)

    def test_app_css_supports_dark_mode(self):
        from web_app import _read_static

        app_css = _read_static("app.css")
        self.assertIn("prefers-color-scheme: dark", app_css)
        self.assertIn("#apiKeyModal", app_css)
        self.assertIn(".session-indicator.ok", app_css)
        self.assertIn(".alias-toolbar", app_css)
        self.assertIn(".logout-label { display: none; }", app_css)
        self.assertIn(".toast", app_css)
        self.assertIn(".inbox-grid", app_css)
        self.assertIn(".mail-item", app_css)
        self.assertIn(".code-chip", app_css)

    def _auto_refresh_manager(self, tmp):
        class M:
            def __init__(self, d):
                self.state_dir = Path(d)
                self.reauth = False

            def check(self):
                return {
                    "sessionValid": not self.reauth,
                    "needsReauth": self.reauth,
                    "lastError": "HTTP 401" if self.reauth else None,
                }

        return M(tmp)

    def test_auto_refresh_defaults_enabled_every_ten_minutes(self):
        defaults = auto_refresh.defaults()
        self.assertTrue(defaults["enabled"])
        self.assertEqual(defaults["intervalSeconds"], 600)

    def test_auto_refresh_config_roundtrip_and_min_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._auto_refresh_manager(tmp)
            saved = auto_refresh.save_config({"enabled": True, "intervalSeconds": 60}, manager)
            self.assertTrue(saved["enabled"])
            self.assertEqual(saved["intervalSeconds"], 300)  # clamped to minimum
            updated = auto_refresh.update({"intervalSeconds": 900}, manager)
            self.assertEqual(updated["intervalSeconds"], 900)

    def test_run_auto_refresh_once_success_then_self_disable(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._auto_refresh_manager(tmp)
            auto_refresh.update({"enabled": True}, manager)
            ok = auto_refresh.run_once(manager)
            self.assertTrue(ok["autoRefresh"]["enabled"])
            self.assertIsNotNone(ok["autoRefresh"]["lastSuccessAt"])
            manager.reauth = True  # session now needs re-import
            disabled = auto_refresh.run_once(manager)
            self.assertFalse(disabled["autoRefresh"]["enabled"])
            self.assertTrue(disabled["autoRefresh"]["disabledReason"])

    def test_dispatch_auto_refresh_get_and_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._auto_refresh_manager(tmp)
            status, payload = dispatch_private_api(
                "GET", "/v1/auto-refresh", headers={"X-API-Key": "secret"}, body=b"", manager=manager, api_key="secret"
            )
            self.assertEqual(status, HTTPStatus.OK)
            self.assertIn("intervalSeconds", payload["data"])
            status2, payload2 = dispatch_private_api(
                "POST", "/v1/auto-refresh", headers={"X-API-Key": "secret"}, body=b'{"enabled": true}', manager=manager, api_key="secret"
            )
            self.assertEqual(status2, HTTPStatus.OK)
            self.assertTrue(payload2["data"]["enabled"])

    def test_render_index_no_console_api_key_param(self):
        html = render_index()
        self.assertNotIn("__CONSOLE_API_KEY__", html)
        self.assertNotIn("HME_CONSOLE_API_KEY", html)

    def test_old_api_paths_are_not_routed(self):
        for method, path in [
            ("GET", "/api/status"),
            ("GET", "/api/hme/list"),
            ("GET", "/api/hme/export.csv"),
            ("GET", "/admin/import-session"),
            ("POST", "/api/hme/create"),
            ("POST", "/admin/import-session"),
            ("POST", "/auth/start"),
            ("POST", "/auth/check"),
        ]:
            self.assertFalse(
                is_api_path(path),
                f"{path} should not match is_api_path",
            )

    def test_is_api_path_detects_private_api(self):
        self.assertTrue(is_api_path("/v1/aliases"))
        self.assertTrue(is_api_path("/v1/aliases?id=1"))
        self.assertFalse(is_api_path("/api/hme/list"))

    def test_dispatch_private_api_rejects_missing_key(self):
        status, payload = dispatch_private_api(
            "GET",
            "/v1/aliases",
            headers={},
            body=b"",
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.UNAUTHORIZED)
        self.assertEqual(payload["error"]["code"], "UNAUTHORIZED")

    def test_dispatch_private_api_lists_aliases(self):
        status, payload = dispatch_private_api(
            "GET",
            "/v1/aliases",
            headers={"X-API-Key": "secret"},
            body=b"",
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["data"][0]["hme"], "a@icloud.com")

    def test_dispatch_private_api_refreshes_session(self):
        status, payload = dispatch_private_api(
            "POST",
            "/v1/session/refresh",
            headers={"X-API-Key": "secret"},
            body=b"",
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["data"]["sessionValid"])

    def test_dispatch_private_api_creates_alias(self):
        status, payload = dispatch_private_api(
            "POST",
            "/v1/aliases",
            headers={"X-API-Key": "secret"},
            body=b'{"label":"GPT","note":"75"}',
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["data"]["hme"], "new@icloud.com")

    def test_dispatch_private_api_enables_alias(self):
        status, payload = dispatch_private_api(
            "POST",
            "/v1/aliases/id1/enable",
            headers={"X-API-Key": "secret"},
            body=b"",
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["data"], {"anonymousId": "id1", "isActive": True})

    def test_dispatch_private_api_disables_alias(self):
        status, payload = dispatch_private_api(
            "POST",
            "/v1/aliases/id1/disable",
            headers={"X-API-Key": "secret"},
            body=b"",
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["data"], {"anonymousId": "id1", "isActive": False})

    def test_dispatch_private_api_deletes_alias(self):
        status, payload = dispatch_private_api(
            "POST",
            "/v1/aliases/id1/delete",
            headers={"X-API-Key": "secret"},
            body=b"",
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["data"], {"anonymousId": "id1", "deleted": True})

    def test_dispatch_private_api_lists_mail_folders(self):
        status, payload = dispatch_private_api(
            "GET",
            "/v1/mail/folders",
            headers={"X-API-Key": "secret"},
            body=b"",
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["data"][0]["name"], "Inbox")

    def test_dispatch_private_api_lists_mail_messages_with_default_inbox(self):
        status, payload = dispatch_private_api(
            "GET",
            "/v1/mail/messages",
            headers={"X-API-Key": "secret"},
            body=b"",
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["data"]["folder"], "folder-1")
        self.assertEqual(payload["data"]["messages"][0]["guid"], "msg 1")

    def test_dispatch_private_api_lists_mail_messages_with_query(self):
        status, payload = dispatch_private_api(
            "GET",
            "/v1/mail/messages?folder=custom-guid&limit=5&offset=10",
            headers={"X-API-Key": "secret"},
            body=b"",
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["data"]["folder"], "custom-guid")
        self.assertEqual(payload["data"]["offset"], 10)
        self.assertEqual(payload["data"]["messages"][0]["limit"], 5)

    def test_dispatch_private_api_rejects_bad_mail_limit(self):
        status, payload = dispatch_private_api(
            "GET",
            "/v1/mail/messages?limit=abc",
            headers={"X-API-Key": "secret"},
            body=b"",
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload["error"]["code"], "BAD_REQUEST")

    def test_dispatch_private_api_gets_mail_message_with_encoded_guid(self):
        status, payload = dispatch_private_api(
            "GET",
            "/v1/mail/messages/msg%201",
            headers={"X-API-Key": "secret"},
            body=b"",
            manager=FakeManager(),
            api_key="secret",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["data"]["guid"], "msg 1")

    def test_create_server_uses_threading_http_server(self):
        server = create_server("127.0.0.1", 0)
        try:
            self.assertIsInstance(server, HTTPServer)
            self.assertIsInstance(server, ThreadingHTTPServer)
            self.assertTrue(server.daemon_threads)
        finally:
            server.server_close()

    def test_dispatch_private_api_imports_session(self):
        import json
        body = json.dumps({
            "curl_text": (
                "curl 'https://p119-maildomainws.icloud.com/v2/hme/list?"
                "clientBuildNumber=2614Build17&"
                "clientMasteringNumber=2614Build17&"
                "clientId=client-1&"
                "dsid=608658063' "
                "-b 'X-APPLE-WEBAUTH-USER=user; "
                "X-APPLE-WEBAUTH-TOKEN=token; "
                "X-APPLE-DS-WEB-SESSION-TOKEN=session'"
            )
        }).encode("utf-8")
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            manager = FakeManager()
            manager.config_path = Path(tmp) / "hme-config.json"
            manager.metadata_path = Path(tmp) / "state" / "hme-session.json"
            manager.state_dir = Path(tmp) / "state"
            status, payload = dispatch_private_api(
                "POST", "/v1/session/import",
                headers={"X-API-Key": "secret"},
                body=body, manager=manager, api_key="secret",
            )
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(payload["data"]["imported"])

    def test_dispatch_private_api_does_not_route_browser_auth(self):
        for path in ("/v1/auth/start", "/v1/auth/check"):
            status, payload = dispatch_private_api(
                "POST", path,
                headers={"X-API-Key": "secret"},
                body=b"", manager=FakeManager(), api_key="secret",
            )
            self.assertEqual(status, HTTPStatus.NOT_FOUND)
            self.assertEqual(payload["error"]["code"], "NOT_FOUND")

    def test_dispatch_private_api_exports_csv(self):
        status, payload = dispatch_private_api(
            "GET", "/v1/aliases/export.csv",
            headers={"X-API-Key": "secret"},
            body=b"", manager=FakeManager(), api_key="secret",
        )
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("a@icloud.com", payload["data"])

    def test_dispatch_session_import_requires_api_key(self):
        status, payload = dispatch_private_api(
            "POST", "/v1/session/import",
            headers={}, body=b'{"curl_text":"x"}',
            manager=FakeManager(), api_key="secret",
        )
        self.assertEqual(status, HTTPStatus.UNAUTHORIZED)


if __name__ == "__main__":
    unittest.main()
