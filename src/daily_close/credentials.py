"""Credential presence only. Never expose values, lengths, prefixes or hashes."""

import os
from urllib.parse import quote, quote_plus

from dotenv import load_dotenv


def credential_health(root):
    load_dotenv(root / ".env", override=False)
    return {
        "tushare_token": "AVAILABLE" if os.environ.get("TUSHARE_TOKEN", "").strip() else "MISSING"
    }


def redact(value):
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        token = os.environ.get("TUSHARE_TOKEN", "").strip()
        if token:
            for secret in (token, quote(token, safe=""), quote_plus(token)):
                value = value.replace(secret, "[REDACTED]")
    return value


def daily_api_health(target, client=None):
    """Probe the required API without persisting provider messages or credentials."""
    try:
        if client is None:
            import tushare as ts

            client = ts.pro_api(os.environ["TUSHARE_TOKEN"], timeout=20)
        frame = client.daily(trade_date=target.strftime("%Y%m%d"))
        if frame is None or frame.empty:
            return "EMPTY_RESPONSE"
        if "trade_date" not in frame or not frame.trade_date.astype(str).eq(target.strftime("%Y%m%d")).all():
            return "SOURCE_DATE_MISMATCH"
        return "AVAILABLE"
    except Exception as exc:
        message = str(exc).lower()
        if any(word in message for word in ("频率", "频次", "rate limit", "too many")):
            return "RATE_LIMITED"
        if any(word in message for word in ("权限", "permission", "积分")):
            return "PERMISSION_DENIED"
        if any(word in message for word in ("token", "认证", "auth")):
            return "AUTH_FAILED"
        if any(word in message for word in ("timeout", "connection", "proxy", "network", "网络")):
            return "NETWORK_FAILED"
        return "API_FAILED"
