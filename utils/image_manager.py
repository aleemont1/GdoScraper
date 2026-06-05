import sqlite3
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
    The directory storage/standard_images/ can be populated with user assets.
    """
    norm = _normalize_string(product_name)
    if not norm:
        return None

    # Fresh Produce (Ortofrutta) - Substring mappings
    fruit_veg_map = {
        "banan": "banane.png",
        "mela": "mele.png",
        "mele": "mele.png",
        "limon": "limoni.png",
        "aranc": "arance.png",
        "pomodor": "pomodori.png",
        "zucchin": "zucchine.png",
        "patat": "patate.png",
        "insalat": "insalata.png",
        "carot": "carote.png",
        "cipoll": "cipolle.png",
        "fragol": "fragole.png",
        "pesch": "pesche.png",
        "albicocc": "albicocche.png",
        "anguri": "anguria.png",
        "melone": "melone.png",
        "uva": "uva.png",
        "per": "pere.png",
    }

    # Exclusion list for fresh produce standard images:
    # If the product name contains any of these processed/packaged keywords,
    # we block it from matching raw fresh fruit/vegetable illustrations.
    produce_exclusions = [
        "yogurt", "yogourt", "succo", "passata", "purea", "salsa", "sugo", 
        "gelato", "sorbetto", "confettura", "marmellata", "essiccat", "secc", 
        "bevanda", "liquore", "sciroppo", "preparato", "snack", "torta", 
        "biscott", "te ", "tè ", "infuso", "aroma", "crema", "pelati",
        "scatola", "lattina", "cotto", "omogeneizzato", "nettare"
    ]
    
    is_excluded_from_fresh = any(exc in norm for exc in produce_exclusions)

    if not is_excluded_from_fresh:
        for key, filename in fruit_veg_map.items():
            if key in norm:
                logger.info(f"Standard fresh produce image match for '{product_name}' -> '{filename}'")
                return f"/storage/standard_images/{filename}"

    # Major Brands & Common Packaged Items
    brand_packaged_map = {
        "nutella": "nutella.png",
        "lavazza": "caffe_lavazza.png",
        "moretti": "birra_moretti.png",
        "uova": "uova.png",
    }

    for key, filename in brand_packaged_map.items():
        if key in norm:
            logger.info(f"Standard brand/packaged image match for '{product_name}' -> '{filename}'")
            return f"/storage/standard_images/{filename}"

    return None


def find_reusable_image(
    supermarket: str,
    product_name: str,
    db_path: str = "storage/promotions.db",
    threshold: float = 0.88,
) -> Optional[str]:
    """
    Scans the promotions database for products with highly similar names (using fuzzy matching)
    within the same supermarket chain. If a match is found, returns its existing image URL,
    allowing us to reuse the crop on disk and save massive disk space.
    """
    if not os.path.exists(db_path):
        return None

    normalized_new = _normalize_string(product_name)
    if not normalized_new or len(normalized_new) < 3:
        return None

    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            cursor = conn.cursor()
            
            # 1. Fast exact-match lookup on raw name
            cursor.execute(
                "SELECT image_url FROM promotions WHERE supermarket = ? AND name = ? AND image_url IS NOT NULL AND image_url != '' LIMIT 1;",
                (supermarket, product_name),
            )
            row = cursor.fetchone()
            if row:
                logger.info(f"Fast exact raw match found for '{product_name}': reusing '{row[0]}'")
                return row[0]

            # 2. Word/keyword filtering inside SQLite before using difflib.SequenceMatcher
            words = [w for w in normalized_new.split() if len(w) >= 3]
            if words:
                like_clauses = " OR ".join(["name LIKE ?" for _ in words])
                query = f"""
                    SELECT name, image_url 
                    FROM promotions 
                    WHERE supermarket = ? 
                      AND image_url IS NOT NULL 
                      AND image_url != '' 
                      AND ({like_clauses});
                """
                params = [supermarket] + [f"%{w}%" for w in words]
                cursor.execute(query, params)
            else:
                cursor.execute(
                    "SELECT name, image_url FROM promotions WHERE supermarket = ? AND image_url IS NOT NULL AND image_url != '';",
                    (supermarket,),
                )
            rows = cursor.fetchall()

        best_match_url = None
        best_ratio = 0.0

        for old_name, image_url in rows:
            normalized_old = _normalize_string(old_name)
            if not normalized_old:
                continue

            # Quick check if exact match after normalization
            if normalized_new == normalized_old:
                logger.info(f"Exact semantic image match found for '{product_name}': reusing '{image_url}'")
                return image_url

            # Fuzzy match ratio using standard library difflib (fast and zero-dependency)
            ratio = difflib.SequenceMatcher(None, normalized_new, normalized_old).ratio()
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


def post_process_image_background(pil_img: Image.Image, padding_percent: float = 0.03) -> Image.Image:
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
                f"Background auto-trimmer optimized bounding box from {w}x{h} to {crop_box[2]-crop_box[0]}x{crop_box[3]-crop_box[1]}"
            )
            return pil_img.crop(crop_box)

    except Exception as err:
        logger.warning(f"Background auto-trimming post-process failed: {err}")

    return pil_img
