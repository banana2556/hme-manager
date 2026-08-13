import json
import unittest

from hme import HmeConfig, HmeError
from icloud_mail import MailClient, mail_host_for, normalize_message_summary


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        if not self.responses:
            raise AssertionError("No fake response queued")
        return self.responses.pop(0)


def make_config(**overrides):
    values = {
        "host": "p119-maildomainws.icloud.com",
        "dsid": "608658063",
        "client_id": "client-1",
        "client_build_number": "2626Build17",
        "client_mastering_number": "2626Build17",
        "cookie": "X-APPLE-WEBAUTH-TOKEN=redacted",
    }
    values.update(overrides)
    return HmeConfig(**values)


class MailHostTests(unittest.TestCase):
    def test_derives_global_mail_host_from_hme_host(self):
        self.assertEqual(mail_host_for("p119-maildomainws.icloud.com"), "p119-mailws.icloud.com")

    def test_derives_china_mail_host_from_hme_host(self):
        self.assertEqual(mail_host_for("p30-maildomainws.icloud.com.cn"), "p30-mailws.icloud.com.cn")

    def test_rejects_host_without_maildomainws(self):
        with self.assertRaisesRegex(HmeError, "Cannot derive"):
            mail_host_for("www.icloud.com")


class MailHostResolveTests(unittest.TestCase):
    def test_resolves_mail_host_from_setup_webservices(self):
        transport = FakeTransport(
            [
                (200, {"webservices": {"mail": {"url": "https://p88-mailws.icloud.com:443", "status": "active"}}}),
                (200, {"result": {"folders": [{"guid": "f-1", "displayName": "Inbox", "role": "INBOX"}]}}),
            ]
        )
        client = MailClient(make_config(), transport=transport)

        client.list_folders()

        validate_call, folder_call = transport.calls
        self.assertIn("https://setup.icloud.com/setup/ws/1/validate?", validate_call["url"])
        # mail partition (p88) differs from HME partition (p119); we honor setup
        self.assertIn("https://p88-mailws.icloud.com/wm/folder?", folder_call["url"])

    def test_resolves_china_setup_and_mail_host(self):
        transport = FakeTransport(
            [
                (200, {"webservices": {"mail": {"url": "https://p31-mailws.icloud.com.cn"}}}),
                (200, {"result": {"folders": [{"guid": "f-1", "displayName": "收件箱", "role": "INBOX"}]}}),
            ]
        )
        config = make_config(
            host="p30-maildomainws.icloud.com.cn",
            origin="https://www.icloud.com.cn",
            referer="https://www.icloud.com.cn/",
        )
        client = MailClient(config, transport=transport)

        client.list_folders()

        validate_call, folder_call = transport.calls
        self.assertIn("https://setup.icloud.com.cn/setup/ws/1/validate?", validate_call["url"])
        self.assertIn("https://p31-mailws.icloud.com.cn/wm/folder?", folder_call["url"])
        self.assertEqual(folder_call["headers"]["Referer"], "https://www.icloud.com.cn/mail/")

    def test_falls_back_to_derived_host_when_setup_unavailable(self):
        transport = FakeTransport(
            [
                (500, {"error": "unavailable"}),
                (200, {"result": {"folders": [{"guid": "f-1", "displayName": "Inbox", "role": "INBOX"}]}}),
            ]
        )
        client = MailClient(make_config(), transport=transport)

        client.list_folders()

        self.assertIn("https://p119-mailws.icloud.com/wm/folder?", transport.calls[1]["url"])


