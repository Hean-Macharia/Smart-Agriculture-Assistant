"""Safe image decoding and preprocessing for the configured Keras model."""

from io import BytesIO


class InvalidDiseaseImage(ValueError):
    """The uploaded bytes are not a supported, decodable image."""


def preprocess_image(image_bytes: bytes):
    """Decode image bytes, convert BGR to RGB, resize, normalize, and batch."""
    try:
        import cv2
        import numpy as np
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise RuntimeError("OpenCV, Pillow, and NumPy are required for disease image preprocessing") from exc

    if not image_bytes:
        raise InvalidDiseaseImage("Image file is empty")
    try:
        with Image.open(BytesIO(image_bytes)) as decoded:
            if decoded.format not in {"JPEG", "PNG", "WEBP"}:
                raise InvalidDiseaseImage("Uploaded file is not a supported JPEG, PNG, or WebP image")
            if decoded.width < 1 or decoded.height < 1 or decoded.width * decoded.height > 25_000_000:
                raise InvalidDiseaseImage("Image dimensions exceed the supported limit")
            image = np.asarray(decoded.convert("RGB"))
    except InvalidDiseaseImage:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidDiseaseImage("Uploaded file is not a valid JPEG, PNG, or WebP image") from exc

    from app.core.config import settings

    image = cv2.resize(image, (settings.disease_input_size, settings.disease_input_size), interpolation=cv2.INTER_AREA)
    image = image.astype(np.float32) / 255.0
    return np.expand_dims(image, axis=0)
