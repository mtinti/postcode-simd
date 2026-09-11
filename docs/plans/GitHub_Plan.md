# Publishing to GitHub

Proposed 11 September 2026. Three steps. The first tidies the tree for a public audience,
the second creates the repository and pushes, the third sets up what runs there.

Checked before writing this: the GitHub CLI on this machine is authenticated as `mtinti`;
48 files totalling 576 KB would be tracked under the current `.gitignore`; none of them
contains a personal path or address. Source data, the cache, results and the Dagster
instance are all ignored and stay local.

## Decisions only you can take

| Decision | My suggestion | Why |
| --- | --- | --- |
| Repository name | `postcode-simd` | Says what the table is; the package name `simd_ingest` stays as it is |
| Visibility | Public | The original plan called for a public repository, and nothing tracked is sensitive |
| Code licence | MIT | Short, permissive, and what HIC's RDMP uses; Apache-2.0 if you want its patent clause |
| Retired prototype | Delete | `build.py`, `acceptance.py`, `sources_v1.yaml`, their test and the parity test exist only to compare against output that will not be in the repository |
| CI contacting the publishers | Manual trigger only | Automatic downloads on every push would hit NRS and gov.scot for no reason |
| The table as a release asset | Not yet | The Parquet contains NRS directory columns; confirm the redistribution terms first. Code, manifests and the dictionary can go out now |

## Step 1. Tidy for publication

**Build**

- Fix one `.gitignore` line: ignoring the `.dagster/` directory also hides the
  `dagster.yaml` inside it, which should be tracked. Ignore `.dagster/*` and un-ignore the file.
- Move the seven planning documents into `docs/plans/` with a one-paragraph index saying
  which superseded which. The root then holds the README, the build files and the package.
- Delete the retired prototype, if you agree, and the parity test with it.
- Add `LICENSE`, and a `pyproject.toml` so `pip install -e .` works and the package carries a
  version, `1.1.0`, with dependencies taken from `requirements.txt`.
- Add two GitHub Actions workflows. `ci.yml` runs on every push: the unit tests, which need
  no data and skip the integration tests cleanly, and a Docker build. `build.yml` runs only
  when triggered by hand: a download-mode build inside the container, uploading the manifest,
  the dictionary and the check results as workflow artefacts, and the Parquet only if the
  redistribution decision above allows it.
- README: a short opening on what the table is and who it is for, a status line, how to
  cite it, and attribution to the three publishers as their licences require.
- Regenerate the dictionary and run the full suite.

**Done when**

- The tree is what a stranger sees first: README, package, docs, tests, build files.
- `pip install -e .` followed by `python -m pytest tests` passes in a fresh environment
  without any data present, with the integration tests skipped and reported as skipped.

## Step 2. Create the repository and push

```bash
git init -b main
git add -A
git commit -m "Postcode-SIMD reference table, v1.1.0"
git tag -a v1.1.0 -m "First public release"
gh repo create mtinti/postcode-simd --public --source . --push --description "..."
git push --tags
```

Commits I make carry a co-author trailer naming the model, as this session requires. If
you would rather the first commit were yours alone, run the four git commands yourself and I
will do the rest.

**Done when**

- The repository exists under your account with the tag, and a fresh clone builds the image
  and passes the unit tests.

## Step 3. Set up what runs there

- Confirm `ci.yml` is green on the first push.
- Create the GitHub release `v1.1.0` from the tag, attaching `manifest.json` and
  `DATA_DICTIONARY.md`, so the hashes of the release build are recorded where a reader of
  the code will look.
- Set the repository description and topics: `simd`, `deprivation`, `scotland`,
  `postcodes`, `dagster`, `public-health`.
- Optionally run `build.yml` once by hand to show that a clean GitHub runner reproduces the
  rows-only fingerprint recorded in the release.

**Done when**

- The release page shows the tag, the manifest and the dictionary, and CI has run on `main`.

## What stays out of the repository

`manual_data/`, `data/`, `results/`, `out/` and the Dagster instance's history and storage.
The repository holds the means to reproduce the table and the record of how it was built,
not the table. Anyone who clones it and runs `docker compose run --rm build` gets the same
file, hash for hash, which is the point.
