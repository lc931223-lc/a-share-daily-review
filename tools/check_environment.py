from __future__ import annotations

import importlib.util
import os
import sys
import urllib.request
from pathlib import Path


REQUIRED_MODULES = [
    "requests",
    "pandas",
    "numpy",
    "lxml",
    "bs4",
    "mootdx",
    "akshare",
    "tushare",
    "stockstats",
]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def module_status(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def check_url(url: str) -> tuple[bool, str]:
    headers = {"User-Agent": "Mozilla/5.0"}
    if module_status("requests"):
        import requests

        try:
            response = requests.get(url, headers=headers, timeout=10)
            return 200 <= response.status_code < 400, f"HTTP {response.status_code}"
        except Exception as exc:
            return False, exc.__class__.__name__

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return 200 <= response.status < 400, f"HTTP {response.status}"
    except Exception as exc:
        return False, exc.__class__.__name__


def main() -> int:
    load_dotenv(Path(".env"))

    print(f"Python: {sys.version.split()[0]}")
    print(f"Executable: {sys.executable}")
    print()

    missing = []
    print("Python modules:")
    for name in REQUIRED_MODULES:
        ok = module_status(name)
        print(f"  {name}: {'OK' if ok else 'MISSING'}")
        if not ok:
            missing.append(name)

    print()
    print("Environment variables:")
    for name in ["TUSHARE_TOKEN", "IWENCAI_API_KEY", "IWENCAI_BASE_URL"]:
        value = os.getenv(name, "")
        if name.endswith("TOKEN") or name.endswith("KEY"):
            status = "SET" if value else "MISSING"
        else:
            status = value or "MISSING"
        print(f"  {name}: {status}")

    print()
    print("Network probes:")
    probes = {
        "Tencent quote": "https://qt.gtimg.cn/q=sh000001",
        "Eastmoney quote": "https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001",
    }
    failed_probes = []
    for label, url in probes.items():
        ok, detail = check_url(url)
        print(f"  {label}: {'OK' if ok else 'FAILED'} ({detail})")
        if not ok:
            failed_probes.append(label)

    if missing:
        return 1
    if failed_probes:
        print()
        print("Warnings:")
        print("  Some external data probes failed. Dependencies are installed, but this network")
        print("  path may need retrying, throttling, or a different network when fetching data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
