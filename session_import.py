from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from hme import default_lang_code_for_host, web_origin_for_host


CORE_SESSION_COOKIE_NAMES = (
    "X-APPLE-DS-WEB-SESSION-TOKEN",
    "X-APPLE-WEBAUTH-USER",
    "X-APPLE-WEBAUTH-TOKEN",
)

# Global iCloud plus the mainland-China partition (icloud.com.cn).
HME_HOST_SUFFIXES = ("-maildomainws.icloud.com", "-maildomainws.icloud.com.cn")


def is_hme_host(netloc: str) -> bool:
    return netloc.endswith(HME_HOST_SUFFIXES)


def parse_hme_curl(curl_text: str) -> dict[str, str]:
    url = _extract_url(curl_text)
    parsed = urlparse(url)
    if not is_hme_host(parsed.netloc):
        raise ValueError("cURL URL must be a maildomainws.icloud.com or maildomainws.icloud.com.cn HME request")
    if not (parsed.path.startswith("/v2/hme/list") or parsed.path.startswith("/v1/hme/")):
        raise ValueError("cURL URL must point to an HME endpoint such as /v2/hme/list")

    query = parse_qs(parsed.query)
    config = {
        "host": parsed.netloc,
        "dsid": _query_value(query, "dsid"),
        "clientId": _query_value(query, "clientId"),
        "clientBuildNumber": _query_value(query, "clientBuildNumber"),
        "clientMasteringNumber": _query_value(query, "clientMasteringNumber"),
        "cookie": _extract_cookie(curl_text),
        "langCode": default_lang_code_for_host(parsed.netloc),
    }
    _require_core_session_cookies(config["cookie"])
    _add_optional_curl_header(config, curl_text, "Origin", "origin")
    _add_optional_curl_header(config, curl_text, "Referer", "referer")
    _add_optional_curl_header(config, curl_text, "User-Agent", "userAgent")
    _fill_region_defaults(config)
    return config


def parse_import_text(text: str) -> dict[str, str]:
    stripped = text.strip()
    if not stripped:
        raise ValueError("Paste a cURL command or HAR JSON first")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return parse_hme_curl(text)
    if isinstance(data, dict) and isinstance(data.get("log"), dict):
        return _parse_har(data)
    return parse_hme_curl(text)


