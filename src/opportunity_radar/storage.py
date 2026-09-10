"""Immutable evidence versions in the existing FactStore, not another quote DB."""
import json
from datetime import date
from pathlib import Path

import pandas as pd
import hashlib

from src.storage.fact_store import FactStore
from src.opportunity_radar.contracts import normalize, stamp, digest


def semantic_key(row):
    return digest({k: row.get(k) for k in (
        "signal_type", "entity", "theme", "stock_code", "metric", "unit", "currency", "value",
        "source_date", "published_at", "source", "url", "body_evidence", "title", "facts")})


def receipt_matches(data, expected):
    return receipt_bytes(data, expected) is not None


def receipt_bytes(data, expected):
    # Git text transport may convert LF/CRLF, without changing the JSON content.
    lf = data.replace(b"\r\n", b"\n")
    return next((candidate for candidate in (data, lf, lf.replace(b"\n", b"\r\n")) if hashlib.sha256(candidate).hexdigest() == expected), None)


class ObservationStore:
    def __init__(self, root: Path):
        self.root = root
        self.facts = FactStore(root / "data/facts")

    def all(self):
        result = {}
        folder = self.facts.root / "dataset=opportunity_observation"
        # Reading all content-addressed partitions preserves earlier revisions.
        for path in sorted(folder.glob("trade_date=*/*.parquet")):
            for record in pd.read_parquet(path).to_dict("records"):
                row = json.loads(record["payload_json"])
                key = semantic_key(row)
                old = result.get(key)
                if old is None or row["first_seen_at"] < old["first_seen_at"]:
                    result[key] = row
        return list(result.values())

    def append(self, rows):
        known = {semantic_key(r) for r in self.all()}
        partitions = {}
        content = {}
        for raw in rows:
            path = (self.root / str(raw.get("source_path") or "")).resolve()
            if not path.is_relative_to(self.root.resolve()) or not path.is_file():
                raise ValueError("LOCAL_PROVENANCE_RECEIPT_REQUIRED")
            if path not in content:
                content[path] = path.read_bytes()
            if not receipt_matches(content[path], (raw.get("provenance") or {}).get("sha256")):
                raise ValueError("PROVENANCE_SHA_MISMATCH")
            expected = raw["provenance"]["sha256"]
            archive = self.root / "data/raw/opportunity_radar/provenance" / (expected + ".json")
            archive.parent.mkdir(parents=True, exist_ok=True)
            if not archive.exists():
                archive.write_bytes(receipt_bytes(content[path], expected))
            row = normalize(raw)
            seen = stamp(row["first_seen_at"])
            if not seen:
                raise ValueError("FIRST_SEEN_TIMESTAMP_REQUIRED")
            key = semantic_key(row)
            if key in known:
                continue
            known.add(key)
            partitions.setdefault(seen.date(), []).append({
                "observation_id": row["observation_id"], "source_date": row["source_date"],
                "first_seen_at": row["first_seen_at"], "payload_json": json.dumps(row, ensure_ascii=False, allow_nan=False),
            })
        return [self.facts.write_dataset("opportunity_observation", day, batch) for day, batch in partitions.items()]


def archive_json(root, dataset, payload):
    from src.opportunity_radar.contracts import digest
    path = root / "data/raw/opportunity_radar" / dataset / (digest(payload) + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return path
