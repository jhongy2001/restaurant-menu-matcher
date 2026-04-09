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
  1. Search restaurants by `location` or `postal code`
  2. Choose a restaurant from name + address list
  3. Load menu dishes and descriptions
  4. Click a dish and view top-k matched images
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
4. Start server:

```bash
uvicorn app.main:app --reload
```

5. Open:
- UI: `http://127.0.0.1:8000/`
- API docs: `http://127.0.0.1:8000/docs`

## Next implementation step (no refactor needed)

1. Add `YelpRestaurantProvider` and `GooglePlacesProvider` under `app/services/providers/`.
2. Add provider selection/fallback policy in `app/api/dependencies.py`.
3. Replace `LexicalImageMatcher` with CLIP-based matcher implementation in `app/services/matching/`.
4. Keep all API routes and frontend unchanged.
