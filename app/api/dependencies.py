from functools import lru_cache

from app.core.config import get_settings
from app.services.matching.lexical_matcher import LexicalImageMatcher
from app.services.menu_photo_service import MenuPhotoService
from app.services.providers.composite_provider import CompositeRestaurantProvider
from app.services.providers.google_places_provider import GooglePlacesProvider
from app.services.providers.mock_provider import MockRestaurantProvider
from app.services.providers.yelp_provider import YelpRestaurantProvider


@lru_cache
def get_menu_photo_service() -> MenuPhotoService:
    settings = get_settings()
    mock = MockRestaurantProvider()
    yelp = YelpRestaurantProvider(settings.yelp_api_key) if settings.yelp_api_key else None
    google = GooglePlacesProvider(settings.google_places_api_key) if settings.google_places_api_key else None
    provider = CompositeRestaurantProvider(mock=mock, yelp=yelp, google=google)
    matcher = LexicalImageMatcher()
    return MenuPhotoService(provider=provider, matcher=matcher, settings=settings)
