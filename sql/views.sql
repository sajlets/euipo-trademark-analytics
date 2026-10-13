CREATE OR REPLACE VIEW stg_trademarks AS
WITH cleaned AS (
    SELECT
        app_number,
        filing_date,
        applicant_country,
        filing_type,
        REGEXP_REPLACE(
            NULLIF(TRIM(nice_class), ''),
            '(?i)^class[[:space:]]*',
            ''
        ) AS nice_class_text,
        source_record_number
    FROM raw_tm_filings
)
SELECT
    NULLIF(TRIM(app_number), '') AS app_number,
    COALESCE(
        TRY_STRPTIME(
            NULLIF(TRIM(filing_date), ''),
            ['%Y-%m-%d', '%d/%m/%Y', '%d.%m.%Y', '%Y%m%d']
        )::DATE,
        TRY_CAST(NULLIF(TRIM(filing_date), '') AS DATE)
    ) AS filing_date,
    CASE
        WHEN UPPER(TRIM(applicant_country)) IN ('ESTONIA', 'EESTI') THEN 'EE'
        ELSE UPPER(TRIM(applicant_country))
    END AS applicant_country,
    NULLIF(TRIM(filing_type), '') AS filing_type,
    CASE
        WHEN REGEXP_FULL_MATCH(nice_class_text, '[0-9]{1,2}')
            THEN TRY_CAST(nice_class_text AS INTEGER)
    END AS nice_class,
    source_record_number
FROM cleaned;

CREATE OR REPLACE VIEW v_applications AS
SELECT DISTINCT
    app_number AS application_number,
    filing_date,
    applicant_country,
    filing_type
FROM stg_trademarks;

CREATE OR REPLACE VIEW kpi_filings_per_year AS
SELECT
    YEAR(filing_date) AS filing_year,
    COUNT(*) AS application_count
FROM v_applications
GROUP BY YEAR(filing_date);

CREATE OR REPLACE VIEW kpi_estonian_share AS
SELECT
    YEAR(filing_date) AS filing_year,
    COUNT(*) FILTER (WHERE applicant_country = 'EE') AS estonian_application_count,
    COUNT(*) AS total_application_count,
    COUNT(*) FILTER (WHERE applicant_country = 'EE') * 1.0
        / NULLIF(COUNT(*), 0) AS estonian_share
FROM v_applications
GROUP BY YEAR(filing_date);

CREATE OR REPLACE VIEW kpi_top_nice_classes AS
SELECT
    YEAR(filing_date) AS filing_year,
    nice_class,
    COUNT(DISTINCT app_number) AS application_count
FROM stg_trademarks
GROUP BY YEAR(filing_date), nice_class;

CREATE OR REPLACE VIEW kpi_filing_type_split AS
SELECT
    YEAR(filing_date) AS filing_year,
    filing_type,
    COUNT(*) AS application_count
FROM v_applications
GROUP BY YEAR(filing_date), filing_type;

CREATE OR REPLACE VIEW kpi_year_over_year_growth AS
WITH yearly AS (
    SELECT YEAR(filing_date) AS filing_year, COUNT(*) AS application_count
    FROM v_applications
    GROUP BY YEAR(filing_date)
),
with_previous AS (
    SELECT
        filing_year,
        application_count,
        LAG(filing_year) OVER (ORDER BY filing_year) AS prior_observed_year,
        LAG(application_count) OVER (ORDER BY filing_year) AS prior_observed_count
    FROM yearly
)
SELECT
    filing_year,
    application_count,
    CASE
        WHEN prior_observed_year = filing_year - 1 THEN prior_observed_count
    END AS previous_year_count,
    CASE
        WHEN prior_observed_year = filing_year - 1 THEN
            (application_count - prior_observed_count) * 1.0
                / NULLIF(prior_observed_count, 0)
    END AS yoy_growth
FROM with_previous;
