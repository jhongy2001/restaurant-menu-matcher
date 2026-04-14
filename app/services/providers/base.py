from abc import ABC, abstractmethod

from app.models.domain import Dish, Photo, Restaurant


class RestaurantDataProvider(ABC):
    @abstractmethod
    def suggest_locations(self, query: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def search_restaurants(self, *, area_query: str, name: str | None) -> list[Restaurant]:
        raise NotImplementedError

    @abstractmethod
    def get_restaurant(self, restaurant_id: str) -> Restaurant | None:
        raise NotImplementedError

    @abstractmethod
    def get_menu(self, restaurant_id: str) -> list[Dish]:
        raise NotImplementedError

    @abstractmethod
    def get_review_photos(self, restaurant_id: str) -> list[Photo]:
        raise NotImplementedError
