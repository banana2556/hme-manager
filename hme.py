#!/usr/bin/env python3
"""CLI client for iCloud Hide My Email endpoints.

This tool does not log in to Apple ID. It uses an already-authorized iCloud
web session supplied through config or environment variables.
"""

from __future__ import annotations

import csv
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


DEFAULT_CONFIG_PATH = Path("hme-config.json")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)

REGION_GLOBAL = "global"
REGION_CHINA = "china"


def region_for_host(host: str) -> str:
    """Mainland-China iCloud accounts live on *.icloud.com.cn partitions."""
    return REGION_CHINA if host.rstrip("/").endswith(".icloud.com.cn") else REGION_GLOBAL


def web_origin_for_host(host: str) -> str:
    if region_for_host(host) == REGION_CHINA:
        return "https://www.icloud.com.cn"
    return "https://www.icloud.com"


def default_lang_code_for_host(host: str) -> str:
    return "zh-cn" if region_for_host(host) == REGION_CHINA else "zh-tw"


class HmeError(Exception):
    """Raised for config, protocol, or HTTP errors."""


@dataclass(frozen=True)
class HmeConfig:
    host: str
    dsid: str
    client_id: str
    client_build_number: str
    client_mastering_number: str
    cookie: str
    lang_code: str = "zh-tw"
    origin: str = "https://www.icloud.com"
    referer: str = "https://www.icloud.com/"
    user_agent: str = DEFAULT_USER_AGENT

    @property
    def region(self) -> str:
        return region_for_host(self.host)


Transport = Callable[[dict[str, Any]], tuple[int, Any]]


def load_config(path: str | Path | None = DEFAULT_CONFIG_PATH, env: Mapping[str, str] | None = None) -> HmeConfig:
    env = os.environ if env is None else env
    config_path = Path(env.get("ICLOUD_HME_CONFIG", path or "")) if (path or env.get("ICLOUD_HME_CONFIG")) else None
    data: dict[str, Any] = {}

    if config_path and config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise HmeError(f"Config file must contain a JSON object: {config_path}")
        data.update(loaded)
    elif path not in (None, DEFAULT_CONFIG_PATH):
        raise HmeError(f"Config file not found: {config_path}")

    env_map = {
        "host": "ICLOUD_HME_HOST",
        "dsid": "ICLOUD_HME_DSID",
        "clientId": "ICLOUD_HME_CLIENT_ID",
        "clientBuildNumber": "ICLOUD_HME_CLIENT_BUILD_NUMBER",
        "clientMasteringNumber": "ICLOUD_HME_CLIENT_MASTERING_NUMBER",
        "cookie": "ICLOUD_HME_COOKIE",
        "langCode": "ICLOUD_HME_LANG_CODE",
        "origin": "ICLOUD_HME_ORIGIN",
        "referer": "ICLOUD_HME_REFERER",
        "userAgent": "ICLOUD_HME_USER_AGENT",
    }
    for key, env_key in env_map.items():
        if env.get(env_key):
            data[key] = env[env_key]

    host = _clean_host(_value(data, "host", default=""))
    default_origin = web_origin_for_host(host)
    config = HmeConfig(
        host=host,
        dsid=_value(data, "dsid", default=""),
        client_id=_value(data, "clientId", "client_id", default=""),
        client_build_number=_value(data, "clientBuildNumber", "client_build_number", default=""),
        client_mastering_number=_value(data, "clientMasteringNumber", "client_mastering_number", default=""),
        cookie=_value(data, "cookie", default=""),
        lang_code=_value(data, "langCode", "lang_code", default=default_lang_code_for_host(host)),
        origin=_value(data, "origin", default=default_origin),
        referer=_value(data, "referer", default=f"{default_origin}/"),
        user_agent=_value(data, "userAgent", "user_agent", default=DEFAULT_USER_AGENT),
    )
    _validate_config(config)
    return config


def _value(data: Mapping[str, Any], *keys: str, default: str | None = None) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    if default is not None:
        return default
    raise HmeError(f"Missing required config value: {keys[0]}")


def _clean_host(host: str) -> str:
    if host.startswith("http://") or host.startswith("https://"):
        parsed = urllib.parse.urlparse(host)
        return parsed.netloc
    return host.strip("/")


