# EU trade mark filing KPI dashboard

A small data-analytics project that loads trade mark application records into
DuckDB, calculates filing KPIs in SQL, and presents them in a Streamlit
dashboard. It demonstrates a basic ingestion and reporting workflow using
Python, SQL, DuckDB, data-quality checks, and a dashboard.

> **Data warning:** `data/sample_filings.csv` contains invented demonstration
> records. Its KPIs are not EUIPO statistics and must not be used as factual
> findings. No real EUIPO dataset is included or currently connected.

## Project question

The dashboard explores filing volume over time, the share of applications
associated with Estonian applicants, the most common Nice classes, and filing
type. These indicators can help a reader describe changes in filing activity
and the mix of applications. 

## Why these tools

- **Python** handles CSV ingestion, header mapping, loading, and validation.
- **DuckDB** stores the local dataset in one portable database file and runs
  analytical SQL without requiring a separate database server.
- **SQL views** separate source data, normalized staging data, and KPI
  calculations so that the metric logic is visible and reusable.
- **Streamlit** provides a small interactive dashboard directly from Python.
  Power BI is not required to run this version.
- **GitHub Actions** can run a scheduled refresh and update a Markdown KPI
  snapshot in the repository when a compatible source URL is configured.

## Data and interpretation

The expected source grain is one row per application and Nice class. Required
CSV fields are application number, filing date, applicant country, filing type,
and Nice class. The loader recognizes common header variations such as
`application_number` or `application number`, `filing_date` or
`applicationDate`, and `nice_class` or `class`.

The included sample has seven synthetic application/class rows. Some
applications have more than one Nice class to demonstrate why the input row
count differs from the application count.

EUIPO's documented [Trademark Search API](https://dev.euipo.europa.eu/product/trademark-search_110/api/trademark-search)
requires approved, authenticated access; it is not an anonymous CSV download.
Applicant country also requires a related Persons API lookup. This project
does not currently implement that OAuth/API integration. Use a real source
only when you have an authorized, supported CSV export or have implemented an
appropriate API connector.

## Run locally

Requirements: Python 3.10 or newer. These commands are for macOS/Linux and
should be run from the repository root.

Create an environment and install the project:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Load the included offline sample into `data/trademarks.duckdb`:

```bash
.venv/bin/load-trademarks
```

Start the dashboard:

```bash
.venv/bin/streamlit run dashboard/app.py
```

Open the local URL printed by Streamlit (usually `http://localhost:8501`).
The dashboard reads the DuckDB file created by the loader and displays a
warning when the synthetic sample is loaded.

To use a local CSV instead of the sample, load it before starting the
dashboard:

```bash
.venv/bin/load-trademarks /path/to/your_filings.csv
.venv/bin/streamlit run dashboard/app.py
```

The loader replaces the current dataset on a successful load. If the CSV fails
validation, the previous successful dataset is retained.

## Data pipeline

1. The loader reads a local CSV file or a direct HTTPS URL. It requires CSV
   columns for application number, filing date, applicant country, filing
   type, and Nice class.
2. `raw_tm_filings` stores the source fields as text so the ingested values are
   available for inspection.
3. `stg_trademarks`, defined in [`sql/views.sql`](sql/views.sql), trims values,
   converts filing dates to `DATE`, converts Nice classes to integers, and
   standardizes country text to uppercase. `ESTONIA` and `EESTI` are mapped to
   `EE`.
4. The loader rejects missing or unparseable required values, Nice classes
   outside 1–45, duplicate application/class pairs, and applications whose
   date, country, or filing type conflicts across classes.
5. SQL views calculate the KPIs. The dashboard queries those views from
   DuckDB.

The raw table is retained to make the source representation auditable; the
staging view expresses cleaning rules in SQL. The load and validation run in a
transaction, so a failed refresh does not replace the prior successful data.

## KPI definitions

See [`docs/kpi_definitions.md`](docs/kpi_definitions.md) for full definitions
and caveats.

- **Applications by year:** count distinct applications by filing year.
- **Estonian applicant share:** applications whose standardized applicant
  country is `EE`, divided by all applications in the year.
- **Top Nice classes:** distinct applications per class and year. An
  application can appear in several classes, so class counts do not sum to the
  total number of applications.
- **Filing type split:** distinct applications by the source filing-type
  label.
- **Year-over-year growth:** change in distinct application count compared
  with the immediately preceding calendar year. The result is unavailable when
  that prior year is missing or has a zero count.

“Estonian applicant share” is not the share of applications filed at the
Estonian Patent Office. It describes the applicant-country field as provided by
the source. If a source contains multiple applicants, the current one-country
per-application structure may not represent all applicants correctly.

## KPI snapshot on GitHub

