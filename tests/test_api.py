import httpx
from app.api.dependencies import build_image_matcher, build_image_search, build_restaurant_provider, get_menu_photo_service
from app.core.config import Settings
from app.models.domain import Dish, Photo
from app.services.image_search.serpapi_image_search import SerpApiImageSearch
from app.services.matching.clip_matcher import ClipImageMatcher
from app.services.matching.lexical_matcher import LexicalImageMatcher
from app.services.menu_photo_service import MenuPhotoService
from app.services.providers.composite_provider import CompositeRestaurantProvider
from app.services.providers.google_places_provider import GooglePlacesProvider
from app.services.providers.mock_provider import MockRestaurantProvider
from app.services.providers.yelp_provider import YelpRestaurantProvider
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_search_requires_required_params() -> None:
    response = client.get("/api/restaurants/search")
    assert response.status_code == 422
    response = client.get("/api/restaurants/search", params={"area_query": "Boston"})
    assert response.status_code == 422


def test_end_to_end_happy_path() -> None:
    menu = client.get("/api/restaurants/r1/menu")
    assert menu.status_code == 200
    dishes = menu.json()["dishes"]
    assert dishes

    dish_id = dishes[0]["id"]
    images = client.get(f"/api/restaurants/r1/dishes/{dish_id}/images")
    assert images.status_code == 200
    payload = images.json()
    assert payload["dish_id"] == dish_id
    assert payload["top_k"] == 5


def test_build_image_matcher_hybrid_uses_clip_matcher() -> None:
    settings = Settings(
        image_matcher_backend="hybrid",
        clip_model_name="openai/clip-vit-base-patch32",
        clip_request_timeout_seconds=8,
        clip_max_images_per_request=4,
    )

    matcher = build_image_matcher(settings)

    assert isinstance(matcher, ClipImageMatcher)
    assert isinstance(matcher.fallback_matcher, LexicalImageMatcher)


def test_build_image_search_serpapi_backend_returns_client() -> None:
    settings = Settings(
        image_source_backend="serpapi_search",
        serpapi_api_key="serp-key",
        serpapi_timeout_seconds=6,
        serpapi_max_results=4,
    )

    image_search = build_image_search(settings)

    assert isinstance(image_search, SerpApiImageSearch)
    assert image_search.api_key == "serp-key"
    assert image_search.timeout_seconds == 6
    assert image_search.max_results == 4


def test_build_restaurant_provider_demo_mode_keeps_mock() -> None:
    settings = Settings(data_provider_mode="demo")

    provider = build_restaurant_provider(settings)

    assert provider.mode == "demo"
    assert provider.mock is not None


def test_build_restaurant_provider_real_mode_requires_keys() -> None:
    settings = Settings(data_provider_mode="real", yelp_api_key="", google_places_api_key="")

    try:
        build_restaurant_provider(settings)
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail == "Real data mode requires both Yelp and Google Places API keys."
    else:
        raise AssertionError("Expected HTTPException for missing real mode keys.")


def test_build_restaurant_provider_real_mode_disables_mock() -> None:
    settings = Settings(
        data_provider_mode="real",
        yelp_api_key="test-yelp",
        google_places_api_key="test-google",
    )

    provider = build_restaurant_provider(settings)

    assert provider.mode == "real"
    assert provider.mock is None


def test_yelp_provider_menu_returns_empty_list() -> None:
    provider = YelpRestaurantProvider("test-yelp")
    provider.get_menu_url = lambda restaurant_id: None

    assert provider.get_menu("yelp:any-id") == []


