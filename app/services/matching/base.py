from abc import ABC, abstractmethod

from app.models.domain import Dish, Photo


class ImageMatcher(ABC):
    @abstractmethod
    def rank(self, *, dish: Dish, photos: list[Photo], top_k: int) -> list[tuple[Photo, float]]:
        raise NotImplementedError
