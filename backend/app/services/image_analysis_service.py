import io
import logging
import os
from typing import List

import cv2
import imagehash
import numpy as np
from colorthief import ColorThief
from PIL import Image
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)
_ocr_engine = None
_face_cascade = None


def _get_ocr_engine():
    global _ocr_engine

    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _ocr_engine = RapidOCR()
        except Exception as exc:
            logger.warning(f"RapidOCR initialization warning: {exc}")
            _ocr_engine = False

    return _ocr_engine if _ocr_engine is not False else None


def _get_face_cascade():
    global _face_cascade

    if _face_cascade is None:
        try:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"

            if os.path.exists(cascade_path):
                _face_cascade = cv2.CascadeClassifier(cascade_path)
            else:
                _face_cascade = False
        except Exception as exc:
            logger.warning(f"OpenCV Haar Cascade loading warning: {exc}")
            _face_cascade = False

    return _face_cascade if _face_cascade is not False else None


class ImageFeatureProfile(BaseModel):
    category: str = "asset"
    filename: str = ""
    width: int = 0
    height: int = 0
    aspect_ratio: str = "UNKNOWN"
    is_vertical: bool = False
    blur_score: float = 0.0
    is_sharp: bool = True
    framing_type: str = "GENERAL"
    detected_faces_count: int = 0
    dominant_color_hex: str = "#000000"
    color_palette_hex: List[str] = Field(default_factory=list)
    lighting_style: str = "BALANCED"
    phash: str = ""
    detected_labels: List[str] = Field(default_factory=list)
    visual_summary_bullet: str = ""


