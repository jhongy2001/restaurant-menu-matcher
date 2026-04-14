import logging

import httpx
from fastapi import HTTPException, status

from app.core.config import Settings
from app.models.domain import Dish, Photo, Restaurant
from app.repositories.ttl_cache import TTLCache
from app.schemas.api import DishImagesResponse, DishItem, ImageMatchItem, RestaurantItem
from app.services.image_search.serpapi_image_search import SerpApiImageSearch
from app.services.matching.base import ImageMatcher
from app.services.providers.base import RestaurantDataProvider

logger = logging.getLogger(__name__)


class MenuPhotoService:
    def __init__(
        self,
        provider: RestaurantDataProvider,
        matcher: ImageMatcher,
        settings: Settings,
        image_search: SerpApiImageSearch | None = None,
    ):
        self.provider = provider
        self.matcher = matcher
        self.settings = settings
        self.image_search = image_search
        self.menu_cache = TTLCache[list[Dish]](ttl_seconds=settings.cache_ttl_seconds)
        self.restaurant_cache = TTLCache[Restaurant | None](ttl_seconds=settings.cache_ttl_seconds)

    def suggest_locations(self, query: str) -> list[str]:
        if not query.strip():
            return []
        return self.provider.suggest_locations(query)

    def search_restaurants(self, area_query: str | None, name: str | None) -> list[RestaurantItem]:
        if not area_query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="area_query is required.",
            )
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Restaurant name is required.",
            )
        restaurants = self.provider.search_restaurants(area_query=area_query, name=name)
        return [
            RestaurantItem(
                id=r.id,
                name=r.name,
                address=r.address,
                city=r.city,
                postal_code=r.postal_code,
                source=r.source,
            )
            for r in restaurants
        ]

    def get_menu(self, restaurant_id: str) -> list[DishItem]:
        dishes = self.menu_cache.get_or_set(
            f"menu:{restaurant_id}",
            lambda: self.provider.get_menu(restaurant_id),
        )
        return [DishItem(id=d.id, name=d.name, description=d.description) for d in dishes]

    def _serialize_ranked_matches(
        self,
        *,
        restaurant_id: str,
        dish: Dish,
        top_k: int,
        ranked: list[tuple[Photo, float]],
    ) -> DishImagesResponse:
        return DishImagesResponse(
            restaurant_id=restaurant_id,
            dish_id=dish.id,
            dish_name=dish.name,
            top_k=top_k,
            matches=[
                ImageMatchItem(
                    photo_id=photo.id,
                    photo_url=photo.url,
                    score=round(score, 4),
                    caption=photo.caption,
                    source=photo.source,
                    is_user_contributed=photo.is_user_contributed,
                    is_placeholder=photo.is_placeholder,
                )
                for photo, score in ranked
            ],
        )

    def _get_cached_menu(self, restaurant_id: str) -> list[Dish]:
        return self.menu_cache.get_or_set(
            f"menu:{restaurant_id}",
            lambda: self.provider.get_menu(restaurant_id),
        )

    def _get_cached_restaurant(self, restaurant_id: str) -> Restaurant | None:
        return self.restaurant_cache.get_or_set(
            f"restaurant:{restaurant_id}",
            lambda: self.provider.get_restaurant(restaurant_id),
        )

    def _get_ranked_review_matches(self, *, restaurant_id: str, dish: Dish, top_k: int) -> list[tuple[Photo, float]]:
        photos = self.provider.get_review_photos(restaurant_id)
        if not photos:
            return []
        return self.matcher.rank(dish=dish, photos=photos, top_k=top_k)

    def _get_serpapi_matches(self, *, restaurant_id: str, dish: Dish, top_k: int) -> list[tuple[Photo, float]]:
        restaurant = self._get_cached_restaurant(restaurant_id)
        if restaurant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found.")
        if self.image_search is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Image search backend is unavailable for IMAGE_SOURCE_BACKEND=serpapi_search.",
            )
        try:
            photos = self.image_search.search_images(restaurant_name=restaurant.name, dish=dish, top_k=top_k)
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            logger.exception("SerpApi image search request failed for restaurant_id=%s dish_id=%s", restaurant_id, dish.id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SerpApi image search is unavailable. Check the API key and network connectivity.",
            ) from exc
        return [
            (photo, round(max(0.0, 1.0 - ((idx - 1) * 0.01)), 4))
            for idx, photo in enumerate(photos, start=1)
        ]

    def get_dish_images(self, restaurant_id: str, dish_id: str, top_k: int | None = None) -> DishImagesResponse:
        top_k = top_k or self.settings.default_top_k
        top_k = max(1, min(top_k, self.settings.max_top_k))
        dishes = self._get_cached_menu(restaurant_id)
        dish = next((d for d in dishes if d.id == dish_id), None)
        if dish is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dish not found.")

        backend = self.settings.image_source_backend.strip().lower()
        if backend == "serpapi_search":
            ranked = self._get_serpapi_matches(restaurant_id=restaurant_id, dish=dish, top_k=top_k)
        elif backend == "review_match":
            ranked = self._get_ranked_review_matches(restaurant_id=restaurant_id, dish=dish, top_k=top_k)
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unsupported image source backend: {self.settings.image_source_backend}.",
            )

        return self._serialize_ranked_matches(
            restaurant_id=restaurant_id,
            dish=dish,
            top_k=top_k,
            ranked=ranked,
        )
