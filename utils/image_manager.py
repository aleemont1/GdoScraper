import os
import re
import difflib
from typing import Optional
from PIL import Image, ImageChops
from utils.logger import setup_logger

logger = setup_logger("ImageManager")


def _normalize_string(text: str) -> str:
    """
    Lowercases, removes accented chars, filters out special characters,
    and strips extra spaces to ease comparison.
    """
    if not text:
        return ""
    text = text.lower()
    # Accented char normalizations
    text = re.sub(r"[àáâäãå]", "a", text)
    text = re.sub(r"[èéêë]", "e", text)
    text = re.sub(r"[ìíîï]", "i", text)
    text = re.sub(r"[òóôöõ]", "o", text)
    text = re.sub(r"[ùúûü]", "u", text)
    # Strip non-alphanumeric
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return " ".join(text.split())


def get_standard_image(product_name: str) -> Optional[str]:
    """
    Maps highly common product names (fresh produce, major brands) to standardized image assets.
    Returns the served web URL if matched, otherwise None.
    The directory assets/standard_images/ can be populated with user assets.
    """
    norm = _normalize_string(product_name)
    if not norm:
        return None

    # Fresh Produce (Ortofrutta) - Substring mappings
    fruit_veg_map = {
        "banan": "banane.png",
        "mele": "mele.png",
        "limon": "limoni.png",
        "aranc": "arance.png",
        "pomodor": "pomodori.png",
        "zucchin": "zucchine.png",
        "patat": "patate.png",
        "lattuga": "lattuga.png",
        "carot": "carote.png",
        "cipoll": "cipolle.png",
        "fragol": "fragole.png",
        "pesch": "pesche.png",
        "albicocc": "albicocche.png",
        "anguri": "anguria.png",
        "melone": "melone.png",
        "uva": "uva.png",
        "pere": "pere.png",
        "pera": "pere.png",
        "melanzan": "melanzane.png",
        "peperon": "peperoni.png",
        "cavolfior": "cavolfiore.png",
        "broccol": "broccoli.png",
        "cavolo": "cavolo.png",
        "finocch": "finocchi.png",
        "sedano": "sedano.png",
        "radicch": "radicchio.png",
        "ravanell": "ravanelli.png",
    }

    # Exclusion list for fresh produce standard images:
    # If the product name contains any of these processed/packaged keywords,
    # we block it from matching raw fresh fruit/vegetable illustrations.
    produce_exclusions = [
        "yogurt",
        "yogourt",
        "succo",
        "passata",
        "purea",
        "salsa",
        "sugo",
        "gelato",
        "sorbetto",
        "composta",
        "centrifuga",
        "confettura",
        "marmellata",
        "essiccat",
        "secc",
        "bevanda",
        "liquore",
        "sciroppo",
        "preparato",
        "snack",
        "torta",
        "biscott",
        "te ",
        "tè ",
        "infuso",
        "aroma",
        "crema",
        "pelati",
        "scatola",
        "lattina",
        "cotto",
        "omogeneizzato",
        "nettare",
        "gusto",
        "sapore",
        "profumo",
        "aromatizzat",
        "insalata di",
        "insalata russa",
        "insalata caprese",
        "insalata di riso",
        "insalata di mare",
        "insalata di pollo",
        "insalata greca",
        "insalata ricca",
        "insalata mista",
        "insalata di patate",
        "insalata di tonno",
        "insalata di pasta",
    ]

    is_excluded_from_fresh = any(exc in norm for exc in produce_exclusions)

    if not is_excluded_from_fresh:
        for key, filename in fruit_veg_map.items():
            if key in norm:
                logger.info(
                    f"Standard fresh produce image match for '{product_name}' -> '{filename}'"
                )
                return f"/assets/standard_images/{filename}"

    # Major Brands & Common Packaged Items
    brand_packaged_map = {
        "nutella": "nutella.png",
        "lavazza": "caffe_lavazza.png",
        "moretti": "birra_moretti.png",
        "uova": "uova.png",
    }

    for key, filename in brand_packaged_map.items():
        if key in norm:
            logger.info(
                f"Standard brand/packaged image match for '{product_name}' -> '{filename}'"
            )
            return f"/assets/standard_images/{filename}"

    return None


