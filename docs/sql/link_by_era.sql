-- VERSION 2: latest postcode geography, SIMD edition chosen by EVENT YEAR.
-- Run create_latest_postcode_lookup.sql first. Input: events(id, postcode, event_date).
-- event_date must be DATE (or TIMESTAMP); reject invalid date text before this query.
-- Repeated/null IDs and duplicate input rows are retained: there is no grouping by id.
--
-- PHS v3.5 section 3.2.1.1: use the appropriate SIMD release for each period.
-- IMPORTANT: the date chooses SIMD, NOT a historical postcode life. Both examples
-- use the SAME latest-postcode/linked-small-user view. See ../LINKAGE_BY_ERA.md.

WITH era AS (
    -- 1. PHS v3.5, Table 4 (printed page 17), transcribed without interpolation.
    -- This is a reviewed recommendation, not automatic "latest edition" detection.
    SELECT * FROM (VALUES
        (1996, 2003, '2004'),
        (2004, 2006, '2006'),
        (2007, 2009, '2009v2'),
        (2010, 2013, '2012'),
        (2014, 2016, '2016'),
        (2017, 9999, '2020v2')
    ) AS v(year_from, year_to, edition)
),
matched AS (
    -- 2. Choose the edition by year and match the ordinary postcode once.
    -- LEFT JOINs retain missing dates, pre-1996 events and unmatched postcodes.
    SELECT e.id, e.postcode, e.event_date,
           NULLIF(UPPER(REPLACE(e.postcode, ' ', '')), '') AS postcode_key,
           era.edition AS simd_edition,
           p.postcode_status,
           p.matched_pc_norm, p.matched_introduced_on,
           p.matched_is_current, p.matched_user_type,
           p.simd_source_pc_norm, p.simd_source_introduced_on,
           p.simd_source_is_current, p.spd_release,
           -- 3. Select the already-attached PHS quintile for that edition.
           -- The CLI used the correct data-zone vintage and reversed early bands.
           CASE era.edition
               WHEN '2004'   THEN p.simd2004_pw_scotland_quintile
               WHEN '2006'   THEN p.simd2006_pw_scotland_quintile
               WHEN '2009v2' THEN p.simd2009v2_pw_scotland_quintile
               WHEN '2012'   THEN p.simd2012_pw_scotland_quintile
               WHEN '2016'   THEN p.simd2016_pw_scotland_quintile
               WHEN '2020v2' THEN p.simd2020v2_pw_scotland_quintile
           END AS simd_value
    FROM events e
    LEFT JOIN era ON YEAR(e.event_date) BETWEEN era.year_from AND era.year_to
    LEFT JOIN simd_postcode_latest p
           ON p.pc_base = NULLIF(UPPER(REPLACE(e.postcode, ' ', '')), '')
)
-- 4. Report the result and retain both record keys so the route can be reviewed.
-- Missing date is distinct from "no recommended SIMD before 1996".
-- Postcode provenance may remain present even when no SIMD edition can be selected.
SELECT id, postcode, event_date, simd_edition,
       'PHS population-weighted within-Scotland quintile; 1 = most deprived' AS simd_measure,
       CASE
           WHEN event_date IS NULL THEN 'missing_date'
           WHEN simd_edition IS NULL THEN 'no_edition'
           WHEN postcode_key IS NULL THEN 'missing_postcode'
           WHEN postcode_status IS NULL THEN 'not_found'
           WHEN postcode_status NOT IN ('matched', 'a_part', 'linked_small_user') THEN postcode_status
           WHEN simd_value IS NULL THEN 'missing_simd'
           ELSE postcode_status
       END AS simd_status,
       simd_value,
       matched_pc_norm, matched_introduced_on, matched_is_current, matched_user_type,
       simd_source_pc_norm, simd_source_introduced_on, simd_source_is_current,
       spd_release
FROM matched;
