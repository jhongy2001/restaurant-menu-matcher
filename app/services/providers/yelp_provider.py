import logging

import httpx

from app.models.domain import Dish, Photo, Restaurant
from app.services.providers.base import RestaurantDataProvider

logger = logging.getLogger(__name__)


class YelpRestaurantProvider(RestaurantDataProvider):
    BASE_URL = "https://api.yelp.com/v3"
    FALLBACK_FOOD_IMAGES = [
        "https://images.unsplash.com/photo-1557872943-16a5ac26437e",
        "https://images.unsplash.com/photo-1585032226651-759b368d7246",
        "https://images.unsplash.com/photo-1612929633738-8fe44f7ec841",
        "https://images.unsplash.com/photo-1604908177522-0407c68f1882",
        "https://images.unsplash.com/photo-1617093727343-374698b1b08d",
    ]

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._business_payload_cache: dict[str, dict] = {}

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.BASE_URL,
            timeout=10.0,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def suggest_locations(self, query: str) -> list[str]:
        # Yelp does not provide a dedicated location autocomplete endpoint.
        # Return the current text as fallback option.
        value = query.strip()
        return [value] if value else []

    def search_restaurants(self, *, area_query: str, name: str | None) -> list[Restaurant]:
        params = {
            "term": name or "restaurant",
            "location": area_query,
            "categories": "restaurants",
            "limit": 15,
        }
        with self._client() as client:
            response = client.get("/businesses/search", params=params)
            response.raise_for_status()
            payload = response.json()
        businesses = payload.get("businesses", [])
        results: list[Restaurant] = []
        for b in businesses:
            location = b.get("location", {})
            results.append(
                Restaurant(
                    id=f"yelp:{b.get('id', '')}",
                    name=b.get("name", "Unknown"),
                    address=", ".join(location.get("display_address", [])),
                    city=location.get("city", ""),
                    postal_code=location.get("zip_code", ""),
                    source="yelp",
                )
            )
        return results

    def _strip_id(self, restaurant_id: str) -> str:
        return restaurant_id.split(":", 1)[1] if restaurant_id.startswith("yelp:") else restaurant_id

    def get_business_payload(self, restaurant_id: str) -> dict:
        """Cached Yelp business details (used for menu, photos, and Google place resolution)."""
        business_id = self._strip_id(restaurant_id)
        if business_id in self._business_payload_cache:
            return self._business_payload_cache[business_id]
        with self._client() as client:
            response = client.get(f"/businesses/{business_id}")
            response.raise_for_status()
            payload = response.json()
        self._business_payload_cache[business_id] = payload
        return payload

    def get_menu(self, restaurant_id: str) -> list[Dish]:
        # Yelp API does not provide structured menu; generate stable pseudo-menu from categories.
        payload = self.get_business_payload(restaurant_id)
        categories = [c.get("title", "") for c in payload.get("categories", []) if c.get("title")]
        if not categories:
            categories = ["Chef Special"]
        dishes: list[Dish] = []
        for idx, category in enumerate(categories[:6], start=1):
            dishes.append(
                Dish(
                    id=f"{restaurant_id}:dish:{idx}",
                    name=f"{category} Signature",
                    description=f"Representative dish generated from Yelp category: {category}",
                )
            )
        return dishes

    def get_review_photos(self, restaurant_id: str) -> list[Photo]:
        payload = self.get_business_payload(restaurant_id)
        urls = list(payload.get("photos", []) or [])
        # Yelp business details sometimes omit `photos`; use `image_url` as fallback.
        if not urls and payload.get("image_url"):
            urls = [payload["image_url"]]
        if not urls:
            urls = self.FALLBACK_FOOD_IMAGES
        photos: list[Photo] = []
        for idx, url in enumerate(urls, start=1):
            photos.append(
                Photo(
                    id=f"{restaurant_id}:photo:{idx}",
                    url=url,
                    caption="Yelp listing photo food restaurant",
                )
            )
        return photos
