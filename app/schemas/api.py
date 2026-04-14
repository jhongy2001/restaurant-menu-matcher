from pydantic import BaseModel, Field


class RestaurantItem(BaseModel):
    id: str
    name: str
    address: str
    city: str
    postal_code: str
    source: str


class DishItem(BaseModel):
    id: str
    name: str
    description: str = ""


class ImageMatchItem(BaseModel):
    photo_id: str
    photo_url: str
    score: float = Field(ge=0.0, le=1.0)
    caption: str = ""
    source: str = ""
    is_user_contributed: bool = False
    is_placeholder: bool = False


class SearchRestaurantsResponse(BaseModel):
    restaurants: list[RestaurantItem]


class LocationSuggestionsResponse(BaseModel):
    suggestions: list[str]


class RestaurantMenuResponse(BaseModel):
    restaurant_id: str
    dishes: list[DishItem]


class DishImagesResponse(BaseModel):
    restaurant_id: str
    dish_id: str
    dish_name: str
    top_k: int
    matches: list[ImageMatchItem]
