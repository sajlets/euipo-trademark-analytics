CREATE OR REPLACE VIEW data_quality_checks AS
SELECT
    'duplicate_application_class' AS check_name,
    'error' AS severity,
    COUNT(*) AS issue_count
FROM (
    SELECT app_number, nice_class
    FROM stg_trademarks
    GROUP BY app_number, nice_class
    HAVING COUNT(*) > 1
)
UNION ALL
SELECT
    'inconsistent_application_attributes',
    'error',
    COUNT(*)
FROM (
    SELECT app_number
    FROM stg_trademarks
    GROUP BY app_number
    HAVING COUNT(DISTINCT filing_date) > 1
        OR COUNT(DISTINCT applicant_country) > 1
        OR COUNT(DISTINCT filing_type) > 1
)
UNION ALL
SELECT
    'future_filing_date',
    'warning',
    COUNT(*)
FROM v_applications
WHERE filing_date > CURRENT_DATE;
