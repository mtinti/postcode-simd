-- SSPL SETUP: run once, then link_by_era.sql.
-- Import results/postcode_simd.parquet as postcode_simd, primary key pc_norm.
-- This view only reshapes the existing columns: one row per (pc_norm, simd_edition).
-- It does NOT follow large-user links, choose split parts, or recompute any SIMD value.
-- NRS already selected the latest whole postcode and its output-area-based geography:
-- https://www.nrscotland.gov.uk/publications/geography-scottish-statistics-postcode-lookup-information-note/
--
-- PHS v3.5 Table 4: 2004-2012 use 2001 data zones; 2016/2020v2 use 2011 data zones.
-- Sections 3.1.1-3.1.2: keep PHS population-weighted and Government unweighted bands
-- distinct. Ingestion already standardised early PHS bands to 1 = most deprived.
-- Section 3.4: local PHS bands must travel with their PHS geography codes.
-- https://publichealthscotland.scot/media/24056/2023-12-phs-deprivation-guidance-v35.pdf
-- SQL Server: execute this CREATE VIEW in its own batch.

CREATE VIEW simd_postcode_by_edition AS
-- SIMD 2004: copy this edition's published/standardised values, using 2001 zones.
SELECT pc_norm,
       CAST('2004' AS varchar(6)) AS simd_edition,
       2001 AS data_zone_vintage,
       DataZone2001Code AS data_zone_code,
       phs_dz2001_hb AS phs_hb_code,
       phs_dz2001_hscp AS phs_hscp_code,
       phs_dz2001_ca AS phs_ca_code,
       simd2004_rank AS simd_rank,
       simd2004_pw_scotland_quintile AS phs_pw_scotland_quintile,
       simd2004_pw_scotland_decile AS phs_pw_scotland_decile,
       simd2004_pw_hb_quintile AS phs_pw_hb_quintile,
       simd2004_pw_hb_decile AS phs_pw_hb_decile,
       simd2004_pw_hscp_quintile AS phs_pw_hscp_quintile,
       simd2004_pw_hscp_decile AS phs_pw_hscp_decile,
       simd2004_pw_ca_quintile AS phs_pw_ca_quintile,
       simd2004_pw_ca_decile AS phs_pw_ca_decile,
       simd2004_most15pc AS phs_pw_most15pc,
       simd2004_least15pc AS phs_pw_least15pc,
       simd2004_uw_scotland_quintile AS gov_uw_scotland_quintile,
       simd2004_uw_scotland_decile AS gov_uw_scotland_decile,
       simd2004_uw_scotland_vigintile AS gov_uw_scotland_vigintile
FROM postcode_simd

UNION ALL

-- SIMD 2006: copy this edition's published/standardised values, using 2001 zones.
SELECT pc_norm,
       CAST('2006' AS varchar(6)) AS simd_edition,
       2001 AS data_zone_vintage,
       DataZone2001Code AS data_zone_code,
       phs_dz2001_hb AS phs_hb_code,
       phs_dz2001_hscp AS phs_hscp_code,
       phs_dz2001_ca AS phs_ca_code,
       simd2006_rank AS simd_rank,
       simd2006_pw_scotland_quintile AS phs_pw_scotland_quintile,
       simd2006_pw_scotland_decile AS phs_pw_scotland_decile,
       simd2006_pw_hb_quintile AS phs_pw_hb_quintile,
       simd2006_pw_hb_decile AS phs_pw_hb_decile,
       simd2006_pw_hscp_quintile AS phs_pw_hscp_quintile,
       simd2006_pw_hscp_decile AS phs_pw_hscp_decile,
       simd2006_pw_ca_quintile AS phs_pw_ca_quintile,
       simd2006_pw_ca_decile AS phs_pw_ca_decile,
       simd2006_most15pc AS phs_pw_most15pc,
       simd2006_least15pc AS phs_pw_least15pc,
       simd2006_uw_scotland_quintile AS gov_uw_scotland_quintile,
       simd2006_uw_scotland_decile AS gov_uw_scotland_decile,
       simd2006_uw_scotland_vigintile AS gov_uw_scotland_vigintile
FROM postcode_simd

UNION ALL

-- SIMD 2009v2: copy this edition's published/standardised values, using 2001 zones.
SELECT pc_norm,
       CAST('2009v2' AS varchar(6)) AS simd_edition,
       2001 AS data_zone_vintage,
       DataZone2001Code AS data_zone_code,
       phs_dz2001_hb AS phs_hb_code,
       phs_dz2001_hscp AS phs_hscp_code,
       phs_dz2001_ca AS phs_ca_code,
       simd2009v2_rank AS simd_rank,
       simd2009v2_pw_scotland_quintile AS phs_pw_scotland_quintile,
       simd2009v2_pw_scotland_decile AS phs_pw_scotland_decile,
       simd2009v2_pw_hb_quintile AS phs_pw_hb_quintile,
       simd2009v2_pw_hb_decile AS phs_pw_hb_decile,
       simd2009v2_pw_hscp_quintile AS phs_pw_hscp_quintile,
       simd2009v2_pw_hscp_decile AS phs_pw_hscp_decile,
       simd2009v2_pw_ca_quintile AS phs_pw_ca_quintile,
       simd2009v2_pw_ca_decile AS phs_pw_ca_decile,
       simd2009v2_most15pc AS phs_pw_most15pc,
       simd2009v2_least15pc AS phs_pw_least15pc,
       simd2009v2_uw_scotland_quintile AS gov_uw_scotland_quintile,
       simd2009v2_uw_scotland_decile AS gov_uw_scotland_decile,
       simd2009v2_uw_scotland_vigintile AS gov_uw_scotland_vigintile
