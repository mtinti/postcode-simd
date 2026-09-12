-- SHARED SETUP: run once, then use link_latest.sql or link_by_era.sql.
-- Input: postcode_simd, the validated table produced by the ingestion CLI.
-- Output: one row per ordinary postcode in simd_postcode_latest.
--
-- Guidance references and project choices: ../LINKAGE_BY_ERA.md.
-- PHS postcode-file documentation: most recent postcode version; A part for splits.
-- PHS deprivation guidance v3.5, Appendix A: geography is needed; large users may
-- be linked to small users. We use that linked small-user geography, by explicit
-- project choice. Exact equivalence to a PHS postcode lookup is NOT established.
--
-- These are latest-postcode lookups, NOT historical address reconstruction.
-- Deleted postcodes are retained where they are the last known version.
-- Ordinary postcode inputs only: do not supply an NRS A/B/C suffix.
-- SQL Server: execute this CREATE VIEW in its own batch. See the guide for setup.

CREATE VIEW simd_postcode_latest AS
WITH full_key_versions AS (
    -- 1. Keep the newest life of each complete NRS key, across BOTH user types.
    -- A postcode can change from small to large user, or vice versa.
    -- Do this before excluding unlinked large users: never revive an older life.
    SELECT p.pc_norm, p.pc_base, p.introduced_on, p.is_current,
           p.spd_user_type, p.LinkedSmallUserPostcode, p.spd_release,
           p.DataZone2001Code, p.DataZone2011Code,
           p.simd2004_pw_scotland_quintile, p.simd2006_pw_scotland_quintile,
           p.simd2009v2_pw_scotland_quintile, p.simd2012_pw_scotland_quintile,
           p.simd2016_pw_scotland_quintile, p.simd2020v2_pw_scotland_quintile,
           ROW_NUMBER() OVER (
               PARTITION BY pc_norm ORDER BY introduced_on DESC
           ) AS version_number
    FROM postcode_simd p
),
latest_full_keys AS (
    SELECT * FROM full_key_versions WHERE version_number = 1
),
ordinary_postcode_priority AS (
    -- 2. Choose an ordinary-postcode representative.
    -- PHS says A is the representative split part. Never use B/C as a fallback.
    -- Project tie policy: prefer live records; then whole/A; then newest introduction.
    -- This handles unequal introduction dates on the parts of a live split postcode.
    -- If only B/C is live, keep it solely to report split_a_missing, not to use its SIMD.
    SELECT p.*,
           DENSE_RANK() OVER (
               PARTITION BY pc_base
               ORDER BY CASE WHEN is_current = 1 THEN 0 ELSE 1 END,
                        CASE WHEN pc_norm = pc_base OR RIGHT(pc_norm, 1) = 'A' THEN 0 ELSE 1 END,
                        introduced_on DESC
           ) AS postcode_priority
    FROM latest_full_keys p
),
best_candidates AS (
    -- 3. Do not turn an equally preferred pair into an arbitrary SIMD answer.
    -- A deterministic row is kept for reporting, but ties receive no geography.
    SELECT p.*,
           COUNT(*) OVER (PARTITION BY pc_base) AS candidate_count,
           ROW_NUMBER() OVER (PARTITION BY pc_base ORDER BY pc_norm) AS candidate_number
    FROM ordinary_postcode_priority p
    WHERE postcode_priority = 1
),
representatives AS (
    SELECT * FROM best_candidates WHERE candidate_number = 1
)
SELECT p.pc_base,
       p.pc_norm AS matched_pc_norm,
       p.introduced_on AS matched_introduced_on,
       p.is_current AS matched_is_current,
       p.spd_user_type AS matched_user_type,
       p.spd_release,
       CASE
           WHEN p.candidate_count > 1 THEN 'ambiguous_postcode'
           WHEN p.pc_norm <> p.pc_base AND RIGHT(p.pc_norm, 1) <> 'A' THEN 'split_a_missing'
           WHEN p.spd_user_type = 'large_user'
                AND (p.LinkedSmallUserPostcode IS NULL
                     OR UPPER(REPLACE(p.LinkedSmallUserPostcode, ' ', '')) IN ('', 'NOLINKP', 'NOLINK'))
               THEN 'unlinked_large_user'
           WHEN g.pc_norm IS NULL THEN 'linked_small_user_not_found'
           WHEN p.spd_user_type = 'large_user' THEN 'linked_small_user'
           WHEN p.pc_norm <> p.pc_base THEN 'a_part'
           ELSE 'matched'
       END AS postcode_status,
       -- 4. Keep the matched record separate from the record supplying geography.
       -- Small user: its own geography. Large user: its named linked small user.
       -- An explicit link to a split part is kept exactly; B is not rewritten to A.
       g.pc_norm AS simd_source_pc_norm,
       g.introduced_on AS simd_source_introduced_on,
       g.is_current AS simd_source_is_current,
       g.DataZone2001Code AS simd_source_dz2001,
       g.DataZone2011Code AS simd_source_dz2011,
       -- 5. Copy PHS population-weighted Scotland quintiles, never Government bands.
       -- Guidance sections 3.1.1/3.1.2: weighting is explicit; 1 means most deprived.
       -- The CLI already reversed 2004/2006 bands. Do NOT reverse them again here.
       g.simd2004_pw_scotland_quintile,
       g.simd2006_pw_scotland_quintile,
       g.simd2009v2_pw_scotland_quintile,
       g.simd2012_pw_scotland_quintile,
       g.simd2016_pw_scotland_quintile,
       g.simd2020v2_pw_scotland_quintile
FROM representatives p
LEFT JOIN latest_full_keys g
       ON g.pc_norm = CASE
           -- An unresolved representative has no eligible geography key.
           WHEN p.candidate_count > 1 THEN NULL
           WHEN p.pc_norm <> p.pc_base AND RIGHT(p.pc_norm, 1) <> 'A' THEN NULL
           WHEN p.spd_user_type = 'small_user' THEN p.pc_norm
           ELSE UPPER(REPLACE(p.LinkedSmallUserPostcode, ' ', ''))
       END
      AND g.spd_user_type = 'small_user';
