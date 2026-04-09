from dataclasses import dataclass


@dataclass(frozen=True)
class Restaurant:
    id: str
    name: str
    address: str
    city: str
    postal_code: str
    source: str


@dataclass(frozen=True)
class Dish:
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class Photo:
    id: str
    url: str
    caption: str
