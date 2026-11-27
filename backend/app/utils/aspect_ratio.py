"""Shared aspect-ratio detection, normalization, and resolution helpers.

Provides a single source of truth so user/script aspect ratios (e.g., 16:9, 9:16)
are preserved end-to-end from initial script parsing through image and video
generation without being overwritten by noisy keywords or loose fallbacks.
"""
from collections import Counter
import re
from typing import Any, Optional

SUPPORTED_ASPECT_RATIOS: tuple[str, ...] = ("16:9", "9:16", "1:1", "4:3", "3:4")
VEO_SUPPORTED_ASPECT_RATIOS: tuple[str, ...] = ("16:9", "9:16", "1:1")

_RE_NUMERIC_RATIO = re.compile(
    r"(?<![\d:])(16\s*[:/x]\s*9|9\s*[:/x]\s*16|1\s*:\s*1|1\s*x\s*1|4\s*[:/x]\s*3|3\s*[:/x]\s*4)(?![\d:])",
    re.IGNORECASE,
)

_RE_NEGATED_ASPECT = re.compile(
    r"\b(?:not|never|no|avoid|without|instead\s+of|rather\s+than)\s+"
    r"(?:be\s+|make\s+it\s+|use\s+|using\s+|in\s+|a\s+|an\s+|to\s+)*"
    r"(?:9\s*[:/x]\s*16|16\s*[:/x]\s*9|1\s*[:/x]\s*1|4\s*[:/x]\s*3|3\s*[:/x]\s*4|"
    r"vertical|horizontal|widescreen|landscape|square|"
    r"portrait(?:\s+(?:orientation|mode|format|aspect|ratio|video|frame|layout))?)\b",
    re.IGNORECASE,
)

# Explicit field headers such as "Aspect ratio: 16:9 for youtube" or "Format: 9:16 Reels"
_RE_EXPLICIT_HEADER = re.compile(
    r"(?:^|[\n\r;|(\[])\s*(?:target\s+|output\s+|video\s+|master\s+)?"
    r"(?:aspect\s*ratio|aspect|output\s*format|video\s*format|framing\s*ratio|orientation|format)\s*"
    r"[:=\-]\s*([^\n\r;|]+)",
    re.IGNORECASE | re.MULTILINE,
)

# Inline declarations such as "all shots and images in aspect ratio 16:9 for youtube"
_RE_INLINE_ASPECT_DECL = re.compile(
    r"\baspect\s*ratio\b\s*(?:is|should\s+be|of|=|:|-)?\s*"
    r"(16\s*[:/x]\s*9|9\s*[:/x]\s*16|1\s*:\s*1|1\s*x\s*1|4\s*[:/x]\s*3|3\s*[:/x]\s*4|"
    r"vertical|horizontal|widescreen|landscape|square|portrait)\b",
    re.IGNORECASE,
)

# Careful vertical/horizontal platform & orientation keywords:
# Intentionally avoids ambiguous English words like "short" ("a short laugh"),
# "story" ("storyline"), or bare "portrait" ("close-up portrait of a person").
RE_VERTICAL_KEYWORDS = re.compile(
    r"\b(?:9\s*:\s*16|vertical|reels?|tiktok|ig\s+reels?|instagram\s+reels?|"
    r"youtube\s+shorts?|yt\s+shorts?|shorts\s+(?:video|format|reel)|"
    r"(?:ig|instagram|snapchat)\s+stor(?:y|ies)|"
    r"portrait\s+(?:orientation|mode|format|aspect|ratio|video|frame|layout))\b",
    re.IGNORECASE,
)

RE_HORIZONTAL_KEYWORDS = re.compile(
    r"\b(?:16\s*:\s*9|horizontal|widescreen|landscape|youtube|cinemascope)\b",
    re.IGNORECASE,
)


def _normalize_numeric_token(token: str) -> Optional[str]:
    compact = re.sub(r"\s+", "", token.lower()).replace("/", ":").replace("x", ":")
    if compact in SUPPORTED_ASPECT_RATIOS:
        return compact
    return None


def _coerce_to_allowed(
    ratio: Optional[str],
    allowed: Optional[tuple[str, ...]],
    default: Optional[str],
) -> Optional[str]:
    if not ratio:
        return default
    if allowed is None or ratio in allowed:
        return ratio
    # Map non-Veo 4:3 / 3:4 to the closest matching orientation when Veo is targeted
    if ratio == "3:4" and "9:16" in allowed:
        return "9:16"
    if ratio == "4:3" and "16:9" in allowed:
        return "16:9"
    return default


def normalize_aspect_ratio(
    value: Optional[str],
    allowed: Optional[tuple[str, ...]] = None,
    default: Optional[str] = None,
) -> Optional[str]:
    """Normalize aspect-ratio inputs into canonical strings (e.g. '16:9', '9:16')."""
    if value is None:
        return default
    raw = str(value).strip()
    if not raw or raw.lower() in {"unknown", "none", "null", "n/a", "auto"}:
        return default

    # 1. Explicit numeric ratio (handles "16:9", "16:9 (Landscape)", "16 / 9", "9x16")
    m = _RE_NUMERIC_RATIO.search(raw)
    if m:
        numeric = _normalize_numeric_token(m.group(1))
        return _coerce_to_allowed(numeric, allowed, default)

    lower = raw.lower()
    # 2. Pixel dimensions when passed instead of ratio
    if any(res in lower for res in ("1920x1080", "1280x720", "3840x2160")):
        return _coerce_to_allowed("16:9", allowed, default)
    if any(res in lower for res in ("1080x1920", "720x1280", "2160x3840")):
        return _coerce_to_allowed("9:16", allowed, default)
    if "1080x1080" in lower:
        return _coerce_to_allowed("1:1", allowed, default)

    # 3. Clear orientation / platform words
    if RE_VERTICAL_KEYWORDS.search(lower) or re.search(r"\bportrait\b", lower):
        return _coerce_to_allowed("9:16", allowed, default)
    if re.search(r"\b(?:horizontal|landscape|widescreen|cinemascope)\b", lower):
        return _coerce_to_allowed("16:9", allowed, default)
    if re.search(r"\bsquare\b", lower):
        return _coerce_to_allowed("1:1", allowed, default)

    return default


