# Python current and historical record lookups

The PHS deprivation guidance for analysts, version 3.5, gives a four-step method: choose the
index, choose the edition for the years of your data, choose the category and level, then
match by postcode. `simd_ingest.lookup` offers current-only or event-date-valid record
matching. The choices stay with you and are passed explicitly as `edition` and `measure`.

This is a separate API from the [SQL sets](LINKAGE_BY_ERA.md). Python uses the selected
record's own attached geography, including for large users, with its current/as-of and
sentinel-exclusion rules; the SQL sets use the latest postcode, or in `link_as_of.sql` the
life valid on the address date, and follow large-user links. Applying that link rule to SSPL
is a project interpretation of PHS Appendix A, not verified parity with PHS's own lookup.
Historical postcode selection is a project policy, not the PHS postcode file's
latest-version policy. Do not treat the two interfaces as interchangeable or this helper as
verified PHS postcode-lookup equivalence.

Every result carries the label the guidance's checklist asks you to state: edition, whether
the category is population-weighted, the level, which end is most deprived, and how split
postcodes were resolved.

Examples below use SPD 2026/2 history, whose data rows are unchanged by the SSPL migration.
For current-only SSPL lookups, load `results/postcode_simd.parquet` instead. SSPL rejects
`on=`, an event-date column, `attach_by_era`, and `split="report"`: it has neither historical
lives nor individual split parts. The SQL era query is different: it selects an edition
by year without asking which postcode life was valid then.

```python
from simd_ingest import lookup
t = lookup.load("results/postcode_simd_history.parquet")  # every life; dated questions need this table
```

## 1. A current postcode, using a chosen SIMD edition

```python
print(lookup.lookup(t, "AB10 1BF", edition="2020v2"))
```
```text
AB10 1BF currently: unique, SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived, split postcodes resolved to the A part = 3
```

The default measure is the PHS population-weighted within-Scotland quintile, which the
guidance recommends for routine reporting. Any SIMD column can be requested by name without
its `simd{edition}_` prefix, for example `measure="pw_hb_decile"` or `measure="rank"`.

Some postcodes are more than one record:

```python
r = lookup.lookup(t, "G71 8BQ", edition="2020v2")
print(r)
print(r.candidates[["pc_norm", "DataZone2011Code", "simd2020v2_pw_scotland_quintile"]])
```
```text
G71 8BQ currently: a_part, SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived, split postcodes resolved to the A part = 5
pc_norm DataZone2011Code  simd2020v2_pw_scotland_quintile
G718BQA        S01012800                                5
G718BQB        S01011534                                2
```

NRS split this postcode into two parts on different data zones, one in the least deprived
quintile and one in the second most deprived. The default follows NRS's own convention in the
Scottish Statistics Postcode Lookup: use the A part, which is the part with more addresses.
The status `a_part` says that is what happened, and the candidates show both parts.

If you would rather not choose, ask for the report rule:

```python
print(lookup.lookup(t, "G71 8BQ", edition="2020v2", split="report"))
```
```text
G71 8BQ currently: split_conflict, SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived, split postcodes reported = None
```

## 2. Historical postcode record, edition chosen using Table 4

Table 4 of the guidance maps years of health data to the edition to use. It is available as
a function, and nothing calls it for you.

```python
edition = lookup.recommended_edition(2012)        # '2012'
print(lookup.lookup(t, "AB10 1BF", edition=edition, on="2012-06-01"))
```
```text
AB10 1BF on 2012-06-01: unique, SIMD 2012, ..., split postcodes resolved to the A part = 3
```

A postcode can be out of use on the date you ask about. AB10 1BF was deleted in 2005 and
reintroduced in 2011, so on 2008-01-01 no record is valid. The life that ended in 2005 is
used, and the status says so:

```python
r = lookup.lookup(t, "AB10 1BF", edition=lookup.recommended_edition(2008), on="2008-01-01")
print(r)
print(r.candidates[["pc_norm", "introduced_on", "deleted_on"]])
```
```text
AB10 1BF on 2008-01-01: previous_life, SIMD 2009v2, ..., split postcodes resolved to the A part = 3
pc_norm introduced_on deleted_on
AB101BF    2003-04-15 2005-10-05
```

Never the 2011 reissue, which may be somewhere else entirely. This is a project choice: the
usual reason a record carries a retired postcode is a Royal Mail recoding it never caught up
with, and the building did not move. `candidates` shows the life used, so its deletion date
tells you how stale the postcode was.

Validity is the half-open interval `introduced_on <= day < deleted_on`. On 2004-06-01 the
first record applies and the answer is quintile 3 in SIMD 2004.

## 3. A split postcode under each rule

Whether a split matters depends on the measure you ask for and the rule you choose.

```python
print(lookup.lookup(t, "AB12 3GQ", edition="2020v2"))
print(lookup.lookup(t, "AB12 3GQ", edition="2020v2", measure="rank"))
print(lookup.lookup(t, "AB12 3GQ", edition="2020v2", split="report"))
print(lookup.lookup(t, "AB12 3GQ", edition="2020v2", measure="rank", split="report"))
```
```text
AB12 3GQ currently: a_part, ... quintile, 1 = most deprived, split postcodes resolved to the A part = 4
AB12 3GQ currently: a_part, SIMD 2020v2 rank, 1 = most deprived, split postcodes resolved to the A part = 5484
AB12 3GQ currently: split_consensus, ... quintile, 1 = most deprived, split postcodes reported = 4
AB12 3GQ currently: split_conflict, SIMD 2020v2 rank, 1 = most deprived, split postcodes reported = None
```
```text
 pc_norm CouncilArea2019Code DataZone2011Code  simd2020v2_rank  simd2020v2_pw_scotland_quintile
AB123GQA           S12000034        S01006848             5484                                4
AB123GQB           S12000033        S01006608             5522                                4
```

