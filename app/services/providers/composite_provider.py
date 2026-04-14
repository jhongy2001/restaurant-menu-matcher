import logging

from fastapi import HTTPException, status

from app.models.domain import Dish, Photo, Restaurant
from app.services.providers.base import RestaurantDataProvider
from app.services.providers.google_places_provider import GooglePlacesProvider
from app.services.providers.mock_provider import MockRestaurantProvider
from app.services.providers.yelp_provider import YelpRestaurantProvider

logger = logging.getLogger(__name__)
REAL_MODE_CONFIGURATION_ERROR = "Real data mode requires both Yelp and Google Places API keys."
REAL_MODE_UPSTREAM_ERROR = "Real data providers are unavailable. Check external API configuration and connectivity."


def _merge_photos_by_url(*groups: list[Photo]) -> list[Photo]:
    seen: set[str] = set()
    out: list[Photo] = []
    for group in groups:
        for p in group:
            key = p.url.split("?", 1)[0].rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
    return out


def _sort_photos_by_trust(photos: list[Photo]) -> list[Photo]:
    return sorted(
        photos,
        key=lambda photo: (
            photo.is_placeholder,
            not photo.is_user_contributed,
            photo.source or "zz",
            photo.id,
        ),
    )


class CompositeRestaurantProvider(RestaurantDataProvider):
    def __init__(
        self,
        *,
        mock: MockRestaurantProvider | None = None,
        yelp: YelpRestaurantProvider | None = None,
        google: GooglePlacesProvider | None = None,
        mode: str = "demo",
    ):
        self.mock = mock
        self.yelp = yelp
        self.google = google
        self.mode = mode.strip().lower()
        self._google_place_by_yelp_restaurant: dict[str, str] = {}

    def _is_real_mode(self) -> bool:
        return self.mode == "real"

    def _require_real_providers(self) -> None:
        if self.yelp and self.google:
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REAL_MODE_CONFIGURATION_ERROR,
        )

    def _mock_or_raise(self, action: str):
        if self.mock is not None:
            return self.mock
        if self._is_real_mode():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=REAL_MODE_UPSTREAM_ERROR,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No provider available for {action}.",
        )

    def suggest_locations(self, query: str) -> list[str]:
        if self._is_real_mode():
            self._require_real_providers()
        suggestions: list[str] = []
        if self.google:
            try:
                suggestions.extend(self.google.suggest_locations(query))
            except Exception:
                logger.exception("Google location suggestions failed for query=%r", query)
                if self._is_real_mode():
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=REAL_MODE_UPSTREAM_ERROR,
                    )
        if self.mock is not None:
            suggestions.extend(self.mock.suggest_locations(query))
        seen: set[str] = set()
        ordered: list[str] = []
        for s in suggestions:
            if s and s not in seen:
                seen.add(s)
                ordered.append(s)
        return ordered[:10]

    def _resolve_google_place_id(self, restaurant_id: str) -> str | None:
        if not self.google or not self.yelp or not restaurant_id.startswith("yelp:"):
            return None
        cached = self._google_place_by_yelp_restaurant.get(restaurant_id)
        if cached:
            return cached
        try:
            payload = self.yelp.get_business_payload(restaurant_id)
            name = (payload.get("name") or "").strip()
            loc = payload.get("location") or {}
            addr = ", ".join(loc.get("display_address") or [])
            query = f"{name} {addr}".strip()
            if not query:
                return None
            place_id = self.google.search_place_id(query)
            if place_id:
                self._google_place_by_yelp_restaurant[restaurant_id] = place_id
            return place_id
        except Exception:
            logger.exception("Failed to resolve Google place id for restaurant_id=%s", restaurant_id)
            return None

    def search_restaurants(self, *, area_query: str, name: str | None) -> list[Restaurant]:
        if self._is_real_mode():
            self._require_real_providers()
        if self.yelp:
            try:
                results = self.yelp.search_restaurants(area_query=area_query, name=name)
                if results:
                    return results
            except Exception:
                logger.exception(
                    "Yelp restaurant search failed for area_query=%r name=%r",
                    area_query,
                    name,
                )
                if self._is_real_mode():
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=REAL_MODE_UPSTREAM_ERROR,
                    )
        return self._mock_or_raise("restaurant search").search_restaurants(area_query=area_query, name=name)

    def get_restaurant(self, restaurant_id: str) -> Restaurant | None:
        if self._is_real_mode():
            self._require_real_providers()
        if restaurant_id.startswith("yelp:") and self.yelp:
            try:
                return self.yelp.get_restaurant(restaurant_id)
            except Exception:
                logger.exception("Yelp restaurant lookup failed for restaurant_id=%s", restaurant_id)
                if self._is_real_mode():
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=REAL_MODE_UPSTREAM_ERROR,
                    )
                return None
        return self._mock_or_raise("restaurant lookup").get_restaurant(restaurant_id)

    def get_menu(self, restaurant_id: str) -> list[Dish]:
        if self._is_real_mode():
            self._require_real_providers()
        if restaurant_id.startswith("yelp:") and self.yelp:
            if self.google:
                try:
                    place_id = self._resolve_google_place_id(restaurant_id)
                    if place_id:
                        dishes = self.google.menu_dishes_for_restaurant(restaurant_id, place_id)
                        if dishes:
                            return dishes
                except Exception:
                    logger.exception("Google menu lookup failed for restaurant_id=%s", restaurant_id)
                    if self._is_real_mode():
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=REAL_MODE_UPSTREAM_ERROR,
                        )
            try:
                return self.yelp.get_menu(restaurant_id)
            except Exception:
                logger.exception("Yelp menu extraction failed for restaurant_id=%s", restaurant_id)
                if self._is_real_mode():
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=REAL_MODE_UPSTREAM_ERROR,
                    )
                return []
        return self._mock_or_raise("menu lookup").get_menu(restaurant_id)

    def get_review_photos(self, restaurant_id: str) -> list[Photo]:
        if self._is_real_mode():
            self._require_real_providers()
        yelp_photos: list[Photo] = []
        google_photos: list[Photo] = []
        if restaurant_id.startswith("yelp:") and self.yelp:
            try:
                yelp_photos = self.yelp.get_review_photos(restaurant_id)
            except Exception:
                logger.exception("Yelp photo lookup failed for restaurant_id=%s", restaurant_id)
                if self._is_real_mode():
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=REAL_MODE_UPSTREAM_ERROR,
                    )
                yelp_photos = []
            if self.google:
                try:
                    place_id = self._resolve_google_place_id(restaurant_id)
                    if place_id:
                        google_photos = self.google.place_photos_for_restaurant(restaurant_id, place_id)
                except Exception:
                    logger.exception("Google photo lookup failed for restaurant_id=%s", restaurant_id)
                    if self._is_real_mode():
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=REAL_MODE_UPSTREAM_ERROR,
                        )
                    google_photos = []
            merged = _merge_photos_by_url(yelp_photos, google_photos)
            if self._is_real_mode():
                merged = [photo for photo in merged if not photo.is_placeholder and photo.source in {"yelp", "google_places"}]
            return _sort_photos_by_trust(merged)
        return self._mock_or_raise("photo lookup").get_review_photos(restaurant_id)
