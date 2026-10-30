# Column descriptions for the NRS 2026/1 build

Reviewer: Claude (AI-assisted review), for Michele Tinti. Date: 30 October 2026.
Branch: `build/nrs-2026-1`, from `main` at ca5318be6c429ee70bc7c9bbd41d4698443a4aa0.

## Outcome

The NRS descriptions were extracted again, from the 2026/1 data dictionaries:

| File | SHA256 |
| --- | --- |
| `SPD/spd_postcodeindex_cut_26_1_csv/spd-indexdatadictionary-2026-1.docx` | `88d3eb39e9c63f3740fec85868d9da78f6c3d600112ab1b1c99a990da9d8738e` |
| `SSPL/sspl-2026-1/SSPL Data Dictionary 2026-1.docx` | `59e6eb66723d451dffa9ff6f046341461da9bbbd3a050acd4510f0d2f7777590` |

Both files match their pins in `sources.yaml`.

**67 fields are unchanged.** For each of them, the type, range and text of every dictionary
table are identical to the 2026/2 extraction approved in
[the 2 October 2026 review](2026-10-02-column-descriptions.md). That approval therefore still
applies, and their entries keep citing it.

**2 fields are new, and approved here.** NRS 2026/1 carries the 2021 Scottish Parliament fields
where 2026/2 carries the 2026 ones:

| Field | Type | Range | Text |
| --- | --- | --- | --- |
| `ScottishParliamentaryRegion2021Code` | Char(9) | S17000011 to S17000020 | A code that identifies a 2021 Scottish Parliamentary Region. |
| `ScottishParliamentaryConstituency2021Code` | Char(9) | S16000074 to S16000150 | A code that identifies a 2021 Scottish Parliamentary Constituency. |

The wording is the same in the SPD small-user, SPD large-user and SSPL tables.

## How it was checked

- The extracted entries were compared with the 2026/2 extraction field by field and table by
  table. The only differences are the two renamed fields: the year in the text, and the range.
- The two new entries were read again straight from each DOCX file's XML, without the project's
  extractor. The name, type, range and text agree in all three tables.
- The data agree with the descriptions. In `SmallUser.csv`, `LargeUser.csv` and
  `SingleRecord.csv` of 2026/1, every row has both codes. There are 8 region codes, from
  S17000011 to S17000020, and 73 constituency codes, from S16000074 to S16000150, all inside
  the published ranges.

The SIMD glossary was extracted again too, and is unchanged.
