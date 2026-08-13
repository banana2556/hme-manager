from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hme import HmeClient, HmeError, load_config, region_for_host
from icloud_mail import MailClient

COOKIE_PLACEHOLDER = "PASTE_AUTHORIZED_ICLOUD_WEB_COOKIE_HERE"
SESSION_MISSING_MESSAGE = (
    "尚未匯入 iCloud session。請先在後台「匯入 Session」貼上 /v2/hme/list 的 cURL/HAR。"
)


@dataclass(frozen=True)
class HmeSessionMetadata:
    host: str
    dsid: str
    client_id: str
    client_build_number: str
    client_mastering_number: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HmeSessionMetadata":
        return cls(
            host=str(data["host"]),
            dsid=str(data["dsid"]),
            client_id=str(data["clientId"]),
            client_build_number=str(data["clientBuildNumber"]),
            client_mastering_number=str(data["clientMasteringNumber"]),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "host": self.host,
            "dsid": self.dsid,
            "clientId": self.client_id,
            "clientBuildNumber": self.client_build_number,
            "clientMasteringNumber": self.client_mastering_number,
        }


class ICloudSessionManager:
    """Import-only session manager: the session comes from a cURL/HAR import
    that writes hme-config.json; all iCloud calls go through the cookie client."""

    def __init__(self, state_dir: Path | str = "state", config_path: Path | str = "hme-config.json"):
        self.state_dir = Path(state_dir)
        self.config_path = Path(config_path)
        self.metadata_path = self.state_dir / "hme-session.json"
        self.session_state_path = self.state_dir / "session-state.json"
        self._lock = threading.RLock()
        self._mail_client: MailClient | None = None
        self.metadata = self._load_metadata()

    def get_client(self) -> HmeClient:
        with self._lock:
            client = self._get_imported_cookie_client()
            if client is None:
                raise HmeError(SESSION_MISSING_MESSAGE)
            return client

    def get_mail_client(self) -> MailClient:
        """Mail web service client backed by the same imported session.

        Cached so the setup-service host resolution only runs once per import."""
        with self._lock:
            if self._mail_client is not None:
                return self._mail_client
            client = self._get_imported_cookie_client()
            if client is None:
                raise HmeError(SESSION_MISSING_MESSAGE)
            self._mail_client = MailClient(client.config)
            return self._mail_client

    def reload(self) -> None:
        """Re-read metadata after the config file changed (e.g. new import)."""
        with self._lock:
            self._mail_client = None
            self.metadata = self._load_metadata()

    def check(self) -> dict[str, Any]:
        with self._lock:
            client = self._get_imported_cookie_client()
            if client is None:
                return self.status()
            now = time.time()
            try:
                result = client.check()
                status = self.status()
                status.update(self._record_session_check_success(now))
                status.update({"hme": result})
                return status
            except HmeError as exc:
                status = self.status()
                status.update(self._record_session_check_failure(exc, now))
                return status

    def status(self) -> dict[str, Any]:
        return {
            "metadataDetected": self.metadata is not None,
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "region": region_for_host(self.metadata.host) if self.metadata else None,
            **self._persisted_session_status(),
        }

    def _load_metadata(self) -> HmeSessionMetadata | None:
        if not self.metadata_path.exists():
            return self._load_metadata_from_config()
        try:
            return HmeSessionMetadata.from_dict(json.loads(self.metadata_path.read_text(encoding="utf-8")))
        except Exception:
            return self._load_metadata_from_config()

    def _load_metadata_from_config(self) -> HmeSessionMetadata | None:
        if not self.config_path.exists():
            return None
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None
            return HmeSessionMetadata.from_dict(data)
        except Exception:
            return None

    def _get_imported_cookie_client(self) -> HmeClient | None:
        if not self.config_path.exists():
            return None
        try:
            config = load_config(self.config_path)
        except Exception:
            return None
        if COOKIE_PLACEHOLDER in config.cookie:
            return None
        return HmeClient(config)

    def _persisted_session_status(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "persistedSession": False,
            "configPath": str(self.config_path),
            "configUpdatedAt": None,
            "lastSavedAt": None,
            **self._session_state_defaults(),
        }
        if not self.config_path.exists():
            status.update(self._load_session_state())
            return status
        try:
            config = load_config(self.config_path)
        except Exception:
            status.update(self._load_session_state())
            return status
        if COOKIE_PLACEHOLDER in config.cookie:
            status.update(self._load_session_state())
            return status
        status["persistedSession"] = True
        try:
            status["configUpdatedAt"] = self.config_path.stat().st_mtime
            status["lastSavedAt"] = status["configUpdatedAt"]
        except OSError:
            pass
        status.update(self._load_session_state())
        return status

    def _session_state_defaults(self) -> dict[str, Any]:
        return {
            "sessionValid": False,
            "lastRefreshAt": None,
            "lastValidAt": None,
            "expiresHint": "apple-controlled",
            "lastError": None,
            "needsReauth": False,
        }

    def _load_session_state(self) -> dict[str, Any]:
        if not self.session_state_path.exists():
            return {}
        try:
            loaded = json.loads(self.session_state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(loaded, dict):
            return {}
        allowed = self._session_state_defaults().keys()
        return {key: loaded[key] for key in allowed if key in loaded}

    def _save_session_state(self, state: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {**self._session_state_defaults(), **state}
        self.session_state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _record_session_check_success(self, timestamp: float) -> dict[str, Any]:
        state = {
            "sessionValid": True,
            "lastRefreshAt": timestamp,
            "lastValidAt": timestamp,
            "expiresHint": "apple-controlled",
            "lastError": None,
            "needsReauth": False,
        }
        self._save_session_state(state)
        return state

    def _record_session_check_failure(self, error: HmeError, timestamp: float) -> dict[str, Any]:
        previous_state = self._load_session_state()
        state = {
            "sessionValid": False,
            "lastRefreshAt": timestamp,
            "lastValidAt": previous_state.get("lastValidAt"),
            "expiresHint": "apple-controlled",
            "lastError": _safe_session_error(error),
            "needsReauth": True,
        }
        self._save_session_state(state)
        return state


def _safe_session_error(error: Exception) -> str:
    text = str(error)
    redactions = [
        "X-APPLE-DS-WEB-SESSION-TOKEN",
        "X-APPLE-WEBAUTH-TOKEN",
        "X-APPLE-WEBAUTH-LOGIN",
        "X-APPLE-WEBAUTH-VALIDATE",
    ]
    for token_name in redactions:
        text = text.replace(token_name, f"{token_name}<redacted>")
    return text[:500]
