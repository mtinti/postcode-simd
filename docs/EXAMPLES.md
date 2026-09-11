# Getting SIMD for a postcode, the way the PHS guidance describes

The PHS deprivation guidance for analysts, version 3.5, gives a four-step method: choose the
index, choose the edition for the years of your data, choose the category and level, then
match by postcode. `simd_ingest.lookup` does the matching. The choices stay with you and are
passed explicitly as `edition` and `measure`.

Every result carries the label the guidance's checklist asks you to state: edition, whether
the category is population-weighted, the level, and which end is most deprived.

All output below was produced against the v1.0 file.

```python
from simd_ingest import lookup
t = lookup.load("results/postcode_simd.parquet")
```

## 1. The most recent SIMD for a postcode as a person writes it

```python
print(lookup.lookup(t, "AB10 1BF", edition="2020v2"))
```
```text
AB10 1BF currently: unique, SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived = 3
```

The default measure is the PHS population-weighted within-Scotland quintile, which the
guidance recommends for routine reporting. Any SIMD column can be requested by name without
its `simd{edition}_` prefix, for example `measure="pw_hb_decile"` or `measure="rank"`.

Some postcodes do not have one answer:

```python
r = lookup.lookup(t, "G71 8BQ", edition="2020v2")
print(r)
print(r.candidates[["pc_norm", "DataZone2011Code", "simd2020v2_pw_scotland_quintile"]])
```
```text
G71 8BQ currently: split_conflict, SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived = None
pc_norm DataZone2011Code  simd2020v2_pw_scotland_quintile
G718BQA        S01012800                                5
G718BQB        S01011534                                2
```

NRS split this postcode into two parts on different data zones, one in the least deprived
quintile and one in the second most deprived. The status says so and the value is null.
Nothing here will choose a part for you.

## 2. SIMD at the date of an event, edition chosen by the guidance

Table 4 of the guidance maps years of health data to the edition to use. It is available as
a function, and nothing calls it for you.

```python
edition = lookup.recommended_edition(2012)        # '2012'
print(lookup.lookup(t, "AB10 1BF", edition=edition, on="2012-06-01"))
```
```text
AB10 1BF on 2012-06-01: unique, SIMD 2012, PHS population-weighted, within-Scotland quintile, 1 = most deprived = 3
```

A postcode can be out of use on the date you ask about. AB10 1BF was deleted in 2005 and
reintroduced in 2011:

```python
r = lookup.lookup(t, "AB10 1BF", edition=lookup.recommended_edition(2008), on="2008-01-01")
print(r)
print(r.candidates[["pc_norm", "introduced_on", "deleted_on"]])
```
```text
AB10 1BF on 2008-01-01: deleted, SIMD 2009v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived = None
pc_norm introduced_on deleted_on
AB101BF    2003-04-15 2005-10-05
AB101BF    2011-10-13        NaT
```

Validity is the half-open interval `introduced_on <= day < deleted_on`. On 2004-06-01 the
first record applies and the answer is quintile 3 in SIMD 2004.

## 3. A split postcode: consensus and conflict

Whether a split matters depends on the measure you ask for.

```python
print(lookup.lookup(t, "AB12 3GQ", edition="2020v2"))
print(lookup.lookup(t, "AB12 3GQ", edition="2020v2", measure="rank"))
```
```text
AB12 3GQ currently: split_consensus, SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived = 4
AB12 3GQ currently: split_conflict, SIMD 2020v2 rank, 1 = most deprived = None
```
```text
 pc_norm CouncilArea2019Code DataZone2011Code  simd2020v2_rank  simd2020v2_pw_scotland_quintile
AB123GQA           S12000034        S01006848             5484                                4
AB123GQB           S12000033        S01006608             5522                                4
```

The two parts sit in different council areas and data zones with different ranks, but both
ranks fall in quintile 4, so the quintile is `split_consensus` with a value and the rank is
`split_conflict` without one. If you hold the full NRS key, the answer is unique:

