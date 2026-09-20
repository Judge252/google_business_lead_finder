# Google Business Lead Finder

A local lead-generation web app for finding service businesses through **Google Places API (New)** and enriching the results with **public business contact channels from the businesses' own websites**.

## What it does

- Search by service + location, e.g. `dentists` + `Cairo, Egypt`
- Fetch up to 60 Google Places results per query
- Collect:
  - business name
  - category
  - address
  - phone
  - website
  - Google Maps link
  - rating
  - review count
- Optional public-website enrichment:
  - generic public business email addresses
  - `tel:` phone links
  - WhatsApp links
  - Instagram, Facebook, LinkedIn
- Lead score
- Client-side filtering
- CSV export
- No database required for v1

## Important

This project intentionally does **not** scrape Google Maps HTML. It uses Google's official Places API.

The website-contact enrichment:
- reads only publicly accessible pages
- respects `robots.txt`
- rejects private/local network targets
- limits pages per domain
- accepts only generic/business-looking public email inboxes (such as info@, sales@, contact@, booking@)
- is meant for legitimate B2B prospecting; comply with applicable anti-spam/privacy laws and each site's terms

## Google setup

1. Open Google Cloud Console.
2. Create/select a project.
3. Attach billing.
4. Enable **Places API (New)**.
5. Create an API key.
6. Restrict the key to the Places API and, where practical, to your server environment.
7. Copy `.env.example` to `.env`.
8. Set:

```env
GOOGLE_MAPS_API_KEY=YOUR_KEY
```

Google charges based on the fields requested. This app asks for contact/rating fields because they are core to lead generation.

## Run on Windows

Double-click:

```text
start.bat
```

Or manually:

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
# edit .env
python -m uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Run on macOS / Linux

```bash
chmod +x start.sh
./start.sh
```

Then open:

```text
http://127.0.0.1:8000
```

## Search tips

A single Google Text Search query can return up to 60 results across pages. For larger prospect lists, search smaller geographic areas and combine/export the results, for example:

- dentists — Nasr City, Cairo
- dentists — Heliopolis, Cairo
- dentists — Maadi, Cairo
- dentists — New Cairo, Cairo

The app deduplicates Google Place IDs within each search.

## API endpoints

### Health

`GET /api/health`

### Search

`POST /api/search`

Example JSON:

```json
{
  "service": "dentists",
  "location": "Cairo, Egypt",
  "max_results": 40,
  "enrich_websites": true
}
```

## Production notes

For a public deployment, add:
- authentication
- per-user rate limits / quotas
- a persistent database
- background job queue for large enrichment batches
- audit logs
- domain-level crawl throttling
- a privacy/opt-out process
- server-side export storage if required

Never expose your Google API key in browser JavaScript.
"# google_business_lead_finder" 
