import unittest

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


class FakeClient:
    def __init__(self):
        self.created = []
        self.deactivated = []
        self.deleted = []

    def list_aliases(self):
        return [{"hme": "a@icloud.com", "anonymousId": "id1"}]

    def create_alias(self, label, note=""):
        alias = {"hme": "new@icloud.com", "label": label, "note": note}
        self.created.append(alias)
        return alias

    def deactivate_alias(self, anonymous_id):
        self.deactivated.append(anonymous_id)
        return {"anonymousId": anonymous_id, "isActive": False}

    def activate_alias(self, anonymous_id):
        return {"anonymousId": anonymous_id, "isActive": True}

    def delete_alias(self, anonymous_id):
        self.deleted.append(anonymous_id)
        return {"anonymousId": anonymous_id, "deleted": True}

    def check(self):
        return {"aliasCount": 1, "selectedForwardTo": "me@example.com"}


class FakeManager:
    def __init__(self):
        self.metadata = None
        self.config_path = "hme-config.json"
        self.metadata_path = "state/hme-session.json"
        self.state_dir = "state"
        self.reloaded = False

    def status(self):
        return {"metadataDetected": True}

    def check(self):
        return {"sessionValid": True}

    def reload(self):
        self.reloaded = True


class FakeMailClient:
    def __init__(self):
        self.list_calls = []
        self.inbox_calls = 0

    def list_folders(self):
        return [{"guid": "f-inbox", "name": "Inbox", "role": "INBOX"}]

    def inbox_folder(self):
        self.inbox_calls += 1
        return self.list_folders()[0]

    def list_messages(self, folder_guid, limit=20, offset=0):
        self.list_calls.append({"folder": folder_guid, "limit": limit, "offset": offset})
        return {"folder": folder_guid, "offset": offset, "total": 0, "messages": []}

    def get_message(self, guid):
        return {"guid": guid, "subject": "hello"}


class ApiServiceTests(unittest.TestCase):
    def test_require_api_key_accepts_matching_header(self):
        self.assertIsNone(require_api_key({"X-API-Key": "secret"}, "secret"))

    def test_require_api_key_accepts_case_insensitive_header_name(self):
        self.assertIsNone(require_api_key({"x-api-key": "secret"}, "secret"))

    def test_require_api_key_rejects_missing_header(self):
        with self.assertRaisesRegex(PermissionError, "UNAUTHORIZED"):
            require_api_key({}, "secret")

    def test_require_api_key_rejects_when_expected_key_is_not_configured(self):
        with self.assertRaisesRegex(PermissionError, "UNAUTHORIZED"):
            require_api_key({"X-API-Key": "secret"}, "")

    def test_ok_response_wraps_payload(self):
        self.assertEqual(
            ok_response({"a": 1}),
            {
                "ok": True,
                "data": {"a": 1},
                "error": None,
                "meta": {"service": "hme-manager", "version": "1", "requestId": None},
            },
        )

    def test_error_response_has_code_and_message(self):
        self.assertEqual(
            error_response("SESSION_EXPIRED", "expired"),
            {
                "ok": False,
                "data": None,
                "error": {"code": "SESSION_EXPIRED", "message": "expired"},
                "meta": {"service": "hme-manager", "version": "1", "requestId": None},
            },
        )

    def test_response_helpers_accept_request_id(self):
        self.assertEqual(ok_response({}, request_id="req-1")["meta"]["requestId"], "req-1")
        self.assertEqual(error_response("BAD_REQUEST", "bad", request_id="req-2")["meta"]["requestId"], "req-2")

    def test_list_aliases_returns_data(self):
        response = list_aliases(FakeClient())

        self.assertEqual(response["data"][0]["hme"], "a@icloud.com")

    def test_create_alias_requires_label(self):
        with self.assertRaisesRegex(ValueError, "label"):
            create_alias(FakeClient(), {"label": ""})

    def test_create_alias_passes_label_and_note_to_client(self):
        response = create_alias(FakeClient(), {"label": "GPT", "note": "75"})

        self.assertEqual(response["data"]["hme"], "new@icloud.com")
        self.assertEqual(response["data"]["label"], "GPT")
        self.assertEqual(response["data"]["note"], "75")

    def test_session_status_uses_client_check_when_available(self):
        response = session_status(FakeClient())

        self.assertEqual(response["data"]["aliasCount"], 1)

    def test_refresh_session_uses_source_check(self):
        response = refresh_session(FakeClient())

        self.assertEqual(response["data"]["selectedForwardTo"], "me@example.com")

    def test_disable_alias_deactivates_alias(self):
        response = disable_alias(FakeClient(), anonymous_id="id1")

        self.assertEqual(response["data"], {"anonymousId": "id1", "isActive": False})

    def test_delete_alias_deletes_alias(self):
        response = delete_alias(FakeClient(), anonymous_id="id1")

        self.assertEqual(response["data"], {"anonymousId": "id1", "deleted": True})

    def test_enable_alias_activates_alias(self):
        response = enable_alias(FakeClient(), anonymous_id="id1")

        self.assertEqual(response["data"], {"anonymousId": "id1", "isActive": True})

    def test_import_session_requires_curl_text(self):
        with self.assertRaisesRegex(ValueError, "curl_text"):
            import_session(FakeManager(), {"curl_text": ""})

    def test_export_aliases_csv_returns_csv_string(self):
        result = export_aliases_csv(FakeClient())
        self.assertIn("hme", result)
        self.assertIn("a@icloud.com", result)

    def test_list_mail_folders_wraps_client_folders(self):
        response = list_mail_folders(FakeMailClient())

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"][0]["guid"], "f-inbox")

    def test_list_mail_messages_defaults_to_inbox(self):
        client = FakeMailClient()

        response = list_mail_messages(client, {})

        self.assertEqual(response["data"]["folder"], "f-inbox")
        self.assertEqual(client.list_calls[0], {"folder": "f-inbox", "limit": 20, "offset": 0})

    def test_list_mail_messages_clamps_limit_and_offset(self):
        client = FakeMailClient()

        list_mail_messages(client, {"folder": "f-x", "limit": "999", "offset": "-3"})

        self.assertEqual(client.list_calls[0], {"folder": "f-x", "limit": 100, "offset": 0})

    def test_list_mail_messages_rejects_non_integer_limit(self):
        client = FakeMailClient()

        with self.assertRaisesRegex(ValueError, "limit"):
            list_mail_messages(client, {"limit": "abc"})

        # validation must fail before the inbox lookup, which hits the network
        self.assertEqual(client.inbox_calls, 0)

    def test_get_mail_message_requires_guid(self):
        with self.assertRaisesRegex(ValueError, "guid"):
            get_mail_message(FakeMailClient(), "  ")

    def test_get_mail_message_returns_detail(self):
        response = get_mail_message(FakeMailClient(), "m-1")

        self.assertEqual(response["data"]["subject"], "hello")


if __name__ == "__main__":
    unittest.main()