class MailClientTests(unittest.TestCase):
    def test_list_folders_sends_jsonrpc_and_normalizes(self):
        transport = FakeTransport(
            [
                (
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": "1/1",
                        "result": {
                            "folders": [
                                {"guid": "f-1", "displayName": "Inbox", "role": "INBOX", "unreadCount": 3, "totalCount": 12},
                                {"guid": "f-2", "name": "Archive"},
                                {"noGuid": True},
                            ]
                        },
                    },
                )
            ]
        )
        client = MailClient(make_config(), transport=transport, mail_host="p119-mailws.icloud.com")

        folders = client.list_folders()

        self.assertEqual(len(folders), 2)
        self.assertEqual(folders[0], {"guid": "f-1", "name": "Inbox", "role": "INBOX", "unreadCount": 3, "totalCount": 12})
        call = transport.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertIn("https://p119-mailws.icloud.com/wm/folder?", call["url"])
        self.assertIn("clientBuildNumber=2626Build17", call["url"])
        self.assertIn("dsid=608658063", call["url"])
        body = json.loads(call["body"])
        self.assertEqual(body["jsonrpc"], "2.0")
        self.assertEqual(body["method"], "list")
        self.assertEqual(body["params"], {})
        self.assertEqual(call["headers"]["Referer"], "https://www.icloud.com/mail/")
        self.assertEqual(call["headers"]["Cookie"], "X-APPLE-WEBAUTH-TOKEN=redacted")

    def test_china_config_uses_cn_mail_referer(self):
        transport = FakeTransport(
            [(200, {"result": {"folders": [{"guid": "f-1", "displayName": "收件箱", "role": "INBOX"}]}})]
        )
        config = make_config(
            host="p30-maildomainws.icloud.com.cn",
            origin="https://www.icloud.com.cn",
            referer="https://www.icloud.com.cn/",
        )
        client = MailClient(config, transport=transport, mail_host="p31-mailws.icloud.com.cn")

        folders = client.list_folders()

        self.assertEqual(folders[0]["name"], "收件箱")
        call = transport.calls[0]
        self.assertIn("https://p31-mailws.icloud.com.cn/wm/folder?", call["url"])
        self.assertEqual(call["headers"]["Origin"], "https://www.icloud.com.cn")
        self.assertEqual(call["headers"]["Referer"], "https://www.icloud.com.cn/mail/")

    def test_inbox_folder_prefers_inbox_role(self):
        transport = FakeTransport(
            [
                (
                    200,
                    {
                        "result": {
                            "folders": [
                                {"guid": "f-trash", "displayName": "Trash", "role": "TRASH"},
                                {"guid": "f-inbox", "displayName": "Inbox", "role": "INBOX"},
                            ]
                        }
                    },
                )
            ]
        )
        client = MailClient(make_config(), transport=transport, mail_host="p119-mailws.icloud.com")

        self.assertEqual(client.inbox_folder()["guid"], "f-inbox")

    def test_list_messages_sends_paging_params_and_normalizes(self):
        transport = FakeTransport(
            [
                (
                    200,
                    {
                        "result": {
                            "total": 42,
                            "messages": [
                                {
                                    "guid": "m-1",
                                    "from": {"name": "OpenAI", "emailAddress": "noreply@openai.com"},
                                    "to": [{"emailAddress": "alias@icloud.com"}],
                                    "subject": "Your code",
                                    "dateReceived": 1778246060430,
                                    "snippet": "Your code is 123456",
                                    "read": False,
                                }
                            ],
                        }
                    },
                )
            ]
        )
        client = MailClient(make_config(), transport=transport, mail_host="p119-mailws.icloud.com")

        result = client.list_messages("f-inbox", limit=5, offset=10)

        self.assertEqual(result["total"], 42)
        self.assertEqual(result["folder"], "f-inbox")
        message = result["messages"][0]
        self.assertEqual(message["guid"], "m-1")
        self.assertEqual(message["from"], "OpenAI <noreply@openai.com>")
        self.assertEqual(message["to"], "alias@icloud.com")
        self.assertFalse(message["isRead"])
        self.assertTrue(message["date"].startswith("2026-"))
        body = json.loads(transport.calls[0]["body"])
        self.assertEqual(body["method"], "list")
        self.assertEqual(body["params"]["guid"], "f-inbox")
        self.assertEqual(body["params"]["count"], 5)
        self.assertEqual(body["params"]["selected"], 10)
        self.assertEqual(body["params"]["sortorder"], "descending")

    def test_list_messages_filters_by_recipient_across_pages(self):
        page_one = [
            {"guid": f"g{i}", "subject": f"s{i}", "to": [{"emailAddress": "other@icloud.com"}], "dateReceived": 1}
            for i in range(100)
        ]
        page_one[5]["to"] = [{"name": "Hide My Email", "emailAddress": "Target.Alias@icloud.com"}]
        page_two = [
            {"guid": f"g{100 + i}", "subject": "x", "to": [{"emailAddress": "target.alias@icloud.com"}], "dateReceived": 1}
            for i in range(30)
        ]
        transport = FakeTransport(
            [
                (200, {"result": {"total": 130, "messages": page_one}}),
                (200, {"result": {"total": 130, "messages": page_two}}),
            ]
        )
        client = MailClient(make_config(), transport=transport, mail_host="p119-mailws.icloud.com")

        result = client.list_messages("f-inbox", limit=5, offset=0, to="target.alias@icloud.com")

        self.assertEqual([m["guid"] for m in result["messages"]], ["g5", "g100", "g101", "g102", "g103"])
        self.assertEqual(result["filteredTo"], "target.alias@icloud.com")
        self.assertEqual(result["matchedCount"], 31)
        self.assertEqual(result["scannedCount"], 130)
        self.assertTrue(result["scanComplete"])
        self.assertEqual(result["total"], 130)
        first_call, second_call = (json.loads(call["body"]) for call in transport.calls)
        self.assertEqual(first_call["params"]["selected"], 0)
        self.assertEqual(second_call["params"]["selected"], 100)

    def test_list_messages_filter_stops_when_page_has_enough_matches(self):
        page_one = [
            {"guid": f"g{i}", "subject": "hit", "to": [{"emailAddress": "alias@icloud.com"}], "dateReceived": 1}
            for i in range(100)
        ]
        transport = FakeTransport([(200, {"result": {"total": 400, "messages": page_one}})])
        client = MailClient(make_config(), transport=transport, mail_host="p119-mailws.icloud.com")

        result = client.list_messages("f-inbox", limit=3, offset=0, to="alias@icloud.com")

        self.assertEqual(len(transport.calls), 1)
        self.assertEqual([m["guid"] for m in result["messages"]], ["g0", "g1", "g2"])
        self.assertFalse(result["scanComplete"])
        self.assertEqual(result["scannedCount"], 100)

    def test_get_message_requests_parts_and_returns_bodies(self):
        transport = FakeTransport(
            [
                (
                    200,
                    {
                        "result": {
                            "message": {
                                "guid": "m-1",
                                "subject": "Your code",
                                "from": "noreply@openai.com",
                                "textBody": "Your code is 123456",
                                "htmlBody": "<p>Your code is <b>123456</b></p>",
                                "attachments": [{"filename": "a.pdf", "mimeType": "application/pdf", "size": 123}],
                            }
                        }
                    },
                )
            ]
        )
        client = MailClient(make_config(), transport=transport, mail_host="p119-mailws.icloud.com")

        detail = client.get_message("m-1")

        self.assertEqual(detail["guid"], "m-1")
        self.assertEqual(detail["textBody"], "Your code is 123456")
        self.assertIn("<b>123456</b>", detail["htmlBody"])
        self.assertEqual(detail["attachments"][0]["filename"], "a.pdf")
        body = json.loads(transport.calls[0]["body"])
        self.assertEqual(body["method"], "get")
        self.assertEqual(body["params"]["guid"], "m-1")
        self.assertIn("HTML", body["params"]["parts"])

    def test_rpc_error_envelope_raises_hme_error(self):
        transport = FakeTransport([(200, {"jsonrpc": "2.0", "error": {"code": -32000, "message": "no session"}})])
        client = MailClient(make_config(), transport=transport, mail_host="p119-mailws.icloud.com")

        with self.assertRaisesRegex(HmeError, "no session"):
            client.list_folders()

    def test_http_error_raises_hme_error_with_status(self):
        transport = FakeTransport([(401, {"error": "unauthorized"})])
        client = MailClient(make_config(), transport=transport, mail_host="p119-mailws.icloud.com")

        with self.assertRaisesRegex(HmeError, "HTTP 401"):
            client.list_folders()

    def test_normalize_message_summary_tolerates_alternate_keys(self):
        message = normalize_message_summary(
            {
                "messageId": "alt-1",
                "sender": "someone@example.com",
                "title": "hello",
                "date": "2026-08-13T10:00:00Z",
                "flags": {"seen": True},
            }
        )

        self.assertEqual(message["guid"], "alt-1")
        self.assertEqual(message["from"], "someone@example.com")
        self.assertEqual(message["subject"], "hello")
        self.assertEqual(message["date"], "2026-08-13T10:00:00Z")
        self.assertTrue(message["isRead"])


if __name__ == "__main__":
    unittest.main()
