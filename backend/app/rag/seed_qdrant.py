"""
One-time seeding script: loads data/pricing_seed.json and upserts it into Qdrant.

Run with:
    python -m app.rag.seed_qdrant
"""

import json
from pathlib import Path

from app.rag.qdrant_client import upsert_pricing_items

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "pricing_seed.json"


def load_pricing_items() -> list[dict]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    items = load_pricing_items()
    count = upsert_pricing_items(items)
    print(f"Seeded {count} pricing items into Qdrant collection.")


if __name__ == "__main__":
    main()
