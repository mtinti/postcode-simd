"""Write the column provenance site as Markdown, for MkDocs (docs/plans/Column_Provenance_Site_Plan.md).

    python -m simd_ingest.provenance_site [out_dir]      # default build/provenance_docs

One page per column name, with each table's provenance side by side where they differ; one page
per pinned source object, per decision, and a page defining the build's checks. Everything comes
from the committed schemas, registry, decisions, export contract, descriptions and the lineage
map: the site describes the code at this commit and holds no data values.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

import yaml

from .core import text_output
from .core.sources import load_registry
from .lineage import PACKAGE, TABLES, lineage
from .sql_check import SQL_DECLARED, SQL_TYPE, TEXT_WIDTH

ROOT = PACKAGE.parent
TABLE_TITLE = {"history": "history table (`postcode_simd_history`, SPD)", "main": "main table (`postcode_simd`, SSPL)"}
CATEGORY = {"directory": "NRS Scottish Postcode Directory field", "lookup": "NRS Scottish Statistics Postcode Lookup field",
            "derived": "derived from the NRS record", "phs": "PHS SIMD, population-weighted",
            "govscot": "Scottish Government SIMD", "govscot_bands": "Scottish Government published domain band",
            "computed": "computed population-weighted domain band", "rurality": "Urban Rural Classification, placed"}

# What each kind of check tests. Every check a page cites must match one of these (tested).
CHECKS = [
    (r"^source\.hash\.", "the pinned file's SHA256 equals the registry's: the bytes are exactly the ones reviewed"),
    (r"^spd\.(small_user|large_user)\.schema$", "the SPD file's header is exactly the reviewed header, in order"),
    (r"^spd\.columns$", "the two SPD files together carry the expected columns"),
    (r"^spd\.primary_key_(unique|nonnull)$", "the key (pc_norm, introduced_on) is unique and never null"),
    (r"^sspl\.schema$", "the SSPL file's header is exactly the reviewed header, in order"),
    (r"^sspl\.primary_key_unique$", "pc_norm is unique in the SSPL"),
    (r"^sspl\.postcode_type$", "PostcodeType takes only the values S and L"),
    (r"^phs\.[^.]+\.source\.schema$", "the PHS file's header is the declared one"),
    (r"^phs\.[^.]+\.source\.key_unique$", "each data zone appears once in the PHS file"),
    (r"^phs\.[^.]+\.source\.rank_dense$", "the PHS ranks run 1 to the number of zones with no gap"),
    (r"^phs\.[^.]+\.source\.\w+\.range$", "every published band is within its range"),
    (r"^phs\.[^.]+\.source\.\w+\.binary$", "every published flag is 0 or 1"),
    (r"^phs\.[^.]+\.\w+\.monotone$", "after any inversion, the band never falls as the rank rises, within its geography"),
    (r"^phs\.[^.]+\.rank1_in_band1$", "the most deprived zone is in band 1 of every band: the direction is right"),
    (r"^phs\.[^.]+\.flag_anchors$", "the most deprived zone is flagged most deprived, the least deprived least"),
    (r"^phs\.[^.]+\.shared_geography$", "this edition's PHS geography codes equal those of the first edition of its vintage"),
    (r"^cross\.[^.]+\.same_zones$", "PHS and the Government publish the same data zones for the edition"),
    (r"^cross\.[^.]+\.rank_identical$", "PHS and the Government publish the same rank for every zone"),
    (r"^govscot\.[^.]+\.columns_present$", "every declared shapefile column is in the file"),
    (r"^govscot\.[^.]+\.key_unique$", "each data zone appears once in the shapefile table"),
    (r"^govscot\.[^.]+\.uw_scotland_\w+\.range$", "every unweighted band is within its range"),
    (r"^govscot\.[^.]+\.uw_scotland_\w+\.monotone$", "the unweighted band never falls as the rank rises"),
    (r"^govscot\.[^.]+\.\w+_domain\.present$", "the declared domain rank column is in the file"),
    (r"^govscot\.[^.]+\.\w+_domain\.complete$", "every zone has a domain rank"),
    (r"^govscot\.[^.]+\.\w+_domain\.half_units$", "every domain rank is a whole multiple of 0.5"),
    (r"^govscot\.[^.]+\.\w+_domain\.range$", "every domain rank is between 1 and the number of zones"),
    (r"^govscot\.[^.]+\.population\.integral$", "every population is a whole number"),
    (r"^govscot\.[^.]+\.population_nonnegative$", "no population is negative"),
    (r"^govscot\.[^.]+\.bands\.years$", "the band file holds exactly the years the registry declares for it"),
    (r"^govscot\.[^.]+\.bands\.\w+\.zones$", "every zone of the edition is published once for the domain"),
    (r"^govscot\.[^.]+\.bands\.\w+\.ranks_agree$", "every published rank equals the shapefile rank, or differs only in a declared way"),
    (r"^govscot\.[^.]+\.bands\.\w+\.rank_disagreements_as_pinned$", "the zones whose ranks differ are exactly the committed list, with exactly its ranks"),
    (r"^govscot\.[^.]+\.bands\.\w+\.\w+\.whole$", "every published band is a whole number"),
    (r"^govscot\.[^.]+\.bands\.\w+\.\w+\.range$", "every published band is within its range"),
    (r"^govscot\.[^.]+\.bands\.\w+\.\w+\.monotone$", "the published band never falls as the published rank rises (a split tie is allowed)"),
    (r"^weighted\.[^.]+\.zones$", "the population is joined to every PHS zone of the edition"),
    (r"^weighted\.[^.]+\.reproduces_phs_scotland_\w+$", "the population midpoint rule reproduces PHS's published overall Scotland band on every zone"),
    (r"^rurality\.[^.]+\.columns_present$", "the shapefile carries the declared 6-fold and 8-fold columns"),
    (r"^rurality\.[^.]+\.polygons$", "the shapefile has the declared number of polygons"),
    (r"^rurality\.[^.]+\.reference_system$", "the shapefile is in British National Grid"),
    (r"^rurality\.[^.]+\.folds_nest$", "the 6-fold is exactly the official collapse of the 8-fold"),
    (r"^rurality\.points_present$", "the records to place carry grid references"),
    (r"^rurality\.agreement\.\w+$", "the placed 2022 codes agree with the codes NRS publishes, cohort by cohort"),
    (r"^join\.[^.]+\.(phs|gov)\.[^.]+\.every_record_matched$", "every record found its data zone in the edition: no empty cell"),
    (r"^join\.[^.]+\.geography_nonnull$", "every PHS geography code is filled"),
    (r"^join\.[^.]+\.domain_ranks_half_units$", "every joined domain rank is a whole multiple of 0.5"),
    (r"^join\.[^.]+\.\w+\.range$", "every joined band is within its range"),
    (r"^join\.[^.]+\.\w+\.binary$", "every joined flag is 0 or 1"),
    (r"^join\.[^.]+\.\w+\.values$", "the status holds only null or rank_sources_disagree"),
    (r"^readback\.[^.]+\.index_columns$", "the saved file's NRS columns equal the source, re-read"),
    (r"^readback\.[^.]+\.attached_values$", "every attached value in the saved file is looked up again from the sources and equal"),
    (r"^readback\.[^.]+\.rurality_values$", "every point is placed again from the saved file's grid references and equal"),
]


def describe_check(name: str) -> str | None:
    return next((text for pattern, text in CHECKS if re.search(pattern, name)), None)


def _sql_type(kind: str) -> str:
    return {"string": f"nvarchar({TEXT_WIDTH})", **SQL_DECLARED}.get(kind, SQL_TYPE.get(kind, kind))


def _version() -> dict:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    package = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    schemas = {t: yaml.safe_load((PACKAGE / f).read_text())["version"] for t, f in TABLES.items()}
    registry = load_registry(PACKAGE / "sources.yaml")
    return {"commit": commit or "unknown", "package": package, "schemas": schemas,
            "spd": registry.spd_release, "sspl": registry.sspl_release}


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-")


GLOSSARY_DOMAIN = {"Income": "income", "Employment": "employment", "Health": "health",
                   "Education, Skills and Training": "education", "Geographic Access to Services": "access",
                   "Crime": "crime", "Housing": "housing"}


def _glossary() -> dict:
    return yaml.safe_load((PACKAGE / "simd_glossary.yaml").read_text())


def _input_row(i: dict, glossary: dict) -> str:
    if i["kind"] == "pinned_file":
        ref = f"[`{i['path']}`](../sources/{_slug(i['path'])}.md) (pinned, SHA256 `{i['sha256'][:12]}…`)"
    elif i["kind"] == "repository_file":
        ref = f"`{i['path']}` (committed in this repository)"
    elif i["kind"] == "derived_column":
        ref = f"[`{i['field']}`]({i['field']}.md), a derived column of the same row"
    else:
        ref = f"`{i['path']}`: `{i['entry']}` (registry)"
    field = f"`{i['field']}`"
    entry = glossary.get(str(i["field"]).lower()) if i["kind"] == "pinned_file" and i["path"].endswith("SG_SIMD_2020.dbf") else None
    if entry:
        field += f": {entry['description']} (SIMD 2020v2 glossary{'' if entry.get('reviewed') else ', not yet reviewed'})"
    return f"| {ref} | {field} | {i['condition'] or ''} | {('`' + i['join'] + '`') if i['join'] else 'the row itself'} |"


def _lineage_block(r: dict, lines: list, glossary: dict) -> None:
    lines += ["**Where it comes from**", "", "| Input | Field | Condition | Reaches the row by |", "| --- | --- | --- | --- |"]
    lines += [_input_row(i, glossary) for i in r["inputs"]] + [""]
    lines += [f"**Scope:** {r['scope']}.", "",
              f"**What was done to it:** *{r['transformation']['kind']}*. {r['transformation']['rule']} "
              f"(code: `{r['transformation']['code']}`)", ""]
    lines += ["**How it is checked** (what each check tests; whether a build passed it is in that build's "
              "`manifest.json[\"checks\"]`)", ""]
    lines += [f"- `{c}`: {describe_check(c.replace('.<table>', '.history'))}" for c in r["checks"]] + [""]
    lines += ["**Why:** " + ", ".join(f"[`{d}`](../decisions/{d}.md)" for d in r["decisions"]), ""]


def _general(r: dict) -> dict:
    """A record with its table removed from the check names, to compare the two tables' records."""
    g = {k: v for k, v in r.items() if k != "table"}
    g["checks"] = [re.sub(r"\.(history|main)\b", ".<table>", c) for c in r["checks"]]
    return g


