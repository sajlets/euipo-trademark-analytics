# KPI definitions

| KPI | Business question | Definition | Important caveat |
|---|---|---|---|
| Applications by filing year | How many EU trade mark applications were filed each year? | Count distinct application numbers by the calendar year of the filing date. | The source must contain application-level filing dates and be filtered to EU trade marks before loading. |
| Estonian applicant share | What proportion of applications list an Estonian applicant country? | Distinct applications with applicant country `EE` divided by all distinct applications in the year. | This is a country-of-applicant measure, not a count of applications filed at the Estonian Patent Office. Confirm how the source represents multiple applicants. |
| Applications by Nice class | Which goods/services classes are most common? | Count distinct application numbers by filing year and Nice class. | An application may cover multiple classes and therefore appear once in several class counts. Class totals must not be summed to represent total applications. |
| Filing type split | What types of applications are being filed? | Count distinct applications by filing year and filing type. | Keep source filing-type labels or document any mapping; do not assume different labels are equivalent. |
| Year-over-year growth | Is the annual application volume growing or shrinking? | `(current-year applications - previous-year applications) / previous-year applications`. | The first year has no comparison and returns NULL. A zero prior-year count also has undefined growth; do not report it as zero. |

## Grain and interpretation

The input grain is one row per application number and Nice class. The staging table
preserves that grain; application-level KPIs first use a distinct application view.
The country KPI uses applicant country and should not be described as Estonia's
share of applications filed with the Estonian Patent Office.

## Source and refresh notes

Record the EUIPO dataset name, download URL, retrieval date, file name, and any
source filters alongside each published analysis. Do not combine different
dataset vintages without documenting the coverage dates and any source changes.

## Data preparation

The input grain is one row per application number and Nice class. The
`raw_tm_filings` table preserves source values; the `stg_trademarks` SQL view
trims and types fields while retaining that grain. Country values are uppercased,
and `ESTONIA`/`EESTI` are mapped to `EE`. Application-level KPIs use a distinct
application view. The country KPI is not a measure of applications filed at the
Estonian Patent Office.
