# Postcode products and guidance

Updated 13 September 2026 after the SSPL migration review. Current pins are SSPL 2026/2 and
SPD 2026/2. Source details and hashes live in `simd_ingest/sources.yaml`; current counts and
comparisons are generated in `results/BUILD_REPORT.md`.

## What NRS recommends

The [NRS information note](https://www.nrscotland.gov.uk/publications/geography-scottish-statistics-postcode-lookup-information-note/)
recommends SSPL for statistical production, using output areas as consistent building
blocks. SPD is recommended for operational/administrative questions requiring postcode
locations and associated higher areas.

| Property | SSPL main table | SPD history table |
| --- | --- | --- |
| Postcode records | Latest life per whole postcode, including deleted latest lives | All directory lives |
| Natural key | `pc_norm` | `(pc_norm, introduced_on)` |
| Higher-geography allocation | From the 2022 output-area centroid | From the postcode grid reference |
| Ordinary split postcodes | NRS makes whole on A; census counts summed | Individual parts retained |
| Large-user geography in the stored table | Source record's own assigned geography | Source record's own assigned geography |

The [SSPL 2026/2 publication](https://www.nrscotland.gov.uk/publications/scottish-statistics-postcode-lookup-20262/)
uses the July 2026 PAF. Its two Scottish Parliament fields moved from 2021 to 2026, which
the main schema now reflects. The postcode release and SIMD edition are independent.

## What the project implements

The [SQL sets](LINKAGE_BY_ERA.md) are one per product, with no default. Both take a postcode
and either the year of the health data or one chosen edition, and return every stored measure
of that edition from the record that supplies the geography. The SPD set selects the latest
life and the A part; the SSPL set does not, because NRS did. Both follow a large user's link
to its small-user postcode and give PO boxes and unlinked large users no SIMD, as PHS
Appendix A describes; NRS publishes nothing against following the link, and its SPD
dictionary calls PO-box grid references low quality. A dated question, which postcode life
was valid when the address was recorded, is answered by `link_as_of.sql` in the SPD set and
by the Python API, both from the SPD validity intervals; the SSPL cannot answer it.

Using an event year to choose a SIMD edition does **not** require historical postcode
selection: the SQL era query uses the latest postcode with a Table 4 edition. Conversely,
a latest-life SSPL record cannot establish which earlier postcode life existed at a date.
The Python API refuses dated questions against SSPL.

All SIMD joins use the source product's data-zone code of the edition's required vintage.
The main table's 2001/2011 data zones are allocated through 2022 output areas. SPD nesting
within its older output areas does not prove that the two products assign the same zones.
The former “agrees by construction” conclusion was incorrect.

PHS within-area bands use the PHS geography codes stored as `phs_dz*`, not interchangeable
NRS council/health-board fields. This is separate from choosing SSPL or SPD for the postcode
to data-zone allocation.

## What comparison can and cannot show

The build report compares source records and attached values, without following large-user
links. SPD representatives follow the SQL ordering: newest life per full key; then live,
whole/A, newest introduction. Missing-A and tied representatives are reported and excluded
from value comparisons. A deleted C part cannot displace a live A.

Differences are observations, never acceptance gates. Allocation methods, release changes,
postcode reintroductions and publisher corrections can all affect them. A common release
label does not prove that every difference is methodological. The earlier comparison of
SSPL 2026/1 with SPD 2026/2 did not isolate these causes and also used incorrect
representatives for 19 postcodes. Do not reuse its provisional counts as acceptance values.

## PHS interpretation

[PHS's postcode-file documentation](https://publichealthscotland.scot/resources-and-tools/health-intelligence-and-data-management/geography-population-and-deprivation-support/geography/postcode-file/)
describes latest versions, retained deleted records and A representatives.
[PHS deprivation guidance v3.5](../manual_data/2023-12-phs-deprivation-guidance-v35.pdf)
distinguishes edition policies (section 3.2, Table 4) and discusses postcode/large-user links
(Appendix A). Both SQL sets follow a large user's link. In the reviewed SSPL 2026/2 snapshot
that changes the PHS 2020v2 quintile of 147 large-user postcodes (50 live) against their own
record; the own-record data zone is returned beside the linked value so the change is visible.
AB24 2TY gets its link's quintile 1, not its own quintile 5, in both products.

Neither table nor SQL query has been compared against a published PHS postcode-level
oracle. Sharing SPD inputs or using A does not establish record-level parity, and exact PHS
deleted-record retention has not been reproduced. The source-faithful build is not itself a
claim that every stored large-user or PO-box value is appropriate for patient linkage.
The SQL reports PO boxes and unlinked large users as statuses with no SIMD, and keeps a
deleted latest life with `matched_is_current` false. Residence eligibility stays a downstream
decision.

For UK-wide statistics the NRS note recommends NSPL. This project remains Scotland-only.
