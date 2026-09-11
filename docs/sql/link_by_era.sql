-- Attach SIMD to events by era, following the PHS deprivation guidance for analysts v3.5:
-- each event takes the edition recommended for its year (table 4) and the directory record
-- valid on its date. Same rules as simd_ingest.lookup.attach_by_era, and tested to agree with it.
--
-- Inputs:  events(id, postcode, event_date)      one row per event; postcode as written
--          postcode_simd                          the v1 table, as a table or a view
-- Output:  one row per event: simd_edition, simd_status, simd_value, simd_pc_norm
--
-- Runs unchanged on DuckDB and SQL Server. On DuckDB, expose the file first:
--     CREATE VIEW postcode_simd AS SELECT * FROM 'results/postcode_simd.parquet';
--
-- The measure is the PHS population-weighted within-Scotland quintile, 1 = most deprived.
-- To change it, edit the six lines of the CASE that picks the column. PO boxes are excluded
-- by default, following the PHS guidance; see the predicate on the join.

WITH era AS (
    SELECT * FROM (VALUES (1996, 2003, '2004'), (2004, 2006, '2006'), (2007, 2009, '2009v2'),
                          (2010, 2013, '2012'), (2014, 2016, '2016'), (2017, 9999, '2020v2'))
           AS v(year_from, year_to, edition)
),
ev AS (
    -- The same normalisation as pc_norm: uppercase, ASCII spaces removed.
    SELECT e.id, e.event_date, UPPER(REPLACE(e.postcode, ' ', '')) AS pc_key, era.edition
    FROM events e
    LEFT JOIN era ON YEAR(e.event_date) BETWEEN era.year_from AND era.year_to
),
matched AS (
    -- An ordinary postcode matches every record whose base it is: an old unsplit life and
    -- the current split parts. A full NRS key with a suffix also matches its own part.
    SELECT ev.id, ev.event_date, ev.edition, ev.pc_key,
           p.pc_norm, p.pc_base,
           CASE WHEN p.pc_norm = ev.pc_key AND p.pc_norm <> p.pc_base THEN 1 ELSE 0 END AS is_part,
           CASE WHEN p.introduced_on <= ev.event_date
                 AND (p.deleted_on IS NULL OR p.deleted_on > ev.event_date) THEN 1 ELSE 0 END AS is_valid,
           CASE ev.edition
               WHEN '2004'   THEN p.simd2004_pw_scotland_quintile
               WHEN '2006'   THEN p.simd2006_pw_scotland_quintile
               WHEN '2009v2' THEN p.simd2009v2_pw_scotland_quintile
               WHEN '2012'   THEN p.simd2012_pw_scotland_quintile
               WHEN '2016'   THEN p.simd2016_pw_scotland_quintile
               WHEN '2020v2' THEN p.simd2020v2_pw_scotland_quintile
           END AS value
    FROM ev
    LEFT JOIN postcode_simd p
           ON (p.pc_base = ev.pc_key OR (p.pc_norm = ev.pc_key AND p.pc_norm <> p.pc_base))
          -- PHS practice: no deprivation for PO boxes and other unlinked large-user postcodes.
          -- Delete the next line to attach whatever the directory assigns them.
          AND (p.LinkedSmallUserPostcode IS NULL OR p.LinkedSmallUserPostcode NOT IN ('NO LINKP', 'NO LINK'))
),
scoped AS (
    -- A full NRS key selects its own split part only.
    SELECT * FROM (SELECT m.*, MAX(is_part) OVER (PARTITION BY id) AS any_part FROM matched m) x
    WHERE any_part = 0 OR is_part = 1
),
summary AS (
    SELECT id,
           MIN(event_date) AS event_date,
           MIN(edition)    AS edition,
           COUNT(pc_norm)  AS n_known,
           SUM(is_valid)   AS n_valid,
           COUNT(DISTINCT CASE WHEN is_valid = 1 THEN value END)   AS n_values,
           MIN(CASE WHEN is_valid = 1 THEN value END)              AS value,
           MIN(CASE WHEN is_valid = 1 THEN pc_norm END)            AS pc_norm
    FROM scoped
    GROUP BY id
)
SELECT id, event_date, edition AS simd_edition,
       CASE WHEN edition IS NULL THEN 'no_edition'       -- before 1996: Carstairs territory
            WHEN n_known = 0     THEN 'not_found'
            WHEN n_valid = 0     THEN 'deleted'          -- known postcode, nothing valid that day
            WHEN n_valid = 1     THEN 'unique'
            WHEN n_values = 1    THEN 'split_consensus'  -- several parts, one value
            ELSE                      'split_conflict'   -- several parts, different values
       END AS simd_status,
       CASE WHEN n_valid = 1 OR (n_valid > 1 AND n_values = 1) THEN value END AS simd_value,
       -- No edition means no SIMD answer at all, so the matched key is withheld too. An as-of
       -- lookup without an edition still finds the record if that is what you need.
       CASE WHEN n_valid = 1 AND edition IS NOT NULL THEN pc_norm END AS simd_pc_norm
FROM summary
ORDER BY id;