def infer_orientation_from_aspect_ratio(aspect_ratio: Optional[str]) -> Optional[str]:
    """Return canonical orientation ('horizontal', 'vertical', or 'square') for a ratio."""
    norm = normalize_aspect_ratio(aspect_ratio)
    if norm in ("9:16", "3:4"):
        return "vertical"
    if norm in ("16:9", "4:3"):
        return "horizontal"
    if norm == "1:1":
        return "square"
    return None


def _strip_negated_mentions(text: str) -> str:
    """Replace negated aspect-ratio phrases with spaces so banned ratios are never chosen."""
    return _RE_NEGATED_ASPECT.sub(lambda m: " " * len(m.group(0)), text)


def _extract_ratio_from_declaration(decl_value: str) -> Optional[str]:
    """Extract an aspect ratio strictly from a declaration header or phrase."""
    m = _RE_NUMERIC_RATIO.search(decl_value)
    if m:
        return _normalize_numeric_token(m.group(1))
    lower = decl_value.lower()
    if RE_VERTICAL_KEYWORDS.search(lower) or re.search(r"\bportrait\b", lower):
        return "9:16"
    if re.search(r"\b(?:horizontal|landscape|widescreen|cinemascope)\b", lower):
        return "16:9"
    if re.search(r"\bsquare\b", lower):
        return "1:1"
    return None


def _winner_or_none(counts: Counter[str]) -> Optional[str]:
    if not counts:
        return None
    ranked = counts.most_common()
    if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
        return ranked[0][0]
    return None


def detect_aspect_ratio_from_script(script_text: str) -> tuple[Optional[str], bool]:
    """Detect script aspect ratio without false positives from narrative prose.

    Returns:
        (normalized_ratio_or_None, is_explicit)
        `is_explicit` is True only when the user wrote an explicit aspect declaration
        or unambiguous numeric ratio (e.g. "Aspect ratio: 16:9", "9:16").
    """
    if not script_text or not script_text.strip():
        return None, False

    sanitized = _strip_negated_mentions(script_text)

    # Tier 1: Explicit header declarations ("Aspect ratio: 16:9", "Format: 9:16 Reels")
    # and inline declarations ("in Aspect ratio 16:9")
    explicit_counts: Counter[str] = Counter()
    for match in _RE_EXPLICIT_HEADER.finditer(sanitized):
        parsed = _extract_ratio_from_declaration(match.group(1))
        if parsed:
            explicit_counts[parsed] += 1
    for match in _RE_INLINE_ASPECT_DECL.finditer(sanitized):
        parsed = _extract_ratio_from_declaration(match.group(1))
        if parsed:
            explicit_counts[parsed] += 1

    tier1_winner = _winner_or_none(explicit_counts)
    if tier1_winner:
        return tier1_winner, True

    # Tier 2: Standalone numeric ratios anywhere in the script (e.g. "16:9", "9:16")
    numeric_counts: Counter[str] = Counter()
    for match in _RE_NUMERIC_RATIO.finditer(sanitized):
        parsed = _normalize_numeric_token(match.group(1))
        if parsed:
            numeric_counts[parsed] += 1

    if numeric_counts:
        tier2_winner = _winner_or_none(numeric_counts)
        if tier2_winner:
            return tier2_winner, True
        # Equal tie in body numeric ratios (e.g. both 16:9 and 9:16 mentioned once with no header)
        return None, False

    # Tier 3: Unambiguous platform/orientation keywords (advisory, never strict override)
    # Mask "youtube shorts" / "yt shorts" first so "youtube" is not double-counted as horizontal.
    vert_matches = list(RE_VERTICAL_KEYWORDS.finditer(sanitized))
    horiz_source = re.sub(
        r"\b(?:youtube|yt)\s+shorts?\b",
        lambda m: " " * len(m.group(0)),
        sanitized,
        flags=re.IGNORECASE,
    )
    horiz_matches = list(RE_HORIZONTAL_KEYWORDS.finditer(horiz_source))

    if len(vert_matches) > len(horiz_matches):
        return "9:16", False
    if len(horiz_matches) > len(vert_matches):
        return "16:9", False

    return None, False


def get_spec_aspect_ratio(
    spec: Any,
    prompt_set: Any = None,
    fallback: str = "16:9",
    allowed: Optional[tuple[str, ...]] = None,
) -> str:
    """Resolve the normalized target aspect ratio from VideoSpecification or PromptSet."""
    spec_ratio = None
    if spec is not None and getattr(spec, "output_requirements", None) is not None:
        spec_ratio = getattr(spec.output_requirements, "aspect_ratio", None)

    prompt_set_ratio = getattr(prompt_set, "aspect_ratio", None) if prompt_set is not None else None

    resolved = normalize_aspect_ratio(spec_ratio, allowed=allowed) or normalize_aspect_ratio(
        prompt_set_ratio, allowed=allowed
    )
    if resolved:
        return resolved
    return normalize_aspect_ratio(fallback, allowed=allowed, default="16:9") or "16:9"
