# Column description editorial review

Reviewer: Codex (AI-assisted review). Date: 2 October 2026.
Commit: 4a40b6e538a149d87a3ab2f37665eae92c6ebb17.

## Outcome

Reviewed all 69 NRS description entries (176 dictionary-table variants) and all 48 SIMD glossary entries. I approve 67 NRS entries and all 48 glossary entries within their stated source scope. Two NRS entries need changes before approval. The repository's review flags were not changed.

All three source files match the SHA256 pins. An independent check of the DOCX and XLSX XML, without the project's extraction functions, found no missing entries or differences in the normalized type, range and literal description text. The Word numbering issue below is outside literal text and is therefore not detected by a text-equality check.

## Changes requested

### GridLinkPositionalAccuracy

The SPD dictionary numbers the eight status definitions, but the extraction drops the Word-generated numbers. The page presents a single paragraph containing “As for status value 1” without identifying the eight definitions. Restore the explicit code-to-description mapping in both SPD variants and preserve the PO-box qualification.

The source order is:

1. Automatically located inside the matched address building.
2. Building location established by visual inspection.
3. Approximate location within 50 metres.
4. Mean of matched addresses in the postcode, without snapping to a building.
5. Imputed from surrounding known postcodes.
6. Postcode sector mean, mainly PO boxes.
7. Terminated postcode; accuracy follows its status immediately before termination.
8. No coordinates available.

These are review paraphrases. Preserve the dictionary's wording when restoring the published definitions. The PO-box warning remains essential: a code of 1 can describe the sorting/delivery office instead of a residential address.

Source locator: SPD dictionary, Small User table row 67 and Large User table row 57, counting the header as row 1. Both use decimal numbering in the DOCX numbering definitions.

### PostcodeSector

The Large User dictionary declares Char(4), while the same entry gives EH10 4 as its example. The pinned LargeUser.csv contains sectors up to six characters; 46,661 of 51,004 records exceed four characters. This is a source-dictionary inconsistency, not a transcription error.

Keep the original declaration identifiable as a quotation, with an adjacent reviewer note explaining the discrepancy and pointing to the output's actual string/SQL export types. Do not change or truncate postcode data to fit the source dictionary. The neighboring PostcodeDistrict declaration is Char(6), while observed districts are at most four characters; that suggests the two lengths may have been swapped, but the cause is not confirmed.

Source locator: SPD dictionary, Large User table row 4, counting the header as row 1.

## Context retained during approval

- SPD Small User, SPD Large User and SSPL variants remain distinct, especially Postcode, SplitIndicator and LinkedSmallUserPostcode.
- The NRS dictionary types describe the source. The pipeline retains raw NRS columns as text; parsed and computed output columns have their own types.
- The SPD and SSPL dictionary introductions describe different geography allocation and postcode grains. SSPL combines split-postcode counts into a whole postcode and uses the A part as the representative; SPD retains individual lives and split parts. The shared short count descriptions do not replace that product-level context.
- The three Royal Mail count entries present in the full dictionaries are not columns in the pinned cut output; reviewing their text does not add them to the site.
- The SIMD glossary approval applies to 2020v2. Its descriptions can be identified as 2020v2 examples on earlier-edition pages, but they are not verification of those editions' indicator definitions.

## Validation

The current provenance suite passed all 28 tests, and the strict MkDocs build passed. These checks do not detect the two editorial issues above. No repository files were edited.

Detailed per-entry verdicts, source hashes, source row locators and comparison evidence are in [the JSON review record](2026-10-02-column-descriptions.json).
