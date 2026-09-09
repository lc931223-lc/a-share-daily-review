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
