"""Extract the NRS field descriptions from the pinned data dictionaries, once, for review.

    python -m simd_ingest.extract_descriptions        # writes simd_ingest/column_descriptions.yaml

The SPD dictionary has one table for small-user and one for large-user fields; the SSPL
dictionary one. Each field's type, range and comment is kept per dictionary table, with the
file it came from, because the wording can differ between them. The output is a starting point:
every entry is marked `reviewed: false` until a person has read it against the dictionary.
Re-running overwrites the file, so review edits belong in the file only after the last extraction.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import docx
import yaml

from .core.sources import load_registry

PACKAGE = Path(__file__).resolve().parent
OUT = PACKAGE / "column_descriptions.yaml"
# Dictionary file (by its pinned path's name) -> the tables to read, in order, as (label, index).
TABLES = {"spd-indexdatadictionary": [("spd_small_user", 0), ("spd_large_user", 1)],
          "SSPL Data Dictionary": [("sspl", 2)]}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\t", " ")).strip()


def extract(root: Path) -> dict:
    registry = load_registry(PACKAGE / "sources.yaml")
    out = {}
    for f in registry.files:
        prefix = next((p for p in TABLES if Path(f.path).name.startswith(p)), None)
        if f.role != "documentation" or prefix is None:
            continue
        document = docx.Document(str(Path(root) / f.path))
        for label, index in TABLES[prefix]:
            table = document.tables[index]
            header = [_clean(c.text) for c in table.rows[0].cells]
            if header[:4] != ["Field Name", "Type/ Size", "Range", "Comments"]:
                raise ValueError(f"{f.path} table {index}: unexpected header {header}")
            for row in table.rows[1:]:
                cells = [_clean(c.text) for c in row.cells]
                name = cells[0].replace(" ", "")
                if not name:
                    continue
                entry = out.setdefault(name, {"reviewed": False})
                entry[label] = {"type": cells[1], "range": cells[2], "text": cells[3],
                                "source": {"file": f.path, "sha256": f.sha256}}
    return out


def main(argv=None) -> int:
    root = Path(argv[0]) if argv else PACKAGE.parent / "manual_data"
    descriptions = extract(root)
    header = ("# NRS field descriptions, extracted from the pinned SPD and SSPL data dictionaries by\n"
              "# simd_ingest/extract_descriptions.py, per dictionary table, with the file and hash they came\n"
              "# from. reviewed: false until a person has read the entry against the dictionary.\n")
    OUT.write_text(header + yaml.safe_dump(descriptions, sort_keys=True, allow_unicode=True, width=100))
    print(f"wrote {OUT}: {len(descriptions)} fields")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