def find_reusable_image(
    supermarket: str,
    product_name: str,
    db_path: str = "storage/promotions.db",
    threshold: float = 0.88,
) -> Optional[str]:
    """
    Scans the promotions database or active storage engine for products with highly similar names
    within the same supermarket chain. If a match is found, returns its existing image URL,
    allowing us to reuse the crop on disk and save massive disk space.
    """
    from db_engine.database import get_storage

    storage = get_storage(db_path=db_path)

    # If using local SQLite and the DB file doesn't exist, search can't proceed
    if hasattr(storage, "db_path") and not os.path.exists(storage.db_path):
        return None

    normalized_new = _normalize_string(product_name)
    if not normalized_new or len(normalized_new) < 3:
        return None

    try:
        # Fetch reusable image candidates from active storage engine
        rows = storage.find_reusable_images(supermarket)
        if not rows:
            return None

        # 1. Fast exact-match lookup on raw name
        for r in rows:
            name = r.get("name")
            image_url = r.get("image_url")
            if name == product_name and image_url:
                logger.info(
                    f"Fast exact raw match found for '{product_name}': reusing '{image_url}'"
                )
                return image_url

        best_match_url = None
        best_ratio = 0.0

        for r in rows:
            old_name = r.get("name")
            image_url = r.get("image_url")
            if not old_name or not image_url:
                continue
            normalized_old = _normalize_string(old_name)
            if not normalized_old:
                continue

            # Quick check if exact match after normalization
            if normalized_new == normalized_old:
                logger.info(
                    f"Exact semantic image match found for '{product_name}': reusing '{image_url}'"
                )
                return image_url

            # Fuzzy match ratio using standard library difflib (fast and zero-dependency)
            ratio = difflib.SequenceMatcher(
                None, normalized_new, normalized_old
            ).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match_url = image_url

        if best_ratio >= threshold and best_match_url:
            logger.info(
                f"Fuzzy semantic image match found (ratio={best_ratio:.2f}) for '{product_name}' resembling existing image: reusing '{best_match_url}'"
            )
            return best_match_url

    except Exception as err:
        logger.error(f"Fuzzy image reuse scan failed: {err}")

    return None


def post_process_image_background(
    pil_img: Image.Image, padding_percent: float = 0.03
) -> Image.Image:
    """
    Cleans up cropped product card images by dynamically trimming flat solid backgrounds
    (like the white margins in paper circular flyers) so that the product visually stands out.
    """
    try:
        # Convert image to RGB if it is RGBA or L
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")

        # Get background color - usually pure white (255, 255, 255)
        # We can construct a solid white image and measure differences
        bg = Image.new("RGB", pil_img.size, (255, 255, 255))
        diff = ImageChops.difference(pil_img, bg)

        # Amplify differences to find edges clearly
        diff = ImageChops.add(diff, diff, 2.0, -100)
        bbox = diff.getbbox()

        if bbox:
            w, h = pil_img.size
            x0, y0, x1, y1 = bbox

            # Add a small aesthetic breathing room margin around the trimmed box
            box_w = x1 - x0
            box_h = y1 - y0
            pad_x = max(2, int(box_w * padding_percent))
            pad_y = max(2, int(box_h * padding_percent))

            crop_box = (
                max(0, x0 - pad_x),
                max(0, y0 - pad_y),
                min(w, x1 + pad_x),
                min(h, y1 + pad_y),
            )

            logger.info(
                f"Background auto-trimmer optimized bounding box from {w}x{h} to {crop_box[2] - crop_box[0]}x{crop_box[3] - crop_box[1]}"
            )
            return pil_img.crop(crop_box)

    except Exception as err:
        logger.warning(f"Background auto-trimming post-process failed: {err}")

    return pil_img


def draw_coordinate_grid(pil_img: Image.Image) -> Image.Image:
    """
    Superimposes a transparent/light coordinate grid (intervals of 100 on a 0-1000 scale)
    with red numeric labels onto a copy of the image. Helps VLMs locate bounding boxes precisely.
    """
    from PIL import ImageDraw, ImageFont

    # Work on a copy of the image so that the original remains clean for final cropping
    grid_img = pil_img.copy()
    w, h = grid_img.size

    draw = ImageDraw.Draw(grid_img)

    # 1. Draw light coordinate grid lines
    # We use a neutral light gray (200, 200, 200) so it doesn't obstruct visual text
    grid_color = (200, 200, 200)

    for i in range(100, 1000, 100):
        # Vertical grid line at x = i (normalized to w)
        x = int((i / 1000.0) * w)
        draw.line([(x, 0), (x, h)], fill=grid_color, width=1)

        # Horizontal grid line at y = i (normalized to h)
        y = int((i / 1000.0) * h)
        draw.line([(0, y), (w, y)], fill=grid_color, width=1)

    # 2. Draw border numeric coordinates (Red text for maximum visibility to VLMs)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    text_color = (255, 0, 0)

    for i in range(100, 1000, 100):
        x = int((i / 1000.0) * w)
        y = int((i / 1000.0) * h)

        # Top margin labels
        draw.text((x + 2, 2), str(i), fill=text_color, font=font)
        # Bottom margin labels
        draw.text((x + 2, h - 15), str(i), fill=text_color, font=font)

        # Left margin labels
        draw.text((2, y + 2), str(i), fill=text_color, font=font)
        # Right margin labels
        draw.text((w - 25, y + 2), str(i), fill=text_color, font=font)

    return grid_img
