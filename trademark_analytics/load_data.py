"""Fetch an EU trade mark CSV and load validated rows into DuckDB."""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
import urllib.request
from contextlib import contextmanager
from itertools import chain
from pathlib import Path
from typing import Iterator, TextIO
from urllib.parse import parse_qsl, urlparse

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "trademarks.duckdb"
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample_filings.csv"
SQL_DIR = PROJECT_ROOT / "sql"

FIELD_ALIASES = {
    "application_number": {
        "applicationnumber",
        "applicationno",
        "applicationid",
        "eutmnumber",
    },
    "filing_date": {"filingdate", "applicationdate", "dateoffiling"},
    "applicant_country": {
        "applicantcountry",
        "applicantcountrycode",
        "countryofapplicant",
        "applicantcountryoforigin",
    },
    "filing_type": {"filingtype", "applicationtype", "type"},
    "nice_class": {"niceclass", "niceclassification", "class"},
}
REQUIRED_FIELDS = tuple(FIELD_ALIASES)


class DataValidationError(ValueError):
    """Raised when a CSV row cannot be loaded without corrupting the dataset."""


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


def _map_headers(headers: list[str]) -> dict[str, str]:
    normalized = {_normalized_header(header): header for header in headers if header}
    mapping: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[field] = normalized[alias]
                break
    missing = sorted(set(REQUIRED_FIELDS) - mapping.keys())
    if missing:
        raise DataValidationError(
            "CSV is missing required columns: " + ", ".join(missing)
        )
    return mapping


