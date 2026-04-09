import httpx


class GooglePlacesProvider:
    BASE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def suggest_locations(self, query: str) -> list[str]:
        text = query.strip()
        if not text:
            return []
        response = httpx.get(
            self.BASE_URL,
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
