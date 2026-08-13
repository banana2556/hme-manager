"""Read-only client for the iCloud Mail web service.

Reuses the imported iCloud web session (same cookie/config as the HME client).
The mail web service speaks JSON-RPC 2.0 over POST at pNN-mailws.icloud.com
(or pNN-mailws.icloud.com.cn for mainland-China accounts); the partition (pNN)
is derived from the imported maildomainws host, so no extra setup is needed.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from hme import HmeConfig, HmeError, Transport, default_transport, region_for_host, REGION_CHINA

_MAIL_HOST_RE = re.compile(r"^(?P<partition>p\d+)-maildomainws\.(?P<domain>icloud\.com(?:\.cn)?)$")

MESSAGE_PARTS = ["HEADER", "TEXT", "HTML", "ATTACHMENTS", "STRUCTURE"]
MAX_PAGE_SIZE = 100


def mail_host_for(hme_host: str) -> str:
    """Best-effort derive the mailws host from the maildomainws host.

    Note: the mail partition (pNN) does not always match the HME partition,
    so this is only a fallback. The mail host is normally resolved from the
    iCloud setup webservices map (see MailClient._resolve_mail_host)."""
    match = _MAIL_HOST_RE.match(hme_host.strip())
    if match:
        return f"{match.group('partition')}-mailws.{match.group('domain')}"
    if "maildomainws" in hme_host:
        return hme_host.replace("maildomainws", "mailws")
    raise HmeError(f"Cannot derive iCloud Mail host from HME host: {hme_host}")


class MailClient:
    def __init__(self, config: HmeConfig, transport: Transport = default_transport, mail_host: str | None = None):
        self.config = config
        self.transport = transport
        self._mail_host = mail_host

    @property
    def host(self) -> str:
        if self._mail_host is None:
            self._mail_host = self._resolve_mail_host()
        return self._mail_host

    def _setup_host(self) -> str:
        return "setup.icloud.com.cn" if region_for_host(self.config.host) == REGION_CHINA else "setup.icloud.com"

    def _resolve_mail_host(self) -> str:
        """Resolve the mail web service host from iCloud's setup service, since
        the mail partition can differ from the HME partition. Falls back to the
        derived host if setup is unavailable."""
        try:
            payload = self._setup_validate()
            found = _find_mailws_host(payload)
            if found:
                return found
        except Exception:
            pass
        return mail_host_for(self.config.host)

    def _setup_validate(self) -> Any:
        query = urllib.parse.urlencode(
            {
                "clientBuildNumber": self.config.client_build_number,
                "clientMasteringNumber": self.config.client_mastering_number,
                "clientId": self.config.client_id,
                "dsid": self.config.dsid,
            }
        )
        request = {
            "method": "POST",
            "url": f"https://{self._setup_host()}/setup/ws/1/validate?{query}",
            "headers": {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "text/plain",
                "Origin": self.config.origin,
                "Referer": f"{self.config.origin}/",
                "User-Agent": self.config.user_agent,
                "Cookie": self.config.cookie,
            },
            "body": "null",
            "timeout": 30,
        }
        status, response = self.transport(request)
        if status >= 400:
            raise HmeError(f"HTTP {status}: setup validate failed")
        return response

    def list_folders(self) -> list[dict[str, Any]]:
        payload = self._rpc("/wm/folder", "list", {})
        raw_folders = _find_list(payload, ("folders", "folder", "items", "collections"))
        folders = [folder for folder in (normalize_folder(entry) for entry in raw_folders) if folder]
        if not folders:
            raise HmeError("Unexpected folder list response from iCloud Mail: no folders found")
        return folders

    def inbox_folder(self) -> dict[str, Any]:
        folders = self.list_folders()
        for folder in folders:
            if is_inbox_folder(folder):
                return folder
        return folders[0]

    def list_messages(self, folder_guid: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        count = max(1, min(int(limit), MAX_PAGE_SIZE))
        selected = max(0, int(offset))
        payload = self._rpc(
            "/wm/message",
            "list",
            {
                "guid": folder_guid,
                "sorttype": "Date",
                "sortorder": "descending",
                "requesttype": "index",
                "selected": selected,
                "count": count,
                "rollbackslot": "0.0",
            },
        )
        raw_messages = _find_list(payload, ("messages", "items", "message", "emails"))
        messages = [message for message in (normalize_message_summary(entry) for entry in raw_messages) if message]
        total = _first_int(payload, ("total", "totalCount", "messageCount", "messagesCount"))
        return {
            "folder": folder_guid,
            "offset": selected,
            "total": total if total is not None else selected + len(messages),
            "messages": messages,
        }

    def get_message(self, message_guid: str) -> dict[str, Any]:
        payload = self._rpc("/wm/message", "get", {"guid": message_guid, "parts": MESSAGE_PARTS})
        record = _find_message_record(payload) or (payload if isinstance(payload, dict) else {})
        detail = normalize_message_detail(record, fallback_guid=message_guid)
        if detail is None:
            raise HmeError("Unexpected message response from iCloud Mail: no message payload found")
        return detail

    def _rpc(self, path: str, method: str, params: dict[str, Any]) -> Any:
        body = {
            "jsonrpc": "2.0",
            "id": f"{int(time.time() * 1000)}/1",
            "method": method,
            "params": params,
        }
        request = {
            "method": "POST",
            "url": self._url(path),
            "headers": self._headers(),
            "body": json.dumps(body, separators=(",", ":"), ensure_ascii=False),
            "timeout": 30,
        }
        status, response = self.transport(request)
        if status >= 400:
            raise HmeError(f"HTTP {status}: {_safe_error(response)}")
        return _unwrap_rpc(response)

    def _url(self, path: str) -> str:
        query = urllib.parse.urlencode(
            {
                "clientBuildNumber": self.config.client_build_number,
                "clientMasteringNumber": self.config.client_mastering_number,
                "clientId": self.config.client_id,
                "dsid": self.config.dsid,
            }
        )
        return f"https://{self.host}{path}?{query}"

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "text/plain",
            "Origin": self.config.origin,
            "Referer": f"{self.config.origin}/mail/",
            "User-Agent": self.config.user_agent,
            "Cookie": self.config.cookie,
        }


def _find_mailws_host(value: Any) -> str | None:
    """Find the mail web service host anywhere in the setup payload.

    Prefers webservices.mail.url but tolerates schema drift by scanning for any
    URL containing '-mailws.' (works for both icloud.com and icloud.com.cn)."""
    if isinstance(value, dict):
        webservices = value.get("webservices")
        if isinstance(webservices, dict):
            mail = webservices.get("mail")
            if isinstance(mail, dict):
                host = _host_from_mailws_url(mail.get("url"))
                if host:
                    return host
        for nested in value.values():
            found = _find_mailws_host(nested)
            if found:
                return found
    elif isinstance(value, list):
        for entry in value:
            found = _find_mailws_host(entry)
            if found:
                return found
    elif isinstance(value, str):
        return _host_from_mailws_url(value)
    return None


def _host_from_mailws_url(value: Any) -> str | None:
    if not isinstance(value, str) or "-mailws." not in value:
        return None
    netloc = urllib.parse.urlparse(value).netloc or value
    return netloc.split("/")[0].split(":")[0] or None


def _unwrap_rpc(response: Any) -> Any:
    if not isinstance(response, dict):
        raise HmeError("Unexpected iCloud Mail response: body is not a JSON object")
    error = response.get("error")
    if error:
        raise HmeError(f"iCloud Mail returned an error: {_safe_error(error)}")
    if "result" in response and response["result"] is not None:
        return response["result"]
    responses = response.get("responses")
    if isinstance(responses, list) and responses:
        first = responses[0]
        if isinstance(first, dict):
            inner_error = first.get("error")
            if inner_error:
                raise HmeError(f"iCloud Mail returned an error: {_safe_error(inner_error)}")
            return first.get("result") or first.get("response") or first.get("data") or first
    return response


# ---------- tolerant payload normalization ----------
# Apple's wm API is private and its payload shape drifts between builds, so
# the extractors below accept several historical field spellings.


def normalize_folder(record: Any) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    guid = _first_str(record, ("guid", "folderGuid", "folderGUID", "id"))
    name = _first_str(record, ("displayName", "name", "localizedName", "folderName"))
    if not guid or not name:
        return None
    return {
        "guid": guid,
        "name": name,
        "role": _first_str(record, ("role", "type", "folderType")) or "",
        "unreadCount": _first_int(record, ("unreadCount", "unread", "numUnread")),
        "totalCount": _first_int(record, ("totalCount", "count", "messageCount", "numMessages")),
    }


def is_inbox_folder(folder: dict[str, Any]) -> bool:
    role = str(folder.get("role") or "").strip().lower()
    if role == "inbox":
        return True
    name = str(folder.get("name") or "").strip().lower()
    return name == "inbox" or "收件" in str(folder.get("name") or "")


def normalize_message_summary(record: Any) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    guid = _first_str(record, ("guid", "messageGuid", "messageId", "uid", "id"))
    if not guid:
        return None
    sender = _format_address(record.get("from")) or _format_address(record.get("sender")) or _first_str(record, ("fromAddress",))
    to = (
        _format_address(record.get("to"))
        or _format_address(record.get("recipients"))
        or _format_address(record.get("toRecipients"))
    )
    return {
        "guid": guid,
        "from": sender or "",
        "to": to or "",
        "subject": _first_str(record, ("subject", "title")) or "(無主旨)",
        "date": _normalize_timestamp(record),
        "snippet": _first_str(record, ("snippet", "preview", "summary", "abstract")) or "",
        "isRead": _read_flag(record),
    }


def normalize_message_detail(record: Any, fallback_guid: str) -> dict[str, Any] | None:
    summary = normalize_message_summary(record)
    if summary is None:
        if not isinstance(record, dict):
            return None
        summary = {
            "guid": fallback_guid,
            "from": "",
            "to": "",
            "subject": "(無主旨)",
            "date": None,
            "snippet": "",
            "isRead": True,
        }
    detail = dict(summary)
    detail["textBody"] = _extract_body(record, (("text",), ("textBody",), ("plainText",), ("plainTextBody",), ("bodyText",), ("body", "text")))
    detail["htmlBody"] = _extract_body(record, (("html",), ("htmlBody",), ("bodyHtml",), ("body", "html")))
    detail["attachments"] = _extract_attachments(record)
    return detail


def _find_list(payload: Any, keys: tuple[str, ...]) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    for container_key in ("data", "result"):
        container = payload.get(container_key)
        if isinstance(container, dict):
            for key in keys:
                value = container.get(key)
                if isinstance(value, list):
                    return value
    return []


def _find_message_record(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if _first_str(payload, ("guid", "messageGuid", "messageId", "uid")):
            return payload
        for key in ("message", "data", "result"):
            nested = payload.get(key)
            found = _find_message_record(nested)
            if found:
                return found
        for value in payload.values():
            if isinstance(value, dict) and _first_str(value, ("guid", "messageGuid", "messageId", "uid")):
                return value
    if isinstance(payload, list):
        for entry in payload:
            found = _find_message_record(entry)
            if found:
                return found
    return None


def _first_str(record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return None


def _first_int(record: Any, keys: tuple[str, ...]) -> int | None:
    if not isinstance(record, dict):
        return None
    for key in keys:
        value = record.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def _format_address(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        email = _first_str(value, ("emailAddress", "address", "email", "mailbox"))
        name = _first_str(value, ("name", "displayName", "label", "fullName"))
        if email and name:
            return f"{name} <{email}>"
        return email or name
    if isinstance(value, list):
        formatted = [entry for entry in (_format_address(item) for item in value) if entry]
        return ", ".join(formatted) if formatted else None
    return None


def _read_flag(record: dict[str, Any]) -> bool:
    for key in ("read", "isRead", "seen", "isSeen"):
        value = record.get(key)
        if isinstance(value, bool):
            return value
    flags = record.get("flags")
    if isinstance(flags, dict):
        for key in ("read", "seen"):
            value = flags.get(key)
            if isinstance(value, bool):
                return value
    return True


def _normalize_timestamp(record: dict[str, Any]) -> str | None:
    for key in ("dateReceived", "dateSent", "date", "receivedDate", "sentDate", "timestamp", "createdAt"):
        value = record.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 10_000_000_000 else value
            try:
                return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_body(record: Any, paths: tuple[tuple[str, ...], ...]) -> str:
    if not isinstance(record, dict):
        return ""
    for path in paths:
        value: Any = record
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        text = _body_text(value)
        if text:
            return text
    parts = record.get("parts")
    if isinstance(parts, list):
        joined = "\n".join(
            text
            for text in (
                _first_str(part, ("content", "body", "text", "value"))
                for part in parts
                if isinstance(part, dict)
            )
            if text
        )
        if joined:
            return joined
    return ""


def _body_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, dict):
        return _first_str(value, ("content", "body", "text", "value"))
    if isinstance(value, list):
        joined = "\n".join(text for text in (_body_text(entry) for entry in value) if text)
        return joined or None
    return None


def _extract_attachments(record: Any) -> list[dict[str, Any]]:
    if not isinstance(record, dict):
        return []
    attachments = _find_list(record, ("attachments",))
    normalized = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        normalized.append(
            {
                "filename": _first_str(attachment, ("filename", "fileName", "name")) or "",
                "mimeType": _first_str(attachment, ("mimeType", "contentType", "type")) or "",
                "size": _first_int(attachment, ("size", "length")),
            }
        )
    return normalized


def _safe_error(response: Any) -> str:
    text = json.dumps(response, ensure_ascii=False) if isinstance(response, (dict, list)) else str(response)
    return text[:500]
