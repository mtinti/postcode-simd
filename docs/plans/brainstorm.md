# Brainstorm: easier updates, and a tool that attaches SIMD and rurality

Written 24 September 2026. Status: ideas only. Nothing here is decided or scheduled.

Two questions:

1. How can a new release of the postcode tables, a rurality version or a SIMD edition be taken
   in with as few hand edits as possible, when its format has not changed?
2. Should there be a packaged tool that attaches rurality to any file with a postcode and
   coordinates, and SIMD to any file with a postcode and a date?

## 1. Updating with minimal changes

The aim is two paths:

- **The format is unchanged:** one command, a review, done.
- **The format has changed:** the build stops and says exactly what moved.

The second path mostly exists already: header contracts, count checks, the rurality agreement
gate and readback all stop the build. The work is to take the manual steps out of the first.

### What an update costs today

| Update | How often | What has to be edited by hand |
| --- | --- | --- |
| New SPD or SSPL release | every six months | the registry entry: release, URL, archive and member hashes, published counts. Header lists only if NRS renames a column |
| New rurality version | about every two years | the registry entry and version block, three schema fields, the export contract's never-blank list, the test's independent year windows |
| New SIMD edition | every four to six years | two pins, two edition declarations, fourteen schema columns, PHS Table 4, test expectations, and a new data-zone vintage if it moves to 2022 zones |

Hashes, member lists and column blocks follow mechanically from the file itself. Only a few
items are real judgement: the published counts, which come from the NRS bulletin, PHS's
Table 4, and the rurality year windows.

### Ideas, from most to least valuable

**One source of truth: the registry.** The schema's edition and version columns, and the
contract's never-blank list, are written by hand although they follow from the registry.
Generate them from it, keeping the frozen schema as a committed file. A command rewrites it,
and the diff is the review. The contract stays; the typing goes.

**A `pin` command.** For example `simd-ingest pin rurality <url>`. It downloads the archive,
hashes it and its members, and reads the file to fill in the rest:

- headers for a postcode file;
- column names, polygon count and coordinate system for a shapefile;
- the reference year from the file name.

It then writes the registry entry. For the postcode files, the counts can come from the file,
with the bulletin figures kept as an optional independent check; the registry already records
which basis was used. For a same-format release the update becomes one command plus a URL.

**A read-only `check-updates` command.** Three of the four publishers can be polled:

- the PHS open-data platform has an API that lists a dataset's files;
- the Scottish Government's map service has an ATOM feed;
- NRS has only a web page, fragile to scrape but workable as an alert.

It reports what is new and never pins anything itself.

**A review build before publishing.** Build into a separate directory and compare with the
current build:

- rows added, removed and changed;
- whether the columns that should not have moved kept their fingerprint, as was done for the
  rurality branch;
- the gate results.

Only then promote, regenerate the SQL, dictionaries and database scripts, and refresh the
loader's expected hashes. The loader could read those from the manifest instead of carrying
copies.

**Keep the deliberate human steps, in one place each.**

- PHS's Table 4 cannot be inferred for a new SIMD edition; PHS has to publish it.
- The rurality year windows follow from reference years, but a person should see which years
  move.
- The independent expectations in the tests exist so that the generator is not checking
  itself. Move them into one short reviewed file rather than removing them.

### What stays manual, and should

- Anything the build stops on: a renamed column, counts that disagree, a failed rurality gate.
  A change of format is exactly what should need a person.
- A new SIMD edition on 2022 data zones. The directory already carries 2022 data-zone codes,
  and the synthetic seventh-edition test proves the join extends, but the PHS geography and
  the vintage choice need review.
- The decision-log entry for each release.

### Proposed order

1. Generate the schema blocks and the never-blank list from the registry, with the committed
   files regenerated and compared.
2. Build the `pin` command, starting with rurality and the postcode files, the most frequent
   updates.
3. Build `simd-ingest release`: pin, build into a review directory, write a change report,
   wait for approval, then promote.
4. Add `check-updates` last. It is a convenience, not a correctness step.

After steps 1 and 2, a postcode refresh is one command, a report to read and an approval. A
rurality version is the same plus a glance at the year windows. Only a new SIMD edition still
needs real work, and that happens every few years.

## 2. A tool that attaches SIMD and rurality to a file

The idea: one containerised application that attaches rurality to any file carrying a
postcode and coordinates, and another that attaches SIMD to any file carrying a postcode and a
date.

**One container with two jobs, not two.** Both need the same reference tables, release checks
and provenance. Two images would duplicate that and could drift. One image with two commands,
`attach-simd` and `attach-rurality`, or one command that does both when the columns allow it,
is simpler to version and to trust.

**Run the committed SQL inside it, not new code.** The Python API and the SQL still differ on
one policy: for a large user, the SQL takes the linked small-user postcode's geography, as PHS
Appendix A says, while Python uses the record's own. A container built on Python would ship a
third behaviour. Running the committed dated query in DuckDB inside the image means the
container, the SQL Server queries and the walkthrough give identical answers, and the existing
equivalence tests already cover it.

**Rurality from coordinates is a different, better question.** With real coordinates the
postcode is not needed: place the point directly in the classification polygons, which the
rurality module already does. That is more precise than the postcode's point and removes the
post-office-box problem. Three things to settle:

- **A date or a version.** Coordinates alone do not say which of the nine versions to use.
- **The coordinate system.** Patient data often arrives as latitude and longitude. The input
  must be converted to British National Grid explicitly and stated in the output, never
  guessed.
- **The postcode's role.** A fallback when coordinates are missing, and a sanity check: flag
  rows where the point is far from the postcode.

The same logic could later give a data zone, and so SIMD, from coordinates. That departs from
PHS practice, which is postcode-based, in the same way the two NRS products disagree on data
zones. Keep SIMD postcode-based.

**Keep the data out of the image.** Code in the image; the built tables mounted at run time.
That respects the unresolved NRS redistribution question and the grid-reference restriction.
The container refuses to run if the mounted tables do not match its expected release. The
classification polygons are Open Government Licence and could ship in the image.

**Make the output answer the reporting question.** Every input row back, with its statuses and
provenance columns, and beside the output a short report:

- counts by status;
- the release, edition and version policy used;
- the methods wording and the required attribution.

That is the minimum reporting for a linked analysis, produced automatically.

**Run it with no network.** Patient files go in, so running with no network is a real,
checkable guarantee and a good argument for approval.

**The question to answer first: can Docker run where the data lives?** The NHS side is a
Windows server with SQL Server and Jupyter, and container runtimes are often not permitted in
such environments. If Docker is not allowed, the same tool as an installable Python command,
run in the existing Jupyter environment, gives everything above except the packaging. Ask
information governance before building either.

**Recommendation.** One tool with two commands, running the committed SQL on mounted data,
with coordinates as the preferred input for rurality and a methods report on every run.
Settle the runtime question before choosing between a Docker image and an installable command.
