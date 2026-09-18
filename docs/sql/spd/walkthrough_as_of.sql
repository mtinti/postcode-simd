-- A short, readable version of link_as_of.sql, for reviewing the logic before trusting it.
--
-- Same steps, same rules, but it returns only the rank and the two within-Scotland bands, so
-- the whole thing fits on a screen or two. link_as_of.sql is the complete query: it returns
-- all fourteen measures, the local PHS geography and every original postcode field, and it is
-- generated from the output schema so it cannot drift from the table. Use this one to check
-- that the logic is what you want, and that one to produce values.
--
-- Input: one row per event, with the postcode recorded for it and the date that postcode was
-- the person's address. For SMR01 both come from the episode: POSTCODE and ADMISSION_DATE.
-- Output: one row per input row. Nothing is ever dropped; a row that cannot be resolved comes
-- back with a status saying why and no SIMD.
--
-- Reads postcode_simd_history, one row per postcode life, key (pc_norm, introduced_on).
-- Qualify the table name if it is not in your default schema.

WITH input AS (
    -- STEP 1. The cohort. EDIT THIS. Replace it with a select from your own table, for example
    --   SELECT LINK_NO, POSTCODE, CAST(ADMISSION_DATE AS date), YEAR(ADMISSION_DATE)
    --   FROM ISD_SMR.dbo.SMR01
    SELECT 1 AS id, CAST('FK17 8DS' AS varchar(32)) AS postcode,
           CAST('1975-06-01' AS date) AS address_date, 2020 AS analysis_year
),
request AS (
    -- STEP 2. The join key: uppercase, remove spaces, keep the original text. This is the rule
    -- the table itself was built with, so the two agree. Nothing is repaired and no A/B/C
    -- suffix is stripped: a postcode that is wrong must fail to match rather than quietly
    -- match something else.
    SELECT id, postcode, address_date, analysis_year,
           NULLIF(UPPER(REPLACE(postcode, ' ', '')), '') AS postcode_key
    FROM input
),
era AS (
    -- STEP 3. PHS deprivation guidance v3.5, Table 4, printed page 17. The year of the health
    -- data chooses the SIMD edition, and the edition fixes the data-zone vintage to read it
    -- through. Before 1996 there is no SIMD and the guidance points to Carstairs instead.
    -- Pass one constant year for every row if you want a single edition throughout.
    SELECT * FROM (VALUES
        (1996, 2003, '2004',   2001),
        (2004, 2006, '2006',   2001),
        (2007, 2009, '2009v2', 2001),
        (2010, 2013, '2012',   2001),
        (2014, 2016, '2016',   2011),
        (2017, 9999, '2020v2', 2011)
    ) AS v(year_from, year_to, edition, dz_vintage)
),
chosen AS (
    SELECT r.id, r.postcode, r.postcode_key, r.address_date, r.analysis_year,
           e.edition, e.dz_vintage
    FROM request r
    LEFT JOIN era e ON r.analysis_year BETWEEN e.year_from AND e.year_to
),
lives AS (
    -- STEP 4. The postcode life that was in force on the address date. A life runs from
    -- introduced_on up to but NOT including deleted_on, so a record deleted that day is not
    -- valid on it. This is the step that matters: a postcode can be retired and later reissued
    -- somewhere else entirely, and taking the latest life instead would give a 1975 address the
    -- data zone of a place the patient never lived.
    SELECT c.id, c.address_date,
           p.pc_norm, p.pc_base, p.introduced_on, p.deleted_on, p.is_current,
           p.spd_user_type, p.LinkedSmallUserPostcode
    FROM chosen c
    JOIN postcode_simd_history p
      ON p.pc_base = c.postcode_key
     AND p.introduced_on <= c.address_date
     AND (p.deleted_on IS NULL OR p.deleted_on > c.address_date)
),
ranked AS (
    -- STEP 5. A postcode that straddles a boundary is held by NRS as separate A, B and C parts,
    -- each with its own data zone. The input has no suffix, so something must choose. PHS uses
    -- the A part, because it holds more addresses. Prefer the whole record or the A part, then
    -- the newest. Count the candidates as well, so an unresolvable tie is reported rather than
    -- settled arbitrarily.
    SELECT l.*,
           ROW_NUMBER() OVER (PARTITION BY l.id
               ORDER BY CASE WHEN l.pc_norm = l.pc_base OR RIGHT(l.pc_norm, 1) = 'A'
                             THEN 0 ELSE 1 END,
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
    -- follow a link to another large user.
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
           g.simd2016_pw_scotland_decile, g.simd2020v2_pw_scotland_decile
    FROM matched m
    LEFT JOIN postcode_simd_history g
      ON g.spd_user_type = 'small_user'
     AND g.pc_norm = CASE WHEN m.spd_user_type = 'small_user' THEN m.pc_norm
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
SELECT c.id, c.postcode, c.address_date, c.analysis_year, c.edition AS simd_edition,
       CASE
           WHEN c.postcode_key IS NULL                   THEN 'missing_postcode'
           WHEN b.first_introduced_on IS NULL            THEN 'not_found'
           WHEN m.id IS NULL AND c.address_date IS NULL  THEN 'missing_address_date'
           WHEN m.id IS NULL AND c.address_date < b.first_introduced_on
                                                         THEN 'postcode_not_yet_introduced'
           WHEN m.id IS NULL AND b.next_life IS NOT NULL THEN 'between_lives'
           WHEN m.id IS NULL                             THEN 'postcode_deleted_by_date'
           WHEN m.candidates > 1 AND m.pc_norm = m.pc_base THEN 'ambiguous_postcode'
           WHEN m.pc_norm <> m.pc_base AND RIGHT(m.pc_norm, 1) <> 'A' THEN 'split_a_missing'
           WHEN m.spd_user_type = 'large_user'
                AND UPPER(REPLACE(COALESCE(m.LinkedSmallUserPostcode, ''), ' ', '')) = 'NOLINKP'
                                                         THEN 'po_box'
           WHEN m.spd_user_type = 'large_user'
                AND UPPER(REPLACE(COALESCE(m.LinkedSmallUserPostcode, ''), ' ', '')) IN ('', 'NOLINK')
                                                         THEN 'unlinked_large_user'
           WHEN s.source_pc_norm IS NULL                 THEN 'linked_small_user_not_found'
           WHEN m.spd_user_type = 'large_user'            THEN 'linked_small_user'
           WHEN m.pc_norm <> m.pc_base                    THEN 'a_part'
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
       '1 = most deprived, PHS population weighted, within Scotland' AS band_convention
FROM chosen c
LEFT JOIN matched m ON m.id = c.id
LEFT JOIN bounds  b ON b.id = c.id
LEFT JOIN source  s ON s.id = c.id;