The two parts sit in different council areas and data zones with different ranks, but both
ranks fall in quintile 4. Under the default the A part answers both questions. Under the
report rule the quintile is `split_consensus`, since the parts agree, and the rank is
`split_conflict`, since they do not. If you hold the full NRS key, the answer is unique
under either rule:

```python
print(lookup.lookup(t, "AB12 3GQA", edition="2020v2"))
```
```text
AB12 3GQA currently: unique, ... = 4
```

## 4. A cohort file, attached in one call

`attach` returns one row per input row, in the input order, never dropping or duplicating.
Three columns are added: a status, the value where the status resolves, and the matched NRS
key. The label is stored on the frame's `attrs`.

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
 id postcode event_date simd_status  simd_value simd_pc_norm
101  G71 8BQ 2019-03-04      a_part           5      G718BQA
102 AB10 1BF 2021-11-30      unique           3      AB101BF
103 AB12 3GQ 2020-07-15      a_part           4     AB123GQA
104 EH10 7DU 2023-01-09      a_part           5     EH107DUA
105      NaN 2022-05-05   not_found        <NA>          NaN
106  ZZ1 1ZZ 2020-02-02   not_found        <NA>          NaN
SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived, split postcodes resolved to the A part
a_part       3
not_found    2
unique       1
```

Pass `date_col=None` to use the current record for every event instead, and `split="report"`
to see `split_consensus` and `split_conflict` instead of `a_part`.

When a cohort spans years, the guidance's first approach is one edition per period.
`attach_by_era` applies that edition mapping and this helper's historical postcode policy
in one call. The guidance's second approach, one edition throughout, is a single `attach`
call. Neither changes Python's own-record large-user geography. For latest SSPL geography,
analysis-year edition selection and both publishers' full measures, use the
[SQL guide](LINKAGE_BY_ERA.md).

## The statuses

| Status | Meaning | Value |
| --- | --- | --- |
| `unique` | Exactly one record valid for that postcode on that day, or currently | The value |
| `a_part` | Several split parts valid; the A part was used, following NRS's convention. Default rule only | The A part's value |
| `split_consensus` | Several valid records, all with the same value for the requested measure. Report rule only | The shared value |
| `split_conflict` | Several valid records with different values. Report rule only | Null |
| `previous_life` | No record is valid on that day, but the postcode had a life that ended before it; that life was used. Dated lookups only | The previous life's value |
| `deleted` | The postcode exists but no record is valid on that day and none ended before it, or none is current | Null |
| `not_found` | No record has that postcode, or the postcode is missing, or the record that answers is a PO box under the default | Null |
| `no_edition` | The event is before 1996; the guidance points to Carstairs. `attach_by_era` only | Null |
| `missing_date` | A dated question with no date for this row. Never read as an early date | Null |

Three rules sit behind them. A record is valid for `introduced_on <= day < deleted_on`, with a
null deletion meaning current. An ordinary postcode matches every record whose base it is, so a
postcode that was later split matches its old unsplit record for old dates and its parts for
new ones. And when several parts are valid, the default takes the A part, as NRS does when it
builds the Scottish Statistics Postcode Lookup, because A is the part with more addresses. The
report rule refuses instead. Neither rule averages or votes.

One more Python default to know about. Records with `NO LINKP` or `NO LINK` in the linked
postcode field are excluded, so they come back `not_found`. The record is chosen first and the
exclusion applied to it afterwards, so a date that a PO-box life covers is `not_found`, never
answered by an older life of the same postcode. Appendix A explains why PO boxes
lack usable residential geography. Pass `include_po_boxes=True` to attach the SIMD the
directory assigns them, or `include_large_users=False` to exclude every large-user record.
Other large users still use their own attached SIMD here, not their linked small user's.

## Urban-rural class for the year, history table only

`attach_rurality` returns the Scottish Government Urban Rural Classification of the record
`attach` would choose, in the version that suits each event's year. The history table carries
all nine published versions, 2003-2004 to 2022, each placed from the record's own grid
reference. Which version suits a year is a project choice, the same as in the SPD SQL: by the
year a version describes, until the next version's year, not by when it was published.

```python
out = lookup.attach_rurality(cohort, t, "postcode", "event_date")            # 6-fold, version by year
out = lookup.attach_rurality(cohort, t, "postcode", "event_date", fold=8)
out = lookup.attach_rurality(cohort, t, "postcode", None, version="2022")   # one version, current records
```

The result adds `rurality_status`, `rurality_value`, `rurality_pc_norm`, `rurality_version` and
`rurality_label`. The status is `attach`'s, except where the chosen record has no code in that
version: then it is the reason stored with the record, `outside_polygons`, `ambiguous_polygons`
or `po_box`. The class and its reason come from one record, and split parts agree only if they
agree on both, a missing class included. An event before 2003 gets `before_first_version`, and
an event with no date `missing_date`. PO boxes are excluded unless
you pass `include_po_boxes=True`, and then come back with no code and status `po_box`. The
main table has no versions and is refused. On small-user postcodes the dated SQL query returns
the same version and class; a test compares the two on the built table.

## What to state in your analysis

The guidance's checklist, and where each item comes from here:

- Deprivation index: SIMD. The file carries no Carstairs.
- Edition, and for which years of data: your `edition` argument.
- Population-weighted or not: `pw` or `uw` in the measure name, and in the label.
- Which quintile or decile is most deprived: 1, in every column.
- Within-Scotland, within-board, within-HSCP or within-council-area: the scope in the measure
  name. Use within-board bands only for within-board analyses.
- How split postcodes were resolved: the end of the label.
