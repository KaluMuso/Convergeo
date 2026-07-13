#!/usr/bin/env python3
"""Upload demo category images to Cloudinary for the staging marketplace seed.

Stdlib-only (no pip installs) so it runs anywhere Python 3.10+ exists,
e.g. the staging API host. Reads credentials from the CLOUDINARY_URL env var
(cloudinary://<api_key>:<api_secret>@<cloud_name>) — never hardcode them.

Image sourcing, best-first:
  1. Pexels search (set PEXELS_API_KEY for high-quality, keyword-matched photos
     — free key from https://www.pexels.com/api/).
  2. LoremFlickr keyword placeholder (no key needed, CC-licensed Flickr photos).
  3. Generated gradient SVG placeholder (always succeeds, offline-safe).

Each category uploads to public_id `demo/categories/<slug>` (overwrite on),
so re-runs are idempotent and the DB seed can reference IDs deterministically.

Usage:
  export CLOUDINARY_URL='cloudinary://KEY:SECRET@cloud'   # from the dashboard
  export PEXELS_API_KEY='...'                             # optional but better
  python3 scripts/seed/upload_demo_images.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# category slug -> photo search keywords (Zambia-flavoured where it matters)
CATEGORY_KEYWORDS: dict[str, str] = {
    "mobile-phones": "smartphone",
    "chitenge-fabric": "african fabric colorful",
    "rice-grains": "rice bag grain",
    "flour-baking": "flour baking",
    "cooking-oil": "cooking oil bottle",
    "office-furniture": "office desk chair",
    "tvs-audio": "television living room",
    "mattresses": "mattress bed",
    "solar-power": "solar panel",
    "small-appliances": "kitchen blender appliance",
    "paper-notebooks": "notebook stationery",
    "phone-accessories": "phone case earphones",
    "jewelry": "jewelry necklace",
    "bathroom": "bathroom towels",
    "locks-security": "padlock security",
    "pasta-noodles": "pasta noodles",
    "lighting": "lamp light bulb",
    "spices-seasonings": "spices market",
    "printers-ink": "printer office",
    "kids-clothing": "children clothes",
    "hand-tools": "hand tools workshop",
    "laptops-computers": "laptop computer",
    "home-decor": "home decor vase",
    "mens-clothing": "men shirt fashion",
    "kitchenware": "cooking pots kitchen",
    "garden-tools": "garden tools",
    "footwear": "shoes sneakers",
    "snacks": "snacks chips",
    "tea-coffee": "tea coffee cup",
    "bags-accessories": "handbag leather",
    "hair-care": "hair care products",
    "oral-care": "toothbrush toothpaste",
    "furniture": "sofa furniture",
    "calculators": "calculator desk",
    "storage": "storage boxes",
    "paint": "paint cans brush",
    "deodorants": "deodorant spray",
    "plumbing": "plumbing pipes",
    "fasteners": "screws bolts",
    "womens-clothing": "woman dress fashion",
    "art-supplies": "art supplies paint brushes",
    "filing-storage": "office files folders",
    "traditional-wear": "african traditional clothing",
    "sugar-sweeteners": "sugar bowl",
    "baby-care": "baby products care",
    "safety-equipment": "safety helmet gloves",
    "cameras": "camera photography",
    "electrical-supplies": "electrical cables tools",
    "school-supplies": "school supplies pencils",
    "canned-goods": "canned food",
    "gaming": "game controller console",
    "skincare": "skincare cream",
    "pens-writing": "pens writing desk",
    "beverages": "soft drinks bottles",
    "cleaning-supplies": "cleaning products",
    "makeup": "makeup cosmetics",
    "garden-outdoor": "garden outdoor plants",
    "mens-grooming": "razor shaving men",
    "body-care": "body lotion soap",
    "bedding": "bedding duvet pillows",
}

BRAND_GRADIENTS = [
    ("#0e7a5f", "#12a37f"),
    ("#c2410c", "#f97316"),
    ("#1d4ed8", "#3b82f6"),
    ("#7e22ce", "#a855f7"),
    ("#be123c", "#f43f5e"),
]


def parse_cloudinary_url() -> tuple[str, str, str]:
    raw = os.environ.get("CLOUDINARY_URL", "")
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme != "cloudinary" or not (parsed.username and parsed.password and parsed.hostname):
        sys.exit("Set CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>")
    return parsed.username, parsed.password, parsed.hostname


def http_get(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "vergeo5-seed/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_pexels(keywords: str, api_key: str) -> bytes | None:
    query = urllib.parse.urlencode({"query": keywords, "per_page": 1, "orientation": "landscape"})
    try:
        body = json.loads(
            http_get(f"https://api.pexels.com/v1/search?{query}", headers={"Authorization": api_key})
        )
        photos = body.get("photos") or []
        if not photos:
            return None
        return http_get(photos[0]["src"]["large"])
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, TimeoutError):
        return None


def fetch_loremflickr(keywords: str) -> bytes | None:
    slug = ",".join(keywords.split()[:2])
    try:
        return http_get(f"https://loremflickr.com/800/600/{urllib.parse.quote(slug)}")
    except (urllib.error.URLError, TimeoutError):
        return None


def gradient_svg(slug: str) -> bytes:
    a, b = BRAND_GRADIENTS[int(hashlib.md5(slug.encode()).hexdigest(), 16) % len(BRAND_GRADIENTS)]
    label = slug.replace("-", " ").title()
    return f"""<svg xmlns='http://www.w3.org/2000/svg' width='800' height='600'>
  <defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
    <stop offset='0%' stop-color='{a}'/><stop offset='100%' stop-color='{b}'/>
  </linearGradient></defs>
  <rect width='800' height='600' fill='url(#g)'/>
  <text x='400' y='300' font-family='Arial, sans-serif' font-size='44' font-weight='700'
        fill='white' text-anchor='middle' dominant-baseline='middle' opacity='0.92'>{label}</text>
</svg>""".encode()


def cloudinary_upload(image: bytes, public_id: str, api_key: str, api_secret: str, cloud: str) -> str:
    timestamp = str(int(time.time()))
    params = {"overwrite": "true", "public_id": public_id, "timestamp": timestamp}
    to_sign = "&".join(f"{k}={v}" for k, v in sorted(params.items())) + api_secret
    signature = hashlib.sha1(to_sign.encode()).hexdigest()

    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in {**params, "api_key": api_key, "signature": signature}.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="img"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode()
    )
    body = b"".join(parts) + image + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{cloud}/image/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["public_id"]


def main() -> None:
    api_key, api_secret, cloud = parse_cloudinary_url()
    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    results: dict[str, str] = {}

    for slug, keywords in CATEGORY_KEYWORDS.items():
        image = None
        source = "svg"
        if pexels_key:
            image = fetch_pexels(keywords, pexels_key)
            source = "pexels" if image else source
        if image is None:
            image = fetch_loremflickr(keywords)
            source = "loremflickr" if image else source
        if image is None:
            image = gradient_svg(slug)
            source = "svg"

        public_id = cloudinary_upload(image, f"demo/categories/{slug}", api_key, api_secret, cloud)
        results[slug] = source
        print(f"  {slug:<24} -> {public_id} ({source})")
        time.sleep(0.3)  # be polite to the photo APIs

    counts: dict[str, int] = {}
    for source in results.values():
        counts[source] = counts.get(source, 0) + 1
    print(f"\nDone: {len(results)} categories uploaded to cloud '{cloud}' — sources: {counts}")
    print("Next: run the listing_images seed SQL (see docs/plan/00-status.md deploy notes).")


if __name__ == "__main__":
    main()
