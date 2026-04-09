from fastapi import HTTPException, status

from app.core.config import Settings
from app.models.domain import Dish
from app.repositories.ttl_cache import TTLCache
from app.schemas.api import DishImagesResponse, DishItem, ImageMatchItem, RestaurantItem
from app.services.matching.base import ImageMatcher
from app.services.providers.base import RestaurantDataProvider


class MenuPhotoService:
    def __init__(self, provider: RestaurantDataProvider, matcher: ImageMatcher, settings: Settings):
        self.provider = provider
        self.matcher = matcher
        self.settings = settings
        self.menu_cache = TTLCache[list[Dish]](ttl_seconds=settings.cache_ttl_seconds)

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

    def get_dish_images(self, restaurant_id: str, dish_id: str, top_k: int | None = None) -> DishImagesResponse:
        # Product requirement: fixed top-k = 5 in code, not user-configurable.
        top_k = 5
        dishes = self.menu_cache.get_or_set(
            f"menu:{restaurant_id}",
            lambda: self.provider.get_menu(restaurant_id),
        )
        dish = next((d for d in dishes if d.id == dish_id), None)
        if dish is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dish not found.")

        photos = self.provider.get_review_photos(restaurant_id)
        if not photos:
            return DishImagesResponse(
                restaurant_id=restaurant_id,
                dish_id=dish.id,
                dish_name=dish.name,
                top_k=top_k,
                matches=[],
            )

        ranked = self.matcher.rank(dish=dish, photos=photos, top_k=top_k)
        return DishImagesResponse(
            restaurant_id=restaurant_id,
            dish_id=dish.id,
            dish_name=dish.name,
            top_k=top_k,
            matches=[
                ImageMatchItem(photo_id=p.id, photo_url=p.url, score=round(score, 4), caption=p.caption)
                for p, score in ranked
            ],
        )
