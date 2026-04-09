from app.models.domain import Dish, Photo, Restaurant
from app.services.providers.base import RestaurantDataProvider


class MockRestaurantProvider(RestaurantDataProvider):
    """
    Stable mock provider for early-stage development and demos.
    Replace with Yelp/Google adapters without changing business logic.
    """

    def __init__(self) -> None:
        self._restaurants: list[Restaurant] = [
            Restaurant(
                id="r1",
                name="Tokyo Ramen House",
                address="123 Main St",
                city="Boston",
                postal_code="02115",
                source="mock",
            ),
            Restaurant(
                id="r2",
                name="Golden Wok",
                address="88 Harvard Ave",
                city="Boston",
                postal_code="02134",
                source="mock",
            ),
        ]
        self._menus: dict[str, list[Dish]] = {
            "r1": [
                Dish(id="d1", name="Spicy Tonkotsu Ramen", description="Rich pork broth with chili oil and soft-boiled egg"),
                Dish(id="d2", name="Chicken Karaage", description="Japanese style fried chicken with lemon"),
                Dish(id="d3", name="Miso Ramen", description="Savory miso-based broth with chashu and corn"),
            ],
            "r2": [
                Dish(id="d4", name="Mapo Tofu", description="Silken tofu in spicy Sichuan pepper sauce"),
                Dish(id="d5", name="Kung Pao Chicken", description="Stir-fried chicken with peanuts and dried chili"),
                Dish(id="d6", name="Dan Dan Noodles", description="Noodles with sesame paste and minced pork"),
            ],
        }
        self._photos: dict[str, list[Photo]] = {
            "r1": [
                Photo(id="p1", url="https://images.unsplash.com/photo-1557872943-16a5ac26437e", caption="Tonkotsu ramen bowl"),
                Photo(id="p2", url="https://images.unsplash.com/photo-1617093727343-374698b1b08d", caption="Crispy fried chicken karaage"),
                Photo(id="p3", url="https://images.unsplash.com/photo-1617196038435-89d4f5f4d6c0", caption="Miso ramen with corn"),
                Photo(id="p4", url="https://images.unsplash.com/photo-1512003867696-6d5ce6835040", caption="Assorted japanese dishes"),
            ],
            "r2": [
                Photo(id="p5", url="https://images.unsplash.com/photo-1585032226651-759b368d7246", caption="Mapo tofu close-up"),
                Photo(id="p6", url="https://images.unsplash.com/photo-1604908177522-0407c68f1882", caption="Kung pao chicken in wok"),
                Photo(id="p7", url="https://images.unsplash.com/photo-1612929633738-8fe44f7ec841", caption="Spicy noodles with chili oil"),
                Photo(id="p8", url="https://images.unsplash.com/photo-1526318896980-cf78c088247c", caption="Chinese home style dishes"),
            ],
        }

    def suggest_locations(self, query: str) -> list[str]:
        q = query.strip().lower()
        suggestions = {
            "Boston",
            "02115",
            "02134",
        }
        if not q:
            return sorted(suggestions)
        return sorted([s for s in suggestions if q in s.lower()])

    def search_restaurants(self, *, area_query: str, name: str | None) -> list[Restaurant]:
        area_query = (area_query or "").strip().lower()
        name = (name or "").strip().lower()

        results = self._restaurants
        if area_query:
            results = [r for r in results if area_query in r.city.lower() or area_query in r.postal_code]
        if name:
            results = [r for r in results if name in r.name.lower()]
        return results

    def get_menu(self, restaurant_id: str) -> list[Dish]:
        return self._menus.get(restaurant_id, [])

    def get_review_photos(self, restaurant_id: str) -> list[Photo]:
        return self._photos.get(restaurant_id, [])
