import json
import logging
import re
from html import unescape
from urllib.parse import urljoin, urlparse

import httpx

from app.models.domain import Dish, Photo, Restaurant
from app.services.providers.base import RestaurantDataProvider

logger = logging.getLogger(__name__)


class YelpRestaurantProvider(RestaurantDataProvider):
    BASE_URL = "https://api.yelp.com/v3"
    SERPAPI_URL = "https://serpapi.com/search"
    MENU_SEARCH_SUFFIXES = ("menu", "ubereats", "doordash", "grubhub", "singleplatform")
    MENU_DENYLIST_HOSTS = (
        "facebook.com",
        "instagram.com",
        "reddit.com",
        "findmeglutenfree.com",
        "wheree.com",
    )
    MENU_CATEGORY_PATTERN = re.compile(
        r"""(?P<link>https?://[^\s"'<>]+/full-menu/[^\s"'<>]+\.html|/[^"'<>]*full-menu/[^"'<>]+\.html)"""
    )
    PRODUCT_LINK_PATTERN = re.compile(
        r"""(?P<link>https?://[^\s"'<>]+/product/[^\s"'<>]+\.html|/[^"'<>]*product/[^"'<>]+\.html)"""
    )
    GENERIC_MENU_LINK_PATTERN = re.compile(
        r"""href=["'](?P<link>[^"'<>]+(?:menu|menus|order|ordering|lunch|dinner)[^"'<>]*)["']""",
        re.IGNORECASE,
    )
    JSON_LD_PATTERN = re.compile(
        r"""<script[^>]+type=["']application/ld\+json["'][^>]*>(?P<body>[\s\S]*?)</script>""",
        re.IGNORECASE,
    )
    MENU_TEXT_PATTERN = re.compile(
        r"""<(?P<tag>li|a|button|div|span|h2|h3|h4|p)\b(?P<attrs>[^>]*)>(?P<body>[\s\S]{1,240}?)</(?P=tag)>""",
        re.IGNORECASE,
    )
    MENU_STOPWORDS = {
        "menu",
        "lunch menu",
        "dinner menu",
        "drink menu",
        "full menu",
        "breakfast",
        "appetizers",
        "appetizer",
        "salad",
        "salads",
        "soup",
        "soups",
        "salad soup",
        "dinner entrees",
        "lunch entrees",
        "entrees",
        "sides",
        "side orders",
        "dessert",
        "desserts",
        "starters",
        "drinks",
        "soda",
        "noodle",
        "noodles",
        "sushi sashimi",
        "makimono",
        "vegetarian rolls",
        "special rolls",
        "baked rolls",
        "deep fried rolls",
        "party tray",
        "burgers",
        "chicken fish sandwiches",
        "fries sides",
        "sweets treats",
        "beverages",
        "sauces condiments",
        "featured favorites",
        "order now",
        "start order",
        "nutrition",
        "info hours",
        "all day menu",
        "clear",
        "clear search",
        "list",
        "view all",
        "learn more",
        "featured",
        "featured items",
        "group order",
        "heart",
        "three dots horizontal",
        "rating and reviews",
        "recommended",
        "reported gf menu items",
        "popular items",
        "most popular",
        "add to order",
        "customize",
        "choose options",
        "home",
        "our story",
        "reservation",
        "reservations",
        "contact",
        "news",
        "catering",
        "online order",
        "skip to content",
        "close",
        "google maps",
        "sign in",
        "sign up",
        "download our app",
        "premium",
        "local",
        "chains",
        "pricing",
        "large",
        "small",
        "location",
        "locations",
        "english",
        "chinese",
        "japanese",
        "korean",
        "spanish",
        "french",
        "italian",
        "german",
        "thai",
        "vietnamese",
        "language",
        "faq",
        "faqs",
        "frequently asked questions",
        "accessibility",
        "privacy",
        "privacy policy",
        "terms",
        "terms of use",
        "terms and conditions",
        "terms & conditions",
        "policy",
        "policies",
        "help",
        "support",
        "feedback",
        "login",
        "log in",
        "log out",
        "logout",
        "register",
        "cart",
        "checkout",
        "search",
        "find",
        "my account",
        "profile",
        "settings",
        "directions",
        "hours",
        "map",
        "franchise",
        "franchising",
        "merch",
        "merchandise",
        "rewards",
        "loyalty",
        "deals",
        "offers",
        "coupons",
    }
    MENU_CONTEXT_HINTS = ("menu", "item", "dish", "product", "entree", "appetizer", "special")
    MENU_BAD_SUBSTRINGS = (
        "order now",
        "online order",
        "view our menu",
        "view our menus",
        "menu categories",
        "skip to content",
        "powered by",
        "privacy policy",
        "terms of service",
        "no results found",
        "not accepting online orders",
        "download our app",
        "google maps",
        "sign in",
        "sign up",
        "reported gf",
    )
    MENU_LOW_SIGNAL_PHRASES = {
        "about",
        "about us",
        "additional services",
        "add deal",
        "all locations",
        "careers",
        "carryout",
        "corporate",
        "customer support",
        "delivery",
        "drive thru",
        "email text offers",
        "find a kfc",
        "financial information",
        "gift cards",
        "gluten free warning",
        "ingredients",
        "investor inquiries",
        "investor resources",
        "jobs",
        "legal",
        "offer details",
        "open mobile menu",
        "our company",
        "our pizza",
        "press releases",
        "specialty pizza",
        "start building your own pizza",
        "stock information",
        "trending",
        "wifi",
    }
    MENU_LOW_VALUE_PATTERNS = (
        re.compile(r"^customize\b", re.IGNORECASE),
        re.compile(r"\bdipping cup\b", re.IGNORECASE),
        re.compile(r"\bdressing\b", re.IGNORECASE),
        re.compile(r"^free with\b", re.IGNORECASE),
        re.compile(r"^\d+%\s+off\b", re.IGNORECASE),
    )
    MENU_ENTREE_HINTS = {
        "alfredo",
        "bacon",
        "bbq",
        "bites",
        "bowl",
        "bread",
        "brownie",
        "burger",
        "cake",
        "calzone",
        "caesar",
        "cheese",
        "chicken",
        "combo",
        "cookie",
        "corn",
        "crust",
        "dessert",
        "fries",
        "mac",
        "meal",
        "nuggets",
        "pasta",
        "pepperoni",
        "pie",
        "pizza",
        "potatoes",
        "salad",
        "sandwich",
        "slaw",
        "steak",
        "tenders",
        "tots",
        "wings",
    }
    PRICE_PATTERN = re.compile(r"""^\$?\d+(?:[.,]\d{1,2})?$""")
    PHONE_PATTERN = re.compile(r"""\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}""")
    RATING_PATTERN = re.compile(r"""^\d{1,3}%\s*\(\d+\)$""")
    MENU_JSON_HINTS = {
        "menu",
        "menuitem",
        "menusection",
        "hasmenu",
        "hasmenuitem",
        "offers",
        "price",
        "pricecurrency",
    }

    def __init__(
        self,
        api_key: str,
        *,
        serpapi_api_key: str = "",
        serpapi_timeout_seconds: float = 8.0,
        serpapi_max_results: int = 5,
    ):
        self.api_key = api_key
        self.serpapi_api_key = serpapi_api_key.strip()
        self.serpapi_timeout_seconds = serpapi_timeout_seconds
        self.serpapi_max_results = max(1, serpapi_max_results)
        self._business_payload_cache: dict[str, dict] = {}
        self._menu_page_cache: dict[str, str] = {}

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.BASE_URL,
            timeout=10.0,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def suggest_locations(self, query: str) -> list[str]:
        # Yelp does not provide a dedicated location autocomplete endpoint.
        # Return the current text as fallback option.
        value = query.strip()
        return [value] if value else []

    def search_restaurants(self, *, area_query: str, name: str | None) -> list[Restaurant]:
        params = {
            "term": name or "restaurant",
            "location": area_query,
            "categories": "restaurants",
            "limit": 15,
        }
        with self._client() as client:
            response = client.get("/businesses/search", params=params)
            response.raise_for_status()
            payload = response.json()
        businesses = payload.get("businesses", [])
        results: list[Restaurant] = []
        for b in businesses:
            location = b.get("location", {})
            results.append(
                Restaurant(
                    id=f"yelp:{b.get('id', '')}",
                    name=b.get("name", "Unknown"),
                    address=", ".join(location.get("display_address", [])),
                    city=location.get("city", ""),
                    postal_code=location.get("zip_code", ""),
                    source="yelp",
                )
            )
        return results

    def get_restaurant(self, restaurant_id: str) -> Restaurant | None:
        payload = self.get_business_payload(restaurant_id)
        if not payload:
            return None
        location = payload.get("location", {})
        return Restaurant(
            id=restaurant_id,
            name=payload.get("name", "Unknown"),
            address=", ".join(location.get("display_address", [])),
            city=location.get("city", ""),
            postal_code=location.get("zip_code", ""),
            source="yelp",
        )

    def _strip_id(self, restaurant_id: str) -> str:
        return restaurant_id.split(":", 1)[1] if restaurant_id.startswith("yelp:") else restaurant_id

    def get_business_payload(self, restaurant_id: str) -> dict:
        """Cached Yelp business details (used for menu, photos, and Google place resolution)."""
        business_id = self._strip_id(restaurant_id)
        if business_id in self._business_payload_cache:
            return self._business_payload_cache[business_id]
        with self._client() as client:
            response = client.get(f"/businesses/{business_id}")
            response.raise_for_status()
            payload = response.json()
        self._business_payload_cache[business_id] = payload
        return payload

    def get_menu_url(self, restaurant_id: str) -> str | None:
        payload = self.get_business_payload(restaurant_id)
        attributes = payload.get("attributes") or {}
        menu_url = (attributes.get("menu_url") or "").strip()
        return menu_url or None

    def _menu_search_query(self, restaurant_id: str, suffix: str) -> str:
        payload = self.get_business_payload(restaurant_id)
        name = str(payload.get("name") or "").strip()
        location = payload.get("location") or {}
        city = str(location.get("city") or "").strip()
        return " ".join(part for part in (name, city, suffix) if part).strip()

    def _search_menu_candidate_urls(self, restaurant_id: str) -> list[str]:
        if not self.serpapi_api_key:
            return []

        candidates: list[str] = []
        seen: set[str] = set()

        def add_candidate(link: str, title: str = "", snippet: str = "") -> None:
            normalized = (link or "").strip()
            if not normalized or normalized in seen:
                return
            lowered_link = normalized.lower()
            context = " ".join(part for part in (title, snippet, normalized) if part).lower()
            if any(host in lowered_link for host in self.MENU_DENYLIST_HOSTS):
                return
            if "yelp.com" in lowered_link and "/menu" not in lowered_link:
                return
            if not any(token in context for token in ("menu", "order", "food", "dinner", "lunch", "breakfast", "pdf")):
                return
            seen.add(normalized)
            candidates.append(normalized)

        for suffix in self.MENU_SEARCH_SUFFIXES:
            query = self._menu_search_query(restaurant_id, suffix)
            if not query:
                continue
            try:
                response = httpx.get(
                    self.SERPAPI_URL,
                    params={
                        "engine": "google",
                        "q": query,
                        "api_key": self.serpapi_api_key,
                        "num": self.serpapi_max_results,
                    },
                    timeout=self.serpapi_timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPError as exc:
                logger.warning("SerpApi menu search failed for query=%r: %s", query, exc)
                continue
            for result in payload.get("organic_results") or []:
                if not isinstance(result, dict):
                    continue
                add_candidate(
                    str(result.get("link") or ""),
                    title=str(result.get("title") or ""),
                    snippet=str(result.get("snippet") or ""),
                )
                sitelinks = result.get("sitelinks") or {}
                for group_name in ("inline", "expanded", "list"):
                    for item in sitelinks.get(group_name) or []:
                        if not isinstance(item, dict):
                            continue
                        add_candidate(
                            str(item.get("link") or ""),
                            title=str(item.get("title") or ""),
                            snippet=str(item.get("snippet") or ""),
                        )
        return candidates

    def _fetch_menu_page(self, menu_url: str) -> str:
        if menu_url in self._menu_page_cache:
            return self._menu_page_cache[menu_url]
        response = httpx.get(
            menu_url,
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        self._menu_page_cache[menu_url] = response.text
        return response.text

    def _menu_item_name_from_url(self, item_url: str) -> str:
        path = urlparse(item_url).path.rstrip("/")
        slug = path.rsplit("/", 1)[-1].removesuffix(".html")
        if not slug:
            return ""
        pretty = slug.replace("-", " ")
        pretty = re.sub(r"\s+", " ", pretty).strip()
        title = pretty.title()
        replacements = {
            "Mcdouble": "McDouble",
            "Mccrispy": "McCrispy",
            "Mcnuggets": "McNuggets",
            "Mcmuffin": "McMuffin",
            "Mccafe": "McCafe",
            "Bbq": "BBQ",
            "Blt": "BLT",
        }
        for old, new in replacements.items():
            title = title.replace(old, new)
        return title

    def _normalize_candidate_name(self, value: str) -> str:
        value = unescape(re.sub(r"<[^>]+>", " ", value or ""))
        value = re.sub(r"\s+", " ", value).strip(" -|\t\r\n")
        return value

    def _extract_text_lines(self, html: str) -> list[str]:
        scrubbed = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html, flags=re.IGNORECASE)
        text = unescape(re.sub(r"<[^>]+>", "\n", scrubbed))
        lines = [self._normalize_candidate_name(line) for line in text.splitlines()]
        return [line for line in lines if line]

    def _looks_like_menu_item_name(self, candidate: str) -> bool:
        normalized = self._normalize_candidate_name(candidate)
        if not normalized:
            return False
        lowered = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
        if not lowered or lowered in self.MENU_STOPWORDS:
            return False
        if any(bad in lowered for bad in self.MENU_BAD_SUBSTRINGS):
            return False
        if normalized.startswith("(") and normalized.endswith(")"):
            return False
        if normalized.startswith("#"):
            return False
        if normalized[:1].islower():
            return False
        if normalized.isupper() and len(lowered.split()) > 1:
            return False
        if self.PHONE_PATTERN.search(normalized):
            return False
        if self.RATING_PATTERN.fullmatch(normalized):
            return False
        if normalized.count(",") >= 1 and len(lowered.split()) >= 4:
            return False
        if re.search(r"\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|suite|ste)\b", lowered):
            return False
        if lowered.isdigit():
            return False
        if self.PRICE_PATTERN.fullmatch(normalized):
            return False
        words = [word for word in lowered.split() if word]
        if not words or len(words) > 10:
            return False
        if len(words) == 1 and len(words[0]) < 4:
            return False
        if words[-1] in {"appetizer", "appetizers", "salad", "salads", "side", "sides", "dessert", "desserts", "drink", "drinks", "beverage", "beverages", "starter", "starters", "entree", "entrees"} and len(words) <= 3:
            return False
        if len(words) <= 2 and any(word in {"home", "gallery", "contact", "reservation", "menu", "menus", "news"} for word in words):
            return False
        if re.search(r"https?://|\.jpg|\.png|copyright|privacy|terms", lowered):
            return False
        return True

    def _is_low_signal_menu_name(self, candidate: str) -> bool:
        normalized = self._normalize_candidate_name(candidate)
        if not normalized:
            return True
        lowered = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
        if not lowered:
            return True
        if lowered in self.MENU_STOPWORDS:
            return True
        if lowered in self.MENU_LOW_SIGNAL_PHRASES:
            return True
        if any(phrase in lowered for phrase in self.MENU_LOW_SIGNAL_PHRASES):
            return True
        return False

    def _menu_name_quality(self, candidate: str) -> int:
        normalized = self._normalize_candidate_name(candidate)
        if not normalized or self._is_low_signal_menu_name(normalized):
            return 0
        lowered = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
        if not lowered:
            return 0
        if any(pattern.search(normalized) for pattern in self.MENU_LOW_VALUE_PATTERNS):
            return 0
        words = [word for word in lowered.split() if word]
        score = 1
        if len(words) >= 2:
            score += 1
        if any(hint in words for hint in self.MENU_ENTREE_HINTS):
            score += 1
        if len(words) == 1 and any(ch.isupper() for ch in normalized[1:]):
            score += 1
        return score

    def _menu_result_metrics(self, names: list[str]) -> tuple[int, int, float, int]:
        if not names:
            return 0, 0, 0.0, 0
        qualities = [self._menu_name_quality(name) for name in names]
        strong_item_count = sum(1 for quality in qualities if quality >= 2)
        total_quality = sum(qualities)
        high_signal_ratio = sum(1 for quality in qualities if quality > 0) / len(names)
        return strong_item_count, total_quality, high_signal_ratio, len(names)

    def _is_useful_menu_result(self, names: list[str]) -> bool:
        if not names:
            return False
        strong_item_count, total_quality, high_signal_ratio, total_count = self._menu_result_metrics(names)
        if strong_item_count == 0:
            return False
        if total_count <= 2:
            return strong_item_count == total_count
        if strong_item_count == total_count:
            return strong_item_count >= 2
        if total_count <= 4 and strong_item_count >= 2 and total_quality >= 7 and high_signal_ratio >= 0.75:
            return True
        if strong_item_count >= 5 and total_quality >= 12 and high_signal_ratio >= 0.5:
            return True
        if strong_item_count >= 4 and total_quality >= 10 and high_signal_ratio >= 0.65:
            return True
        return strong_item_count >= 3 and total_quality >= 8 and high_signal_ratio >= 0.75

    def _should_replace_menu_result(self, current_names: list[str], candidate_names: list[str]) -> bool:
        current_is_useful = self._is_useful_menu_result(current_names)
        candidate_is_useful = self._is_useful_menu_result(candidate_names)
        if candidate_is_useful != current_is_useful:
            return candidate_is_useful
        return self._menu_result_metrics(candidate_names) > self._menu_result_metrics(current_names)

    def _extract_menu_item_names_from_price_neighbors(self, html: str) -> list[str]:
        lines = self._extract_text_lines(html)
        names: list[str] = []
        for idx, line in enumerate(lines[:-1]):
            if not self._looks_like_menu_item_name(line):
                continue
            previous_line = lines[idx - 1] if idx > 0 else ""
            if previous_line and self._looks_like_menu_item_name(previous_line) and not self.PRICE_PATTERN.fullmatch(previous_line):
                continue
            window = lines[idx + 1 : idx + 4]
            if any(self.PRICE_PATTERN.fullmatch(candidate) for candidate in window):
                names.append(line)
        return self._dedupe_names(names)

    def _is_platform_menu_host(self, menu_url: str) -> bool:
        host = (urlparse(menu_url).netloc or "").lower()
        return any(domain in host for domain in ("singleplatform.com", "beyondmenu.com", "ubereats.com", "doordash.com"))

    def _extract_menu_item_names_from_platform_page(self, menu_url: str, html: str) -> list[str]:
        if self._is_platform_menu_host(menu_url):
            return self._extract_menu_item_names_from_price_neighbors(html)
        return []

    def _dedupe_names(self, names: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for name in names:
            normalized_name = self._normalize_candidate_name(name)
            normalized_key = re.sub(r"[^a-z0-9]+", " ", normalized_name.lower()).strip()
            if not normalized_key or normalized_key in self.MENU_STOPWORDS or normalized_key in seen:
                continue
            if not self._looks_like_menu_item_name(normalized_name):
                continue
            seen.add(normalized_key)
            out.append(normalized_name)
        return out

    def _remove_restaurant_name_entries(self, restaurant_id: str, names: list[str]) -> list[str]:
        try:
            payload = self.get_business_payload(restaurant_id)
        except Exception:
            logger.debug("Skipping restaurant-name filtering for restaurant_id=%s", restaurant_id, exc_info=True)
            return names
        restaurant_name = self._normalize_candidate_name(str(payload.get("name") or ""))
        if not restaurant_name:
            return names
        normalized_restaurant_name = re.sub(r"[^a-z0-9]+", " ", restaurant_name.lower()).strip()
        if not normalized_restaurant_name:
            return names

        filtered: list[str] = []
        for name in names:
            normalized_name = self._normalize_candidate_name(name)
            normalized_key = re.sub(r"[^a-z0-9]+", " ", normalized_name.lower()).strip()
            if normalized_key == normalized_restaurant_name:
                continue
            if re.fullmatch(rf"{re.escape(restaurant_name)}\s*\([^)]*\)", normalized_name, flags=re.IGNORECASE):
                continue
            filtered.append(name)
        return filtered

    def _iter_json_nodes(self, payload):
        if isinstance(payload, dict):
            yield payload
            for value in payload.values():
                yield from self._iter_json_nodes(value)
        elif isinstance(payload, list):
            for item in payload:
                yield from self._iter_json_nodes(item)

    def _extract_menu_item_names_from_json_ld(self, html: str) -> list[str]:
        names: list[str] = []
        for match in self.JSON_LD_PATTERN.finditer(html):
            body = match.group("body").strip()
            if not body:
                continue
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                continue
            for node in self._iter_json_nodes(payload):
                if not isinstance(node, dict):
                    continue
                types = node.get("@type")
                type_names = types if isinstance(types, list) else [types]
                type_names = [str(type_name).lower() for type_name in type_names if type_name]
                name = node.get("name")
                if "menuitem" in type_names and isinstance(name, str) and self._looks_like_menu_item_name(name):
                    names.append(name)
                    continue
                if not isinstance(name, str):
                    continue
                nearby_keys = {str(key).lower() for key in node.keys()}
                if (
                    "menuitem" not in type_names
                    and {"offers", "price", "pricecurrency"} & nearby_keys
                    and self._looks_like_menu_item_name(name)
                ):
                    names.append(name)
        return self._dedupe_names(names)

    def _extract_menu_item_names_from_markup(self, html: str) -> list[str]:
        names: list[str] = []
        for match in self.MENU_TEXT_PATTERN.finditer(html):
            attrs = (match.group("attrs") or "").lower()
            if not any(hint in attrs for hint in self.MENU_CONTEXT_HINTS):
                continue
            body = self._normalize_candidate_name(match.group("body"))
            if not self._looks_like_menu_item_name(body):
                continue
            names.append(body)
        return self._dedupe_names(names)

    def _extract_menu_category_urls(self, menu_url: str, html: str) -> list[str]:
        discovered: list[str] = []
        seen: set[str] = set()
        for match in self.MENU_CATEGORY_PATTERN.finditer(html):
            candidate = urljoin(menu_url, match.group("link"))
            parsed = urlparse(candidate)
            full_menu_path = parsed.path.split("/full-menu/", 1)
            if len(full_menu_path) != 2:
                continue
            relative = full_menu_path[1].strip("/")
            segments = [segment for segment in relative.split("/") if segment]
            if len(segments) != 1:
                continue
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if normalized in seen:
                continue
            seen.add(normalized)
            discovered.append(normalized)
        return discovered

    def _extract_product_item_urls(self, menu_url: str, html: str) -> list[str]:
        discovered: list[str] = []
        seen: set[str] = set()
        for match in self.PRODUCT_LINK_PATTERN.finditer(html):
            candidate = urljoin(menu_url, match.group("link"))
            normalized = f"{urlparse(candidate).scheme}://{urlparse(candidate).netloc}{urlparse(candidate).path}"
            if normalized in seen:
                continue
            seen.add(normalized)
            discovered.append(normalized)
        return discovered

    def _extract_generic_menu_urls(self, menu_url: str, html: str) -> list[str]:
        discovered: list[str] = []
        seen: set[str] = set()
        for match in self.GENERIC_MENU_LINK_PATTERN.finditer(html):
            candidate = urljoin(menu_url, match.group("link"))
            parsed = urlparse(candidate)
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
            lowered = normalized.lower()
            if not normalized or normalized.rstrip("/") == menu_url.rstrip("/"):
                continue
            if normalized in seen:
                continue
            if not any(token in lowered for token in ("/menu", "/menus", "lunch", "dinner", "order")):
                continue
            seen.add(normalized)
            discovered.append(normalized)
        return discovered

    def _extract_menu_item_names_from_page(self, menu_url: str, html: str) -> list[str]:
        item_urls = self._extract_product_item_urls(menu_url, html)
        names = [self._menu_item_name_from_url(item_url) for item_url in item_urls]
        names.extend(self._extract_menu_item_names_from_price_neighbors(html))
        names.extend(self._extract_menu_item_names_from_json_ld(html))
        if self._is_platform_menu_host(menu_url):
            names.extend(self._extract_menu_item_names_from_platform_page(menu_url, html))
        else:
            names.extend(self._extract_menu_item_names_from_markup(html))
        return self._dedupe_names(names)

    def _collect_page_menu_names(self, menu_url: str, html: str) -> list[str]:
        item_names = self._extract_menu_item_names_from_page(menu_url, html)
        if item_names:
            return item_names
        for category_url in self._extract_menu_category_urls(menu_url, html)[:15]:
            try:
                category_html = self._fetch_menu_page(category_url)
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch category_url=%s: %s", category_url, exc)
                continue
            for name in self._extract_menu_item_names_from_page(category_url, category_html):
                if name not in item_names:
                    item_names.append(name)
        return item_names

    def _collect_child_menu_results(self, menu_url: str, html: str) -> list[tuple[str, list[str]]]:
        results: list[tuple[str, list[str]]] = []
        for child_menu_url in self._extract_generic_menu_urls(menu_url, html)[:15]:
            try:
                child_html = self._fetch_menu_page(child_menu_url)
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch child_menu_url=%s: %s", child_menu_url, exc)
                continue
            child_item_names = self._collect_page_menu_names(child_menu_url, child_html)
            if not child_item_names:
                for nested_url in self._extract_generic_menu_urls(child_menu_url, child_html)[:10]:
                    try:
                        nested_html = self._fetch_menu_page(nested_url)
                    except httpx.HTTPError as exc:
                        logger.warning("Failed to fetch nested_menu_url=%s: %s", nested_url, exc)
                        continue
                    for name in self._extract_menu_item_names_from_page(nested_url, nested_html):
                        if name not in child_item_names:
                            child_item_names.append(name)
            if child_item_names:
                results.append((child_menu_url, child_item_names))
        return results

    def _merge_menu_results(self, page_results: list[tuple[str, list[str]]]) -> tuple[str, list[str]]:
        merged_names: list[str] = []
        merged_urls: list[str] = []
        for page_url, names in page_results:
            quality_names = [name for name in names if self._menu_name_quality(name) > 0]
            if not quality_names:
                continue
            new_quality_names = [name for name in quality_names if name not in merged_names]
            if merged_names and len(new_quality_names) < 2:
                continue
            merged_urls.append(page_url)
            merged_names.extend(new_quality_names)
            if len(merged_names) >= 80:
                break
        if not merged_urls:
            return "", []
        if len(merged_urls) == 1:
            return merged_urls[0], merged_names[:80]
        return f"{merged_urls[0]} (+{len(merged_urls) - 1} related menu pages)", merged_names[:80]

    def _candidate_menu_urls(self, restaurant_id: str) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()
        for candidate in [self.get_menu_url(restaurant_id), *self._search_menu_candidate_urls(restaurant_id)]:
            normalized = (candidate or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(normalized)
        return candidates

    def _build_dishes_from_names(self, restaurant_id: str, names: list[str], menu_url: str) -> list[Dish]:
        cleaned_names = [
            name
            for name in self._remove_restaurant_name_entries(restaurant_id, names)
            if self._menu_name_quality(name) > 0
        ]
        return [
            Dish(
                id=f"{restaurant_id}:menu:{idx}",
                name=name,
                description=f"Extracted from restaurant menu page: {menu_url}",
            )
            for idx, name in enumerate(cleaned_names[:80], start=1)
        ]

    def get_menu(self, restaurant_id: str) -> list[Dish]:
        for menu_url in self._candidate_menu_urls(restaurant_id):
            try:
                html = self._fetch_menu_page(menu_url)
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch menu_url=%s: %s", menu_url, exc)
                continue
            root_item_names = self._collect_page_menu_names(menu_url, html)
            page_results: list[tuple[str, list[str]]] = []
            if self._is_useful_menu_result(root_item_names):
                page_results.append((menu_url, root_item_names))
            for child_menu_url, child_item_names in self._collect_child_menu_results(menu_url, html):
                if self._is_useful_menu_result(child_item_names):
                    page_results.append((child_menu_url, child_item_names))
            merged_menu_url, merged_names = self._merge_menu_results(page_results)
            if merged_names and self._is_useful_menu_result(merged_names):
                return self._build_dishes_from_names(restaurant_id, merged_names, merged_menu_url)
        return []

    def get_review_photos(self, restaurant_id: str) -> list[Photo]:
        payload = self.get_business_payload(restaurant_id)
        urls = list(payload.get("photos", []) or [])
        # Yelp business details sometimes omit `photos`; use `image_url` as fallback.
        if not urls and payload.get("image_url"):
            urls = [payload["image_url"]]
        photos: list[Photo] = []
        for idx, url in enumerate(urls, start=1):
            photos.append(
                Photo(
                    id=f"{restaurant_id}:photo:{idx}",
                    url=url,
                    caption="Yelp listing photo food restaurant",
                    source="yelp",
                    is_user_contributed=False,
                    is_placeholder=False,
                )
            )
        return photos