```python
print(lookup.lookup(t, "AB12 3GQA", edition="2020v2"))
```
```text
AB12 3GQA currently: unique, SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived = 4
```

## 4. A cohort file, attached in one call

`attach` returns one row per input row, in the input order, never dropping or duplicating.
Three columns are added: a status, the value where the status resolves, and the matched NRS
key where it was unique. The label is stored on the frame's `attrs`.

```python
import pandas as pd
cohort = pd.DataFrame({
    "id": [101, 102, 103, 104, 105, 106],
    "postcode": ["G71 8BQ", "AB10 1BF", "AB12 3GQ", "EH10 7DU", None, "ZZ1 1ZZ"],
    "event_date": ["2019-03-04", "2021-11-30", "2020-07-15", "2023-01-09", "2022-05-05", "2020-02-02"]})
out = lookup.attach(cohort, t, "postcode", "event_date", edition="2020v2")
print(out)
print(out.attrs["simd_label"])
print(out["simd_status"].value_counts())
```
```text
 id postcode event_date     simd_status  simd_value simd_pc_norm
101  G71 8BQ 2019-03-04  split_conflict        <NA>          NaN
102 AB10 1BF 2021-11-30          unique           3      AB101BF
103 AB12 3GQ 2020-07-15 split_consensus           4          NaN
104 EH10 7DU 2023-01-09  split_conflict        <NA>          NaN
105      NaN 2022-05-05       not_found        <NA>          NaN
106  ZZ1 1ZZ 2020-02-02       not_found        <NA>          NaN
SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived
split_conflict     2
not_found          2
unique             1
split_consensus    1
```

Pass `date_col=None` to use the current record for every event instead.

When a cohort spans years, the guidance's first approach is one edition per period. Group by
the year, attach each group with its recommended edition, and keep the edition as a column
so the analysis can say which was used:

```python
mixed["year"] = pd.to_datetime(mixed["event_date"]).dt.year
parts = [lookup.attach(g, t, "postcode", "event_date", edition=lookup.recommended_edition(y))
               .assign(edition=lookup.recommended_edition(y))
         for y, g in mixed.groupby("year")]
pd.concat(parts).sort_values("id")
```
```text
 id postcode event_date  year simd_status  simd_value simd_pc_norm edition
  1 AB10 1BF 2005-01-10  2005      unique           2      AB101BF    2006
  2 AB10 1BF 2012-06-01  2012      unique           3      AB101BF    2012
  3 AB10 1BF 2021-01-01  2021      unique           3      AB101BF  2020v2
```

The guidance's second approach, one edition throughout, is a single `attach` call.

## The statuses

| Status | Meaning | Value |
| --- | --- | --- |
| `unique` | Exactly one record valid for that postcode on that day, or currently | The value |
| `split_consensus` | Several valid records, all with the same value for the requested measure | The shared value |
| `split_conflict` | Several valid records with different values | Null |
| `deleted` | The postcode exists but no record is valid on that day, or none is current | Null |
| `not_found` | No record has that postcode, or the postcode is missing | Null |

Two rules sit behind them. A record is valid for `introduced_on <= day < deleted_on`, with a
null deletion meaning current. And an ordinary postcode matches every record whose base it is,
so a postcode that was later split matches its old unsplit record for old dates and its parts
for new ones. The module never chooses A, averages, or votes.

One default to know about. Following the guidance's Appendix A, PO boxes and other large-user
postcodes with no linked small-user postcode are excluded from every lookup, so they come back
`not_found`. Pass `include_po_boxes=True` to attach the SIMD the directory assigns them, or
`include_large_users=False` to exclude every large-user record.

## What to state in your analysis

The guidance's checklist, and where each item comes from here:

- Deprivation index: SIMD. The file carries no Carstairs.
- Edition, and for which years of data: your `edition` argument.
- Population-weighted or not: `pw` or `uw` in the measure name, and in the label.
- Which quintile or decile is most deprived: 1, in every column.
- Within-Scotland, within-board, within-HSCP or within-council-area: the scope in the measure
  name. Use within-board bands only for within-board analyses.
