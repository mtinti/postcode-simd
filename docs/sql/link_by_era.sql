-- DEFAULT LOOKUP: postcode + health-data year -> BOTH PHS and Government SIMD fields.
-- Run create_latest_postcode_lookup.sql first. No patient data leaves your database.
-- Guidance references and the output dictionary: ../LINKAGE_BY_ERA.md.

WITH inputs AS (
    -- 1. EDIT INPUT. For a cohort, replace this SELECT with id, postcode, analysis_year
    -- from your table. The year must be an integer, not a SIMD release label.
    SELECT 1 AS id, CAST('AB24 2TY' AS varchar(32)) AS postcode, 2020 AS analysis_year
),
era AS (
    -- 2. PHS v3.5 Table 4, printed p.17: the year chooses SIMD, NOT postcode history.
    -- https://publichealthscotland.scot/media/24056/2023-12-phs-deprivation-guidance-v35.pdf
    SELECT * FROM (VALUES
        (1996, 2003, '2004'),
        (2004, 2006, '2006'),
        (2007, 2009, '2009v2'),
        (2010, 2013, '2012'),
        (2014, 2016, '2016'),
        (2017, 9999, '2020v2')
    ) AS v(year_from, year_to, edition)
),
requested AS (
    -- 3. Our join-key convention: retain the input, uppercase and remove ASCII spaces.
    -- This does not repair invalid postcodes or remove an NRS A/B/C suffix.
    SELECT id, postcode, analysis_year,
           NULLIF(UPPER(REPLACE(postcode, ' ', '')), '') AS postcode_key
    FROM inputs
)
SELECT i.id, i.postcode, i.analysis_year,
       p.Postcode AS matched_postcode, p.pc_norm AS matched_pc_norm,
       'sspl' AS index_source, p.sspl_release, 'oa2022_centroid' AS allocation,
       p.introduced_on, p.deleted_on, p.is_current,
       p.spd_user_type AS postcode_user_type, p.SplitIndicator AS split_indicator,
       p.LinkedSmallUserPostcode AS linked_small_user_postcode,
       -- 4. Keep matching separate from residence eligibility (PHS Appendix A, p.30).
       -- Warnings do NOT suppress values or redirect the postcode to another record.
       CASE
           WHEN p.spd_user_type IS NULL OR p.spd_user_type <> 'large_user' THEN NULL
           WHEN UPPER(REPLACE(p.LinkedSmallUserPostcode, ' ', '')) = 'NOLINKP' THEN 'po_box'
           WHEN NULLIF(UPPER(REPLACE(p.LinkedSmallUserPostcode, ' ', '')), '') IS NULL
                OR UPPER(REPLACE(p.LinkedSmallUserPostcode, ' ', '')) = 'NOLINK' THEN 'unlinked_large_user'
           WHEN p.spd_user_type = 'large_user' THEN 'large_user'
       END AS address_warning,
       CASE
           WHEN i.postcode_key IS NULL THEN 'missing_postcode'
           WHEN p.pc_norm IS NULL THEN 'not_found'
           ELSE 'matched'
       END AS postcode_status,
       e.edition AS simd_edition, 'PHS v3.5 Table 4 health-data year' AS edition_policy,
       s.data_zone_vintage, s.data_zone_code,
       -- These SSPL context fields describe the current lookup, not the analysis year.
       p.OutputArea2022Code AS nrs_output_area_2022,
       p.CouncilArea2019Code AS nrs_council_area_2019,
       p.HealthBoardArea2019Code AS nrs_health_board_2019,
       p.IntegrationAuthority2019Code AS nrs_hscp_2019,
       p.UrbanRural6Fold2022Code AS nrs_urban_rural_6fold_2022,
       p.UrbanRural8Fold2022Code AS nrs_urban_rural_8fold_2022,
       CASE
           WHEN i.analysis_year IS NULL THEN 'missing_year'
           WHEN i.analysis_year < 1 OR i.analysis_year > 9999 THEN 'invalid_year'
           WHEN e.edition IS NULL THEN 'no_edition'
           WHEN i.postcode_key IS NULL THEN 'missing_postcode'
           WHEN p.pc_norm IS NULL THEN 'not_found'
           WHEN s.simd_rank IS NULL OR s.data_zone_code IS NULL
                OR s.phs_hb_code IS NULL OR s.phs_hscp_code IS NULL OR s.phs_ca_code IS NULL
                OR s.phs_pw_scotland_quintile IS NULL OR s.phs_pw_scotland_decile IS NULL
                OR s.phs_pw_hb_quintile IS NULL OR s.phs_pw_hb_decile IS NULL
                OR s.phs_pw_hscp_quintile IS NULL OR s.phs_pw_hscp_decile IS NULL
                OR s.phs_pw_ca_quintile IS NULL OR s.phs_pw_ca_decile IS NULL
                OR s.phs_pw_most15pc IS NULL OR s.phs_pw_least15pc IS NULL
                OR s.gov_uw_scotland_quintile IS NULL OR s.gov_uw_scotland_decile IS NULL
                OR s.gov_uw_scotland_vigintile IS NULL THEN 'missing_simd'
           ELSE 'matched'
       END AS simd_status,
       -- 5. PHS sections 3.1 and 3.4: label weighting, direction and local band geography.
       -- Rank is shared. Never mix pw (population-weighted) and uw (unweighted) bands.
       '1 = most deprived' AS band_direction, s.simd_rank,
       s.phs_pw_scotland_quintile, s.phs_pw_scotland_decile,
       s.phs_hb_code, s.phs_pw_hb_quintile, s.phs_pw_hb_decile,
       s.phs_hscp_code, s.phs_pw_hscp_quintile, s.phs_pw_hscp_decile,
       s.phs_ca_code, s.phs_pw_ca_quintile, s.phs_pw_ca_decile,
       s.phs_pw_most15pc, s.phs_pw_least15pc,
       s.gov_uw_scotland_quintile, s.gov_uw_scotland_decile, s.gov_uw_scotland_vigintile
FROM requested i
LEFT JOIN era e ON i.analysis_year BETWEEN e.year_from AND e.year_to
-- NRS SSPL already supplies the latest whole record and its allocated geography.
-- No life ranking, linked-small-user join, split aliases, or fallback to SPD.
LEFT JOIN postcode_simd p ON p.pc_norm = i.postcode_key
LEFT JOIN simd_postcode_by_edition s ON s.pc_norm = p.pc_norm AND s.simd_edition = e.edition;
