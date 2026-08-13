import json
import tempfile
import unittest
from pathlib import Path

from session_import import parse_hme_curl, parse_import_text, save_imported_session


class SessionImportTests(unittest.TestCase):
    def test_parse_hme_list_curl_extracts_config(self):
        curl_text = r"""curl 'https://p119-maildomainws.icloud.com/v2/hme/list?clientBuildNumber=2614Build17&clientMasteringNumber=2614Build17&clientId=7365b410-0e63-4047-9627-ae3c99278def&dsid=608658063' \
  -H 'accept: */*' \
  -b 'x-apple-group=false; X-APPLE-WEBAUTH-USER="v=1:s=0:d=608658063"; X-APPLE-WEBAUTH-TOKEN="redacted"; X-APPLE-DS-WEB-SESSION-TOKEN="secret"'"""

        config = parse_hme_curl(curl_text)

        self.assertEqual(config["host"], "p119-maildomainws.icloud.com")
        self.assertEqual(config["dsid"], "608658063")
        self.assertEqual(config["clientId"], "7365b410-0e63-4047-9627-ae3c99278def")
        self.assertEqual(config["clientBuildNumber"], "2614Build17")
        self.assertEqual(config["clientMasteringNumber"], "2614Build17")
        self.assertIn("X-APPLE-DS-WEB-SESSION-TOKEN", config["cookie"])

    def test_parse_complete_curl_extracts_only_needed_runtime_fields(self):
        curl_text = r"""curl 'https://p119-maildomainws.icloud.com/v2/hme/list?clientBuildNumber=2614Build21&clientMasteringNumber=2614Build21&clientId=af8cc870-51b6-4a3c-ac22-e34bd2ba621b&dsid=608658063' \
  -H 'Accept: */*' \
  -H 'Connection: keep-alive' \
  -H 'Origin: https://www.icloud.com' \
  -H 'Referer: https://www.icloud.com/' \
  -H 'User-Agent: Mozilla/5.0 Test Browser' \
  -H 'sec-ch-ua: "Chromium";v="148"' \
  -b 'x-apple-group=false; X-APPLE-WEBAUTH-USER="v=1:s=0:d=608658063"; X-APPLE-WEBAUTH-TOKEN="token"; X-APPLE-DS-WEB-SESSION-TOKEN="session"; X-APPLE-WEB-ID=webid'"""

        config = parse_hme_curl(curl_text)

        self.assertEqual(
            set(config),
            {
                "host",
                "dsid",
                "clientId",
                "clientBuildNumber",
                "clientMasteringNumber",
                "cookie",
                "langCode",
                "origin",
                "referer",
                "userAgent",
            },
        )
        self.assertEqual(config["host"], "p119-maildomainws.icloud.com")
        self.assertEqual(config["clientBuildNumber"], "2614Build21")
        self.assertEqual(config["userAgent"], "Mozilla/5.0 Test Browser")
        self.assertEqual(config["origin"], "https://www.icloud.com")
        self.assertEqual(config["referer"], "https://www.icloud.com/")
        self.assertNotIn("sec-ch-ua", json.dumps(config))

    def test_parse_hme_curl_accepts_url_flag_format(self):
        # Newer Chrome builds copy `curl --url '...'` instead of `curl '...'`,
        # with Origin/Referer URLs appearing later in the text.
        curl_text = r"""curl --url 'https://p119-maildomainws.icloud.com/v2/hme/list?clientBuildNumber=2628Build19&clientMasteringNumber=2628Build19&clientId=0cb3e48f-3a83-4564-923b-3b71528d5989&dsid=608658063' \
  -H 'Accept: */*' \
  -H 'Content-Type: text/plain' \
  -b 'x-apple-group=false; X-APPLE-WEBAUTH-PCS-Mail="fake-mail-token"; X-APPLE-WEBAUTH-LOGIN="fake"; X-APPLE-WEBAUTH-USER="v=1:s=1:d=608658063"; X-APPLE-DS-WEB-SESSION-TOKEN="fake-session"; X-APPLE-WEBAUTH-VALIDATE="fake"; X-APPLE-WEBAUTH-TOKEN="fake-token"' \
  -H 'Origin: https://www.icloud.com' \
  -H 'Referer: https://www.icloud.com/' \
  -H 'User-Agent: Mozilla/5.0 Test Browser'"""

        config = parse_hme_curl(curl_text)

        self.assertEqual(config["host"], "p119-maildomainws.icloud.com")
        self.assertEqual(config["dsid"], "608658063")
        self.assertEqual(config["clientBuildNumber"], "2628Build19")
        self.assertIn("X-APPLE-WEBAUTH-PCS-Mail", config["cookie"])
        self.assertEqual(config["origin"], "https://www.icloud.com")

    def test_parse_complete_curl_requires_core_icloud_session_cookies(self):
        curl_text = r"""curl 'https://p119-maildomainws.icloud.com/v2/hme/list?clientBuildNumber=2614Build21&clientMasteringNumber=2614Build21&clientId=client-1&dsid=608658063' \
  -b 'X-APPLE-WEBAUTH-VALIDATE="validate-only"'"""

        with self.assertRaisesRegex(ValueError, "X-APPLE-DS-WEB-SESSION-TOKEN"):
            parse_hme_curl(curl_text)

    def test_parse_import_text_finds_hme_request_inside_har(self):
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "url": "https://www.icloud.com/",
                            "headers": [],
                            "cookies": [],
                        }
                    },
                    {
                        "request": {
                            "url": (
                                "https://p119-maildomainws.icloud.com/v2/hme/list?"
                                "clientBuildNumber=2614Build17&"
                                "clientMasteringNumber=2614Build17&"
                                "clientId=client-1&"
                                "dsid=608658063"
                            ),
                            "headers": [
                                {
                                    "name": "Cookie",
                                    "value": (
                                        'X-APPLE-WEBAUTH-USER="user"; '
                                        'X-APPLE-WEBAUTH-TOKEN="token"; '
                                        'X-APPLE-DS-WEB-SESSION-TOKEN="session"'
                                    ),
                                }
                            ],
                            "cookies": [],
                        }
                    },
                ]
            }
        }

        config = parse_import_text(json.dumps(har))

        self.assertEqual(config["host"], "p119-maildomainws.icloud.com")
        self.assertEqual(config["clientId"], "client-1")
        self.assertIn("X-APPLE-DS-WEB-SESSION-TOKEN", config["cookie"])

    def test_parse_import_text_builds_cookie_from_har_cookie_array(self):
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "url": (
                                "https://p119-maildomainws.icloud.com/v2/hme/list?"
                                "clientBuildNumber=2614Build17&"
                                "clientMasteringNumber=2614Build17&"
                                "clientId=client-1&"
                                "dsid=608658063"
                            ),
                            "headers": [],
                            "cookies": [
                                {"name": "X-APPLE-WEBAUTH-USER", "value": "user"},
                                {"name": "X-APPLE-WEBAUTH-TOKEN", "value": "token"},
                                {"name": "X-APPLE-DS-WEB-SESSION-TOKEN", "value": "session"},
                            ],
                        }
                    }
                ]
            }
        }

        config = parse_import_text(json.dumps(har))

        self.assertEqual(
            config["cookie"],
            "X-APPLE-WEBAUTH-USER=user; X-APPLE-WEBAUTH-TOKEN=token; X-APPLE-DS-WEB-SESSION-TOKEN=session",
        )

    def test_parse_hme_curl_rejects_non_hme_url(self):
        with self.assertRaisesRegex(ValueError, "maildomainws"):
            parse_hme_curl("curl 'https://www.icloud.com/' -b 'a=b'")

    def test_parse_hme_curl_accepts_china_host_and_fills_region_defaults(self):
        curl_text = r"""curl 'https://p30-maildomainws.icloud.com.cn/v2/hme/list?clientBuildNumber=2626Build17&clientMasteringNumber=2626Build17&clientId=client-cn&dsid=12345678' \
  -H 'accept: */*' \
  -b 'X-APPLE-WEBAUTH-USER="user"; X-APPLE-WEBAUTH-TOKEN="token"; X-APPLE-DS-WEB-SESSION-TOKEN="session"'"""

        config = parse_hme_curl(curl_text)

        self.assertEqual(config["host"], "p30-maildomainws.icloud.com.cn")
        self.assertEqual(config["dsid"], "12345678")
        self.assertEqual(config["langCode"], "zh-cn")
        self.assertEqual(config["origin"], "https://www.icloud.com.cn")
        self.assertEqual(config["referer"], "https://www.icloud.com.cn/")

    def test_parse_hme_curl_keeps_captured_china_origin_header(self):
        curl_text = r"""curl 'https://p30-maildomainws.icloud.com.cn/v2/hme/list?clientBuildNumber=2626Build17&clientMasteringNumber=2626Build17&clientId=client-cn&dsid=12345678' \
  -H 'Origin: https://www.icloud.com.cn' \
  -H 'Referer: https://www.icloud.com.cn/' \
  -b 'X-APPLE-WEBAUTH-USER="user"; X-APPLE-WEBAUTH-TOKEN="token"; X-APPLE-DS-WEB-SESSION-TOKEN="session"'"""

        config = parse_hme_curl(curl_text)

        self.assertEqual(config["origin"], "https://www.icloud.com.cn")
        self.assertEqual(config["referer"], "https://www.icloud.com.cn/")

    def test_parse_import_text_finds_china_hme_request_inside_har(self):
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "url": (
                                "https://p30-maildomainws.icloud.com.cn/v2/hme/list?"
                                "clientBuildNumber=2626Build17&"
                                "clientMasteringNumber=2626Build17&"
                                "clientId=client-cn&"
                                "dsid=12345678"
                            ),
                            "headers": [
                                {
                                    "name": "Cookie",
                                    "value": (
                                        'X-APPLE-WEBAUTH-USER="user"; '
                                        'X-APPLE-WEBAUTH-TOKEN="token"; '
                                        'X-APPLE-DS-WEB-SESSION-TOKEN="session"'
                                    ),
                                }
                            ],
                            "cookies": [],
                        }
                    }
                ]
            }
        }

        config = parse_import_text(json.dumps(har))

        self.assertEqual(config["host"], "p30-maildomainws.icloud.com.cn")
        self.assertEqual(config["langCode"], "zh-cn")
        self.assertEqual(config["origin"], "https://www.icloud.com.cn")

    def test_parse_hme_curl_fills_global_defaults_when_headers_missing(self):
        curl_text = r"""curl 'https://p119-maildomainws.icloud.com/v2/hme/list?clientBuildNumber=2614Build17&clientMasteringNumber=2614Build17&clientId=client-1&dsid=608658063' \
  -b 'X-APPLE-WEBAUTH-USER="user"; X-APPLE-WEBAUTH-TOKEN="token"; X-APPLE-DS-WEB-SESSION-TOKEN="session"'"""

        config = parse_hme_curl(curl_text)

        self.assertEqual(config["origin"], "https://www.icloud.com")
        self.assertEqual(config["referer"], "https://www.icloud.com/")
        self.assertEqual(config["langCode"], "zh-tw")

    def test_save_imported_session_writes_config_and_metadata(self):
        config = {
            "host": "p119-maildomainws.icloud.com",
            "dsid": "608658063",
            "clientId": "client-1",
            "clientBuildNumber": "2614Build17",
            "clientMasteringNumber": "2614Build17",
            "cookie": "SESSION=ok",
            "langCode": "zh-tw",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_imported_session(config, root / "hme-config.json", root / "state" / "hme-session.json")

            saved_config = json.loads((root / "hme-config.json").read_text(encoding="utf-8"))
            saved_metadata = json.loads((root / "state" / "hme-session.json").read_text(encoding="utf-8"))

        self.assertEqual(saved_config["cookie"], "SESSION=ok")
        self.assertNotIn("cookie", saved_metadata)
        self.assertEqual(saved_metadata["clientId"], "client-1")


if __name__ == "__main__":
    unittest.main()