def test_yelp_provider_extracts_menu_items_from_menu_url(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp")
    menu_html = """
    <a href="/us/en-us/full-menu/burgers.html">Burgers</a>
    <a href="/us/en-us/full-menu/breakfast.html">Breakfast</a>
    """
    burgers_html = """
    <a href="/us/en-us/product/big-mac.html">Big Mac</a>
    <a href="/us/en-us/product/quarter-pounder-with-cheese.html">Quarter Pounder with Cheese</a>
    """
    breakfast_html = """
    <a href="/us/en-us/product/egg-mcmuffin.html">Egg McMuffin</a>
    """

    monkeypatch.setattr(provider, "get_menu_url", lambda restaurant_id: "https://www.mcdonalds.com/us/en-us/full-menu.html")
    monkeypatch.setattr(
        provider,
        "_fetch_menu_page",
        lambda menu_url: {
            "https://www.mcdonalds.com/us/en-us/full-menu.html": menu_html,
            "https://www.mcdonalds.com/us/en-us/full-menu/burgers.html": burgers_html,
            "https://www.mcdonalds.com/us/en-us/full-menu/breakfast.html": breakfast_html,
        }[menu_url],
    )

    dishes = provider.get_menu("yelp:r1")

    assert [dish.name for dish in dishes] == [
        "Big Mac",
        "Quarter Pounder With Cheese",
        "Egg McMuffin",
    ]


def test_yelp_provider_extracts_menu_items_from_json_ld(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp")
    menu_html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Restaurant",
          "name": "Pasta Corner",
          "hasMenu": {
            "@type": "Menu",
            "hasMenuSection": [{
              "@type": "MenuSection",
              "name": "Entrees",
              "hasMenuItem": [
                {"@type": "MenuItem", "name": "Margherita Pizza"},
                {"@type": "MenuItem", "name": "Rigatoni Alla Vodka"}
              ]
            }]
          }
        }
        </script>
      </head>
    </html>
    """

    monkeypatch.setattr(provider, "get_menu_url", lambda restaurant_id: "https://example.com/menu")
    monkeypatch.setattr(provider, "_fetch_menu_page", lambda menu_url: menu_html)

    dishes = provider.get_menu("yelp:r1")

    assert [dish.name for dish in dishes] == [
        "Margherita Pizza",
        "Rigatoni Alla Vodka",
    ]


def test_yelp_provider_extracts_menu_items_from_html_menu_markup(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp")
    menu_html = """
    <div class="menu-item-name">Spicy Tuna Roll</div>
    <div class="menu-item-name">Salmon Nigiri</div>
    <button class="menu-item-card">California Roll</button>
    <div class="menu-item-name">Order Now</div>
    """

    monkeypatch.setattr(provider, "get_menu_url", lambda restaurant_id: "https://example.com/menu")
    monkeypatch.setattr(provider, "_fetch_menu_page", lambda menu_url: menu_html)

    dishes = provider.get_menu("yelp:r1")

    assert [dish.name for dish in dishes] == [
        "Spicy Tuna Roll",
        "Salmon Nigiri",
        "California Roll",
    ]


def test_yelp_provider_falls_back_to_serpapi_menu_search_when_menu_url_missing(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp", serpapi_api_key="serp-key")
    search_payload = {
        "organic_results": [
            {
                "title": "Sample Bistro Menu",
                "link": "https://sample-bistro.com/menu",
                "snippet": "Dinner menu and online ordering",
            }
        ]
    }
    menu_html = """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Menu",
      "hasMenuSection": [{
        "@type": "MenuSection",
        "hasMenuItem": [
          {"@type": "MenuItem", "name": "Truffle Pasta"},
          {"@type": "MenuItem", "name": "Roasted Salmon"}
        ]
      }]
    }
    </script>
    """

    monkeypatch.setattr(
        provider,
        "get_business_payload",
        lambda restaurant_id: {
            "name": "Sample Bistro",
            "location": {"city": "San Jose"},
            "attributes": {},
        },
    )

    def fake_get(url: str, params: dict | None = None, timeout: float = 0.0, **kwargs) -> httpx.Response:
        if url == "https://serpapi.com/search":
            return httpx.Response(200, json=search_payload, request=httpx.Request("GET", url))
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(provider, "_fetch_menu_page", lambda menu_url: menu_html)

    dishes = provider.get_menu("yelp:r1")

    assert [dish.name for dish in dishes] == ["Truffle Pasta", "Roasted Salmon"]


def test_yelp_provider_uses_serpapi_candidate_when_primary_menu_page_has_only_navigation(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp", serpapi_api_key="serp-key")
    primary_menu_html = """
    <div class="menu-item-name">Home</div>
    <div class="menu-item-name">Dinner Menu</div>
    <div class="menu-item-name">Reservation</div>
    """
    fallback_menu_html = """
    <div class="menu-item-name">Dragon Roll</div>
    <div class="menu-item-name">Rainbow Roll</div>
    """
    search_payload = {
        "organic_results": [
            {
                "title": "Fuji Sushi dinner menu",
                "link": "https://example.com/real-menu",
                "snippet": "Dinner menu and sushi rolls",
            }
        ]
    }

    monkeypatch.setattr(
        provider,
        "get_business_payload",
        lambda restaurant_id: {
            "name": "Fuji Sushi",
            "location": {"city": "San Jose"},
            "attributes": {"menu_url": "https://example.com/nav-menu"},
        },
    )

    def fake_get(url: str, params: dict | None = None, timeout: float = 0.0, **kwargs) -> httpx.Response:
        if url == "https://serpapi.com/search":
            return httpx.Response(200, json=search_payload, request=httpx.Request("GET", url))
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(
        provider,
        "_fetch_menu_page",
        lambda menu_url: {
            "https://example.com/nav-menu": primary_menu_html,
            "https://example.com/real-menu": fallback_menu_html,
        }[menu_url],
    )

    dishes = provider.get_menu("yelp:r1")

    assert [dish.name for dish in dishes] == ["Dragon Roll", "Rainbow Roll"]


def test_yelp_provider_menu_search_tries_multiple_suffixes(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp", serpapi_api_key="serp-key")

    monkeypatch.setattr(
        provider,
        "get_business_payload",
        lambda restaurant_id: {
            "name": "Sample Sushi",
            "location": {"city": "San Jose"},
            "attributes": {},
        },
    )

    seen_queries: list[str] = []

    def fake_get(url: str, params: dict | None = None, timeout: float = 0.0, **kwargs) -> httpx.Response:
        if url != "https://serpapi.com/search":
            raise AssertionError(f"Unexpected URL {url}")
        query = str((params or {}).get("q") or "")
        seen_queries.append(query)
        if query.endswith("menu"):
            return httpx.Response(200, json={"organic_results": []}, request=httpx.Request("GET", url))
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {"title": "Sample Sushi Order Online", "link": "https://example.com/order", "snippet": "online order"}
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    candidates = provider._search_menu_candidate_urls("yelp:r1")

    assert "Sample Sushi San Jose menu" in seen_queries
    assert any(query.endswith("doordash") or query.endswith("ubereats") for query in seen_queries)
    assert candidates == ["https://example.com/order"]


def test_yelp_provider_menu_search_filters_irrelevant_hosts(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp", serpapi_api_key="serp-key")

    monkeypatch.setattr(
        provider,
        "get_business_payload",
        lambda restaurant_id: {
            "name": "Pizza Antica",
            "location": {"city": "San Jose"},
            "attributes": {},
        },
    )

    def fake_get(url: str, params: dict | None = None, timeout: float = 0.0, **kwargs) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "organic_results": [
                    {"title": "Pizza Antica menu", "link": "https://www.findmeglutenfree.com/biz/pizza-antica/1", "snippet": "menu"},
                    {"title": "Pizza Antica order online", "link": "https://www.facebook.com/pizzaanticasanjose/", "snippet": "food"},
                    {"title": "Pizza Antica full menu", "link": "http://places.singleplatform.com/pizza-antica-2/menu", "snippet": "menu"},
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    candidates = provider._search_menu_candidate_urls("yelp:r1")

    assert candidates == ["http://places.singleplatform.com/pizza-antica-2/menu"]


def test_yelp_provider_follows_child_menu_pages_when_landing_page_is_only_directory(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp")

    monkeypatch.setattr(
        provider,
        "get_business_payload",
        lambda restaurant_id: {
            "name": "Fuji Sushi",
            "location": {"city": "San Jose"},
            "attributes": {"menu_url": "https://example.com/fuji-menu"},
        },
    )
    monkeypatch.setattr(provider, "_search_menu_candidate_urls", lambda restaurant_id: [])
    monkeypatch.setattr(
        provider,
        "_fetch_menu_page",
        lambda menu_url: {
            "https://example.com/fuji-menu": '<a href="/dinnermenus/">View Our Menus</a>',
            "https://example.com/dinnermenus": """
                <div class="menu-item-name">Edamame</div>
                <div class="menu-item-name">Dragon Roll</div>
                <div class="menu-item-name">Rainbow Roll</div>
                <div class="menu-item-name">Miso Soup</div>
                <div class="menu-item-name">Chicken Teriyaki</div>
            """,
        }[menu_url],
    )

    dishes = provider.get_menu("yelp:r1")

    assert [dish.name for dish in dishes] == [
        "Edamame",
        "Dragon Roll",
        "Rainbow Roll",
        "Miso Soup",
        "Chicken Teriyaki",
    ]


def test_yelp_provider_skips_low_quality_page_and_uses_later_candidate(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp")

    monkeypatch.setattr(
        provider,
        "get_business_payload",
        lambda restaurant_id: {
            "name": "Pizza Antica",
            "location": {"city": "San Jose"},
            "attributes": {"menu_url": "https://example.com/bad-menu"},
        },
    )
    monkeypatch.setattr(provider, "_search_menu_candidate_urls", lambda restaurant_id: ["https://example.com/good-menu"])
    monkeypatch.setattr(
        provider,
        "_fetch_menu_page",
        lambda menu_url: {
            "https://example.com/bad-menu": """
                <div>Reported GF menu items</div>
                <div>Sign In</div>
                <div>334 Santana Row San Jose, CA 95128</div>
                <div>(408) 557-8373</div>
                <div>Google Maps</div>
            """,
            "https://example.com/good-menu": """
                <div class="menu-item-name">Cacio e Pepe Fries</div>
                <div class="menu-item-name">Minestrone Soup</div>
                <div class="menu-item-name">Calamari</div>
                <div class="menu-item-name">Margherita Pizza</div>
                <div class="menu-item-name">Burrata and Winter Citrus</div>
            """,
        }[menu_url],
    )

    dishes = provider.get_menu("yelp:r1")

    assert [dish.name for dish in dishes] == [
        "Cacio e Pepe Fries",
        "Minestrone Soup",
        "Calamari",
        "Margherita Pizza",
        "Burrata and Winter Citrus",
    ]


def test_yelp_provider_rejects_low_signal_navigation_terms_as_menu_result() -> None:
    provider = YelpRestaurantProvider("test-yelp")

    names = [
        "Delivery",
        "Carryout",
        "Offer Details",
        "Our Company",
        "Legal",
    ]

    assert provider._is_useful_menu_result(names) is False


def test_yelp_provider_prefers_higher_quality_child_menu_over_noisy_landing_page(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp")

    monkeypatch.setattr(
        provider,
        "get_business_payload",
        lambda restaurant_id: {
            "name": "Domino's Pizza",
            "location": {"city": "Boston"},
            "attributes": {"menu_url": "https://www.dominos.com/en/menu"},
        },
    )
    monkeypatch.setattr(provider, "_search_menu_candidate_urls", lambda restaurant_id: [])
    monkeypatch.setattr(
        provider,
        "_fetch_menu_page",
        lambda menu_url: {
            "https://www.dominos.com/en/menu": """
                <a href="/menu/build-your-own">Start Building Your Own Pizza</a>
                <a href="/menu/wings">Wings</a>
                <div class="menu-item-name">Delivery</div>
                <div class="menu-item-name">Carryout</div>
                <div class="menu-item-name">Offer Details</div>
                <div class="menu-item-name">Our Company</div>
                <div class="menu-item-name">Legal</div>
            """,
            "https://www.dominos.com/menu/build-your-own": """
                <div class="menu-item-name">Hand Tossed Pizza</div>
                <div class="menu-item-name">Brooklyn Style Pizza</div>
                <div class="menu-item-name">Crunchy Thin Crust Pizza</div>
                <div class="menu-item-name">Gluten Free Crust Pizza</div>
            """,
            "https://www.dominos.com/menu/wings": """
                <div class="menu-item-name">Hot Buffalo Wings</div>
                <div class="menu-item-name">Honey BBQ Wings</div>
                <div class="menu-item-name">Plain Wings</div>
            """,
        }[menu_url],
    )

    dishes = provider.get_menu("yelp:r1")

    assert [dish.name for dish in dishes] == [
        "Hand Tossed Pizza",
        "Brooklyn Style Pizza",
        "Crunchy Thin Crust Pizza",
        "Gluten Free Crust Pizza",
        "Hot Buffalo Wings",
        "Honey BBQ Wings",
        "Plain Wings",
    ]


def test_yelp_provider_menu_quality_prefers_entrees_over_condiments() -> None:
    provider = YelpRestaurantProvider("test-yelp")

    condiments = [
        "Slice Sauce Dipping Cup",
        "Hot Buffalo Dipping Cup",
        "Caesar Dressing",
        "Ranch Dressing",
        "Balsamic",
    ]
    entrees = [
        "Spicy Chicken Bacon Ranch",
        "ExtravaganZZa",
        "MeatZZa",
        "Pacific Veggie",
        "Ultimate Pepperoni",
    ]

    assert provider._should_replace_menu_result(condiments, entrees) is True


def test_yelp_provider_build_dishes_filters_customize_and_dipping_items(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp")

    monkeypatch.setattr(
        provider,
        "get_business_payload",
        lambda restaurant_id: {"name": "Domino's Pizza"},
    )

    dishes = provider._build_dishes_from_names(
        "yelp:r1",
        [
            "Slice Sauce Dipping Cup",
            "Customize Slice Sauce Dipping Cup",
            "Ranch Dressing",
            "Ultimate Pepperoni",
            "Pacific Veggie",
        ],
        "https://www.dominos.com/menu/sides",
    )

    assert [dish.name for dish in dishes] == [
        "Ultimate Pepperoni",
        "Pacific Veggie",
    ]


def test_yelp_provider_merges_multiple_high_quality_child_menu_pages(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp")

    monkeypatch.setattr(
        provider,
        "get_business_payload",
        lambda restaurant_id: {
            "name": "Domino's Pizza",
            "location": {"city": "Boston"},
            "attributes": {"menu_url": "https://www.dominos.com/en/menu"},
        },
    )
    monkeypatch.setattr(provider, "_search_menu_candidate_urls", lambda restaurant_id: [])
    monkeypatch.setattr(
        provider,
        "_fetch_menu_page",
        lambda menu_url: {
            "https://www.dominos.com/en/menu": """
                <a href="/menu/specialty">Specialty Pizza</a>
                <a href="/menu/bread">Bread</a>
                <a href="/menu/wings">Wings</a>
                <a href="/menu/sides">Sides</a>
            """,
            "https://www.dominos.com/menu/specialty": """
                <div class="menu-item-name">ExtravaganZZa</div>
                <div class="menu-item-name">MeatZZa</div>
                <div class="menu-item-name">Pacific Veggie</div>
                <div class="menu-item-name">Ultimate Pepperoni</div>
            """,
            "https://www.dominos.com/menu/bread": """
                <div class="menu-item-name">Parmesan Bread Bites</div>
                <div class="menu-item-name">Stuffed Cheesy Bread</div>
                <div class="menu-item-name">Pepperoni Stuffed Cheesy Bread</div>
            """,
            "https://www.dominos.com/menu/wings": """
                <div class="menu-item-name">Hot Buffalo Wings</div>
                <div class="menu-item-name">Honey BBQ Wings</div>
                <div class="menu-item-name">Plain Wings</div>
            """,
            "https://www.dominos.com/menu/sides": """
                <div class="menu-item-name">Slice Sauce Dipping Cup</div>
                <div class="menu-item-name">Ranch Dressing</div>
                <div class="menu-item-name">Customize Slice Sauce Dipping Cup</div>
            """,
        }[menu_url],
    )

    dishes = provider.get_menu("yelp:r1")

    assert [dish.name for dish in dishes] == [
        "ExtravaganZZa",
        "MeatZZa",
        "Pacific Veggie",
        "Ultimate Pepperoni",
        "Parmesan Bread Bites",
        "Stuffed Cheesy Bread",
        "Pepperoni Stuffed Cheesy Bread",
        "Hot Buffalo Wings",
        "Honey BBQ Wings",
        "Plain Wings",
    ]


def test_yelp_provider_extracts_menu_items_from_singleplatform_page() -> None:
    provider = YelpRestaurantProvider("test-yelp")
    html = """
    <h4>Edamame</h4>
    <div>$3.95</div>
    <h4>Soft Shell Crab</h4>
    <div>$8.95</div>
    <h4>Wakame</h4>
    <div>$3.95</div>
    """

    names = provider._extract_menu_item_names_from_page("http://places.singleplatform.com/fuji/menu", html)

    assert names == ["Edamame", "Soft Shell Crab", "Wakame"]


def test_yelp_provider_extracts_menu_items_from_beyondmenu_page() -> None:
    provider = YelpRestaurantProvider("test-yelp")
    html = """
    <div>Appetizers</div>
    <div>Edamame</div>
    <div>Lightly salted soy beans</div>
    <div>$3.95</div>
    <div>Agedashi Tofu</div>
    <div>Deep fried tofu</div>
    <div>$7.50</div>
    <div>Yakitori</div>
    <div>$6.95</div>
    """

    names = provider._extract_menu_item_names_from_page("https://www.beyondmenu.com/store/foo", html)

    assert names == ["Edamame", "Agedashi Tofu", "Yakitori"]


def test_yelp_provider_price_neighbor_parser_skips_descriptions() -> None:
    provider = YelpRestaurantProvider("test-yelp")
    html = """
    <div>Dragon Ball 4pcs</div>
    <div>spicy tuna, crab meat, mushroom deep fried</div>
    <div>$9.95</div>
    <div>Hamachi Carpaccio</div>
    <div>Ponzu sauce, jalapeno, radish, tobiko</div>
    <div>$19.95</div>
    <div>(seaweed salad)</div>
    <div>$5.95</div>
    """

    names = provider._extract_menu_item_names_from_price_neighbors(html)

    assert names == ["Dragon Ball 4pcs", "Hamachi Carpaccio"]


def test_yelp_provider_rejects_platform_metadata_as_menu_items() -> None:
    provider = YelpRestaurantProvider("test-yelp")

    assert provider._looks_like_menu_item_name("Group order") is False
    assert provider._looks_like_menu_item_name("#2 most liked") is False
    assert provider._looks_like_menu_item_name("STARTERS") is False
    assert provider._looks_like_menu_item_name("Gluten-Free Appetizers") is False
    assert provider._looks_like_menu_item_name("Three dots horizontal") is False
    assert provider._looks_like_menu_item_name("Rating and reviews") is False


def test_yelp_provider_removes_restaurant_name_entries(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp")

    monkeypatch.setattr(
        provider,
        "get_business_payload",
        lambda restaurant_id: {"name": "Pizza Antica"},
    )

    names = provider._remove_restaurant_name_entries(
        "yelp:r1",
        ["Pizza Antica", "Pizza Antica (Santana Row)", "Margherita Pizza", "Fuji Roll"],
    )

    assert names == ["Margherita Pizza", "Fuji Roll"]


def test_serpapi_image_search_maps_results(monkeypatch) -> None:
    search = SerpApiImageSearch(api_key="serp-key", timeout_seconds=8, max_results=3)
    captured: dict[str, object] = {}

    def fake_get(url: str, params: dict, timeout: float) -> httpx.Response:
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            json={
                "images_results": [
                    {
                        "original": "https://example.com/big-mac.jpg",
                        "title": "Big Mac",
                        "source": "mcdonalds.com",
                    },
                    {
                        "thumbnail": "https://example.com/big-mac-thumb.jpg",
                        "title": "Big Mac review photo",
                        "source": "foodblog.example",
                    },
                    {
                        "thumbnail": "data:image/gif;base64,aaaa",
                        "title": "skip me",
                    },
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    photos = search.search_images(
        restaurant_name="McDonald's",
        dish=Dish(id="d1", name="Big Mac", description=""),
        top_k=5,
    )

    assert captured["url"] == "https://serpapi.com/search"
    assert captured["params"]["engine"] == "google_images"
    assert captured["params"]["q"] == "McDonald's Big Mac"
    assert captured["timeout"] == 8
    assert [photo.url for photo in photos] == [
        "https://example.com/big-mac.jpg",
        "https://example.com/big-mac-thumb.jpg",
    ]
    assert photos[0].caption == "Big Mac | mcdonalds.com"
    assert photos[1].source == "serpapi"


def test_google_menu_parser_ignores_section_titles(monkeypatch) -> None:
    provider = GooglePlacesProvider("test-google")

    def fake_place_details(place_id: str, field_mask: str) -> dict:
        return {
            "businessMenus": [
                {
                    "sections": [
                        {
                            "displayName": {"text": "Appetizers"},
                            "items": [
                                {
                                    "displayName": {"text": "Appetizers"},
                                    "description": {"text": "Section heading only"},
                                },
                                {
                                    "displayName": {"text": "Chicken Karaage"},
                                    "description": {"text": "Japanese fried chicken"},
                                },
                            ],
                        }
                    ]
                }
            ]
        }

    monkeypatch.setattr(provider, "place_details", fake_place_details)

    dishes = provider.menu_dishes_for_restaurant("yelp:r1", "place-1")

    assert len(dishes) == 1
    assert dishes[0].name == "Chicken Karaage"


def test_composite_provider_real_mode_returns_empty_menu_without_real_menu(monkeypatch) -> None:
    yelp = YelpRestaurantProvider("test-yelp")
    google = GooglePlacesProvider("test-google")
    provider = CompositeRestaurantProvider(mock=None, yelp=yelp, google=google, mode="real")

    monkeypatch.setattr(yelp, "get_menu", lambda restaurant_id: [])

    dishes = provider.get_menu("yelp:r1")

    assert dishes == []


def test_composite_provider_real_mode_uses_yelp_menu_extraction(monkeypatch) -> None:
    yelp = YelpRestaurantProvider("test-yelp")
    google = GooglePlacesProvider("test-google")
    provider = CompositeRestaurantProvider(mock=None, yelp=yelp, google=google, mode="real")

    monkeypatch.setattr(
        yelp,
        "get_menu",
        lambda restaurant_id: [
            MockRestaurantProvider().get_menu("r1")[0],
        ],
    )

    dishes = provider.get_menu("yelp:r1")

    assert dishes
    assert dishes[0].name == "Spicy Tonkotsu Ramen"


def test_composite_provider_demo_mode_keeps_mock_menu() -> None:
    mock = MockRestaurantProvider()
    provider = CompositeRestaurantProvider(mock=mock, yelp=None, google=None, mode="demo")

    dishes = provider.get_menu("r1")

    assert dishes
    assert dishes[0].name == "Spicy Tonkotsu Ramen"


def test_yelp_provider_photos_do_not_use_fixed_fallback_images(monkeypatch) -> None:
    provider = YelpRestaurantProvider("test-yelp")
    monkeypatch.setattr(provider, "get_business_payload", lambda restaurant_id: {"photos": [], "image_url": ""})

    photos = provider.get_review_photos("yelp:r1")

    assert photos == []


def test_composite_provider_real_mode_filters_to_real_photo_sources(monkeypatch) -> None:
    yelp = YelpRestaurantProvider("test-yelp")
    google = GooglePlacesProvider("test-google")
    provider = CompositeRestaurantProvider(mock=None, yelp=yelp, google=google, mode="real")

    monkeypatch.setattr(
        yelp,
        "get_review_photos",
        lambda restaurant_id: [
            MockRestaurantProvider().get_review_photos("r1")[0],
        ],
    )
    monkeypatch.setattr(provider, "_resolve_google_place_id", lambda restaurant_id: "place-1")
    monkeypatch.setattr(
        google,
        "place_photos_for_restaurant",
        lambda restaurant_id, place_id: [
            GooglePlacesProvider("x").place_photos_for_restaurant if False else None
        ],
    )

    google_photo = MockRestaurantProvider().get_review_photos("r1")[1]
    object.__setattr__(google_photo, "source", "google_places")
    object.__setattr__(google_photo, "is_user_contributed", True)
    object.__setattr__(google_photo, "is_placeholder", False)
    monkeypatch.setattr(
        google,
        "place_photos_for_restaurant",
        lambda restaurant_id, place_id: [google_photo],
    )

    photos = provider.get_review_photos("yelp:r1")

    assert len(photos) == 1
    assert photos[0].source == "google_places"
    assert photos[0].is_user_contributed is True


def test_images_endpoint_returns_photo_source_metadata() -> None:
    get_menu_photo_service.cache_clear()
    menu = client.get("/api/restaurants/r1/menu")
    assert menu.status_code == 200
    dish_id = menu.json()["dishes"][0]["id"]

    images = client.get(f"/api/restaurants/r1/dishes/{dish_id}/images")
    assert images.status_code == 200
    first_match = images.json()["matches"][0]

    assert "source" in first_match
    assert "is_user_contributed" in first_match
    assert "is_placeholder" in first_match
    assert first_match["source"] in {"mock", "serpapi"}


def test_menu_photo_service_uses_serpapi_search_for_dish_images() -> None:
    class FakeImageSearch:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, int]] = []

        def search_images(self, *, restaurant_name: str, dish: Dish, top_k: int) -> list[Photo]:
            self.calls.append((restaurant_name, dish.name, top_k))
            return [
                Photo(
                    id="serp-1",
                    url="https://example.com/ramen-1.jpg",
                    caption="Spicy Tonkotsu Ramen | ramen.example",
                    source="serpapi",
                ),
                Photo(
                    id="serp-2",
                    url="https://example.com/ramen-2.jpg",
                    caption="Tokyo Ramen House ramen | food.example",
                    source="serpapi",
                ),
            ]

    fake_search = FakeImageSearch()
    service = MenuPhotoService(
        provider=MockRestaurantProvider(),
        matcher=LexicalImageMatcher(),
        settings=Settings(image_source_backend="serpapi_search"),
        image_search=fake_search,
    )

    response = service.get_dish_images("r1", "d1", top_k=2)

    assert fake_search.calls == [("Tokyo Ramen House", "Spicy Tonkotsu Ramen", 2)]
    assert [match.photo_url for match in response.matches] == [
        "https://example.com/ramen-1.jpg",
        "https://example.com/ramen-2.jpg",
    ]
    assert response.matches[0].source == "serpapi"
    assert response.matches[0].score == 1.0
    assert response.matches[1].score == 0.99


def test_menu_photo_service_requires_serpapi_key_when_backend_enabled() -> None:
    service = MenuPhotoService(
        provider=MockRestaurantProvider(),
        matcher=LexicalImageMatcher(),
        settings=Settings(image_source_backend="serpapi_search"),
        image_search=SerpApiImageSearch(api_key="", timeout_seconds=8, max_results=5),
    )

    try:
        service.get_dish_images("r1", "d1")
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail == "SERPAPI_API_KEY is required when IMAGE_SOURCE_BACKEND=serpapi_search."
    else:
        raise AssertionError("Expected HTTPException when SerpApi backend is enabled without an API key.")


def test_images_endpoint_falls_back_when_clip_fails(monkeypatch) -> None:
    get_menu_photo_service.cache_clear()
    original_rank = ClipImageMatcher._rank_with_clip

    def raise_clip_failure(self, *, dish, photos, top_k):
        raise RuntimeError("simulated clip failure")

    monkeypatch.setattr(ClipImageMatcher, "_rank_with_clip", raise_clip_failure)
    try:
        menu = client.get("/api/restaurants/r1/menu")
        assert menu.status_code == 200
        dish_id = menu.json()["dishes"][0]["id"]

        images = client.get(f"/api/restaurants/r1/dishes/{dish_id}/images")
        assert images.status_code == 200
        payload = images.json()
        assert payload["dish_id"] == dish_id
        assert payload["matches"]
    finally:
        monkeypatch.setattr(ClipImageMatcher, "_rank_with_clip", original_rank)
        get_menu_photo_service.cache_clear()
