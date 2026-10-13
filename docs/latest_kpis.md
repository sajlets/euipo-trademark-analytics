# Latest trade mark filing KPIs

No live dataset has been configured yet, so this repository does not have
verified KPI results to display. To enable the weekly GitHub Actions refresh,
set the repository variable `EUIPO_CSV_URL` to a stable, public CSV download
URL whose columns are supported by the loader, then run **Refresh trade mark
KPIs** from the repository's Actions tab.

The workflow will replace this message with calculated results after a
successful download and validation. EUIPO's documented trademark-search API
requires authenticated access and does not provide an anonymous bulk CSV, so
the actual EUIPO source/API integration still needs to be arranged. For an
offline demonstration, load `data/sample_filings.csv`; it contains synthetic
rows and must not be presented as actual EUIPO results. Data and calculations
are not fabricated for this published snapshot.
