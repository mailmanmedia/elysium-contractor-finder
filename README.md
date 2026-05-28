# Elysium Contractor Finder

A local tool for **Elysium Contracting (Chicago)** to discover subcontractors
to invite to bid. It pulls from public, searchable sources and presents them
in one searchable, filterable, exportable view.

## What it does

- Pulls **City of Chicago Building Permits** — every permit lists up to 15
  contractors with names, addresses, phone numbers, and a `reported_cost`
  per permit. Roll-ups give you each contractor's job count + total reported
  dollars over a date range you choose.
- Pulls **City of Chicago Contract Awards** — vendor names, addresses, and
  award amounts for public-works contracts.
- Loads **IDFPR licensed contractor rosters** (Roofing, Plumbing, etc.) that
  you drop into `data/idfpr/` as the latest .xlsx files from
  <https://idfpr.illinois.gov/profs/licenselookup.html>.
- Optional: **DuckDuckGo search results** scraper (opt-in toggle).
- Optional: **Yellow Pages / BBB** scrapers (opt-in toggle).
- Optional: **Google Places / Hunter.io / Apollo.io** paid enrichment for
  phone numbers, websites, contact names, and emails.
- **27+ trades** classified, including Glazing, Millwork, Doors/Frames/Hardware,
  Framing, Electrical, Plumbing, HVAC, Fire Protection, Roofing, Concrete,
  Masonry, Drywall, Painting, Flooring, Demolition, Excavation, etc.
- Filters: keyword, trade, city, ZIP, date range, min jobs, min total $.
- Export: **Excel** (one click) or CSV.

## Setup

```bash
cd ~/elysium-contractor-finder
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # optional, only needed for paid APIs
```

## Run

```bash
streamlit run app.py
```

The app opens in your browser (usually <http://localhost:8501>).

## Optional API keys

All keys are optional. Add them to `.env` if you want them.

| Key | Source | Why |
|---|---|---|
| `SOCRATA_APP_TOKEN` | <https://data.cityofchicago.org/profile/edit/developer_settings> | Free, raises Chicago Data Portal rate limit |
| `GOOGLE_PLACES_API_KEY` | Google Cloud Console | Phone, website, rating |
| `HUNTER_API_KEY` | <https://hunter.io> | Email addresses for a contractor's domain |
| `APOLLO_API_KEY` | <https://apollo.io> | Org info, LinkedIn, phone |

## Adding IDFPR rosters

1. Go to <https://idfpr.illinois.gov/profs/licenselookup.html>
2. Download the weekly Excel for **Roofing Contractor** and **Plumbing Contractor**.
3. Drop the files into `data/idfpr/`. Filenames containing "roof", "plumb",
   or "elect" are auto-tagged.

## How "what they were paid" works

For private jobs the actual contract price is not public. The tool surfaces
the **closest public proxies**:

- `reported_cost` on each Chicago building permit (the value the GC declared).
- `award_amount` on Chicago contract awards (public-works subs).

Both are aggregated per contractor across the date range you pick, so the
roll-up reflects ongoing activity, not just one job.

## Project layout

```
elysium-contractor-finder/
├── app.py                       # Streamlit UI
├── sources/
│   ├── chicago_permits.py
│   ├── chicago_contracts.py
│   ├── idfpr_licenses.py
│   ├── yellow_pages.py
│   ├── bbb.py
│   ├── enrichment.py
│   ├── trades.py
│   ├── merge.py
│   └── common.py
├── data/
│   ├── cache/                   # HTTP cache (auto)
│   └── idfpr/                   # drop license rosters here
├── exports/                     # Excel exports (auto)
├── requirements.txt
├── .env.example
└── README.md
```

## Legal notes

- Chicago Data Portal and IDFPR data are public and meant for download.
- Search engine scraping uses DuckDuckGo search results and is opt-in only.
  Review DuckDuckGo policies and throttle requests; follow landing-page scraping
  best practices.
- Yellow Pages and BBB scraping violate their Terms of Use. The toggles
  exist for personal research only; throttle politely and review their ToS
  before any production use.
- Google / Hunter / Apollo usage is governed by their respective APIs.
