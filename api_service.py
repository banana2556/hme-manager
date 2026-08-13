from __future__ import annotations

import hmac
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def require_api_key(headers: Mapping[str, str], expected: str | None) -> None:
    if not expected:
        raise PermissionError("UNAUTHORIZED: HME_API_KEY is not configured")
    candidate = _header_value(headers, "X-API-Key") or ""
    if not hmac.compare_digest(candidate, expected):
        raise PermissionError("UNAUTHORIZED: invalid API key")


def ok_response(data: Any, request_id: str | None = None) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None, "meta": _meta(request_id)}


def error_response(code: str, message: str, request_id: str | None = None) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}, "meta": _meta(request_id)}


def list_aliases(client: Any) -> dict[str, Any]:
    return ok_response(client.list_aliases())


def create_alias(client: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    label = str(payload.get("label", "")).strip()
    if not label:
        raise ValueError("label is required")
    note = str(payload.get("note", ""))
    return ok_response(client.create_alias(label=label, note=note))


def session_status(source: Any) -> dict[str, Any]:
    if hasattr(source, "status"):
        return ok_response(source.status())
    return ok_response(source.check())


def refresh_session(source: Any) -> dict[str, Any]:
    if hasattr(source, "refresh_via_validate"):
        return ok_response(source.refresh_via_validate())
    return ok_response(source.check())


def import_session(manager: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    curl_text = str(payload.get("curl_text", "")).strip()
    if not curl_text:
        raise ValueError("curl_text is required")
    from session_import import parse_import_text, save_imported_session

    config = parse_import_text(curl_text)
    save_imported_session(config, Path(manager.config_path), Path(manager.metadata_path))
    manager.reload()
    return ok_response({"imported": True, "region": _region_of(config)})


def _region_of(config: Mapping[str, Any]) -> str:
    from hme import region_for_host

    return region_for_host(str(config.get("host", "")))


def export_aliases_csv(client: Any) -> str:
    from hme import aliases_to_csv
    return aliases_to_csv(client.list_aliases())


def list_mail_folders(client: Any) -> dict[str, Any]:
    return ok_response(client.list_folders())


def list_mail_messages(client: Any, query: Mapping[str, Any]) -> dict[str, Any]:
    folder = str(query.get("folder") or "").strip()
    if not folder:
        folder = str(client.inbox_folder().get("guid") or "")
    if not folder:
        raise ValueError("folder is required (no inbox folder could be detected)")
    limit = _int_param(query, "limit", default=20, minimum=1, maximum=100)
    offset = _int_param(query, "offset", default=0, minimum=0, maximum=None)
    return ok_response(client.list_messages(folder, limit=limit, offset=offset))


def get_mail_message(client: Any, message_guid: str) -> dict[str, Any]:
    if not message_guid.strip():
        raise ValueError("message guid is required")
    return ok_response(client.get_message(message_guid))


def _int_param(query: Mapping[str, Any], name: str, default: int, minimum: int, maximum: int | None) -> int:
    raw = query.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(str(raw).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def disable_alias(client: Any, anonymous_id: str) -> dict[str, Any]:
    return ok_response(client.deactivate_alias(anonymous_id))


def delete_alias(client: Any, anonymous_id: str) -> dict[str, Any]:
    return ok_response(client.delete_alias(anonymous_id))


def enable_alias(client: Any, anonymous_id: str) -> dict[str, Any]:
    return ok_response(client.activate_alias(anonymous_id))


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    value = headers.get(name)
    if value is not None:
        return str(value)
    lowered = name.lower()
    for key, candidate in headers.items():
        if str(key).lower() == lowered:
            return str(candidate)
    return None


def _meta(request_id: str | None) -> dict[str, str | None]:
    return {"service": "hme-manager", "version": "1", "requestId": request_id}
