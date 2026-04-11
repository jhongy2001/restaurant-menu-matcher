from app.models.domain import Dish, Photo, Restaurant
from app.services.providers.base import RestaurantDataProvider
from app.services.providers.google_places_provider import GooglePlacesProvider
from app.services.providers.mock_provider import MockRestaurantProvider
from app.services.providers.yelp_provider import YelpRestaurantProvider


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


class CompositeRestaurantProvider(RestaurantDataProvider):
    def __init__(
        self,
        *,
        mock: MockRestaurantProvider,
        yelp: YelpRestaurantProvider | None = None,
        google: GooglePlacesProvider | None = None,
    ):
        self.mock = mock
        self.yelp = yelp
        self.google = google
        self._google_place_by_yelp_restaurant: dict[str, str] = {}

    def suggest_locations(self, query: str) -> list[str]:
        suggestions: list[str] = []
        if self.google:
            try:
                suggestions.extend(self.google.suggest_locations(query))
            except Exception:
                pass
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
            return None

    def search_restaurants(self, *, area_query: str, name: str | None) -> list[Restaurant]:
        if self.yelp:
            try:
                results = self.yelp.search_restaurants(area_query=area_query, name=name)
                if results:
                    return results
            except Exception:
                pass
        return self.mock.search_restaurants(area_query=area_query, name=name)

    def get_menu(self, restaurant_id: str) -> list[Dish]:
        if restaurant_id.startswith("yelp:") and self.yelp:
            if self.google:
                try:
                    place_id = self._resolve_google_place_id(restaurant_id)
                    if place_id:
                        dishes = self.google.menu_dishes_for_restaurant(restaurant_id, place_id)
                        if dishes:
                            return dishes
                except Exception:
                    pass
            try:
                return self.yelp.get_menu(restaurant_id)
            except Exception:
                return []
        return self.mock.get_menu(restaurant_id)

    def get_review_photos(self, restaurant_id: str) -> list[Photo]:
        yelp_photos: list[Photo] = []
        google_photos: list[Photo] = []
        if restaurant_id.startswith("yelp:") and self.yelp:
            try:
                yelp_photos = self.yelp.get_review_photos(restaurant_id)
            except Exception:
                yelp_photos = []
            if self.google:
                try:
                    place_id = self._resolve_google_place_id(restaurant_id)
                    if place_id:
                        google_photos = self.google.place_photos_for_restaurant(restaurant_id, place_id)
                except Exception:
                    google_photos = []
            return _merge_photos_by_url(yelp_photos, google_photos)
        return self.mock.get_review_photos(restaurant_id)
