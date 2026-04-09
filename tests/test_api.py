from fastapi.testclient import TestClient

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
    search = client.get("/api/restaurants/search", params={"area_query": "Boston", "name": "Tokyo"})
    assert search.status_code == 200
    restaurants = search.json()["restaurants"]
    assert restaurants

    restaurant_id = restaurants[0]["id"]
    menu = client.get(f"/api/restaurants/{restaurant_id}/menu")
    assert menu.status_code == 200
    dishes = menu.json()["dishes"]
    assert dishes

    dish_id = dishes[0]["id"]
    images = client.get(f"/api/restaurants/{restaurant_id}/dishes/{dish_id}/images")
    assert images.status_code == 200
    payload = images.json()
    assert payload["dish_id"] == dish_id
    assert payload["top_k"] == 5
