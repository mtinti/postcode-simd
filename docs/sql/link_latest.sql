-- VERSION 1: latest postcode geography, ONE chosen SIMD edition throughout.
-- Run the SSPL setup (default) or the explicitly named history setup first.
-- Input: events(id, postcode). The result names the selected product and release.
-- id need not be unique: this LEFT JOIN keeps each input row, without grouping.
--
-- "Latest" means the latest postcode record, not an automatic choice of SIMD.
-- Default edition: 2020v2, the most recent edition configured in this project.
-- For another edition, change the TWO marked lines together.
-- PHS v3.5 section 3.2.1.2 describes using one edition throughout a trend;
-- choose the edition appropriate to the study, not necessarily the newest.

WITH matched AS (
    -- 1. Normalise as the CLI does: uppercase and remove ASCII spaces.
    -- PHS Appendix A permits postcode linkage; normalisation is our join-key rule.
    SELECT e.id, e.postcode,
           NULLIF(UPPER(REPLACE(e.postcode, ' ', '')), '') AS postcode_key,
           '2020v2' AS simd_edition,                             -- EDIT EDITION 1/2
           p.simd2020v2_pw_scotland_quintile AS simd_value,       -- EDIT EDITION 2/2
           p.postcode_status,
           p.matched_pc_norm, p.matched_introduced_on,
           p.matched_is_current, p.matched_user_type,
           p.simd_source_pc_norm, p.simd_source_introduced_on,
           p.simd_source_is_current, p.requested_link_postcode,
           p.index_source, p.index_release, p.allocation
    FROM events e
    LEFT JOIN simd_postcode_latest p
           ON p.postcode_key = NULLIF(UPPER(REPLACE(e.postcode, ' ', '')), '')
)
-- 2. Keep missing/excluded postcodes visible, with null SIMD and a reason.
-- A latest record can be deleted: that is not a failed match in this policy.
-- The shared view has already withheld geography for ambiguous/excluded records.
SELECT id, postcode, simd_edition,
       'PHS population-weighted within-Scotland quintile; 1 = most deprived' AS simd_measure,
       CASE
           WHEN postcode_key IS NULL THEN 'missing_postcode'
           WHEN postcode_status IS NULL THEN 'not_found'
           WHEN postcode_status NOT IN ('matched', 'a_part', 'linked_small_user') THEN postcode_status
           WHEN simd_value IS NULL THEN 'missing_simd'
           ELSE postcode_status
       END AS simd_status,
       simd_value,
       matched_pc_norm, matched_introduced_on, matched_is_current, matched_user_type,
       simd_source_pc_norm, simd_source_introduced_on, simd_source_is_current,
       requested_link_postcode, index_source, index_release, allocation
FROM matched;
