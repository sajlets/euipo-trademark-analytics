from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from trademark_analytics.load_data import DataValidationError, load_csv
from trademark_analytics.publish_kpis import build_report


def write_csv(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_rows_and_counts_applications_once(tmp_path):
    source = write_csv(
        tmp_path,
        "filings.csv",
        "Application Number,Filing Date,Applicant Country,Filing Type,Nice Class\n"
        "A1,2024-01-03,EE,Individual,9\n"
        "A1,2024-01-03,EE,Individual,42\n"
        "A2,04/02/2024,DE,Collective,9\n"
        "A3,2023-12-31,Estonia,Individual,35\n",
    )
    database = tmp_path / "analytics.duckdb"

    assert load_csv(str(source), database) == 4

    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            "SELECT filing_year, application_count FROM kpi_filings_per_year "
            "ORDER BY filing_year"
        ).fetchall() == [(2023, 1), (2024, 2)]
        assert connection.execute(
            "SELECT estonian_application_count, total_application_count "
            "FROM kpi_estonian_share WHERE filing_year = 2024"
        ).fetchone() == (1, 2)
        assert connection.execute(
            "SELECT application_count, previous_year_count, yoy_growth "
            "FROM kpi_year_over_year_growth WHERE filing_year = 2024"
        ).fetchone() == (2, 1, 1.0)
        assert connection.execute(
            "SELECT issue_count FROM data_quality_checks "
            "WHERE check_name = 'duplicate_application_class'"
        ).fetchone() == (0,)


def test_failed_load_does_not_replace_existing_data(tmp_path):
    valid = write_csv(
        tmp_path,
        "valid.csv",
        "application_number,filing_date,applicant_country,filing_type,nice_class\n"
        "A1,2024-01-03,EE,Individual,9\n",
    )
    invalid = write_csv(
        tmp_path,
        "invalid.csv",
        "application_number,filing_date,applicant_country,filing_type,nice_class\n"
        "A2,2024-01-03,EE,Individual,46\n",
    )
    database = tmp_path / "analytics.duckdb"
    load_csv(str(valid), database)

    with pytest.raises(DataValidationError, match="invalid required value"):
        load_csv(str(invalid), database)

    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            "SELECT app_number FROM stg_trademarks"
        ).fetchall() == [("A1",)]


def test_sql_staging_casts_and_normalizes_source_values(tmp_path):
    source = write_csv(
        tmp_path,
        "filings.csv",
        "application_number,filing_date,applicant_country,filing_type,nice_class\n"
        " A1 , 03/02/2024 , estonia , Individual , Class 9 \n",
    )
    database = tmp_path / "analytics.duckdb"
    load_csv(str(source), database)

    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            """
            SELECT app_number, filing_date, applicant_country, nice_class,
                   typeof(filing_date)
            FROM stg_trademarks
            """
        ).fetchone() == ("A1", datetime(2024, 2, 3).date(), "EE", 9, "DATE")


def test_rejects_duplicate_application_and_class(tmp_path):
    source = write_csv(
        tmp_path,
        "duplicate.csv",
        "application_number,filing_date,applicant_country,filing_type,nice_class\n"
        "A1,2024-01-03,EE,Individual,9\n"
        "A1,2024-01-03,EE,Individual,9\n",
    )

    with pytest.raises(DataValidationError, match="Duplicate application/class"):
        load_csv(str(source), tmp_path / "analytics.duckdb")


def test_rejects_non_integer_nice_class(tmp_path):
    source = write_csv(
        tmp_path,
        "decimal-class.csv",
        "application_number,filing_date,applicant_country,filing_type,nice_class\n"
        "A1,2024-01-03,EE,Individual,9.5\n",
    )

    with pytest.raises(DataValidationError, match="Nice class is empty or unparseable"):
        load_csv(str(source), tmp_path / "analytics.duckdb")


def test_supports_semicolon_delimited_and_nice_class_label(tmp_path):
    source = write_csv(
        tmp_path,
        "filings.csv",
        "application number;filing date;applicant country;filing type;nice class\n"
        "A1;20240103;Eesti;Individual;Class 9\n",
    )

    assert load_csv(str(source), tmp_path / "analytics.duckdb") == 1


def test_yoy_does_not_compare_across_a_missing_calendar_year(tmp_path):
    source = write_csv(
        tmp_path,
        "gapped-years.csv",
        "application_number,filing_date,applicant_country,filing_type,nice_class\n"
        "A1,2022-01-03,EE,Individual,9\n"
        "A2,2024-01-03,EE,Individual,9\n",
    )
    database = tmp_path / "analytics.duckdb"
    load_csv(str(source), database)

    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            "SELECT previous_year_count, yoy_growth "
            "FROM kpi_year_over_year_growth WHERE filing_year = 2024"
        ).fetchone() == (None, None)


def test_generates_kpi_report_from_database(tmp_path):
    source = write_csv(
        tmp_path,
        "filings.csv",
        "application_number,filing_date,applicant_country,filing_type,nice_class\n"
        "A1,2024-01-03,EE,Individual,9\n"
        "A2,2024-02-03,DE,Collective,42\n",
    )
    database = tmp_path / "analytics.duckdb"
    load_csv(str(source), database)

    report = build_report(
        database,
        "https://example.test/filings.csv",
        datetime(2026, 10, 13, 12, 0),
    )

    assert "Latest year in source:** 2024" in report
    assert "| 2024 | 2 |" in report
    assert "https://example.test/filings.csv" in report
    assert "EE share" in report
    report = build_report(
        database,
        "https://example.test/filings.csv?access_token=do-not-publish",
        datetime(2026, 10, 13, 12, 0),
    )
    assert "do-not-publish" not in report
    assert "access_token" not in report


def test_checked_in_sample_loads_without_external_data(tmp_path):
    sample = Path(__file__).resolve().parents[1] / "data" / "sample_filings.csv"
    database = tmp_path / "sample.duckdb"

    assert load_csv(str(sample), database) == 7

    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            "SELECT filing_year, application_count FROM kpi_filings_per_year "
            "ORDER BY filing_year"
        ).fetchall() == [(2023, 2), (2024, 3)]
        assert connection.execute(
            "SELECT yoy_growth FROM kpi_year_over_year_growth "
            "WHERE filing_year = 2024"
        ).fetchone() == (0.5,)
        assert connection.execute(
            "SELECT source_type, input_rows FROM ingestion_metadata"
        ).fetchone() == ("synthetic_sample", 7)

    report = build_report(database, "not a real source", datetime(2026, 10, 13))
    assert "synthetic sample data (not EUIPO observations)" in report
    assert "not a real source" not in report


@pytest.mark.parametrize(
    "source",
    [
        "http://example.test/filings.csv",
        "https://user:password@example.test/filings.csv",
        "https://example.test/filings.csv?access_token=secret",
    ],
)
def test_rejects_insecure_or_credential_bearing_source_urls(tmp_path, source):
    with pytest.raises(DataValidationError):
        load_csv(source, tmp_path / "analytics.duckdb")
