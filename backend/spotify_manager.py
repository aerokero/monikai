import base64
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class SpotifyManager:
    AUTH_BASE = "https://accounts.spotify.com"
    API_BASE = "https://api.spotify.com/v1"

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tokens_file = self.data_dir / "spotify_tokens.json"
        self.oauth_state_file = self.data_dir / "spotify_oauth_state.json"

        self.client_id = str(os.getenv("SPOTIFY_CLIENT_ID", "")).strip()
        self.client_secret = str(os.getenv("SPOTIFY_CLIENT_SECRET", "")).strip()
        self.redirect_uri = str(
            os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/spotify/callback")
        ).strip()
        self.scope = str(
            os.getenv(
                "SPOTIFY_SCOPE",
                "user-read-playback-state user-read-currently-playing user-read-recently-played "
                "playlist-read-private playlist-read-collaborative",
            )
        ).strip()

        self._tokens: Dict[str, Any] = {}
        self._pending_states: Dict[str, int] = {}
        self._load_tokens()
        self._load_pending_states()

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def status(self) -> Dict[str, Any]:
        self._prune_pending_states()
        return {
            "configured": self.is_configured(),
            "connected": bool(self._tokens.get("refresh_token") or self._tokens.get("access_token")),
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "expires_at": self._tokens.get("expires_at"),
            "has_refresh_token": bool(self._tokens.get("refresh_token")),
            "pending_oauth": bool(self._pending_states),
        }

    def _load_tokens(self) -> None:
        try:
            if self.tokens_file.exists():
                raw = self.tokens_file.read_text(encoding="utf-8")
                data = json.loads(raw)
                if isinstance(data, dict):
                    self._tokens = data
        except Exception:
            self._tokens = {}

    def _save_tokens(self) -> None:
        try:
            self.tokens_file.write_text(
                json.dumps(self._tokens, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load_pending_states(self) -> None:
        try:
            if self.oauth_state_file.exists():
                raw = self.oauth_state_file.read_text(encoding="utf-8")
                data = json.loads(raw)
                if isinstance(data, dict):
                    self._pending_states = {
                        str(k): int(v)
                        for k, v in data.items()
                        if str(k).strip()
                    }
        except Exception:
            self._pending_states = {}

    def _save_pending_states(self) -> None:
        try:
            self.oauth_state_file.write_text(
                json.dumps(self._pending_states, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    @staticmethod
    def _now() -> int:
        return int(time.time())

    def _prune_pending_states(self, max_age_sec: int = 900) -> None:
        now = self._now()
        changed = False
        fresh: Dict[str, int] = {}
        for state, ts in self._pending_states.items():
            try:
                age = now - int(ts)
            except Exception:
                changed = True
                continue
            if age <= max_age_sec:
                fresh[str(state)] = int(ts)
            else:
                changed = True
        if changed or len(fresh) != len(self._pending_states):
            self._pending_states = fresh
            self._save_pending_states()

    def _issue_state(self) -> str:
        state = secrets.token_urlsafe(24)
        self._remember_state(state)
        return state

    def _remember_state(self, state: str) -> str:
        clean_state = str(state or "").strip()
        if not clean_state:
            raise ValueError("Missing OAuth state.")
        self._prune_pending_states()
        state = clean_state
        self._pending_states[state] = self._now()
        self._save_pending_states()
        return state

    def build_auth_url(self, state: Optional[str] = None) -> str:
        if not self.is_configured():
            raise RuntimeError("Spotify is not configured. Set SPOTIFY_CLIENT_ID/SECRET/REDIRECT_URI.")
        issued_state = self._remember_state(state) if str(state or "").strip() else self._issue_state()
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "scope": self.scope,
            "redirect_uri": self.redirect_uri,
            "show_dialog": "false",
            "state": issued_state,
        }
        return f"{self.AUTH_BASE}/authorize?{urllib.parse.urlencode(params)}"

    def _token_headers(self) -> Dict[str, str]:
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        return {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _post_token(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Spotify is not configured.")
        url = f"{self.AUTH_BASE}/api/token"
        body = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url=url, data=body, headers=self._token_headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            detail = self._parse_error_body(e)
            raise RuntimeError(f"Spotify token error: {detail}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Spotify token connection error: {e}")
        try:
            data = json.loads(raw)
        except Exception as e:
            raise RuntimeError(f"Invalid token response from Spotify: {e}")
        if not isinstance(data, dict):
            raise RuntimeError("Invalid token response from Spotify.")
        if data.get("error"):
            err = data.get("error_description") or data.get("error")
            raise RuntimeError(f"Spotify token error: {err}")
        return data

    def exchange_code(self, code: str, state: Optional[str] = None) -> Dict[str, Any]:
        clean_code = str(code or "").strip()
        if not clean_code:
            raise ValueError("Missing auth code.")
        clean_state = str(state or "").strip()
        self._prune_pending_states()
        if not clean_state:
            raise ValueError("Missing OAuth state.")
        if clean_state not in self._pending_states:
            raise ValueError("Invalid or expired OAuth state.")
        data = self._post_token(
            {
                "grant_type": "authorization_code",
                "code": clean_code,
                "redirect_uri": self.redirect_uri,
            }
        )
        self._pending_states.pop(clean_state, None)
        self._save_pending_states()
        self._store_token_payload(data)
        return self.status()

    def _store_token_payload(self, data: Dict[str, Any]) -> None:
        expires_in = int(data.get("expires_in") or 3600)
        self._tokens["access_token"] = data.get("access_token") or self._tokens.get("access_token")
        if data.get("refresh_token"):
            self._tokens["refresh_token"] = data.get("refresh_token")
        self._tokens["scope"] = data.get("scope") or self.scope
        self._tokens["token_type"] = data.get("token_type") or "Bearer"
        self._tokens["expires_at"] = self._now() + max(60, expires_in - 30)
        self._save_tokens()

    def refresh_access_token(self) -> Dict[str, Any]:
        refresh_token = str(self._tokens.get("refresh_token") or "").strip()
        if not refresh_token:
            raise RuntimeError("No Spotify refresh token available. Re-auth required.")
        data = self._post_token(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        )
        self._store_token_payload(data)
        return self.status()

    def _ensure_access_token(self) -> str:
        token = str(self._tokens.get("access_token") or "").strip()
        expires_at = int(self._tokens.get("expires_at") or 0)
        if token and self._now() < max(0, expires_at - 20):
            return token
        self.refresh_access_token()
        token = str(self._tokens.get("access_token") or "").strip()
        if not token:
            raise RuntimeError("Failed to obtain Spotify access token.")
        return token

    @staticmethod
    def _parse_error_body(err: urllib.error.HTTPError) -> str:
        try:
            raw = err.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            if isinstance(data, dict):
                if isinstance(data.get("error"), dict):
                    return str(data["error"].get("message") or data["error"].get("status") or raw)
                return str(data.get("error_description") or data.get("error") or raw)
            return raw
        except Exception:
            return str(err)

    def _api_get(self, path: str, params: Optional[Dict[str, Any]] = None, retry_on_401: bool = True) -> Tuple[int, Any]:
        token = self._ensure_access_token()
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{self.API_BASE}{path}{query}"
        req = urllib.request.Request(
            url=url,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                status = int(getattr(resp, "status", 200))
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw:
                    return status, None
                try:
                    return status, json.loads(raw)
                except Exception as e:
                    raise RuntimeError(f"Invalid Spotify API response: {e}")
        except urllib.error.HTTPError as e:
            if e.code == 204:
                return 204, None
            if e.code == 401 and retry_on_401:
                self.refresh_access_token()
                return self._api_get(path, params=params, retry_on_401=False)
            detail = self._parse_error_body(e)
            raise RuntimeError(f"Spotify API {e.code}: {detail}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Spotify API connection error: {e}")

    def get_now_playing(self) -> Dict[str, Any]:
        status, data = self._api_get("/me/player/currently-playing")
        if status == 204 or not isinstance(data, dict):
            return {"is_playing": False, "item": None}

        item = data.get("item") if isinstance(data, dict) else None
        artists: List[str] = []
        if isinstance(item, dict):
            for a in item.get("artists") or []:
                if isinstance(a, dict) and a.get("name"):
                    artists.append(str(a["name"]))

        return {
            "is_playing": bool(data.get("is_playing")),
            "progress_ms": data.get("progress_ms"),
            "device": (data.get("device") or {}).get("name") if isinstance(data.get("device"), dict) else None,
            "item": {
                "id": (item or {}).get("id") if isinstance(item, dict) else None,
                "name": (item or {}).get("name") if isinstance(item, dict) else None,
                "artists": artists,
                "album": ((item or {}).get("album") or {}).get("name")
                if isinstance(item, dict) and isinstance((item or {}).get("album"), dict)
                else None,
                "duration_ms": (item or {}).get("duration_ms") if isinstance(item, dict) else None,
                "external_url": (((item or {}).get("external_urls") or {}).get("spotify"))
                if isinstance(item, dict)
                else None,
            },
        }

    def list_playlists(self, limit: int = 20) -> Dict[str, Any]:
        lim = max(1, min(int(limit or 20), 50))
        _, data = self._api_get("/me/playlists", params={"limit": lim})
        items = data.get("items") if isinstance(data, dict) else []
        out: List[Dict[str, Any]] = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            out.append(
                {
                    "id": it.get("id"),
                    "name": it.get("name"),
                    "owner": ((it.get("owner") or {}).get("display_name") if isinstance(it.get("owner"), dict) else None),
                    "tracks_total": ((it.get("tracks") or {}).get("total") if isinstance(it.get("tracks"), dict) else None),
                    "public": it.get("public"),
                    "collaborative": it.get("collaborative"),
                    "external_url": ((it.get("external_urls") or {}).get("spotify") if isinstance(it.get("external_urls"), dict) else None),
                }
            )
        return {"count": len(out), "items": out}

    def recently_played(self, limit: int = 20) -> Dict[str, Any]:
        lim = max(1, min(int(limit or 20), 50))
        _, data = self._api_get("/me/player/recently-played", params={"limit": lim})
        items = data.get("items") if isinstance(data, dict) else []
        out: List[Dict[str, Any]] = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            tr = it.get("track") if isinstance(it.get("track"), dict) else {}
            artists: List[str] = []
            for a in tr.get("artists") or []:
                if isinstance(a, dict) and a.get("name"):
                    artists.append(str(a["name"]))
            out.append(
                {
                    "played_at": it.get("played_at"),
                    "track": tr.get("name"),
                    "artists": artists,
                    "album": ((tr.get("album") or {}).get("name") if isinstance(tr.get("album"), dict) else None),
                    "external_url": ((tr.get("external_urls") or {}).get("spotify") if isinstance(tr.get("external_urls"), dict) else None),
                }
            )
        return {"count": len(out), "items": out}