def _validate_config(config: HmeConfig) -> None:
    required = {
        "host": config.host,
        "dsid": config.dsid,
        "clientId": config.client_id,
        "clientBuildNumber": config.client_build_number,
        "clientMasteringNumber": config.client_mastering_number,
        "cookie": config.cookie,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise HmeError("Missing required config value(s): " + ", ".join(missing))


def default_transport(request: dict[str, Any]) -> tuple[int, Any]:
    body = request.get("body")
    raw_body = body.encode("utf-8") if isinstance(body, str) else None
    req = urllib.request.Request(
        request["url"],
        data=raw_body,
        headers=request["headers"],
        method=request["method"],
    )
    try:
        with urllib.request.urlopen(req, timeout=request.get("timeout", 30)) as response:
            payload = response.read().decode("utf-8")
            return response.status, json.loads(payload)
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(payload)
        except json.JSONDecodeError:
            parsed = payload
        return exc.code, parsed
    except urllib.error.URLError as exc:
        raise HmeError(f"Network error: {exc.reason}") from exc


class HmeClient:
    def __init__(self, config: HmeConfig, transport: Transport = default_transport):
        self.config = config
        self.transport = transport

    def list_aliases(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/v2/hme/list")
        result = response.get("result") or {}
        aliases = result.get("hmeEmails") or []
        if not isinstance(aliases, list):
            raise HmeError("Unexpected list response: result.hmeEmails is not a list")
        return aliases

    def list_settings(self) -> dict[str, Any]:
        response = self._request("GET", "/v2/hme/list")
        result = response.get("result")
        if not isinstance(result, dict):
            raise HmeError("Unexpected list response: result is not an object")
        return result

    def generate_alias(self) -> str:
        response = self._request("POST", "/v1/hme/generate", {"langCode": self.config.lang_code})
        hme = (response.get("result") or {}).get("hme")
        if not isinstance(hme, str) or not hme:
            raise HmeError("Unexpected generate response: result.hme is missing")
        return hme

    def reserve_alias(self, hme: str, label: str, note: str = "") -> dict[str, Any]:
        response = self._request("POST", "/v1/hme/reserve", {"hme": hme, "label": label, "note": note})
        alias = (response.get("result") or {}).get("hme")
        if not isinstance(alias, dict):
            raise HmeError("Unexpected reserve response: result.hme is missing")
        return alias

    def create_alias(self, label: str, note: str = "") -> dict[str, Any]:
        candidate = self.generate_alias()
        return self.reserve_alias(candidate, label=label, note=note)

    def deactivate_alias(self, anonymous_id: str) -> dict[str, Any]:
        response = self._request("POST", "/v1/hme/deactivate", {"anonymousId": anonymous_id})
        result = response.get("result")
        return result if isinstance(result, dict) else {"anonymousId": anonymous_id}

    def activate_alias(self, anonymous_id: str) -> dict[str, Any]:
        response = self._request("POST", "/v1/hme/activate", {"anonymousId": anonymous_id})
        result = response.get("result")
        return result if isinstance(result, dict) else {"anonymousId": anonymous_id, "isActive": True}

    def delete_alias(self, anonymous_id: str) -> dict[str, Any]:
        response = self._request("POST", "/v1/hme/delete", {"anonymousId": anonymous_id})
        result = response.get("result")
        return result if isinstance(result, dict) else {"anonymousId": anonymous_id}

    def check(self) -> dict[str, Any]:
        settings = self.list_settings()
        return {
            "selectedForwardTo": settings.get("selectedForwardTo", ""),
            "forwardToEmails": settings.get("forwardToEmails", []),
            "aliasCount": len(settings.get("hmeEmails") or []),
        }

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        request = {
            "method": method,
            "url": self._url(path),
            "headers": self._headers(),
            "body": json.dumps(payload, separators=(",", ":")) if payload is not None else None,
            "timeout": 30,
        }
        status, response = self.transport(request)
        if status >= 400:
            raise HmeError(f"HTTP {status}: {_safe_error(response)}")
        if not isinstance(response, dict):
            raise HmeError("Unexpected response: body is not JSON object")
        if response.get("success") is not True:
            raise HmeError(f"iCloud returned success=false: {_safe_error(response)}")
        return response

    def _url(self, path: str) -> str:
        query = urllib.parse.urlencode(
            {
                "clientBuildNumber": self.config.client_build_number,
                "clientMasteringNumber": self.config.client_mastering_number,
                "clientId": self.config.client_id,
                "dsid": self.config.dsid,
            }
        )
        return f"https://{self.config.host}{path}?{query}"

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "text/plain",
            "Origin": self.config.origin,
            "Referer": self.config.referer,
            "User-Agent": self.config.user_agent,
            "Cookie": self.config.cookie,
        }


def aliases_to_csv(aliases: list[dict[str, Any]]) -> str:
    columns = [
        "hme",
        "label",
        "note",
        "forwardToEmail",
        "origin",
        "isActive",
        "createTimestamp",
        "anonymousId",
        "domain",
        "originAppName",
        "appBundleId",
        "recipientMailId",
    ]
    output = csv_string_io()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for alias in aliases:
        row = {column: alias.get(column, "") for column in columns}
        if isinstance(row["isActive"], bool):
            row["isActive"] = "true" if row["isActive"] else "false"
        writer.writerow(row)
    return output.getvalue()


def csv_string_io():
    import io

    return io.StringIO()


def _safe_error(response: Any) -> str:
    text = json.dumps(response, ensure_ascii=False) if isinstance(response, (dict, list)) else str(response)
    return text.replace("X-APPLE-DS-WEB-SESSION-TOKEN", "X-APPLE-DS-WEB-SESSION-TOKEN<redacted>")[:500]
