import hashlib
from pathlib import Path


def archive_json(raw: bytes, archive_root: str | Path) -> tuple[str, Path]:
    digest = hashlib.sha256(raw).hexdigest()
    target = Path(archive_root) / digest[:2] / f"{digest}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != raw:
        raise RuntimeError(f"归档摘要冲突：{digest}")
    if not target.exists():
        target.write_bytes(raw)
    return digest, target.resolve()
