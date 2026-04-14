import logging
from functools import lru_cache

from fastapi import HTTPException, status

from app.core.config import Settings, get_settings
from app.services.image_search.serpapi_image_search import SerpApiImageSearch
from app.services.matching.clip_matcher import ClipImageMatcher
from app.services.matching.lexical_matcher import LexicalImageMatcher
from app.services.menu_photo_service import MenuPhotoService
from app.services.providers.composite_provider import CompositeRestaurantProvider
from app.services.providers.google_places_provider import GooglePlacesProvider
from app.services.providers.mock_provider import MockRestaurantProvider
from app.services.providers.yelp_provider import YelpRestaurantProvider

logger = logging.getLogger(__name__)

VALID_DATA_PROVIDER_MODES = {"demo", "real"}


def build_image_matcher(settings: Settings):
    fallback = LexicalImageMatcher()
    backend = settings.image_matcher_backend.strip().lower()
    if backend == "lexical":
        return fallback
    if backend not in {"clip", "hybrid"}:
        logger.warning("Unknown image matcher backend=%r; using lexical fallback.", settings.image_matcher_backend)
        return fallback
    return ClipImageMatcher(
        model_name=settings.clip_model_name,
        request_timeout_seconds=settings.clip_request_timeout_seconds,
        max_images_per_request=settings.clip_max_images_per_request,
        fallback_matcher=fallback,
    )


def build_image_search(settings: Settings) -> SerpApiImageSearch | None:
    backend = settings.image_source_backend.strip().lower()
    if backend == "review_match":
        return None
    if backend == "serpapi_search":
        return SerpApiImageSearch(
            api_key=settings.serpapi_api_key,
            timeout_seconds=settings.serpapi_timeout_seconds,
            max_results=settings.serpapi_max_results,
        )
    logger.warning("Unknown image source backend=%r; using review photo matching.", settings.image_source_backend)
    return None


def build_restaurant_provider(settings: Settings) -> CompositeRestaurantProvider:
    mode = settings.data_provider_mode.strip().lower()
    if mode not in VALID_DATA_PROVIDER_MODES:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unsupported data provider mode: {settings.data_provider_mode}.",
        )
    if mode == "real" and (not settings.yelp_api_key or not settings.google_places_api_key):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Real data mode requires both Yelp and Google Places API keys.",
        )

    mock = MockRestaurantProvider() if mode == "demo" else None
    yelp = (
        YelpRestaurantProvider(
            settings.yelp_api_key,
            serpapi_api_key=settings.serpapi_api_key,
            serpapi_timeout_seconds=settings.serpapi_timeout_seconds,
            serpapi_max_results=settings.serpapi_max_results,
        )
        if settings.yelp_api_key
        else None
    )
    google = GooglePlacesProvider(settings.google_places_api_key) if settings.google_places_api_key else None
    return CompositeRestaurantProvider(mock=mock, yelp=yelp, google=google, mode=mode)


@lru_cache
def get_menu_photo_service() -> MenuPhotoService:
    settings = get_settings()
    provider = build_restaurant_provider(settings)
    matcher = build_image_matcher(settings)
    image_search = build_image_search(settings)
    return MenuPhotoService(provider=provider, matcher=matcher, settings=settings, image_search=image_search)