def write(out: Path) -> dict:
    out = Path(out)
    for sub in ("columns", "sources", "decisions"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    version = _version()
    registry = load_registry(PACKAGE / "sources.yaml")
    schemas = {t: {f["name"]: f for f in yaml.safe_load((PACKAGE / f_).read_text())["fields"]} for t, f_ in TABLES.items()}
    order = {t: [f for f in schemas[t]] for t in TABLES}
    contract = text_output.load_contract(PACKAGE / "export_contract.yaml")
    descriptions = yaml.safe_load((PACKAGE / "column_descriptions.yaml").read_text())
    glossary = _glossary()
    indicators = defaultdict(list)
    for e in glossary.values():
        if e["domain"] in GLOSSARY_DOMAIN and e["type"] != "Rank":
            indicators[GLOSSARY_DOMAIN[e["domain"]]].append(e)
    decisions = {d["id"]: d for d in yaml.safe_load((PACKAGE / "decisions.yaml").read_text())["decisions"]}
    L = lineage()
    names = list(dict.fromkeys(order["history"] + order["main"]))
    by_file, by_decision = defaultdict(set), defaultdict(set)

    for name in names:
        in_tables = [t for t in TABLES if name in schemas[t]]
        records = {t: L[(t, name)] for t in in_tables}
        for r in records.values():
            for i in r["inputs"]:
                if i["kind"] == "pinned_file":
                    by_file[i["path"]].add(name)
            for d in r["decisions"]:
                by_decision[d].add(name)
        lines = [f"# `{name}`", ""]
        notes = {t: (schemas[t][name].get("note") or "").strip() for t in in_tables}
        nrs = descriptions.get(name)
        if any(notes.values()):
            lines += [n for n in dict.fromkeys(v for v in notes.values() if v)] + [""]
        if nrs:
            lines += ["**NRS data dictionary**" + ("" if nrs.get("reviewed") else " (extracted, not yet reviewed)"), "",
                      "| Dictionary table | Type | Range | Description |", "| --- | --- | --- | --- |"]
            for label in ("spd_small_user", "spd_large_user", "sspl"):
                if label in nrs:
                    e = nrs[label]
                    lines.append(f"| {label.replace('_', ' ')} (`{Path(e['source']['file']).name}`) | {e['type']} | {e['range']} | {e['text']} |")
            lines.append("")
        domain = re.search(r"_(income|employment|health|education|access|crime|housing)_domain_", name)
        if domain and indicators.get(domain.group(1)):
            lines += [f"**What the {domain.group(1)} domain measures** (indicators in the Scottish Government's SIMD 2020v2 "
                      "glossary; earlier editions' indicators differ in detail):", ""]
            lines += [f"- {e['description']} (`{e['label']}`, {e['type'].lower()})" for e in indicators[domain.group(1)]] + [""]
        lines += ["| Table | Type | Nullable | Category | In the CSV export | SQL Server type |", "| --- | --- | --- | --- | --- | --- |"]
        for t in in_tables:
            f = schemas[t][name]
            exported = "withheld (coordinates)" if name in contract["tables"][t]["exclude"] else "yes"
            lines.append(f"| {TABLE_TITLE[t]} | {f['type']} | {'yes' if f['nullable'] else 'no'} | {CATEGORY[f['source']]} | {exported} | `{_sql_type(f['type'])}` |")
        lines.append("")
        same = len(in_tables) == 2 and _general(records["history"]) == _general(records["main"])
        if same:
            lines += ["## Provenance (the same in both tables)", "",
                      "Each table runs its own copy of the table-level checks, named `.history.` and `.main.`.", ""]
            _lineage_block(_general(records["history"]), lines, glossary)
        else:
            for t in in_tables:
                lines += [f"## Provenance in the {TABLE_TITLE[t]}", ""]
                _lineage_block(records[t], lines, glossary)
        (out / "columns" / f"{name}.md").write_text("\n".join(lines))

    # Column index, grouped by category, in schema order.
    lines = ["# Columns", "", f"{len(names)} column names: {len(order['history'])} in the history table, "
             f"{len(order['main'])} in the main table, {len(set(order['history']) & set(order['main']))} in both.", ""]
    for cat, title in CATEGORY.items():
        members = [n for n in names if any(n in schemas[t] and schemas[t][n]["source"] == cat for t in TABLES)]
        if not members:
            continue
        lines += [f"## {title.capitalize()}", "", "| Column | History | Main |", "| --- | --- | --- |"]
        lines += [f"| [`{n}`]({n}.md) | {'yes' if n in schemas['history'] else ''} | {'yes' if n in schemas['main'] else ''} |" for n in members]
        lines.append("")
    editions = [e["key"] for e in registry.govscot_editions]
    lines += ["## Filter", "", "- By SIMD edition: " + ", ".join(f"[{e}](edition-{e}.md)" for e in editions),
              "- By category: " + ", ".join(f"[{t}](category-{c}.md)" for c, t in CATEGORY.items()), ""]
    (out / "columns" / "index.md").write_text("\n".join(lines))
    for e in editions:
        members = [n for n in names if n.startswith(f"simd{e}_")]
        page = [f"# SIMD {e} columns", "", f"{len(members)} columns.", "", "| Column | Category | History | Main |", "| --- | --- | --- | --- |"]
        page += [f"| [`{n}`]({n}.md) | {CATEGORY[(schemas['history'].get(n) or schemas['main'][n])['source']]} | "
                 f"{'yes' if n in schemas['history'] else ''} | {'yes' if n in schemas['main'] else ''} |" for n in members]
        (out / "columns" / f"edition-{e}.md").write_text("\n".join(page))
    for c, t in CATEGORY.items():
        members = [n for n in names if any(n in schemas[tb] and schemas[tb][n]["source"] == c for tb in TABLES)]
        page = [f"# {t.capitalize()}", "", f"{len(members)} columns.", "", "| Column | History | Main |", "| --- | --- | --- |"]
        page += [f"| [`{n}`]({n}.md) | {'yes' if n in schemas['history'] else ''} | {'yes' if n in schemas['main'] else ''} |" for n in members]
        (out / "columns" / f"category-{c}.md").write_text("\n".join(page))

    # Sources: one page per pinned file, grouped by the object it is downloaded in.
    licences = registry.licences
    lines = ["# Pinned sources", "", f"Every file the build reads, {len(registry.files)} in {len(registry.objects)} downloads, "
             "pinned by SHA256: a changed byte stops the build.", ""]
    for o in registry.objects:
        lines += [f"## `{o.key}`", "", f"{o.publisher}; <{o.url}>", "", "| File | Role | Columns fed |", "| --- | --- | --- |"]
        for f in o.files:
            fed = sorted(by_file.get(f.path, ()))
            lines.append(f"| [`{f.path}`]({_slug(f.path)}.md) | {f.role} | {len(fed)} |")
            page = [f"# `{f.path}`", "", f"**Publisher:** {o.publisher}. **Licence:** {licences.get(o.publisher, 'see the registry')}.", "",
                    f"**Downloaded in:** `{o.key}`, <{o.url}>" + (f" (archive member `{f.member}`)" if f.member else ""), "",
                    f"**SHA256:** `{f.sha256}`. **Role:** {f.role}.", "",
                    f"**Columns it feeds ({len(fed)}):** " + (", ".join(f"[`{n}`](../columns/{n}.md)" for n in fed)
                                                             or "none (documentation, or a shapefile member read with the others)"), ""]
            (out / "sources" / f"{_slug(f.path)}.md").write_text("\n".join(page))
        lines.append("")
    (out / "sources" / "index.md").write_text("\n".join(lines))

    # Decisions.
    lines = ["# Decisions", "", "The project's decision log (`simd_ingest/decisions.yaml`): what was decided, why, and on what evidence.", "",
             "| Decision | Status | Columns governed |", "| --- | --- | --- |"]
    for did, d in decisions.items():
        lines.append(f"| [`{did}`]({did}.md) | {d['status']} | {len(by_decision.get(did, ()))} |")
        page = [f"# `{did}`", "", f"**Date:** {d['date']}. **Status:** {d['status']}.", ""]
        for part in ("decision", "reason", "evidence"):
            if d.get(part):
                page += [f"**{part.capitalize()}.** {str(d[part]).strip()}", ""]
        gov = sorted(by_decision.get(did, ()))
        if gov:
            page += [f"**Columns ({len(gov)}):** " + ", ".join(f"[`{n}`](../columns/{n}.md)" for n in gov), ""]
        (out / "decisions" / f"{did}.md").write_text("\n".join(page))
    (out / "decisions" / "index.md").write_text("\n".join(lines))

    # Checks: the definitions, never a claim that a build passed them.
    used = sorted({c for r in L.values() for c in r["checks"]})
    lines = ["# Checks", "", "What each build check tests. A page lists the checks that guard its column; whether a given build "
             "passed them is recorded in that build's `manifest.json[\"checks\"]`, not here.", "",
             "| Kind of check | What it tests | Cited checks |", "| --- | --- | --- |"]
    for pattern, text in CHECKS:
        n = sum(1 for c in used if re.search(pattern, c))
        lines.append(f"| `{pattern}` | {text} | {n} |")
    (out / "checks.md").write_text("\n".join(lines))

    home = [
        "# Postcode-SIMD column provenance", "",
        "For every column of the two tables, where its value comes from, what was done to it, how the build checks it, "
        "and why: follow a column to its pinned source file and the decision behind it.", "",
        f"Generated from commit `{version['commit']}`: package {version['package']}; schemas "
        f"`{version['schemas']['history']}` (history) and `{version['schemas']['main']}` (main); "
        f"SPD {version['spd'].replace('_', '/')}, SSPL {version['sspl'].replace('_', '/')}. Metadata only: no data values.", "",
        "- [Columns](columns/index.md): one page per column name, each table's provenance side by side where they differ",
        "- [Pinned sources](sources/index.md): every published file the build reads, and the columns it feeds",
        "- [Decisions](decisions/index.md): why each column is made the way it is",
        "- [Checks](checks.md): what each build check tests", "",
        "## Review status", "",
        f"Descriptions extracted from the pinned NRS dictionaries: {sum(1 for e in descriptions.values() if not e.get('reviewed'))} "
        f"of {len(descriptions)} not yet reviewed. From the SIMD 2020v2 glossary: "
        f"{sum(1 for e in glossary.values() if not e.get('reviewed'))} of {len(glossary)} not yet reviewed. "
        "Each page marks unreviewed text as such.", ""]
    (out / "index.md").write_text("\n".join(home))
    return {"columns": len(names), "sources": len(registry.files), "decisions": len(decisions), "checks": len(used)}


def main(argv=None) -> int:
    out = Path(argv[0]) if argv else ROOT / "build" / "provenance_docs"
    print(write(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
