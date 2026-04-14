# Restaurant Menu Photo Matcher (Foundation)

This repository contains a robust FastAPI project foundation for your CS5100 final project.

## What is implemented now

- FastAPI backend with clean layered architecture:
  - API routes
  - business orchestration service
  - provider abstraction
  - matcher abstraction
  - TTL cache utility
- End-to-end web flow:
  1. Search restaurants by **city or postal code** (`area_query`) and **required restaurant name**
  2. Choose a restaurant from name + address list
  3. Load menu: prefers **Google Maps business menus** when available; otherwise Yelp category-based placeholder items
  4. Hover a dish and view **top-5** images from either **review-photo matching** or **SerpApi Google Images search**
- Stable mock provider so the full flow works before external API integration.
- Basic tests for health check and happy-path flow.

## Project structure

```
app/
  api/                 # FastAPI routes and dependency wiring
  core/                # settings and logging
  models/              # domain models
  repositories/        # cache and storage utilities
  schemas/             # response models
  services/
    providers/         # data source adapters (mock/yelp/google)
    matching/          # image ranking adapters (lexical/clip)
  web/                 # static frontend for demo
tests/
```

## Run locally

1. Create and activate virtualenv.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. (Optional) copy `.env.example` to `.env` and adjust values.
   - To enable direct image search, set `IMAGE_SOURCE_BACKEND=serpapi_search`
   - Create a [SerpApi](https://serpapi.com/) account, generate an API key, and set `SERPAPI_API_KEY=...`
4. Start server:

```bash
uvicorn app.main:app --reload
```

5. Open:
- UI: `http://127.0.0.1:8000/`
- API docs: `http://127.0.0.1:8000/docs`

## External APIs (Google Cloud Console)

Enable for your API key (Maps Platform):

- **Places API** (legacy Autocomplete for location suggestions)
- **Places API (New)** — Text Search, Place Details, Place Photos (used for menus and extra images)

Coverage notes:

- **Google `businessMenus`** exists only for some listings and may require specific billing SKUs; if empty, the app falls back to Yelp pseudo-menu items.
- **Yelp Fusion** does not expose per-review food photos on the standard free tier; user-submitted dish photos in-app mainly come from **Google’s place photo set** (owner + contributor mix) plus **Yelp business photos**.
- **SerpApi Google Images** can be used as an alternate image source when review photos are too sparse or irrelevant; the app queries `restaurant name + dish name` and shows the returned image results directly.

## Next implementation step

1. Replace `LexicalImageMatcher` with a CLIP-based matcher under `app/services/matching/`.
2. Optional: add a dedicated menu data partner (e.g. OpenMenu or delivery-platform APIs) behind a new provider if you need broader real-menu coverage.
