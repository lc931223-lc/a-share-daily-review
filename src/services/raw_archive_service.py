import hashlib
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class RawArchiveResult:
    sha256: str
    path: Path
    bytes_written: int
    existed: bool


def archive_raw(
    raw: bytes,
    source: str,
    dataset: str,
    trade_date: date,
    archive_root: str | Path,
) -> RawArchiveResult:
    digest = hashlib.sha256(raw).hexdigest()
    target = (
        Path(archive_root)
        / "data"
        / "raw"
        / source
        / trade_date.isoformat()
        / dataset
        / f"{digest}.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != raw:
            raise RuntimeError(f"归档摘要冲突：{digest}")
        return RawArchiveResult(digest, target.resolve(), len(raw), True)

    temp_path = target.with_name(f".{target.name}.tmp")
    temp_path.write_bytes(raw)
    os.replace(temp_path, target)
    return RawArchiveResult(digest, target.resolve(), len(raw), False)