@contextmanager
def _open_source(source: str) -> Iterator[TextIO]:
    parsed = urlparse(source)
    if parsed.scheme:
        if parsed.scheme != "https":
            raise DataValidationError("Remote CSV sources must use HTTPS")
        credential_names = {
            "access_token",
            "api_key",
            "apikey",
            "client_secret",
            "key",
            "token",
        }
        has_query_credential = any(
            name.lower() in credential_names for name, _ in parse_qsl(parsed.query)
        )
        if parsed.username or parsed.password or has_query_credential:
            raise DataValidationError(
                "Do not put credentials in a source URL; use a secure "
                "authenticated connector instead"
            )
        request = urllib.request.Request(
            source, headers={"User-Agent": "euipo-trademark-analytics/0.1"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            with io.TextIOWrapper(response, encoding="utf-8-sig", newline="") as stream:
                yield stream
    else:
        with Path(source).open(encoding="utf-8-sig", newline="") as stream:
            yield stream


def _read_rows(stream: TextIO) -> Iterator[tuple[int, dict[str, str]]]:
    header_line = stream.readline()
    if not header_line:
        raise DataValidationError("CSV source is empty")
    try:
        dialect = csv.Sniffer().sniff(header_line, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(chain((header_line,), stream), dialect=dialect)
    if not reader.fieldnames:
        raise DataValidationError("CSV source does not have a header row")
    mapping = _map_headers(reader.fieldnames)
    for row_number, raw in enumerate(reader, start=2):
        yield row_number, {
            field: raw.get(column) or "" for field, column in mapping.items()
        }


def load_csv(source: str, database: Path = DEFAULT_DATABASE) -> int:
    """Load raw CSV fields and replace the normalized DuckDB staging view."""
    database.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(database))
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute(
            """
            CREATE OR REPLACE TEMP TABLE incoming_tm_filings (
                app_number VARCHAR,
                filing_date VARCHAR,
                applicant_country VARCHAR,
                filing_type VARCHAR,
                nice_class VARCHAR,
                source_record_number INTEGER NOT NULL
            )
            """
        )
        batch: list[tuple[str, str, str, str, str, int]] = []
        count = 0
        with _open_source(source) as stream:
            for row_number, row in _read_rows(stream):
                batch.append(
                    (
                        row["application_number"],
                        row["filing_date"],
                        row["applicant_country"],
                        row["filing_type"],
                        row["nice_class"],
                        row_number,
                    )
                )
                if len(batch) >= 5_000:
                    con.executemany(
                        "INSERT INTO incoming_tm_filings VALUES (?, ?, ?, ?, ?, ?)",
                        batch,
                    )
                    count += len(batch)
                    batch.clear()
        if batch:
            con.executemany(
                "INSERT INTO incoming_tm_filings VALUES (?, ?, ?, ?, ?, ?)", batch
            )
            count += len(batch)
        if count == 0:
            raise DataValidationError("CSV contains no data rows")

        con.execute(
            """
            CREATE OR REPLACE TABLE raw_tm_filings AS
            SELECT * FROM incoming_tm_filings
            """
        )
        con.execute((SQL_DIR / "views.sql").read_text(encoding="utf-8"))
        con.execute((SQL_DIR / "data_quality.sql").read_text(encoding="utf-8"))

        invalid = con.execute(
            """
            SELECT source_record_number, app_number, filing_date, applicant_country,
                   filing_type, nice_class
            FROM stg_trademarks
            WHERE app_number IS NULL
                OR filing_date IS NULL
                OR NULLIF(TRIM(applicant_country), '') IS NULL
                OR filing_type IS NULL
                OR nice_class IS NULL
                OR nice_class NOT BETWEEN 1 AND 45
            LIMIT 1
            """
        ).fetchone()
        if invalid:
            problems = ["invalid required value(s) after SQL staging"]
            if invalid[1] is None:
                problems.append("application number is empty")
            if invalid[2] is None:
                problems.append("filing date is empty or unparseable")
            if not invalid[3]:
                problems.append("applicant country is empty")
            if invalid[4] is None:
                problems.append("filing type is empty")
            if invalid[5] is None:
                problems.append("Nice class is empty or unparseable")
            elif not 1 <= invalid[5] <= 45:
                problems.append("Nice class must be between 1 and 45")
            raise DataValidationError(
                f"Row {invalid[0]}: {'; '.join(problems)}; "
                f"app_number={invalid[1]!r}, filing_date={invalid[2]!r}, "
                f"applicant_country={invalid[3]!r}, filing_type={invalid[4]!r}, "
                f"nice_class={invalid[5]!r}"
            )

        duplicate = con.execute(
            """
            SELECT app_number, nice_class, COUNT(*) AS copies
            FROM stg_trademarks
            GROUP BY app_number, nice_class
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        ).fetchone()
        if duplicate:
            raise DataValidationError(
                "Duplicate application/class row found for "
                f"{duplicate[0]} / class {duplicate[1]} ({duplicate[2]} copies)"
            )

        inconsistent = con.execute(
            """
            SELECT app_number
            FROM stg_trademarks
            GROUP BY app_number
            HAVING COUNT(DISTINCT filing_date) > 1
                OR COUNT(DISTINCT applicant_country) > 1
                OR COUNT(DISTINCT filing_type) > 1
            LIMIT 1
            """
        ).fetchone()
        if inconsistent:
            raise DataValidationError(
                "Application has inconsistent filing date, applicant country, or "
                f"filing type across its Nice classes: {inconsistent[0]}"
            )

        parsed_source = urlparse(source)
        if parsed_source.scheme in {"http", "https"}:
            source_type = "http_csv"
        elif Path(source).expanduser().resolve() == SAMPLE_CSV.resolve():
            source_type = "synthetic_sample"
        else:
            source_type = "local_csv"
        con.execute(
            """
            CREATE OR REPLACE TABLE ingestion_metadata AS
            SELECT ? AS source_type, CURRENT_TIMESTAMP AS loaded_at, ? AS input_rows
            """,
            [source_type, count],
        )

        con.execute("COMMIT")
        return count
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load an EU trade mark CSV into DuckDB; a synthetic fixture "
        "is used when no source is specified."
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=os.environ.get("EUIPO_CSV_URL", str(SAMPLE_CSV)),
        help="CSV path or direct HTTPS CSV URL (default: EUIPO_CSV_URL or "
        "the synthetic local sample)",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"DuckDB file (default: {DEFAULT_DATABASE})",
    )
    args = parser.parse_args()
    try:
        loaded = load_csv(args.source, args.database)
    except (DataValidationError, OSError, ValueError, duckdb.Error) as error:
        print(f"Load failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(f"Loaded {loaded:,} application/class rows into {args.database}")


if __name__ == "__main__":
    main()
