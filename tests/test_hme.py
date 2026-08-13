import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from hme import (
    HmeClient,
    HmeConfig,
    HmeError,
    aliases_to_csv,
    default_lang_code_for_host,
    load_config,
    region_for_host,
    web_origin_for_host,
)


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request):
        self.calls.append(request)
        if not self.responses:
            raise AssertionError("No fake response queued")
        return self.responses.pop(0)


class HmeClientTests(unittest.TestCase):
    def config(self):
        return HmeConfig(
            host="p119-maildomainws.icloud.com",
            dsid="608658063",
            client_id="7365b410-0e63-4047-9627-ae3c99278def",
            client_build_number="2614Build17",
            client_mastering_number="2614Build17",
            cookie="X-APPLE-WEBAUTH-TOKEN=redacted",
            lang_code="zh-tw",
        )

    def test_load_config_reads_json_and_requires_session_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "host": "p119-maildomainws.icloud.com",
                        "dsid": "608658063",
                        "clientId": "client-1",
                        "clientBuildNumber": "2614Build17",
                        "clientMasteringNumber": "2614Build17",
                        "cookie": "SESSION=ok",
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, env={})

        self.assertEqual(config.host, "p119-maildomainws.icloud.com")
        self.assertEqual(config.client_id, "client-1")
        self.assertEqual(config.cookie, "SESSION=ok")

        with self.assertRaisesRegex(HmeError, "cookie"):
            load_config(None, env={"ICLOUD_HME_HOST": "p119-maildomainws.icloud.com"})

    def test_list_aliases_calls_v2_list_and_returns_aliases(self):
        transport = FakeTransport(
            [
                (
                    200,
                    {
                        "success": True,
                        "result": {
                            "selectedForwardTo": "target@example.com",
                            "hmeEmails": [
                                {
                                    "hme": "alias@icloud.com",
                                    "label": "GPT",
                                    "note": "74",
                                    "forwardToEmail": "target@example.com",
                                    "origin": "ON_DEMAND",
                                    "isActive": True,
                                    "createTimestamp": 1778246060430,
                                    "anonymousId": "zkbr7mgpwc6315",
                                }
                            ],
                        },
                    },
                )
            ]
        )
        client = HmeClient(self.config(), transport=transport)

        aliases = client.list_aliases()

        self.assertEqual(aliases[0]["hme"], "alias@icloud.com")
        call = transport.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertIn("/v2/hme/list?", call["url"])
        self.assertIn("clientBuildNumber=2614Build17", call["url"])
        self.assertEqual(call["headers"]["Cookie"], "X-APPLE-WEBAUTH-TOKEN=redacted")

    def test_create_generates_then_reserves_candidate(self):
        transport = FakeTransport(
            [
                (200, {"success": True, "result": {"hme": "new.alias@icloud.com"}}),
                (
                    200,
                    {
                        "success": True,
                        "result": {
                            "hme": {
                                "hme": "new.alias@icloud.com",
                                "label": "GPT",
                                "note": "75",
                                "origin": "ON_DEMAND",
                                "isActive": True,
                            }
                        },
                    },
                ),
            ]
        )
        client = HmeClient(self.config(), transport=transport)

        created = client.create_alias(label="GPT", note="75")

        self.assertEqual(created["hme"], "new.alias@icloud.com")
        generate_call, reserve_call = transport.calls
        self.assertIn("/v1/hme/generate?", generate_call["url"])
        self.assertEqual(json.loads(generate_call["body"]), {"langCode": "zh-tw"})
        self.assertIn("/v1/hme/reserve?", reserve_call["url"])
        self.assertEqual(
            json.loads(reserve_call["body"]),
            {"hme": "new.alias@icloud.com", "label": "GPT", "note": "75"},
        )

    def test_deactivate_alias_calls_v1_deactivate(self):
        transport = FakeTransport([(200, {"success": True, "result": {"anonymousId": "id1"}})])
        client = HmeClient(self.config(), transport=transport)

        result = client.deactivate_alias("id1")

        self.assertEqual(result["anonymousId"], "id1")
        call = transport.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertIn("/v1/hme/deactivate?", call["url"])
        self.assertEqual(json.loads(call["body"]), {"anonymousId": "id1"})

    def test_activate_alias_calls_v1_activate(self):
        transport = FakeTransport([(200, {"success": True, "result": {"anonymousId": "id1", "isActive": True}})])
        client = HmeClient(self.config(), transport=transport)

        result = client.activate_alias("id1")

        self.assertEqual(result["anonymousId"], "id1")
        call = transport.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertIn("/v1/hme/activate?", call["url"])
        self.assertEqual(json.loads(call["body"]), {"anonymousId": "id1"})

    def test_delete_alias_calls_v1_delete(self):
        transport = FakeTransport([(200, {"success": True, "result": {"anonymousId": "id1"}})])
        client = HmeClient(self.config(), transport=transport)

        result = client.delete_alias("id1")

        self.assertEqual(result["anonymousId"], "id1")
        call = transport.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertIn("/v1/hme/delete?", call["url"])
        self.assertEqual(json.loads(call["body"]), {"anonymousId": "id1"})

    def test_region_helpers_detect_china_partition(self):
        self.assertEqual(region_for_host("p119-maildomainws.icloud.com"), "global")
        self.assertEqual(region_for_host("p30-maildomainws.icloud.com.cn"), "china")
        self.assertEqual(web_origin_for_host("p30-maildomainws.icloud.com.cn"), "https://www.icloud.com.cn")
        self.assertEqual(web_origin_for_host("p119-maildomainws.icloud.com"), "https://www.icloud.com")
        self.assertEqual(default_lang_code_for_host("p30-maildomainws.icloud.com.cn"), "zh-cn")

    def test_load_config_defaults_origin_by_region(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "host": "p30-maildomainws.icloud.com.cn",
                        "dsid": "12345678",
                        "clientId": "client-cn",
                        "clientBuildNumber": "2626Build17",
                        "clientMasteringNumber": "2626Build17",
                        "cookie": "SESSION=ok",
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, env={})

        self.assertEqual(config.region, "china")
        self.assertEqual(config.origin, "https://www.icloud.com.cn")
        self.assertEqual(config.referer, "https://www.icloud.com.cn/")
        self.assertEqual(config.lang_code, "zh-cn")

    def test_china_client_sends_cn_origin_headers(self):
        transport = FakeTransport([(200, {"success": True, "result": {"hmeEmails": []}})])
        config = HmeConfig(
            host="p30-maildomainws.icloud.com.cn",
            dsid="12345678",
            client_id="client-cn",
            client_build_number="2626Build17",
            client_mastering_number="2626Build17",
            cookie="X-APPLE-WEBAUTH-TOKEN=redacted",
            lang_code="zh-cn",
            origin="https://www.icloud.com.cn",
            referer="https://www.icloud.com.cn/",
        )
        client = HmeClient(config, transport=transport)

        client.list_aliases()

        call = transport.calls[0]
        self.assertIn("https://p30-maildomainws.icloud.com.cn/v2/hme/list?", call["url"])
        self.assertEqual(call["headers"]["Origin"], "https://www.icloud.com.cn")
        self.assertEqual(call["headers"]["Referer"], "https://www.icloud.com.cn/")

    def test_aliases_to_csv_writes_stable_columns(self):
        csv_text = aliases_to_csv(
            [
                {
                    "hme": "alias@icloud.com",
                    "label": "GPT",
                    "note": "61\n",
                    "forwardToEmail": "target@example.com",
                    "origin": "ON_DEMAND",
                    "isActive": True,
                    "createTimestamp": 1778246060430,
                    "anonymousId": "zkbr7mgpwc6315",
                }
            ]
        )

        row = next(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(row["hme"], "alias@icloud.com")
        self.assertEqual(row["note"], "61\n")
        self.assertEqual(row["isActive"], "true")


if __name__ == "__main__":
    unittest.main()
