-- A short, readable version of link_as_of.sql, for reviewing the logic before trusting it.
--
-- Same steps, same rules, but it returns only the rank, both publishers' within-Scotland
-- quintile and decile, and the urban-rural classification, so the whole thing fits on a screen
-- or two. link_as_of.sql is the complete query: it returns all fourteen measures, the bands
-- within health board, partnership and council area, and every original postcode field, and it
-- is generated from the output schema so it cannot drift from the table. Use this one to check
-- that the logic is what you want, and that one to produce values.
--
-- Input: one row per event, with the postcode recorded for it and the date that postcode was
-- the person's address. For SMR01 both come from the episode: POSTCODE and ADMISSION_DATE.
-- That one date does two jobs: it picks the postcode life, and its year picks the SIMD edition.
-- Output: one row per input row. Nothing is ever dropped; a row that cannot be resolved comes
-- back with a status saying why and no SIMD.
--
-- Reads postcode_simd_history, one row per postcode life, key (pc_norm, introduced_on).
-- Qualify the table name if it is not in your default schema.

WITH input AS (
    -- STEP 1. The cohort. EDIT THESE THREE ROWS, or replace the whole block with a select from
    -- your own table, for example
    --   SELECT LINK_NO, POSTCODE, CAST(ADMISSION_DATE AS date), CAST(NULL AS int)
    --   FROM ISD_SMR.dbo.SMR01
    --
    -- id             anything identifying the row; it is returned untouched
    -- postcode       as written, with or without the space
    -- address_date   the date that postcode was this person's address
    -- analysis_year  leave NULL and the SIMD edition comes from the year of the address date,
    --                which is what a single event date means. Set it only to force one
    --                edition, as row 3 does.
    --
    -- Row 1 reads the data zone this postcode had in 2005, not the one it has now. Row 2 is
    -- the ordinary case, and the two publishers put it in different bands: quintile 3 weighted
    -- by population, 4 by data zone. Row 3 needs its override, because deriving would give
    -- 1975 and SIMD did not exist then.
    SELECT * FROM (VALUES
        (1, 'AB11 5FA', CAST('2005-06-10' AS date), CAST(NULL AS int)),
        (2, 'AB21 0SB', CAST('2015-06-01' AS date), CAST(NULL AS int)),
        (3, 'FK17 8DS', CAST('1975-06-01' AS date), 2020)
    ) AS v(id, postcode, address_date, analysis_year)
),
request AS (
    -- STEP 2. The join key: uppercase, remove spaces, keep the original text. This is the rule
    -- the table itself was built with, so the two agree. Nothing is repaired and no A/B/C
    -- suffix is stripped: a postcode that is wrong must fail to match rather than quietly
    -- match something else.
    -- analysis_year is settled here so the rest of the query has one year to work with.
    SELECT id, postcode, address_date,
           COALESCE(analysis_year, YEAR(address_date)) AS analysis_year,
           NULLIF(UPPER(REPLACE(postcode, ' ', '')), '') AS postcode_key
    FROM input
),
era AS (
    -- STEP 3. PHS deprivation guidance v3.5, Table 4, printed page 17. The year of the health
    -- data chooses the SIMD edition, and the edition fixes the data-zone vintage to read it
    -- through. Before 1996 there is no SIMD and the guidance points to Carstairs instead.
    -- That year comes from the address date, which for an episode is the year of the event, so
    -- each row gets the edition current when it happened. Section 3.2.1.2 of the guidance
    -- describes the other option: to compare across a long period on one fixed classification,
    -- pass a constant analysis_year for every row and it overrides the derived one. The value
    -- reported below is whichever year was actually used.
    SELECT * FROM (VALUES
        (1996, 2003, '2004',   2001),
        (2004, 2006, '2006',   2001),
        (2007, 2009, '2009v2', 2001),
        (2010, 2013, '2012',   2001),
        (2014, 2016, '2016',   2011),
        (2017, 9999, '2020v2', 2011)
    ) AS v(year_from, year_to, edition, dz_vintage)
),
rurality_era AS (
    -- STEP 3b. The same year also chooses the Urban Rural Classification version. This one is a
    -- PROJECT CHOICE: PHS publishes no table for it. A version is chosen by its reference
    -- year, the year it describes, not by when it was published: the 2022 version describes
    -- Census Day 2022 and appeared in December 2024. It applies until the next version's year.
    SELECT * FROM (VALUES
        (2003, 2004, '2003-2004'),
        (2005, 2006, '2005-2006'),
        (2007, 2008, '2007-2008'),
        (2009, 2010, '2009-2010'),
        (2011, 2012, '2011-2012'),
        (2013, 2015, '2013-2014'),
        (2016, 2019, '2016'),
        (2020, 2021, '2020'),
        (2022, 9999, '2022')
    ) AS v(year_from, year_to, version)
),
chosen AS (
    SELECT r.id, r.postcode, r.postcode_key, r.address_date, r.analysis_year,
           e.edition, e.dz_vintage, u.version AS rurality_version
    FROM request r
    LEFT JOIN era e ON r.analysis_year BETWEEN e.year_from AND e.year_to
    LEFT JOIN rurality_era u ON r.analysis_year BETWEEN u.year_from AND u.year_to
),
lives AS (
    -- STEP 4. The postcode life that was in force on the address date. A life runs from
    -- introduced_on up to but NOT including deleted_on, so a record deleted that day is not
    -- valid on it. This is the step that matters: a postcode can be retired and later reissued
    -- somewhere else entirely, and taking the latest life instead would give a 1975 address the
    -- data zone of a place the patient never lived.
    SELECT c.id, c.address_date,
           p.pc_norm, p.pc_base, p.introduced_on, p.deleted_on, p.is_current,
           -- The NRS split suffix: '' for a whole postcode, else A, B or C. Taken from the key
           -- and its base, not the last character: whole postcodes end in A, B and C too.
           SUBSTRING(p.pc_norm, LEN(p.pc_base) + 1, 10) AS part,
           p.spd_user_type, p.LinkedSmallUserPostcode,
           -- Rurality travels with the matched record itself, not with the data zone: see the
           -- note at the end of step 6. The two 2022 codes are what NRS publishes; the rest are
           -- every version placed from this record's own grid reference, with the reason a
           -- version has no code.
           p.UrbanRural6Fold2022Code, p.UrbanRural8Fold2022Code,
           p.urbanrural2003_2004_6fold, p.urbanrural2003_2004_8fold, p.urbanrural2003_2004_status,
           p.urbanrural2005_2006_6fold, p.urbanrural2005_2006_8fold, p.urbanrural2005_2006_status,
           p.urbanrural2007_2008_6fold, p.urbanrural2007_2008_8fold, p.urbanrural2007_2008_status,
           p.urbanrural2009_2010_6fold, p.urbanrural2009_2010_8fold, p.urbanrural2009_2010_status,
           p.urbanrural2011_2012_6fold, p.urbanrural2011_2012_8fold, p.urbanrural2011_2012_status,
           p.urbanrural2013_2014_6fold, p.urbanrural2013_2014_8fold, p.urbanrural2013_2014_status,
           p.urbanrural2016_6fold, p.urbanrural2016_8fold, p.urbanrural2016_status,
           p.urbanrural2020_6fold, p.urbanrural2020_8fold, p.urbanrural2020_status,
           p.urbanrural2022_6fold, p.urbanrural2022_8fold, p.urbanrural2022_status
    FROM chosen c
    JOIN postcode_simd_history p
      ON p.pc_base = c.postcode_key
     AND p.introduced_on <= c.address_date
     AND (p.deleted_on IS NULL OR p.deleted_on > c.address_date)
),
ranked AS (
    -- STEP 5. A postcode that straddles a boundary is held by NRS as separate A, B and C parts,
    -- each with its own data zone. The input has no suffix, so something must choose. PHS uses
    -- the A part, because it holds more addresses. Rank the whole record as A, so whole and A
    -- tie and the newest wins between them; then B, then C; then the newest. Only a whole
    -- record or an A part carries a value (step 6), so the B-then-C order decides which part
    -- is reported as matched, not which value is used. NRS introduces and retires the parts
    -- together: no date in the current directory has a B or C part valid without A. Count the
    -- candidates as well, so an unresolvable tie is reported rather than settled arbitrarily.
    SELECT l.*,
           ROW_NUMBER() OVER (PARTITION BY l.id
               ORDER BY CASE WHEN l.part = '' THEN 'A' ELSE l.part END,
                        l.introduced_on DESC, l.pc_norm) AS preference,
           COUNT(*) OVER (PARTITION BY l.id) AS candidates
    FROM lives l
),
matched AS (
    SELECT * FROM ranked WHERE preference = 1
),
bounds AS (
    -- When no life covers the date, say where the date falls rather than only that it failed:
    -- before the postcode existed, in a gap between two lives, or after it was retired. That
    -- turns a linkage failure into a reviewable finding about the address.
    SELECT c.id,
           MIN(p.introduced_on) AS first_introduced_on,
           MIN(CASE WHEN p.introduced_on > c.address_date THEN p.introduced_on END) AS next_life,
           MAX(CASE WHEN p.deleted_on <= c.address_date THEN p.deleted_on END)      AS previous_end
    FROM chosen c
    JOIN postcode_simd_history p ON p.pc_base = c.postcode_key
    GROUP BY c.id
),
source AS (
    -- STEP 6. A large-user postcode is a single address with no boundary of its own, so it has
    -- no data zone to speak of. PHS Appendix A, printed page 30, takes the geography from the
    -- small-user postcode NRS linked it to, and gives none to a PO box. The linked record must
    -- itself be valid on the same date. Never fall back to the large user's own zone, and never
    -- follow a link to another large user. An ambiguous postcode and a B or C part supply no
    -- geography at all, so their status and their empty values agree; the generated queries
    -- do the same.
    SELECT m.id,
           g.pc_norm       AS source_pc_norm,
           g.is_current    AS source_is_current,
           g.DataZone2001Code, g.DataZone2011Code,
           g.simd2004_rank, g.simd2006_rank, g.simd2009v2_rank,
           g.simd2012_rank, g.simd2016_rank, g.simd2020v2_rank,
           g.simd2004_pw_scotland_quintile, g.simd2006_pw_scotland_quintile,
           g.simd2009v2_pw_scotland_quintile, g.simd2012_pw_scotland_quintile,
           g.simd2016_pw_scotland_quintile, g.simd2020v2_pw_scotland_quintile,
           g.simd2004_pw_scotland_decile, g.simd2006_pw_scotland_decile,
           g.simd2009v2_pw_scotland_decile, g.simd2012_pw_scotland_decile,
           g.simd2016_pw_scotland_decile, g.simd2020v2_pw_scotland_decile,
           g.simd2004_uw_scotland_quintile, g.simd2006_uw_scotland_quintile,
           g.simd2009v2_uw_scotland_quintile, g.simd2012_uw_scotland_quintile,
           g.simd2016_uw_scotland_quintile, g.simd2020v2_uw_scotland_quintile,
           g.simd2004_uw_scotland_decile, g.simd2006_uw_scotland_decile,
           g.simd2009v2_uw_scotland_decile, g.simd2012_uw_scotland_decile,
           g.simd2016_uw_scotland_decile, g.simd2020v2_uw_scotland_decile
    FROM matched m
    LEFT JOIN postcode_simd_history g
      ON g.spd_user_type = 'small_user'
     AND g.pc_norm = CASE WHEN m.candidates > 1 AND m.part = '' THEN NULL
                          WHEN m.part NOT IN ('', 'A')           THEN NULL
                          WHEN m.spd_user_type = 'small_user'    THEN m.pc_norm
                          ELSE UPPER(REPLACE(m.LinkedSmallUserPostcode, ' ', '')) END
     AND g.introduced_on <= m.address_date
     AND (g.deleted_on IS NULL OR g.deleted_on > m.address_date)
)
-- STEP 7 and 8. Report. The values come from the record that supplied the geography, read
-- through the data zone of the edition's own vintage: 2001 zones for SIMD 2004 to 2012, 2011
-- zones for 2016 and 2020v2. Nothing is recalculated. Band 1 is the most deprived in every
-- edition, because ingestion already turned the 2004 and 2006 bands the right way round.
-- postcode_status says what happened to the postcode; simd_status says whether the numbers can
-- be used. Only matched, a_part and linked_small_user carry a value.
--
-- Two bandings are returned because the publishers band the same ranks differently. PHS splits
-- them so each band holds a fifth or a tenth of the POPULATION, and its guidance expects those
-- for health analysis. The Scottish Government splits the DATA ZONES themselves, equal counts
-- of zones, which is what SIMD's own published files carry. They disagree for many postcodes,
-- so report which one you used and never mix them in one measure.
--
-- Rurality is the Scottish Government Urban Rural Classification, twice. rurality_6fold and
-- rurality_8fold are the version step 3b chose for the year, placed from this record's own
-- grid reference in that version's polygons, so a 2005 address is described as it was
-- classified then. UrbanRural6Fold2022Code and its 8-fold are the 2022 codes NRS publishes,
-- whatever the year, kept so the two can be compared. rurality_status says why the chosen
-- version has no code: a postcode problem, no version for the year, a point outside every
-- polygon, or a PO box, whose grid reference is the sorting office. All of it comes from the
-- matched record itself rather than the record that supplied the data zone, so a large user
-- reports its own location. Read it beside matched_user_type.
SELECT c.id, c.postcode, c.address_date, c.analysis_year, c.edition AS simd_edition,
       CASE
           WHEN c.postcode_key IS NULL                   THEN 'missing_postcode'
           WHEN b.first_introduced_on IS NULL            THEN 'not_found'
           WHEN m.id IS NULL AND c.address_date IS NULL  THEN 'missing_address_date'
           WHEN m.id IS NULL AND c.address_date < b.first_introduced_on
                                                         THEN 'postcode_not_yet_introduced'
           WHEN m.id IS NULL AND b.next_life IS NOT NULL THEN 'between_lives'
           WHEN m.id IS NULL                             THEN 'postcode_deleted_by_date'
           WHEN m.candidates > 1 AND m.part = ''         THEN 'ambiguous_postcode'
           WHEN m.part NOT IN ('', 'A')                  THEN 'split_a_missing'
           WHEN m.spd_user_type = 'large_user'
                AND UPPER(REPLACE(COALESCE(m.LinkedSmallUserPostcode, ''), ' ', '')) = 'NOLINKP'
                                                         THEN 'po_box'
           WHEN m.spd_user_type = 'large_user'
                AND UPPER(REPLACE(COALESCE(m.LinkedSmallUserPostcode, ''), ' ', '')) IN ('', 'NOLINK')
                                                         THEN 'unlinked_large_user'
           WHEN s.source_pc_norm IS NULL                 THEN 'linked_small_user_not_found'
           WHEN m.spd_user_type = 'large_user'            THEN 'linked_small_user'
           WHEN m.part = 'A'                             THEN 'a_part'
           ELSE 'matched'
       END AS postcode_status,
       m.pc_norm       AS matched_pc_norm,
       m.introduced_on AS matched_introduced_on,
       m.is_current    AS matched_is_current,
       m.spd_user_type AS matched_user_type,
       s.source_pc_norm AS simd_source_pc_norm,
       CASE c.dz_vintage WHEN 2001 THEN s.DataZone2001Code
                         WHEN 2011 THEN s.DataZone2011Code END AS data_zone_code,
       CASE c.edition WHEN '2004'   THEN s.simd2004_rank
                      WHEN '2006'   THEN s.simd2006_rank
                      WHEN '2009v2' THEN s.simd2009v2_rank
                      WHEN '2012'   THEN s.simd2012_rank
                      WHEN '2016'   THEN s.simd2016_rank
                      WHEN '2020v2' THEN s.simd2020v2_rank END AS simd_rank,
       CASE c.edition WHEN '2004'   THEN s.simd2004_pw_scotland_quintile
                      WHEN '2006'   THEN s.simd2006_pw_scotland_quintile
                      WHEN '2009v2' THEN s.simd2009v2_pw_scotland_quintile
                      WHEN '2012'   THEN s.simd2012_pw_scotland_quintile
                      WHEN '2016'   THEN s.simd2016_pw_scotland_quintile
                      WHEN '2020v2' THEN s.simd2020v2_pw_scotland_quintile END AS phs_pw_scotland_quintile,
       CASE c.edition WHEN '2004'   THEN s.simd2004_pw_scotland_decile
                      WHEN '2006'   THEN s.simd2006_pw_scotland_decile
                      WHEN '2009v2' THEN s.simd2009v2_pw_scotland_decile
                      WHEN '2012'   THEN s.simd2012_pw_scotland_decile
                      WHEN '2016'   THEN s.simd2016_pw_scotland_decile
                      WHEN '2020v2' THEN s.simd2020v2_pw_scotland_decile END AS phs_pw_scotland_decile,
       CASE c.edition WHEN '2004'   THEN s.simd2004_uw_scotland_quintile
                      WHEN '2006'   THEN s.simd2006_uw_scotland_quintile
                      WHEN '2009v2' THEN s.simd2009v2_uw_scotland_quintile
                      WHEN '2012'   THEN s.simd2012_uw_scotland_quintile
                      WHEN '2016'   THEN s.simd2016_uw_scotland_quintile
                      WHEN '2020v2' THEN s.simd2020v2_uw_scotland_quintile END AS gov_uw_scotland_quintile,
       CASE c.edition WHEN '2004'   THEN s.simd2004_uw_scotland_decile
                      WHEN '2006'   THEN s.simd2006_uw_scotland_decile
                      WHEN '2009v2' THEN s.simd2009v2_uw_scotland_decile
                      WHEN '2012'   THEN s.simd2012_uw_scotland_decile
                      WHEN '2016'   THEN s.simd2016_uw_scotland_decile
                      WHEN '2020v2' THEN s.simd2020v2_uw_scotland_decile END AS gov_uw_scotland_decile,
       c.rurality_version,
       CASE WHEN m.candidates > 1 AND m.part = '' THEN NULL WHEN m.part NOT IN ('', 'A') THEN NULL ELSE
           CASE c.rurality_version WHEN '2003-2004' THEN m.urbanrural2003_2004_6fold
                                             WHEN '2005-2006' THEN m.urbanrural2005_2006_6fold
                                             WHEN '2007-2008' THEN m.urbanrural2007_2008_6fold
                                             WHEN '2009-2010' THEN m.urbanrural2009_2010_6fold
                                             WHEN '2011-2012' THEN m.urbanrural2011_2012_6fold
                                             WHEN '2013-2014' THEN m.urbanrural2013_2014_6fold
                                             WHEN '2016' THEN m.urbanrural2016_6fold
                                             WHEN '2020' THEN m.urbanrural2020_6fold
                                             WHEN '2022' THEN m.urbanrural2022_6fold END END AS rurality_6fold,
       CASE WHEN m.candidates > 1 AND m.part = '' THEN NULL WHEN m.part NOT IN ('', 'A') THEN NULL ELSE
           CASE c.rurality_version WHEN '2003-2004' THEN m.urbanrural2003_2004_8fold
                                             WHEN '2005-2006' THEN m.urbanrural2005_2006_8fold
                                             WHEN '2007-2008' THEN m.urbanrural2007_2008_8fold
                                             WHEN '2009-2010' THEN m.urbanrural2009_2010_8fold
                                             WHEN '2011-2012' THEN m.urbanrural2011_2012_8fold
                                             WHEN '2013-2014' THEN m.urbanrural2013_2014_8fold
                                             WHEN '2016' THEN m.urbanrural2016_8fold
                                             WHEN '2020' THEN m.urbanrural2020_8fold
                                             WHEN '2022' THEN m.urbanrural2022_8fold END END AS rurality_8fold,
       CASE
           WHEN m.id IS NULL AND c.postcode_key IS NULL            THEN 'missing_postcode'
           WHEN m.id IS NULL AND b.first_introduced_on IS NULL     THEN 'not_found'
           WHEN m.id IS NULL AND c.address_date IS NULL            THEN 'missing_address_date'
           WHEN m.id IS NULL AND c.address_date < b.first_introduced_on THEN 'postcode_not_yet_introduced'
           WHEN m.id IS NULL AND b.next_life IS NOT NULL           THEN 'between_lives'
           WHEN m.id IS NULL                                       THEN 'postcode_deleted_by_date'
           WHEN m.candidates > 1 AND m.part = ''                   THEN 'ambiguous_postcode'
           WHEN m.part NOT IN ('', 'A')                            THEN 'split_a_missing'
           WHEN c.rurality_version IS NULL AND c.analysis_year IS NULL THEN 'missing_year'
           WHEN c.rurality_version IS NULL AND c.analysis_year < 2003  THEN 'before_first_version'
           WHEN c.rurality_version IS NULL                         THEN 'invalid_year'
           ELSE COALESCE(
           CASE c.rurality_version WHEN '2003-2004' THEN m.urbanrural2003_2004_status
                                             WHEN '2005-2006' THEN m.urbanrural2005_2006_status
                                             WHEN '2007-2008' THEN m.urbanrural2007_2008_status
                                             WHEN '2009-2010' THEN m.urbanrural2009_2010_status
                                             WHEN '2011-2012' THEN m.urbanrural2011_2012_status
                                             WHEN '2013-2014' THEN m.urbanrural2013_2014_status
                                             WHEN '2016' THEN m.urbanrural2016_status
                                             WHEN '2020' THEN m.urbanrural2020_status
                                             WHEN '2022' THEN m.urbanrural2022_status END, 'matched')
       END AS rurality_status,
       m.UrbanRural6Fold2022Code,
       m.UrbanRural8Fold2022Code,
       CASE m.UrbanRural6Fold2022Code
           WHEN '1' THEN 'Large urban area'      WHEN '2' THEN 'Other urban area'
           WHEN '3' THEN 'Accessible small town' WHEN '4' THEN 'Remote small town'
           WHEN '5' THEN 'Accessible rural'      WHEN '6' THEN 'Remote rural' END AS published_2022_6fold_label,
       '1 = most deprived; phs_* weighted by population, gov_* by data zone; within Scotland' AS band_convention
FROM chosen c
LEFT JOIN matched m ON m.id = c.id
LEFT JOIN bounds  b ON b.id = c.id
LEFT JOIN source  s ON s.id = c.id;