def save_imported_session(config: dict[str, str], config_path: Path, metadata_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    metadata = {
        "host": config["host"],
        "dsid": config["dsid"],
        "clientId": config["clientId"],
        "clientBuildNumber": config["clientBuildNumber"],
        "clientMasteringNumber": config["clientMasteringNumber"],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_url(curl_text: str) -> str:
    match = re.search(r"""curl\s+(?:--location\s+)?(?P<quote>['"])(?P<url>https://.+?)(?P=quote)""", curl_text, re.S)
    if match:
        return match.group("url").strip()
    match = re.search(r"""curl\s+(?P<url>https://[^\s\\]+)""", curl_text, re.S)
    if match:
        return match.group("url").strip()
    raise ValueError("Could not find URL in cURL text")


def _parse_har(data: dict) -> dict[str, str]:
    entries = data.get("log", {}).get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("HAR log.entries must be a list")

    chosen_request = None
    for entry in entries:
        request = entry.get("request") if isinstance(entry, dict) else None
        if not isinstance(request, dict):
            continue
        url = str(request.get("url", ""))
        parsed = urlparse(url)
        if is_hme_host(parsed.netloc) and parsed.path.startswith("/v2/hme/list"):
            chosen_request = request
            break
        if chosen_request is None and is_hme_host(parsed.netloc) and "/hme/" in parsed.path:
            chosen_request = request

    if chosen_request is None:
        raise ValueError("Could not find a maildomainws HME request in the HAR. Open Hide My Email once, then export HAR.")

    url = str(chosen_request.get("url", ""))
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    cookie = _extract_cookie_from_har_request(chosen_request)
    _require_core_session_cookies(cookie)
    config = {
        "host": parsed.netloc,
        "dsid": _query_value(query, "dsid"),
        "clientId": _query_value(query, "clientId"),
        "clientBuildNumber": _query_value(query, "clientBuildNumber"),
        "clientMasteringNumber": _query_value(query, "clientMasteringNumber"),
        "cookie": cookie,
        "langCode": default_lang_code_for_host(parsed.netloc),
    }
    _add_optional_har_header(config, chosen_request, "Origin", "origin")
    _add_optional_har_header(config, chosen_request, "Referer", "referer")
    _add_optional_har_header(config, chosen_request, "User-Agent", "userAgent")
    _fill_region_defaults(config)
    return config


def _extract_cookie_from_har_request(request: dict) -> str:
    headers = request.get("headers", [])
    if isinstance(headers, list):
        for header in headers:
            if not isinstance(header, dict):
                continue
            if str(header.get("name", "")).lower() == "cookie" and str(header.get("value", "")).strip():
                return str(header["value"]).strip()

    cookies = request.get("cookies", [])
    if isinstance(cookies, list):
        pairs = []
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            name = str(cookie.get("name", "")).strip()
            value = str(cookie.get("value", "")).strip()
            if name:
                pairs.append(f"{name}={value}")
        if pairs:
            return "; ".join(pairs)
    raise ValueError("Could not find Cookie in the HAR HME request. Export HAR with request cookies included.")


def _extract_cookie(curl_text: str) -> str:
    patterns = [
        r"""(?:-b|--cookie)\s+(?P<quote>['"])(?P<cookie>.+?)(?P=quote)""",
        r"""(?:-H|--header)\s+(?P<quote>['"])cookie:\s*(?P<cookie>.+?)(?P=quote)""",
        r"""(?:-H|--header)\s+(?P<quote>['"])Cookie:\s*(?P<cookie>.+?)(?P=quote)""",
    ]
    for pattern in patterns:
        match = re.search(pattern, curl_text, re.S)
        if match:
            cookie = match.group("cookie").strip()
            if cookie:
                return cookie
    raise ValueError("Could not find Cookie in cURL text. Use Copy as cURL on /v2/hme/list.")


def _add_optional_curl_header(config: dict[str, str], curl_text: str, header_name: str, config_key: str) -> None:
    value = _extract_curl_header(curl_text, header_name)
    if value:
        config[config_key] = value


def _extract_curl_header(curl_text: str, header_name: str) -> str | None:
    escaped_name = re.escape(header_name)
    pattern = rf"""(?:-H|--header)\s+(?P<quote>['"]){escaped_name}:\s*(?P<value>.*?)(?P=quote)"""
    match = re.search(pattern, curl_text, re.I | re.S)
    if not match:
        return None
    return match.group("value").strip()


def _fill_region_defaults(config: dict[str, str]) -> None:
    """Ensure origin/referer match the account region even when the captured
    request did not include those headers (common with HAR exports)."""
    origin = web_origin_for_host(config["host"])
    config.setdefault("origin", origin)
    config.setdefault("referer", f"{origin}/")


def _add_optional_har_header(config: dict[str, str], request: dict, header_name: str, config_key: str) -> None:
    headers = request.get("headers", [])
    if not isinstance(headers, list):
        return
    for header in headers:
        if not isinstance(header, dict):
            continue
        if str(header.get("name", "")).lower() == header_name.lower():
            value = str(header.get("value", "")).strip()
            if value:
                config[config_key] = value
            return


def _require_core_session_cookies(cookie_header: str) -> None:
    cookie_names = _cookie_names(cookie_header)
    missing = [name for name in CORE_SESSION_COOKIE_NAMES if name not in cookie_names]
    if missing:
        raise ValueError(
            "Cookie is missing required iCloud session value(s): "
            + ", ".join(missing)
            + ". Use DevTools Network on /v2/hme/list and Copy as cURL."
        )


def _cookie_names(cookie_header: str) -> set[str]:
    names = set()
    for part in cookie_header.split(";"):
        name, _, _value = part.partition("=")
        cleaned = name.strip()
        if cleaned:
            names.add(cleaned)
    return names


def _query_value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key)
    if not values or not values[0]:
        raise ValueError(f"Missing query parameter: {key}")
    return values[0]
