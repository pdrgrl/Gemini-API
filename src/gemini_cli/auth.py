import contextlib
import json
import os
import sys
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from gemini_webapi import GeminiClient, logger
from gemini_webapi.exceptions import AuthError


def parse_expiry(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        with contextlib.suppress(ValueError):
            return int(float(raw))
        with contextlib.suppress(ValueError):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return int(dt.timestamp())
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return int(dt.timestamp())
        except Exception:
            return None
    return None


def parse_cookies_data(data: Any) -> Tuple[Dict[str, str], Dict[str, Any]]:
    cookies: Dict[str, str] = {}
    meta: Dict[str, Any] = {}

    def _upsert(name: str, value: str, expires_raw: Any = None):
        if not isinstance(name, str) or not name:
            return
        if not isinstance(value, str) or not value:
            return
        cookies[name] = value
        exp = parse_expiry(expires_raw)
        meta[name] = {
            "expires_raw": expires_raw,
            "expires_epoch": exp,
            "expires_iso": (
                datetime.fromtimestamp(exp, tz=UTC).isoformat().replace("+00:00", "Z")
                if exp is not None
                else None
            ),
        }

    def _handle_obj(item: Any):
        if isinstance(item, dict):
            name = item.get("name")
            value = item.get("value")
            expires_raw = (
                item.get("expirationDate")
                or item.get("expires")
                or item.get("expiry")
                or item.get("expiresDate")
            )
            _upsert(name, value, expires_raw=expires_raw)

    # Flat {name: value}
    if isinstance(data, dict) and all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        for k, v in data.items():
            _upsert(k, v)
        return cookies, meta

    # {"cookies": {name: value}}
    if isinstance(data, dict) and isinstance(data.get("cookies"), dict):
        inner = data["cookies"]
        if all(isinstance(v, str) for v in inner.values()):
            for k, v in inner.items():
                _upsert(k, v)
            return cookies, meta

    # {"cookies": [{name, value}, ...]}
    if isinstance(data, dict) and isinstance(data.get("cookies"), list):
        for item in data["cookies"]:
            _handle_obj(item)
        if cookies:
            return cookies, meta

    # [{name, value}, ...]
    if isinstance(data, list):
        for item in data:
            _handle_obj(item)
        if cookies:
            return cookies, meta

    return cookies, meta


def load_env_file(path: Path) -> Dict[str, str]:
    env_vars = {}
    if not path.is_file():
        return env_vars
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k:
                env_vars[k] = v
    except Exception:
        pass
    return env_vars


def discover_cookies(specified_path: Optional[str] = None) -> Tuple[Dict[str, str], Optional[Path]]:
    """
    Search for cookies in standard locations:
    1. CLI argument specified_path
    2. Local .env file in current or parent dirs
    3. User config ~/.config/gemini/cookies.json or ~/.gemini/cookies.json
    4. Environment variables GEMINI_SECURE_1PSID / GEMINI_SECURE_1PSIDTS
    """
    # 1. Explicit path
    if specified_path:
        p = Path(specified_path)
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            cookies, _ = parse_cookies_data(data)
            return cookies, p

    # 2. Environment variables
    env_psid = os.getenv("GEMINI_SECURE_1PSID", "").strip()
    env_psidts = os.getenv("GEMINI_SECURE_1PSIDTS", "").strip()
    if env_psid:
        cookies = {"__Secure-1PSID": env_psid}
        if env_psidts:
            cookies["__Secure-1PSIDTS"] = env_psidts
        return cookies, None

    # 3. Local .env
    for candidate_dir in [Path.cwd(), *Path.cwd().parents]:
        env_file = candidate_dir / ".env"
        if env_file.is_file():
            env_data = load_env_file(env_file)
            if "GEMINI_SECURE_1PSID" in env_data and env_data["GEMINI_SECURE_1PSID"]:
                cookies = {"__Secure-1PSID": env_data["GEMINI_SECURE_1PSID"]}
                if env_data.get("GEMINI_SECURE_1PSIDTS"):
                    cookies["__Secure-1PSIDTS"] = env_data["GEMINI_SECURE_1PSIDTS"]
                return cookies, None

    # 4. User config directory
    config_candidates = [
        Path.home() / ".config" / "gemini" / "cookies.json",
        Path.home() / ".gemini" / "cookies.json",
        Path("/app/data/cookies.json"),
    ]
    for cfg in config_candidates:
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                cookies, _ = parse_cookies_data(data)
                if cookies.get("__Secure-1PSID"):
                    return cookies, cfg
            except Exception:
                pass

    return {}, None


def persist_cookies(
    cookies_json_path: Path, original: Dict[str, str], client_cookies: Any, verbose: bool = False
):
    merged = dict(original)
    with contextlib.suppress(Exception):
        for cookie in client_cookies.jar:
            name = getattr(cookie, "name", None)
            value = getattr(cookie, "value", None)
            if isinstance(name, str) and isinstance(value, str) and value:
                merged[name] = value
    if merged == original:
        return
    payload = {
        "updated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "cookies": dict(sorted(merged.items())),
    }
    cookies_json_path.parent.mkdir(parents=True, exist_ok=True)
    cookies_json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if verbose:
        changed = [k for k in merged if merged[k] != original.get(k)]
        logger.debug(f"Persisted updated cookies ({', '.join(changed)}) to {cookies_json_path}")


def get_client(
    cookies: Dict[str, str],
    proxy: Optional[str] = None,
    account_index: Optional[int] = None,
    verify: bool = True,
) -> GeminiClient:
    psid = cookies.get("__Secure-1PSID") or os.getenv("GEMINI_SECURE_1PSID")
    psidts = cookies.get("__Secure-1PSIDTS") or os.getenv("GEMINI_SECURE_1PSIDTS")

    if not psid:
        print("\033[1;31mError: Missing __Secure-1PSID session cookie.\033[0m", file=sys.stderr)
        print("Please configure your Gemini session cookies via one of:", file=sys.stderr)
        print("  1. ~/.config/gemini/cookies.json", file=sys.stderr)
        print("  2. .env file in the current directory (GEMINI_SECURE_1PSID=...)", file=sys.stderr)
        print("  3. CLI flag: --cookies-json <path>", file=sys.stderr)
        print("\nGet your cookies by opening gemini.google.com -> F12 -> Application/Storage -> Cookies", file=sys.stderr)
        sys.exit(1)

    extra = {
        k: v for k, v in cookies.items() if k not in {"__Secure-1PSID", "__Secure-1PSIDTS"}
    }

    return GeminiClient(
        secure_1psid=psid,
        secure_1psidts=psidts or "",
        cookies=extra or None,
        proxy=proxy,
        account_index=account_index,
        verify=verify,
    )
