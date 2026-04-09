from app.models.domain import Dish, Photo, Restaurant
from app.services.providers.base import RestaurantDataProvider
from app.services.providers.google_places_provider import GooglePlacesProvider
from app.services.providers.mock_provider import MockRestaurantProvider
from app.services.providers.yelp_provider import YelpRestaurantProvider


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

    def suggest_locations(self, query: str) -> list[str]:
        suggestions: list[str] = []
        if self.google:
            try:
                suggestions.extend(self.google.suggest_locations(query))
            except Exception:
                pass
        suggestions.extend(self.mock.suggest_locations(query))
        # Preserve order and deduplicate.
        seen: set[str] = set()
        ordered: list[str] = []
        for s in suggestions:
            if s and s not in seen:
                seen.add(s)
                ordered.append(s)
        return ordered[:10]

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
            try:
                return self.yelp.get_menu(restaurant_id)
            except Exception:
                return []
        return self.mock.get_menu(restaurant_id)

    def get_review_photos(self, restaurant_id: str) -> list[Photo]:
        if restaurant_id.startswith("yelp:") and self.yelp:
            try:
                return self.yelp.get_review_photos(restaurant_id)
            except Exception:
                return []
        return self.mock.get_review_photos(restaurant_id)