[`docs/latest_kpis.md`](docs/latest_kpis.md) is the repository-readable KPI
snapshot. It currently explains that real data has not been configured; it
does not contain fabricated results.

The GitHub Actions workflow in
`.github/workflows/refresh-kpis.yml` is scheduled for Mondays at 06:17 UTC and
can also be started manually from the repository's **Actions** tab. To enable
it:

1. Obtain an authorized, stable, direct HTTPS URL that serves a CSV with the
   required columns. A webpage or JSON API endpoint is not a CSV download.
2. In the GitHub repository, open **Settings → Secrets and variables →
   Actions → Variables**, create the repository variable `EUIPO_CSV_URL`, and
   set its value to that CSV URL.
3. Run **Refresh trade mark KPIs** once from **Actions** to confirm the source
   works. Subsequent scheduled runs validate and load the data, regenerate
   `docs/latest_kpis.md`, and commit it if the snapshot changed.

The workflow currently supports unauthenticated CSV downloads only. Do not put
credentials in the URL, commit API keys, or assume that adding a secret alone
will authenticate against EUIPO's OAuth API. An API integration must be
implemented separately, use GitHub Actions secrets for credentials, and map
the API response to the fields and grain used by this project. A live EUIPO
refresh is not enabled until that source/access work is completed.

### Connecting the EUIPO API

The project does not currently implement the EUIPO API client. The steps below
describe what a maintainer needs to do before this workflow can retrieve live
EUIPO records; simply adding credentials to GitHub will not make the current
CSV loader call the API.

1. **Request API access.** Create an account in the
   [EUIPO Developer Portal](https://dev.euipo.europa.eu/getting-started),
   register an application, and request production access to the
   [Trademark Search API](https://dev.euipo.europa.eu/product/trademark-search_110/api/trademark-search).
   Follow EUIPO's current onboarding instructions for required approvals and
   quotas. Use the sandbox only for integration testing; its records are not
   production filing data.
2. **Define the business fields before mapping data.** The API's `markKind`
   describes categories such as individual, collective, or certification
   marks; `markFeature` describes a mark's representation, such as word or
   figurative. These are different measures, so document which one the
   dashboard calls “filing type.” The trademark search response does not
   provide the full applicant country needed for the Estonian-share KPI.
   Confirm whether the project should use applicant address country, company
   incorporation country, or an individual's nationality. They are not
   equivalent.
3. **Implement and test authentication.** Follow EUIPO's
   [security documentation](https://dev.euipo.europa.eu/security) to request
   an OAuth client-credentials token and call the production API. EUIPO's
   documented production token endpoint is
   `https://euipo.europa.eu/cas-server-webapp/oidc/accessToken`; use the
   current guide for exact client-credential placement, required headers,
   scope, and token handling. Never commit credentials or print tokens in
   logs.
4. **Build the API-to-staging ingestion.** Implement a separate API client
   rather than treating an API URL as a CSV URL. Query `GET /trademarks` using
   a bounded `applicationDate` range and the EU-trade-mark basis, then follow
   the API's pagination metadata and quotas. Map `applicationNumber` and
   `applicationDate`, retain `markKind` and/or `markFeature` as explicitly
   named fields, and expand each `niceClasses` array into one row per
   application and Nice class. The applicant country requires a related
   Persons API lookup using applicant identifiers; deduplicate person
   identifiers before requesting details, then join results back to the
   application records. Handle unavailable applicant details rather than
   silently treating them as non-Estonian.
5. **Preserve and validate the sample workflow.** Keep the synthetic fixture
   for offline tests. Add API-client tests using mocked responses for token
   handling, pagination, API errors/rate limits, arrays with multiple Nice
   classes, and missing person details. Test a small authorized date range
   against the EUIPO interface before publishing any real-data KPI.
6. **Store credentials in GitHub Actions secrets.** After implementing the
   client, add the credentials it requires (for example, client ID and client
   secret) under **Repository → Settings → Secrets and variables → Actions →
   Secrets**. Update the workflow to pass them to the API client as environment
   variables. Do not put secrets in `EUIPO_CSV_URL`, command-line arguments,
   committed files, or generated KPI reports. The current scheduled workflow
   does not read EUIPO API credentials and will not authenticate to the API.
7. **Run the workflow manually first.** Trigger **Refresh trade mark KPIs**
   from the **Actions** tab, inspect the run result and published source/date
   coverage, and resolve issues before relying on the Monday schedule. The
   workflow must not publish the synthetic fixture as EUIPO data.

## Tests

Run the tests with:

```bash
.venv/bin/python -m pytest
```

The tests cover CSV header variations, SQL normalization and data types, KPI
calculations, invalid and duplicate records, rollback after a failed load,
the synthetic sample, and report generation.
