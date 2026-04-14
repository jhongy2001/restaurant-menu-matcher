import logging
from typing import Any

import httpx

from app.models.domain import Dish, Photo

logger = logging.getLogger(__name__)


def _localized_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return ""


def _is_likely_section_title(candidate: str, section_label: str) -> bool:
    name = candidate.strip().lower()
    section = section_label.strip().lower()
    if not name:
        return True
    if section and name == section:
        return True
    generic_titles = {
        "menu",
        "food menu",
        "main menu",
        "breakfast",
        "lunch",
        "dinner",
        "dessert",
        "drinks",
        "beverages",
        "appetizers",
        "starters",
        "entrees",
        "mains",
        "sides",
        "specials",
    }
    return name in generic_titles


class GooglePlacesProvider:
    """Legacy Autocomplete + Places API (New) for menus and photos."""

    AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    PLACES_V1 = "https://places.googleapis.com/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _v1_headers(self, field_mask: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }

    def suggest_locations(self, query: str) -> list[str]:
        text = query.strip()
        if not text:
            return []
        response = httpx.get(
            self.AUTOCOMPLETE_URL,
            params={
                "input": text,
                "types": "(regions)",
                "key": self.api_key,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        predictions = payload.get("predictions", [])
        return [item.get("description", "") for item in predictions if item.get("description")]

    def search_place_id(self, text_query: str) -> str | None:
        """Resolve a free-text query to a Google Place ID (ChIJ...)."""
        text_query = text_query.strip()
        if not text_query:
            return None
        try:
            response = httpx.post(
                f"{self.PLACES_V1}/places:searchText",
                headers=self._v1_headers("places.id,places.displayName,places.formattedAddress"),
                json={"textQuery": text_query},
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            logger.debug("Google Text Search failed: %s", exc)
            return None
        places = payload.get("places") or []
        if not places:
            return None
        return places[0].get("id") or None

    def place_details(self, place_id: str, field_mask: str) -> dict[str, Any] | None:
        if not place_id:
            return None
        try:
            response = httpx.get(
                f"{self.PLACES_V1}/places/{place_id}",
                headers=self._v1_headers(field_mask),
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            logger.debug("Google Place Details failed (%s): %s", field_mask, exc)
            return None

    def photo_media_uri(self, photo_resource_name: str) -> str | None:
        """photo_resource_name like places/ChIJ.../photos/AwD..."""
        if not photo_resource_name:
            return None
        try:
            response = httpx.get(
                f"{self.PLACES_V1}/{photo_resource_name}/media",
                params={
                    "maxWidthPx": 1600,
                    "maxHeightPx": 1600,
                    "key": self.api_key,
                },
                timeout=10.0,
                follow_redirects=False,
            )
            location = response.headers.get("location")
            if response.is_redirect and location:
                return location
            response.raise_for_status()
            if "application/json" in response.headers.get("content-type", ""):
                data = response.json()
                return data.get("photoUri") or None
        except httpx.HTTPError as exc:
            logger.debug("Google photo media failed: %s", exc)
        return None

    def menu_dishes_for_restaurant(self, restaurant_id: str, place_id: str) -> list[Dish]:
        """
        Parse Google businessMenus when available (coverage varies; may require specific Maps SKUs).
        """
        details = self.place_details(place_id, "businessMenus,displayName")
        if not details:
            return []
        menus = details.get("businessMenus") or []
        items: list[tuple[str, str]] = []
        for menu in menus:
            for section in menu.get("sections") or menu.get("section") or []:
                section_label = _localized_text(
                    section.get("displayName") or section.get("name") or section.get("title")
                )
                for entry in (
                    section.get("items")
                    or section.get("foodMenuItems")
                    or section.get("menuItems")
                    or []
                ):
                    display_name = _localized_text(entry.get("displayName"))
                    raw_name = _localized_text(entry.get("name"))
                    name = display_name or raw_name
                    labels = entry.get("labels")
                    if not name and isinstance(labels, list):
                        for lab in entry["labels"]:
                            name = _localized_text(lab.get("displayName") if isinstance(lab, dict) else lab)
                            if name:
                                break
                    desc = _localized_text(entry.get("description"))
                    if name and not _is_likely_section_title(name, section_label):
                        ctx = section_label or "Menu"
                        items.append((name, desc or f"From Google Maps menu · {ctx}"))
        dishes: list[Dish] = []
        for idx, (name, desc) in enumerate(items[:80], start=1):
            dishes.append(Dish(id=f"{restaurant_id}:gmenu:{idx}", name=name, description=desc))
        return dishes

    def place_photos_for_restaurant(self, restaurant_id: str, place_id: str) -> list[Photo]:
        """Up to 10 place photos (mix of owner and contributor per Google)."""
        details = self.place_details(place_id, "photos")
        if not details:
            return []
        raw_photos = details.get("photos") or []
        out: list[Photo] = []
        for idx, ph in enumerate(raw_photos[:10], start=1):
            resource = ph.get("name")
            uri = self.photo_media_uri(resource) if resource else None
            if not uri:
                continue
            authors = ph.get("authorAttributions") or []
            author = authors[0].get("displayName", "") if authors else ""
            cap = "Google Maps place photo"
            if author:
                cap = f"Google Maps photo · {author}"
            out.append(
                Photo(
                    id=f"{restaurant_id}:gphoto:{idx}",
                    url=uri,
                    caption=cap,
                    source="google_places",
                    is_user_contributed=bool(author),
                    is_placeholder=False,
                )
            )
        return out
