import logging
from collections.abc import Iterable

import httpx

from app.models.domain import Dish, Photo

logger = logging.getLogger(__name__)


class SerpApiImageSearch:
    BASE_URL = "https://serpapi.com/search"

    def __init__(self, *, api_key: str, timeout_seconds: float, max_results: int) -> None:
        self.api_key = api_key.strip()
        self.timeout_seconds = timeout_seconds
        self.max_results = max(1, max_results)

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def build_query(self, *, restaurant_name: str, dish: Dish) -> str:
        return " ".join(part for part in (restaurant_name.strip(), dish.name.strip()) if part).strip()

    def _caption_for_result(self, result: dict, fallback: str) -> str:
        title = str(result.get("title") or "").strip()
        source = str(result.get("source") or "").strip()
        if title and source:
            return f"{title} | {source}"
        if title:
            return title
        if source:
            return source
        return fallback

    def _iter_photo_results(self, *, query: str, image_results: Iterable[dict], limit: int) -> list[Photo]:
        photos: list[Photo] = []
        for idx, result in enumerate(image_results, start=1):
            photo_url = str(result.get("original") or result.get("thumbnail") or "").strip()
            if not photo_url or photo_url.startswith("data:"):
                continue
            photos.append(
                Photo(
                    id=f"serpapi:{query}:{idx}",
                    url=photo_url,
                    caption=self._caption_for_result(result, fallback=query),
                    source="serpapi",
                    is_user_contributed=False,
                    is_placeholder=False,
                )
            )
            if len(photos) >= limit:
                break
        return photos

    def search_images(self, *, restaurant_name: str, dish: Dish, top_k: int) -> list[Photo]:
        if not self.is_configured():
            raise RuntimeError("SERPAPI_API_KEY is required when IMAGE_SOURCE_BACKEND=serpapi_search.")

        query = self.build_query(restaurant_name=restaurant_name, dish=dish)
        if not query:
            return []

        response = httpx.get(
            self.BASE_URL,
            params={
                "engine": "google_images",
                "q": query,
                "api_key": self.api_key,
                "safe": "active",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        error_message = payload.get("error") or payload.get("error_message")
        if error_message:
            raise RuntimeError(f"SerpApi image search failed: {error_message}")

        limit = min(top_k, self.max_results)
        photos = self._iter_photo_results(
            query=query,
            image_results=payload.get("images_results") or [],
            limit=limit,
        )
        logger.debug("SerpApi returned %s image results for query=%r", len(photos), query)
        return photos
