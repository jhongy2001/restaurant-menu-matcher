from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Restaurant Menu Photo Matcher"
    app_env: str = "dev"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_debug: bool = True

    yelp_api_key: str = ""
    google_places_api_key: str = ""
    serpapi_api_key: str = ""

    data_provider_mode: str = "demo"
    image_source_backend: str = "review_match"
    image_matcher_backend: str = "hybrid"
    clip_model_name: str = "openai/clip-vit-base-patch32"
    clip_request_timeout_seconds: float = 8.0
    clip_max_images_per_request: int = 8
    serpapi_timeout_seconds: float = 8.0
    serpapi_max_results: int = 5

    default_top_k: int = 5
    max_top_k: int = 10
    cache_ttl_seconds: int = 900

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
