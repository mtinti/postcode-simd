-- DEFAULT SSPL SETUP: run once, then link_latest.sql or link_by_era.sql.
-- Input: postcode_simd, imported from the MAIN postcode_simd.parquet (key pc_norm).
-- Output: one row per whole postcode in simd_postcode_latest. No life selection is needed:
-- NRS already kept the latest life (including deleted records) and made splits whole on A.
-- For the SPD alternative, use create_latest_postcode_lookup_history.sql instead.
-- SQL Server: execute CREATE VIEW in its own batch. See ../LINKAGE_BY_ERA.md.
--
-- NRS information note: latest life, whole postcodes, output-area-based allocation.
-- PHS v3.5 Appendix A: large users may link to small users. Following that link is our
-- explicit project choice, not proof of equivalence to a published PHS postcode lookup.

CREATE VIEW simd_postcode_latest AS
WITH postcodes AS (
    -- 1. Keep source fields intact; normalise the supplied large-user link once.
    SELECT p.*, UPPER(REPLACE(p.LinkedSmallUserPostcode, ' ', '')) AS link_key
    FROM postcode_simd p
),
small_user_targets AS (
    -- 2. Each small user is addressable by its whole key. A flagged split record also
    -- accepts its original A key, which NRS shortened when publishing SSPL.
    -- Validated whole postcode keys cannot collide with A-suffixed keys.
    -- No B/C aliases: those parts' geographies are unavailable in SSPL.
    SELECT p.pc_norm AS target_key, p.* FROM postcodes p WHERE p.spd_user_type = 'small_user'
    UNION ALL
    SELECT CONCAT(p.pc_norm, 'A') AS target_key, p.* FROM postcodes p
    WHERE p.spd_user_type = 'small_user' AND p.SplitIndicator = 'Y'
),
matched AS (
    -- 3. Small users supply their own geography. Large users use the named small user.
    -- Never follow a large-user target or fall back to SPD/own SIMD.
    SELECT p.*, g.pc_norm AS source_pc_norm, g.introduced_on AS source_introduced_on,
           g.is_current AS source_is_current,
           g.DataZone2001Code AS source_dz2001, g.DataZone2011Code AS source_dz2011,
           g.simd2004_pw_scotland_quintile AS q2004,
           g.simd2006_pw_scotland_quintile AS q2006,
           g.simd2009v2_pw_scotland_quintile AS q2009v2,
           g.simd2012_pw_scotland_quintile AS q2012,
           g.simd2016_pw_scotland_quintile AS q2016,
           g.simd2020v2_pw_scotland_quintile AS q2020v2
    FROM postcodes p
    LEFT JOIN small_user_targets g ON g.target_key = CASE
        WHEN p.spd_user_type = 'small_user' THEN p.pc_norm ELSE p.link_key END
)
SELECT pc_norm AS postcode_key,
       pc_norm AS matched_pc_norm, introduced_on AS matched_introduced_on,
       is_current AS matched_is_current, spd_user_type AS matched_user_type,
       'sspl' AS index_source, sspl_release AS index_release,
       'oa2022_centroid' AS allocation,
       LinkedSmallUserPostcode AS requested_link_postcode,
       -- 4. Make excluded and unresolved links visible. No value is invented.
       -- This includes B/C links: the SSPL cannot supply those split-part geographies.
       CASE
           WHEN spd_user_type = 'large_user' AND (link_key IS NULL OR link_key IN ('', 'NOLINKP', 'NOLINK'))
               THEN 'unlinked_large_user'
           WHEN source_pc_norm IS NULL THEN 'linked_small_user_not_found'
           WHEN spd_user_type = 'large_user' THEN 'linked_small_user'
           WHEN SplitIndicator = 'Y' THEN 'a_part'
           ELSE 'matched'
       END AS postcode_status,
       source_pc_norm AS simd_source_pc_norm,
       source_introduced_on AS simd_source_introduced_on,
       source_is_current AS simd_source_is_current,
       source_dz2001 AS simd_source_dz2001, source_dz2011 AS simd_source_dz2011,
       -- 5. These are already standardised PHS quintiles; do not reverse early bands again.
       q2004 AS simd2004_pw_scotland_quintile, q2006 AS simd2006_pw_scotland_quintile,
       q2009v2 AS simd2009v2_pw_scotland_quintile, q2012 AS simd2012_pw_scotland_quintile,
       q2016 AS simd2016_pw_scotland_quintile, q2020v2 AS simd2020v2_pw_scotland_quintile
FROM matched;
