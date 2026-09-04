import json
from pathlib import Path

from src.validation.review_models import DailyReview, StockReview


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def write_schemas() -> None:
    targets = {
        "daily_review.schema.json": DailyReview.model_json_schema(),
        "stock_review.schema.json": StockReview.model_json_schema(),
    }
    for filename, schema in targets.items():
        path = PROJECT_ROOT / "schemas" / filename
        path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    write_schemas()