FROM postcode_simd

UNION ALL

-- SIMD 2012: copy this edition's published/standardised values, using 2001 zones.
SELECT pc_norm,
       CAST('2012' AS varchar(6)) AS simd_edition,
       2001 AS data_zone_vintage,
       DataZone2001Code AS data_zone_code,
       phs_dz2001_hb AS phs_hb_code,
       phs_dz2001_hscp AS phs_hscp_code,
       phs_dz2001_ca AS phs_ca_code,
       simd2012_rank AS simd_rank,
       simd2012_pw_scotland_quintile AS phs_pw_scotland_quintile,
       simd2012_pw_scotland_decile AS phs_pw_scotland_decile,
       simd2012_pw_hb_quintile AS phs_pw_hb_quintile,
       simd2012_pw_hb_decile AS phs_pw_hb_decile,
       simd2012_pw_hscp_quintile AS phs_pw_hscp_quintile,
       simd2012_pw_hscp_decile AS phs_pw_hscp_decile,
       simd2012_pw_ca_quintile AS phs_pw_ca_quintile,
       simd2012_pw_ca_decile AS phs_pw_ca_decile,
       simd2012_most15pc AS phs_pw_most15pc,
       simd2012_least15pc AS phs_pw_least15pc,
       simd2012_uw_scotland_quintile AS gov_uw_scotland_quintile,
       simd2012_uw_scotland_decile AS gov_uw_scotland_decile,
       simd2012_uw_scotland_vigintile AS gov_uw_scotland_vigintile
FROM postcode_simd

UNION ALL

-- SIMD 2016: copy this edition's published/standardised values, using 2011 zones.
SELECT pc_norm,
       CAST('2016' AS varchar(6)) AS simd_edition,
       2011 AS data_zone_vintage,
       DataZone2011Code AS data_zone_code,
       phs_dz2011_hb AS phs_hb_code,
       phs_dz2011_hscp AS phs_hscp_code,
       phs_dz2011_ca AS phs_ca_code,
       simd2016_rank AS simd_rank,
       simd2016_pw_scotland_quintile AS phs_pw_scotland_quintile,
       simd2016_pw_scotland_decile AS phs_pw_scotland_decile,
       simd2016_pw_hb_quintile AS phs_pw_hb_quintile,
       simd2016_pw_hb_decile AS phs_pw_hb_decile,
       simd2016_pw_hscp_quintile AS phs_pw_hscp_quintile,
       simd2016_pw_hscp_decile AS phs_pw_hscp_decile,
       simd2016_pw_ca_quintile AS phs_pw_ca_quintile,
       simd2016_pw_ca_decile AS phs_pw_ca_decile,
       simd2016_most15pc AS phs_pw_most15pc,
       simd2016_least15pc AS phs_pw_least15pc,
       simd2016_uw_scotland_quintile AS gov_uw_scotland_quintile,
       simd2016_uw_scotland_decile AS gov_uw_scotland_decile,
       simd2016_uw_scotland_vigintile AS gov_uw_scotland_vigintile
FROM postcode_simd

UNION ALL

-- SIMD 2020v2: copy this edition's published/standardised values, using 2011 zones.
SELECT pc_norm,
       CAST('2020v2' AS varchar(6)) AS simd_edition,
       2011 AS data_zone_vintage,
       DataZone2011Code AS data_zone_code,
       phs_dz2011_hb AS phs_hb_code,
       phs_dz2011_hscp AS phs_hscp_code,
       phs_dz2011_ca AS phs_ca_code,
       simd2020v2_rank AS simd_rank,
       simd2020v2_pw_scotland_quintile AS phs_pw_scotland_quintile,
       simd2020v2_pw_scotland_decile AS phs_pw_scotland_decile,
       simd2020v2_pw_hb_quintile AS phs_pw_hb_quintile,
       simd2020v2_pw_hb_decile AS phs_pw_hb_decile,
       simd2020v2_pw_hscp_quintile AS phs_pw_hscp_quintile,
       simd2020v2_pw_hscp_decile AS phs_pw_hscp_decile,
       simd2020v2_pw_ca_quintile AS phs_pw_ca_quintile,
       simd2020v2_pw_ca_decile AS phs_pw_ca_decile,
       simd2020v2_most15pc AS phs_pw_most15pc,
       simd2020v2_least15pc AS phs_pw_least15pc,
       simd2020v2_uw_scotland_quintile AS gov_uw_scotland_quintile,
       simd2020v2_uw_scotland_decile AS gov_uw_scotland_decile,
       simd2020v2_uw_scotland_vigintile AS gov_uw_scotland_vigintile
FROM postcode_simd;
