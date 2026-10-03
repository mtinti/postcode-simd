# Plan: the repository and its sources on Zenodo, with a DOI badge

Drafted 3 October 2026, revised the same day: the NRS files are cited, never uploaded, and NRS is
not asked. Status: the sources record is published (10.5281/zenodo.23119743, 3 October 2026);
the software record follows the 6.1.0 release.

## Aim

Make the work citable and its inputs durable: the repository archived on Zenodo with a DOI for
every release and a concept DOI badge in the README, and every pinned source file archived beside
it, byte for byte, so the build can be reproduced even if a publisher's site moves or retires a
file (statistics.gov.scot may already be moving to data.gov.scot).

## What is already in place

| Fact | Where |
| --- | --- |
| The code is MIT-licensed | `LICENSE`, Michele Tinti, 2026 |
| Every source is pinned: URL, SHA256, the files inside each download | `simd_ingest/sources.yaml`: 26 downloads, 59 files, about 600 MB extracted |
| Releases are tagged | `v2.0.0` to `v2.3.0`, `v4.0.0`; 3.0.0, 5.0.0 and 6.0.0 are not tagged |
| A public site and provenance per column | <https://mtinti.github.io/postcode-simd/> |

## Two records, two DOIs

A software release and the source data differ in licence, size and how often they change, so they
are two Zenodo records, linked to each other:

| Record | Contents | How it is published | Versions |
| --- | --- | --- | --- |
| **Software** | the repository at a release tag | Zenodo's GitHub integration: every GitHub release is archived automatically | one per release; the concept DOI always resolves to the latest |
| **Sources** | the pinned downloads exactly as the registry pins them, with a manifest | a script, through Zenodo's API | one per change to the pinned set (a new SPD release, a new source) |

The badge in the README is the **software concept DOI**, so it never needs updating. The sources
record is cited from the README, the site and `CITATION.cff`, and each record lists the other as
related (software *requires* the sources; sources *is supplement to* the software).

## The licences decide what can be uploaded

Zenodo records are permanent: a published file cannot be withdrawn, only hidden behind a new
version. So nothing is uploaded until its redistribution is settled.

| Publisher | Files | Licence | Upload |
| --- | --- | --- | --- |
| PHS | 6 SIMD CSVs | Open Government Licence v3.0 | yes, with the attribution statement |
| Scottish Government, maps.gov.scot / data.gov.uk | 6 SIMD and 9 Urban Rural shapefiles, the 2020v2 glossary | Open Government Licence | yes, with attribution |
| Scottish Government, statistics.gov.scot | 3 domain-band CSVs | Open Government Licence v3.0 | yes, with attribution |
| NRS | the SPD and SSPL downloads (postcode index, lookup, dictionaries, bulletins) | the registry says "NRS terms; confirm before redistributing copies of the index"; the files carry grid references and coordinates, which the export contract already withholds | **never uploaded: cited** (decided 3 October 2026) |

**The NRS files are cited, not archived, and NRS is not asked.** The sources record's manifest and
README cite each NRS download in full: publisher, product and release (SPD 2026/2, SSPL 2026/2),
publication date, the original URL, and the SHA256 of the download and of every file the build
reads from it. Anyone can fetch the identical files from NRS and the build verifies them by hash,
as it does today. If NRS ever withdraws a release, that release cannot be rebuilt from the archive;
that is the accepted cost of not redistributing it. The PHS deprivation guidance (v3.5),
cited by several decisions but not pinned, can be pinned as documentation and archived under the
same OGL terms.

## Design

### 1. Software record: GitHub integration

- **Metadata in the repository**: a `CITATION.cff` (title, authors with ORCID, affiliation HIC,
  University of Dundee, version, licence MIT, repository, the site) read by GitHub and Zenodo, and a
  `.zenodo.json` for what CFF does not carry (keywords, related identifiers to the sources record,
  upload type software). A test checks both parse and agree with `pyproject.toml`'s version.
- **Enabling it** is Michele's step: sign in to Zenodo with GitHub and switch the repository on
  under GitHub settings. Zenodo then archives every GitHub *release* (a tag alone is not enough).
- **The first DOI**: the integration archives only releases made after it is enabled. The first
  archived release is 6.0.0, published as a GitHub release from its tag (tagging 5.0.0 and 6.0.0
  first, so the history is complete in git). Earlier versions are not back-filled.
- **The badge**, under the title next to the provenance link:
  `[![DOI](https://zenodo.org/badge/DOI/<concept DOI>.svg)](https://doi.org/<concept DOI>)`.

### 2. Sources record: a script

`python -m simd_ingest.zenodo_sources` uploads the pinned **downloads**, the objects as fetched
(the zips, not their extracted members), so the registry's object SHA256 verifies each file, plus:

- `MANIFEST.json`: for each file its registry key, original URL, SHA256, publisher, licence and
  attribution statement, and the members the build extracts with their hashes;
- `README.md` for the record: what the files are, how the build uses them, the licences, and the
  NRS downloads cited in full but not included;
- the registry itself, `sources.yaml`, at the commit uploaded.

The script refuses to upload a file whose hash differs from the registry, or whose publisher is
not cleared for redistribution: a `redistribution` setting per publisher in the registry, `upload`
for PHS and the Scottish Government (Open Government Licence) and `cite` for NRS, whose downloads
appear in the manifest and README as citations only. It uses a personal Zenodo token from the environment
(`ZENODO_TOKEN`), never written anywhere, and runs against the **Zenodo sandbox** first.

### 3. The build can fetch from the archive

Each uploaded registry object gains a `mirror` URL, its file in the sources record; the NRS
objects have none. In download mode the
fetcher tries the publisher's URL first and the mirror if that fails; either way the SHA256 must
match, so a mirror cannot change what is built. This is what makes the archive useful, not only
citable: the build survives a publisher moving its files.

### 4. Where the DOIs appear

The README badge and a citation line; the provenance site's home page and each source page (the
archived copy of the file); `CITATION.cff`; the manifest of every build (`zenodo` in
`manifest.json`, so a loaded table can be traced to the archived release and sources).

## Steps, and who does what

| Step | Who |
| --- | --- |
| ORCID iD for the author list; confirm the affiliation wording | Michele |
| `CITATION.cff`, `.zenodo.json`, their test; tag 5.0.0 and 6.0.0 | me |
| The sources script, sandbox upload, the `mirror` field and fallback, tests | me |
| Enable the GitHub integration on Zenodo; create a Zenodo token (sandbox, then real) | Michele: both need your Zenodo login |
| Publish the GitHub release 6.0.0, so Zenodo mints the software DOI | me, once the integration is on |
| Upload the sources record (OGL files), publish it, add its DOI and the mirrors | me, with your token in the environment for that session |
| Badge and citation in the README, site and manifest | me |

## Tests

- `CITATION.cff` and `.zenodo.json` parse, name the same version as `pyproject.toml`, the MIT
  licence and the related sources DOI once it exists.
- The sources script, against a temporary directory and a fake API: refuses a file whose hash
  differs, never uploads a `cite` publisher's file, and writes a manifest that lists every pinned
  object, the NRS ones as full citations (product, release, URL, SHA256 of the download and its
  members) with no file.
- The fetcher: a dead publisher URL falls back to the mirror; a mirror whose bytes differ is
  refused.

## Out of scope

The built tables and CSVs: they are derived from NRS files and stay out, like the NRS files
themselves. Anything in `local/`.
