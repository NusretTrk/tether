"""
OCR helpers, contained to what still needs pixels after the transcript/UIA
split: typing into the composer, and the model/effort picker. Reading chat
content, session lists, and command output no longer goes through here.
"""
from __future__ import annotations

import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def ocr_text(img: Image.Image) -> str:
    return pytesseract.image_to_string(img)


def ocr_word_data(img: Image.Image) -> dict:
    return pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)


def ocr_find_word(img: Image.Image, target: str):
    """Returns (center_x, center_y) of the first word box matching target
    (case-insensitive), or None."""
    data = ocr_word_data(img)
    for i, word in enumerate(data["text"]):
        if word.strip().lower() == target.lower():
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            return (x + w // 2, y + h // 2)
    return None


def ocr_lines(img: Image.Image) -> list[tuple[str, int, int, int, int]]:
    """Groups OCR word boxes into lines (titles/placeholders are multi-word).
    Returns [(text, left, top, right, bottom), ...] top to bottom, image-relative px."""
    data = ocr_word_data(img)
    lines: dict[tuple[int, int, int], dict] = {}
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        entry = lines.setdefault(key, {"words": [], "left": x, "top": y, "right": x + w, "bottom": y + h})
        entry["words"].append(word)
        entry["left"] = min(entry["left"], x)
        entry["top"] = min(entry["top"], y)
        entry["right"] = max(entry["right"], x + w)
        entry["bottom"] = max(entry["bottom"], y + h)

    result = []
    for key in sorted(lines.keys()):
        e = lines[key]
        result.append((" ".join(e["words"]), e["left"], e["top"], e["right"], e["bottom"]))
    return result


def find_input_box_anchor(img: Image.Image):
    """Locates the message box by its placeholder text ('Type / for commands'),
    visible only while the box is empty. Search is restricted to a bottom
    strip and only requires "type" (not the full phrase) — a narrowed content
    column (side panel open) can wrap or truncate the placeholder to just
    "Type /", and requiring "command" too failed to match then, silently
    falling back to a wrong-for-that-layout fixed-ratio guess. The vertical
    restriction is what keeps a loose single-word match safe.
    Returns (left, top, right, bottom) image-relative px, or None."""
    bottom_y = max(0, img.height - 200)
    strip = img.crop((0, bottom_y, img.width, img.height))
    for t, left, top, right, bottom in ocr_lines(strip):
        if "type" in t.lower():
            return (left, top + bottom_y, right, bottom + bottom_y)
    return None
