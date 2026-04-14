from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING, Any

import httpx

from app.models.domain import Dish, Photo
from app.services.matching.base import ImageMatcher

if TYPE_CHECKING:
    import torch
    from PIL import Image
    from transformers import AutoProcessor, CLIPModel

logger = logging.getLogger(__name__)


class ClipImageMatcher(ImageMatcher):
    def __init__(
        self,
        *,
        model_name: str,
        request_timeout_seconds: float,
        max_images_per_request: int,
        fallback_matcher: ImageMatcher,
    ) -> None:
        self.model_name = model_name
        self.request_timeout_seconds = request_timeout_seconds
        self.max_images_per_request = max_images_per_request
        self.fallback_matcher = fallback_matcher
        self._model: CLIPModel | None = None
        self._processor: AutoProcessor | None = None
        self._torch: Any | None = None

    def _load_runtime(self) -> tuple[Any, AutoProcessor, CLIPModel]:
        if self._model is not None and self._processor is not None and self._torch is not None:
            return self._torch, self._processor, self._model
        try:
            import torch
            from transformers import AutoProcessor, CLIPModel
        except ImportError as exc:
            raise RuntimeError("CLIP dependencies are not installed.") from exc

        model = CLIPModel.from_pretrained(self.model_name)
        processor = AutoProcessor.from_pretrained(self.model_name)
        model.eval()
        self._torch = torch
        self._model = model
        self._processor = processor
        return torch, processor, model

    def _dish_query(self, dish: Dish) -> str:
        description = dish.description.strip()
        return f"{dish.name}. {description}".strip() if description else dish.name

    def _load_pillow(self) -> tuple[Any, Any]:
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:
            raise RuntimeError("Pillow is not installed.") from exc
        return Image, UnidentifiedImageError

    def _download_image(self, client: httpx.Client, photo: Photo) -> Any | None:
        Image, UnidentifiedImageError = self._load_pillow()
        try:
            response = client.get(photo.url)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content))
            return image.convert("RGB")
        except (httpx.HTTPError, UnidentifiedImageError, OSError) as exc:
            logger.warning("Skipping photo_id=%s during CLIP ranking: %s", photo.id, exc)
            return None

    def _rank_with_clip(self, *, dish: Dish, photos: list[Photo], top_k: int) -> list[tuple[Photo, float]]:
        torch, processor, model = self._load_runtime()
        limited_photos = photos[: self.max_images_per_request]
        if not limited_photos:
            return []

        decoded: list[tuple[Photo, Any]] = []
        with httpx.Client(timeout=self.request_timeout_seconds, follow_redirects=True) as client:
            for photo in limited_photos:
                image = self._download_image(client, photo)
                if image is not None:
                    decoded.append((photo, image))

        if not decoded:
            return []

        photo_items = [photo for photo, _ in decoded]
        images = [image for _, image in decoded]
        inputs = processor(
            text=[self._dish_query(dish)],
            images=images,
            return_tensors="pt",
            padding=True,
        )
        with torch.inference_mode():
            outputs = model(**inputs)
            image_embeds = outputs.image_embeds / outputs.image_embeds.norm(dim=-1, keepdim=True)
            text_embeds = outputs.text_embeds / outputs.text_embeds.norm(dim=-1, keepdim=True)
            scores = torch.matmul(image_embeds, text_embeds.T).squeeze(-1)

        ranked = [
            (photo, float(score))
            for photo, score in zip(photo_items, scores.tolist(), strict=False)
        ]
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[:top_k]

    def rank(self, *, dish: Dish, photos: list[Photo], top_k: int) -> list[tuple[Photo, float]]:
        try:
            ranked = self._rank_with_clip(dish=dish, photos=photos, top_k=top_k)
            if ranked:
                return ranked
            logger.warning("CLIP matcher produced no usable images; falling back to lexical matcher.")
        except Exception:
            logger.exception("CLIP matcher failed; falling back to lexical matcher.")
        return self.fallback_matcher.rank(dish=dish, photos=photos, top_k=top_k)
