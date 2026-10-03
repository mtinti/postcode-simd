"""Extract the field descriptions from the pinned data dictionaries and glossary, once, for review.

    python -m simd_ingest.extract_descriptions        # writes simd_ingest/column_descriptions.yaml
                                                      # and simd_ingest/simd_glossary.yaml

The SPD dictionary has one table for small-user and one for large-user fields; the SSPL
dictionary one. Each field's type, range and comment is kept per dictionary table, with the
file it came from, because the wording can differ between them. A numbered list in a cell keeps
its numbers, which Word stores outside the text. The output is the sources' own text only:
review verdicts and reviewer notes live in simd_ingest/description_review.yaml, which this script
never writes, so re-extracting cannot erase a review.
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


def _number_formats(document) -> dict:
    """numId -> the list format (decimal, bullet, ...) of its first level, from the numbering part."""
    from docx.oxml.ns import qn
    try:
        numbering = document.part.numbering_part.element
    except (KeyError, NotImplementedError):
        return {}
    abstract = {a.get(qn("w:abstractNumId")): a for a in numbering.findall(qn("w:abstractNum"))}
    out = {}
    for num in numbering.findall(qn("w:num")):
        a = abstract.get(num.find(qn("w:abstractNumId")).get(qn("w:val")))
        fmt = a.find(qn("w:lvl")).find(qn("w:numFmt")) if a is not None else None
        out[num.get(qn("w:numId"))] = fmt.get(qn("w:val")) if fmt is not None else "decimal"
    return out


def _cell_text(cell, formats: dict) -> str:
    """The cell's paragraphs, with each numbered paragraph given the number or bullet Word shows."""
    from docx.oxml.ns import qn
    parts, counters = [], {}
    for para in cell.paragraphs:
        text = _clean(para.text)
        if not text:
            continue
        ppr = para._p.find(qn("w:pPr"))
        numpr = ppr.find(qn("w:numPr")) if ppr is not None else None
        if numpr is not None and numpr.find(qn("w:numId")) is not None:
            nid = numpr.find(qn("w:numId")).get(qn("w:val"))
            counters[nid] = counters.get(nid, 0) + 1
            text = ("•" if formats.get(nid) == "bullet" else f"{counters[nid]}.") + " " + text
        parts.append(text)
    return " ".join(parts)


def extract(root: Path) -> dict:
    registry = load_registry(PACKAGE / "sources.yaml")
    out = {}
    for f in registry.files:
        prefix = next((p for p in TABLES if Path(f.path).name.startswith(p)), None)
        if f.role != "documentation" or prefix is None:
            continue
        document = docx.Document(str(Path(root) / f.path))
        formats = _number_formats(document)
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
                entry = out.setdefault(name, {})
                entry[label] = {"type": cells[1], "range": cells[2], "text": _cell_text(row.cells[3], formats),
                                "source": {"file": f.path, "sha256": f.sha256}}
    return out


GLOSSARY_OUT = PACKAGE / "simd_glossary.yaml"
GLOSSARY = "SIMD2020v2 - GIS files - glossary.xlsx"


def extract_glossary(root: Path) -> dict:
    """The Scottish Government's SIMD 2020v2 glossary: each shapefile field's label, type,
    description and the domain it belongs to. It describes the 2020v2 shapefile only."""
    import pandas as pd
    registry = load_registry(PACKAGE / "sources.yaml")
    f = next(f for f in registry.files if Path(f.path).name == GLOSSARY)
    sheet = pd.read_excel(Path(root) / f.path, sheet_name=0, header=None)
    header = [str(v).strip() for v in sheet.iloc[0, 1:4]]
    if header != ["Indicator label", "Indicator type", "Description"]:
        raise ValueError(f"{f.path}: unexpected header {header}")
    out, domain = {}, None
    for _, row in sheet.iloc[1:].iterrows():
        if pd.notna(row[0]):
            domain = _clean(str(row[0]))
        label = _clean(str(row[1]))
        out[label.lower()] = {"label": label, "domain": domain, "type": _clean(str(row[2])),
                              "description": _clean(str(row[3])),
                              "source": {"file": f.path, "sha256": f.sha256}}
    return out


def main(argv=None) -> int:
    root = Path(argv[0]) if argv else PACKAGE.parent / "manual_data"
    glossary = extract_glossary(root)
    GLOSSARY_OUT.write_text("# The Scottish Government's SIMD 2020v2 GIS glossary, extracted from the pinned file by\n"
                            "# simd_ingest/extract_descriptions.py, keyed by shapefile field (lower case). It describes the\n"
                            "# 2020v2 shapefile only. Review verdicts are in simd_ingest/description_review.yaml.\n"
                            + yaml.safe_dump(glossary, sort_keys=False, allow_unicode=True, width=100))
    print(f"wrote {GLOSSARY_OUT}: {len(glossary)} fields")
    descriptions = extract(root)
    header = ("# NRS field descriptions, extracted from the pinned SPD and SSPL data dictionaries by\n"
              "# simd_ingest/extract_descriptions.py, per dictionary table, with the file and hash they came\n"
              "# from. Review verdicts and reviewer notes are in simd_ingest/description_review.yaml.\n")
    OUT.write_text(header + yaml.safe_dump(descriptions, sort_keys=True, allow_unicode=True, width=100))
    print(f"wrote {OUT}: {len(descriptions)} fields")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
