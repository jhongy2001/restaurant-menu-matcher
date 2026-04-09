from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_menu_photo_service
from app.schemas.api import (
    DishImagesResponse,
    LocationSuggestionsResponse,
    RestaurantMenuResponse,
    SearchRestaurantsResponse,
)
from app.services.menu_photo_service import MenuPhotoService

router = APIRouter(prefix="/api", tags=["menu-photo-matcher"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/locations/suggest", response_model=LocationSuggestionsResponse)
def suggest_locations(
    q: str = Query(..., min_length=1, description="City, region, or postal code"),
    service: MenuPhotoService = Depends(get_menu_photo_service),
) -> LocationSuggestionsResponse:
    return LocationSuggestionsResponse(suggestions=service.suggest_locations(q))


@router.get("/restaurants/search", response_model=SearchRestaurantsResponse)
def search_restaurants(
    area_query: str = Query(..., min_length=1, description="City, region, or postal code"),
    name: str = Query(..., min_length=1, description="Restaurant name"),
    service: MenuPhotoService = Depends(get_menu_photo_service),
) -> SearchRestaurantsResponse:
    restaurants = service.search_restaurants(area_query=area_query, name=name)
    return SearchRestaurantsResponse(restaurants=restaurants)


@router.get("/restaurants/{restaurant_id}/menu", response_model=RestaurantMenuResponse)
def get_menu(
    restaurant_id: str,
    service: MenuPhotoService = Depends(get_menu_photo_service),
) -> RestaurantMenuResponse:
    dishes = service.get_menu(restaurant_id=restaurant_id)
    return RestaurantMenuResponse(restaurant_id=restaurant_id, dishes=dishes)


@router.get("/restaurants/{restaurant_id}/dishes/{dish_id}/images", response_model=DishImagesResponse)
def get_dish_images(
    restaurant_id: str,
    dish_id: str,
    service: MenuPhotoService = Depends(get_menu_photo_service),
) -> DishImagesResponse:
    return service.get_dish_images(restaurant_id=restaurant_id, dish_id=dish_id)
