# Plan: the SIMD domain ranks

Drafted 29 September 2026 and revised the same day after review. Status: implemented for
release 4.0.0 (decision simd-domain-ranks).

The review found three gaps, all accepted: domain ranks are not whole numbers (the type), 2004 has
no crime rank (availability by edition), and the trace command would not see the new columns
(trace). It supported ranks only, the ranks in the SQL output, and no stored 2004 crime column.

## Aim

Attach the Scottish Government's published SIMD domain ranks, income, employment, health,
education, access, crime and housing, for every edition, to both tables, copied as published.
The HEAL-Scot DRS asks for domain-level data; other projects will too.

## What was checked before writing this

| Fact | Evidence |
| --- | --- |
| The ranks are already pinned | Each edition's Scottish Government shapefile attribute table, already in `sources.yaml` and hashed, carries the domain ranks beside the overall rank |
| 2004 has six domains | `incrank`, `emprank`, `hlthrank`, `edurank`, `houserank`, `gaccrank`; the crime domain began in 2006 |
| 2006 to 2020 have seven | the six plus `crimerank`; the 2020 file's income rank is the revised `incrankv2` |
| Every zone has every rank | 2020: all 6,976 data zones in all seven domains |
| **Ranks are not whole numbers** | 7,796 values across the six files end in .5, for example 2020v2 income for S01006523 is 5955.5. Per file: 2004 2,126; 2006 2,134; 2009 398; 2012 412; 2016 830; 2020 1,896 |
| Ties are mostly, not always, averaged | Of 5,188 tied groups across all domains and editions, 4,116 carry the average of the positions they occupy, as two zones at positions 5955 and 5956 both getting 5955.5. The other 1,072 do not: in 2009 income two zones share 5521 where the average would be 5521.5, and in 2020v2 income twelve zones at positions 6965 to 6976 share 6969 where the average would be 6970.5. Every value is a multiple of 0.5 |
| An independent source agrees | The Scottish Government's `SIMD 2020v2 - ranks.xlsx`, a retired pin still on disk, gives identical ranks on all 6,976 zones for all seven domains and the overall rank. Its headers confirm only income was revised in 2020v2 |
| Only ranks are published | No domain deciles or quintiles in any pinned file; PHS publishes no domain data at all |
| DataLoch releases none | The HEAL-Scot DSF's SIMD dataset has no domain fields |

The Open Government Licence already covers these files.

The publisher does not tie ranks by one consistent rule, so the ranks are copied exactly as
published and never recalculated, the exceptions included. Deciles are not derived (decision 1).

## Decisions

1. **Ranks only**, copied as published. No quintiles, deciles or other n-tiles for domains, in
   the tables, the SQL or Python. (Supported by review; confirmed 29 September: not for now.)
2. **In the SQL output**: seven domain measures in the shared core, chosen by edition like the
   bands. (Option (b); supported by review.)
3. **No 2004 crime column.** The schema holds only what was published; availability by edition
   is explicit everywhere a domain is selected. (Decided.)
4. **Release 4.0.0.** The new columns change both schemas, the CSV digest and the loader's
   expectations, so a loaded table is out of date: the same reasoning as 3.0.0. (Decided.)
5. **Indicators**, such as the income rate: out of scope; a later plan if a project asks.

## Design

### 1. Registry

Each `govscot_editions` entry gains a `domains` map from a fixed vocabulary, `income`,
`employment`, `health`, `education`, `access`, `crime`, `housing`, to that edition's column name,
for example `{income: incrankv2, employment: emprank, ...}` for 2020v2. 2004 declares six. The
loader refuses an unknown domain key or a declared column missing from the file. **The registry
is the single statement of which domain exists in which edition**; everything below reads it.

### 2. A type that keeps the half

A new schema type, `rank`, for a rank that may end in .5:

| Layer | Representation | Why |
| --- | --- | --- |
| Reader | parsed as a decimal, then required to be a whole multiple of 0.5 within 1 to the edition's zone count | anything else is a corrupted source, not a tie |
| Parquet | `float64` | every multiple of 0.5 in this range is exact in binary floating point |
| CSV | always one decimal place: `5955.0`, `5955.5` | one text form per value, so the digest is stable |
| SQL Server | `decimal(6,1)` | exact; renders with one decimal place, so the loaded digest matches the CSV's |
| Python | float, compared exactly | no conversion to integer anywhere |

Every place that today turns a measure into an integer for comparison or rendering, including
`int()` in trace and the `Int64` casts in readback, must treat a `rank` column by this table.

### 3. Schema

Per edition and declared domain, `simd{edition}_{domain}_domain_rank`, type `rank`, not
nullable, source `govscot`, described as the Scottish Government's unweighted domain rank, 1 most
deprived, copied exactly as published; values may end in .5. No `simd2004_crime_domain_rank`. That is 6 + 5 × 7 = 41
columns, appended at the end of both tables so every existing column keeps its position and its
fingerprint can be pinned on its own, as for rurality. Schemas become `postcode_simd_wide_v3`
and `postcode_simd_sspl_v3`.

### 4. Join and readback

The join attaches the ranks on the edition's data-zone vintage, like the government bands.
`attach()` in `core/join.py` re-looks-up government fields from the saved file's own data zones;
its field list becomes per edition, read from the registry, so readback covers exactly the
declared columns and never asks for 2004 crime. Readback compares `rank` columns exactly.

