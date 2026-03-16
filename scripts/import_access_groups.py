from __future__ import annotations

import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parents[1]
    project_root_value = str(project_root)
    if project_root_value not in sys.path:
        sys.path.insert(0, project_root_value)

import argparse
import csv

from sqlalchemy import select

from app.db import SessionLocal
from app.models.access_group import AccessGroup, AccessGroupSource


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import access groups from text or CSV")
    parser.add_argument("--file", required=True, help="Path to source file")
    parser.add_argument(
        "--source",
        choices=[source.value for source in AccessGroupSource],
        help="Source for plain text mode (required when file is not CSV)",
    )
    return parser.parse_args()


def upsert_access_group(db, source: AccessGroupSource, name: str) -> None:
    existing = db.scalar(
        select(AccessGroup).where(
            AccessGroup.source == source,
            AccessGroup.name == name,
        )
    )
    if existing:
        existing.is_active = True
        return

    db.add(AccessGroup(source=source, name=name, is_active=True))


def import_csv(db, file_path: Path) -> int:
    inserted = 0
    with file_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            raw_source = (row.get("source") or "").strip()
            raw_name = (row.get("name") or "").strip()
            if not raw_source or not raw_name:
                continue

            source = AccessGroupSource(raw_source)
            upsert_access_group(db, source, raw_name)
            inserted += 1

    return inserted


def import_text(db, file_path: Path, source: AccessGroupSource) -> int:
    inserted = 0
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            name = line.strip()
            if not name or name.startswith("#"):
                continue
            upsert_access_group(db, source, name)
            inserted += 1

    return inserted


def main() -> None:
    args = parse_args()
    file_path = Path(args.file)
    if not file_path.exists():
        raise SystemExit(f"File does not exist: {file_path}")

    db = SessionLocal()
    try:
        if file_path.suffix.lower() == ".csv":
            count = import_csv(db, file_path)
        else:
            if not args.source:
                raise SystemExit("--source is required for plain text import")
            count = import_text(db, file_path, AccessGroupSource(args.source))

        db.commit()
        print(f"Imported {count} entries")
    finally:
        db.close()


if __name__ == "__main__":
    main()
