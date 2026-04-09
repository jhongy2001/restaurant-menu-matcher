import re

from app.models.domain import Dish, Photo
from app.services.matching.base import ImageMatcher


class LexicalImageMatcher(ImageMatcher):
    """
    Baseline ranker for project foundation.
    It uses token overlap between dish text and photo caption.
    Can later be swapped to CLIP without touching API/service layers.
    """

    TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+")

    @classmethod
    def _tokenize(cls, text: str) -> set[str]:
        return {t.lower() for t in cls.TOKEN_PATTERN.findall(text)}

    def rank(self, *, dish: Dish, photos: list[Photo], top_k: int) -> list[tuple[Photo, float]]:
        query = f"{dish.name} {dish.description}".strip()
        q_tokens = self._tokenize(query)
        ranked: list[tuple[Photo, float]] = []

        for photo in photos:
            caption_tokens = self._tokenize(photo.caption)
            overlap = q_tokens & caption_tokens
            union_size = len(q_tokens | caption_tokens) or 1
            score = len(overlap) / union_size
            ranked.append((photo, score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:top_k]