class ImageAnalysisService:
    @staticmethod
    def _rgb_to_hex(r: int, g: int, b: int) -> str:
        return f"#{r:02x}{g:02x}{b:02x}".upper()

    @staticmethod
    def _calculate_aspect_ratio_str(width: int, height: int) -> str:
        if width == 0 or height == 0:
            return "UNKNOWN"

        ratio = width / height
        ratios = [
            (16 / 9, 0.15, "16:9"),
            (9 / 16, 0.15, "9:16"),
            (1.0, 0.15, "1:1"),
            (4 / 3, 0.15, "4:3"),
            (3 / 4, 0.15, "3:4"),
            (21 / 9, 0.2, "21:9"),
        ]

        for target_ratio, tolerance, label in ratios:
            if abs(ratio - target_ratio) < tolerance:
                return label

        return f"{width}:{height}"

    @staticmethod
    def extract_colors(image_bytes: bytes) -> tuple[str, List[str], str]:
        try:
            thief = ColorThief(io.BytesIO(image_bytes))
            dominant_rgb = thief.get_color(quality=1)
            dominant_hex = ImageAnalysisService._rgb_to_hex(*dominant_rgb)

            palette_rgb = thief.get_palette(color_count=5, quality=1)
            palette_hex = [ImageAnalysisService._rgb_to_hex(*color) for color in palette_rgb]

            luminance = (
                0.299 * dominant_rgb[0]
                + 0.587 * dominant_rgb[1]
                + 0.114 * dominant_rgb[2]
            )

            if luminance < 70:
                lighting = "LOW_KEY"
            elif luminance > 190:
                lighting = "HIGH_KEY"
            else:
                lighting = "BALANCED"

            return dominant_hex, palette_hex, lighting
        except Exception as exc:
            logger.debug(f"ColorThief fallback to numpy: {exc}")

            try:
                image_array = np.frombuffer(image_bytes, np.uint8)
                cv_img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

                if cv_img is not None:
                    average_bgr = cv_img.mean(axis=(0, 1))
                    average_rgb = (
                        int(average_bgr[2]),
                        int(average_bgr[1]),
                        int(average_bgr[0]),
                    )
                    dominant_hex = ImageAnalysisService._rgb_to_hex(*average_rgb)
                    return dominant_hex, [dominant_hex], "BALANCED"
            except Exception:
                pass

            return "#777777", ["#777777"], "BALANCED"

    @staticmethod
    def evaluate_quality_and_framing(
        cv_img: np.ndarray, category: str
    ) -> tuple[float, bool, str, int]:
        if cv_img is None or cv_img.size == 0:
            return 0.0, False, "GENERAL", 0

        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        is_sharp = blur_score >= 80.0

        faces_count = 0
        max_face_area_ratio = 0.0
        cascade = _get_face_cascade()
        image_area = float(cv_img.shape[0] * cv_img.shape[1])

        if cascade:
            try:
                faces = cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(30, 30),
                )
                faces_count = len(faces)

                if faces_count > 0 and image_area > 0:
                    largest_face_area = max(width * height for _, _, width, height in faces)
                    max_face_area_ratio = largest_face_area / image_area
            except Exception as exc:
                logger.debug(f"Face detection failed: {exc}")

        if faces_count > 0:
            if max_face_area_ratio >= 0.20:
                framing = "CLOSE_UP"
            elif max_face_area_ratio >= 0.05:
                framing = "MEDIUM_SHOT"
            else:
                framing = "WIDE_SHOT"
        elif category.lower() in ["product", "brand"]:
            framing = "PRODUCT_ISOLATED"
        else:
            framing = "ENVIRONMENT_OR_PROP"

        return round(blur_score, 1), is_sharp, framing, faces_count

    @staticmethod
    def compute_phash(pil_img: Image.Image) -> str:
        try:
            return str(imagehash.phash(pil_img))
        except Exception:
            return ""

    @staticmethod
    def extract_text_labels(cv_img: np.ndarray) -> List[str]:
        ocr = _get_ocr_engine()

        if not ocr or cv_img is None:
            return []

        try:
            result, _ = ocr(cv_img)

            if result:
                labels = [
                    line[1].strip()
                    for line in result
                    if len(line) > 1 and line[1].strip()
                ]
                return labels[:10]
        except Exception as exc:
            logger.debug(f"OCR label extraction error: {exc}")

        return []

    @staticmethod
    def analyze_image_bytes(
        image_bytes: bytes,
        filename: str = "asset.jpg",
        category: str = "asset",
    ) -> ImageFeatureProfile:
        profile = ImageFeatureProfile(category=category, filename=filename)

        if not image_bytes:
            return profile

        try:
            pil_img = Image.open(io.BytesIO(image_bytes))
            profile.width, profile.height = pil_img.size
            profile.aspect_ratio = ImageAnalysisService._calculate_aspect_ratio_str(
                profile.width, profile.height
            )
            profile.is_vertical = profile.height > profile.width
            profile.phash = ImageAnalysisService.compute_phash(pil_img)
        except Exception as exc:
            logger.warning(f"Pillow decode failed for {filename}: {exc}")

        try:
            image_array = np.frombuffer(image_bytes, np.uint8)
            cv_img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

            if cv_img is not None:
                blur, is_sharp, framing, faces_count = (
                    ImageAnalysisService.evaluate_quality_and_framing(cv_img, category)
                )
                profile.blur_score = blur
                profile.is_sharp = is_sharp
                profile.framing_type = framing
                profile.detected_faces_count = faces_count
                profile.detected_labels = ImageAnalysisService.extract_text_labels(cv_img)
        except Exception as exc:
            logger.warning(f"OpenCV processing failed for {filename}: {exc}")

        dominant_hex, palette, lighting_style = ImageAnalysisService.extract_colors(image_bytes)
        profile.dominant_color_hex = dominant_hex
        profile.color_palette_hex = palette
        profile.lighting_style = lighting_style

        final_category = category.lower()
        if final_category in ("asset", "auto", ""):
            if profile.detected_faces_count > 0:
                final_category = "character"
            elif any(w in filename.lower() for w in ("person", "man", "woman", "girl", "boy", "model", "character")):
                final_category = "character"
            elif any(w in filename.lower() for w in ("logo", "brand", "icon")):
                final_category = "brand"
            else:
                final_category = "product"

        profile.category = final_category

        # Refine framing if auto-detected as product with 0 faces
        if profile.detected_faces_count == 0 and final_category in ("product", "brand"):
            profile.framing_type = "PRODUCT_ISOLATED"

        labels_text = ""
        if profile.detected_labels:
            visible_labels = ", ".join(repr(label) for label in profile.detected_labels[:4])
            labels_text = f" | Detected Text: {visible_labels}"

        faces_text = ""
        if profile.detected_faces_count > 0:
            faces_text = f" | Faces: {profile.detected_faces_count}"

        orientation = "Vertical" if profile.is_vertical else "Horizontal"
        quality = "Sharp" if profile.is_sharp else "Soft/Blurry"
        palette_text = ", ".join(profile.color_palette_hex[:3])

        profile.visual_summary_bullet = (
            f"* [{final_category.upper()} - {filename}]: Ratio {profile.aspect_ratio} ({orientation}) | "
            f"Dominant Color: {profile.dominant_color_hex} | Palette: {palette_text} | "
            f"Framing: {profile.framing_type}{faces_text} | Quality: {quality}{labels_text}"
        )

        return profile

    @staticmethod
    def analyze_batch(
        assets: List[tuple[bytes, str, str]]
    ) -> List[ImageFeatureProfile]:
        results = []
        seen_hashes = {}

        for image_bytes, filename, category in assets:
            profile = ImageAnalysisService.analyze_image_bytes(
                image_bytes,
                filename=filename,
                category=category,
            )

            if profile.phash:
                try:
                    current_hash = imagehash.hex_to_hash(profile.phash)

                    for existing_name, existing_hash in seen_hashes.items():
                        if current_hash - existing_hash <= 5:
                            profile.visual_summary_bullet += (
                                f" (Note: Visually similar to {existing_name})"
                            )
                            break

                    seen_hashes[filename] = current_hash
                except Exception:
                    pass

            results.append(profile)

        return results
