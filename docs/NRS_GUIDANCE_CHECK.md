# Checked against the NRS postcode lookup information note

NRS publishes two postcode products and an information note on which to use: the Scottish
Postcode Directory (SPD), which this pipeline is built on, and the Scottish Statistics
Postcode Lookup (SSPL), which the note recommends "for all statistical production". This
document checks what the pipeline does against each point in the note, on 11 September 2026.

Source: [Geography: Scottish Statistics Postcode Lookup information note](https://www.nrscotland.gov.uk/publications/geography-scottish-statistics-postcode-lookup-information-note/).

## Why the SPD and not the SSPL

The SSPL "only contains the most recent version of a postcode, there are no duplicates or
postcode history". This pipeline's purpose is to attach deprivation to a record at the date
of an event, which needs the history: which data zone a postcode was in on that day, and
whether it existed at all. The SSPL cannot answer that. The SPD is also the base the SSPL is
built from, so nothing in it is a different source of truth.

The note's reason for preferring the SSPL is the GSS Geography Policy: statistics for higher
geographies should be built from statistical building blocks, output areas and data zones,
by a best-fit method, so that two publications cannot be differenced to reveal small
populations. That concern is about aggregating to higher geographies. It does not bear on
attaching a data-zone-level index to individual records, which is what this table does.

## Point by point

| The note says | What the pipeline does | Verdict |
| --- | --- | --- |
| Postcodes are allocated to higher geographies from their output area, so all postcodes in an output area get the same higher geography | SIMD is attached through the data zone. In the SPD every 2011 output area maps to exactly one 2011 data zone, and every 2001 output area to one 2001 data zone, across all 247,773 records. So the output-area route and the SPD's direct route give the same data zone for every postcode. | Agrees by construction |
| The SPD allocates directly by grid reference and can place two postcodes of one output area in different higher geographies | The SPD's health board, HSCP and council area codes are carried as source columns. The PHS within-geography bands use PHS's own data-zone-to-geography assignment, carried as `phs_dz*` columns, not the SPD codes. The two differ on 8 records, all in one data zone, which is exactly the effect the note describes. | Agrees; the SPD codes are provenance, not the basis of any band |
| Use one allocation method only for statistical purposes | Every band in the table is data-zone based, one method. An analyst aggregating the SPD geography columns themselves would be mixing methods; the data dictionary says to use the `phs_dz*` codes with the bands. | Agrees, with the caveat documented |
| Split postcodes are converted to whole postcodes using the A part, "because the A part of the postcode contains more addresses" | Split parts are kept as separate records in the table. By default a lookup on the ordinary postcode resolves to the A part and says so with status `a_part`, following this convention. A `report` rule is available that returns all parts and reports agreement or conflict instead. Of 231 current split postcodes, 203 have parts in different data zones. | Agrees by default; the alternative is explicit |
| Only the latest version of each postcode | All versions kept, keyed on postcode plus introduction date, with half-open validity | Differs, by design; required for as-of linkage |
| Census counts of split parts are added together in the SSPL | Kept per part, as the SPD publishes them | Differs; the counts are carried, not used |
| For UK-level work use the ONS NSPL rather than the SSPL | Scotland only; no NSPL involvement | Not applicable |
| Base data for the SSPL is the SPD; a very small number of postcodes exist on one directory but not the other | The SPD is the pinned source; the ONSPD is not used | Not applicable |

## The one substantive difference: split postcodes

NRS resolves a split postcode by taking the A part, on the grounds that A is the part with
more addresses. The 2026/2 bulletin confirms the convention: suffixes were swapped on four
postcodes so that A is the most populated part by delivery point count. So "use A" means
"use the majority part", and it is what every statistic produced from the SSPL does.

The pipeline's first release refused to choose, reporting a conflict whenever the parts of a
split postcode disagreed. On 11 September 2026 the default was changed to NRS's convention, so
that an analyst reconciling against an official statistic built from the SSPL gets the same
answer, and the lookups gained a `split="report"` rule for anyone who would rather see the
ambiguity than resolve it. Both rules record themselves in the result's label, and the Python
and SQL implementations are tested to agree under both.

## Things the note implies that are worth stating

- **A postcode that changed type** between small-user and large-user is two records in the
  SPD and one in the SSPL. The as-of rule handles it; the current record is never ambiguous
  because no postcode is live in both files.
- **Version alignment.** The SSPL available at the time of writing is 2025/1; the SPD used
  here is 2026/2. Cross-checking data-zone assignments between the two would compare
  different snapshots of Royal Mail's file, so it was not done. The output-area nesting check
  above is the stronger test, and it holds exactly.