### 5. Availability by edition

Where a domain is selected by edition, an undeclared domain is **not published**, never missing:

- **SQL.** The generator emits, for each domain measure, one branch per edition that declares it.
  For an edition without it the measure is a literal `NULL`, so no query references a column
  that does not exist. The `missing_simd` test covers only the measures the chosen edition
  publishes: a 2004 result with every published value present is `matched`, with its crime
  measure null. The linkage guide states which measure is unpublished for which edition.
- **Python.** Asking for a domain an edition does not publish returns null values for those rows
  and says so in the label, rather than raising. A cohort spanning 2004 and later editions gets
  the crime rank where published and null for 2004 rows.

### 6. Trace

`trace.py` checks a fixed list of 14 measures and compares after `int()`. It becomes driven by
the registry: every measure the edition publishes, the declared domains included, each compared
exactly, so a saved 123.5 against a source 5955.5, or 5955.0 against 5955.5, is a mismatch.

### 7. An independent check

A test, not a build dependency: where the retired 2020v2 ranks workbook is on disk, every saved
2020v2 domain rank must equal it exactly.

### 8. Exports

The CSV carries the new columns in the one-decimal form; nothing is excluded. The SQL Server
import restores them as `decimal(6,1)`. The digest, both generated SQL Server scripts and the
loader's expectations change.

### 9. SQL output

The shared core grows from 41 to 48 columns: `gov_income_domain_rank`, `gov_employment_domain_rank`,
`gov_health_domain_rank`, `gov_education_domain_rank`, `gov_access_domain_rank`,
`gov_crime_domain_rank`, `gov_housing_domain_rank`, placed after the existing measures. Every
query's column count changes by seven; the walkthrough follows.

### 10. Python

`column(edition, "income_domain_rank")` works through the existing naming, with the availability
rule of section 5. `label()` describes a domain rank as the Government's unweighted measure.

### 11. Documents

The dictionaries regenerate. `LINKAGE_BY_ERA.md` and `EXAMPLES.md` say that a domain rank is the
Government's unweighted measure, a different basis from the PHS population-weighted decile, that
ranks are copied exactly as published and may end in .5, most but not all tied zones sharing the
average of their positions, that no published band exists for it, and that 2004 has no crime
domain.

## Tests

- **Fractional round trip, mandatory.** A .5 rank survives, unchanged and exactly: source to
  Parquet, Parquet to CSV text (`5955.5`), CSV through the SQL Server import (`decimal(6,1)`),
  the saved table to the digest on both sides, and Python lookups. A whole rank renders as
  `5955.0` everywhere. A synthetic fixture carries both, and one real value, S01006523's 2020v2
  income rank, is checked on the built table. So are two tied values that are not averaged, 2009
  income 5521 and 2020v2 income 6969, which must arrive exactly as published.
- **Reader.** A rank that is not a multiple of 0.5, one out of range, one missing: each refused.
  Ties are counted in the build report and allowed.
- **Registry.** An unknown domain key, a declared column missing from the file, 2004 declaring
  crime: each refused.
- **Availability.** SQL: a 2004 result is `matched` with every published value and a null crime
  measure, and no generated query names `simd2004_crime_domain_rank`. Python: a cohort mixing
  2004 and 2020v2 returns crime for 2020v2 rows and null for 2004 rows, without error.
- **Readback.** A domain rank changed after writing, in 2004 and in 2020v2, and a .5 value changed
  to its whole neighbour, must each be caught.
- **Trace.** A corrupted domain rank, 123.5 against 5955.5, must report a mismatch.
- **Fingerprints.** The 189 existing history columns and the 146 existing main columns unchanged.
- **Independent check.** The 2020v2 workbook comparison.

## Found during implementation

The dated query (`spd/link_as_of.sql`) and the walkthrough found the geography record with a
join whose condition mixed a computed key with alternative date ranges, and matched the date
bounds null-safely with an OR. Engines could not hash either join, so they compared every pair of
rows. The 41 wider rows made DuckDB reverse the join and a full-history cohort went from 87
seconds to over 15 minutes. The key is now computed first and each join is on plain equality, a
missing date compared through a stand-in date and a null flag, so a real date equal to the
stand-in never meets a missing one, rather than `IS NOT DISTINCT FROM`, which SQL Server
supports only from 2022. The results are identical on every one of the 247,745 recorded
lives: the dated query takes 0.9 seconds in DuckDB and 5 in SQL Server, the walkthrough 0.3
and 50. The missing-SIMD test names only the editions that did not publish a domain, with
plain comparisons, since an `IN` list there cost a join each.

Review of the implementation added three guards. Python checks a domain against the registry:
an unknown domain or a published column missing from the table is an error, never "not
published". The SQL Server check compares a rank column's precision and scale as well as its
type and hashes the stored value unrounded, and the import converts a rank only when its text
survives the round trip, so 5955.54 can neither load as 5955.5 nor pass as it.

## For HEAL-Scot meanwhile

The project need not wait. A one-off join of the 2020 shapefile table on `DataZone2011Code` gives
the seven 2020v2 domain ranks today, read as decimals. Whether domains stay in the DRS is still to
be agreed with DataLoch; DataLoch releases none.
