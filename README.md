# Workbook Analyzer for Tableau

[![License: Polyform Noncommercial](https://img.shields.io/badge/License-Polyform_NC-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)

> **日本語版 README**: [README_ja.md](README_ja.md)

A lightweight local web app for **deep workbook analysis** on Tableau Cloud — focused on revision diff comparison and calculated field dependency analysis.

Starts in seconds. No waiting for site-wide data fetches.

---

## Why This Tool?

[Cloud Admin Kit for Tableau](https://github.com/brave-data/Cloud_Admin_Kit_for_Tableau) is a full site management dashboard, but its initial load can take 10–30+ minutes on large sites because it fetches every workbook, data source, view, user, and schedule.

**Workbook Analyzer** takes a different approach: fetch only the workbook list on startup (~10 seconds for 300 workbooks), then pull individual workbook data on demand. If you only need to analyze specific workbooks, this is the right tool.

---

## Features

### 1. Revision Diff Comparison

Compare any two revisions of a workbook to see exactly what changed.

- Search workbooks by name or project
- Select Base and Head revision numbers
- See **added / deleted / changed** for:
  - **Calculated fields** — field name, datasource, old vs. new formula
  - **Filters** — categorical, quantitative, relative-date, top-N
  - **Connected datasources** — additions and removals
  - **Sheets** — worksheets, dashboards, and stories
- Results are cached per revision pair

### 2. Calculated Field Dependency Analysis

Download a workbook and visualize its calculated field dependencies.

- Searchable field list with formula display
- Filter fields by name or formula text
- **Sankey chart** showing which calculated fields reference which others

---

## Getting Started

```bash
git clone https://github.com/brave-data/Workbook_Analyzer_for_Tableau.git
cd Workbook_Analyzer_for_Tableau
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your Tableau Cloud credentials
python main.py
```

Open **http://localhost:8001** in your browser. The workbook list loads in seconds.

---

## Configuration

```ini
TABLEAU_SERVER_URL=https://10ay.online.tableau.com
TABLEAU_SITE_NAME=mycompany
TABLEAU_TOKEN_NAME=my-pat-name
TABLEAU_TOKEN_SECRET=xxxxxxxxxxxxxxxxxxxx
PORT=8001
```

---

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, uvicorn, tableauserverclient, defusedxml
- **Frontend**: Bootstrap 5.3, Bootstrap Icons, D3.js (Sankey)
