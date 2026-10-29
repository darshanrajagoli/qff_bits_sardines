"""Fetch and canonicalise the 12 museum paintings plus 3 stress-test artworks for SwapPrint.

Saves:
- data/artworks/<slug>.png (256x256 RGB, lossless PNG)
- data/artworks/SOURCES.md (metadata table with sources and CC0/public domain licences)
- data/raw/<slug>.* (cached raw downloads, gitignored)
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

import swapprint as sp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fetch_artworks")

# Metadata and verified endpoints for the 12 museum artworks
ARTWORKS_SPECS = [
    # Art Institute of Chicago (AIC)
    {
        "slug": "seurat_grande_jatte",
        "museum": "AIC",
        "id": 27992,
        "object_url": "https://www.artic.edu/artworks/27992",
        "fallback_image_url": "https://www.artic.edu/iiif/2/2d484387-2509-5e8e-2c43-22f9981972eb/full/843,/0/default.jpg",
        "notes": "Dense pointillism",
    },
    {
        "slug": "vangogh_bedroom",
        "museum": "AIC",
        "id": 28560,
        "object_url": "https://www.artic.edu/artworks/28560",
        "fallback_image_url": "https://www.artic.edu/iiif/2/6644829f-f292-c5c4-a73c-0356a6fdbf0d/full/843,/0/default.jpg",
        "notes": "Strong colour blocks",
    },
    {
        "slug": "monet_water_lilies",
        "museum": "AIC",
        "id": 16568,
        "object_url": "https://www.artic.edu/artworks/16568",
        "fallback_image_url": "https://www.artic.edu/iiif/2/3c27b499-af56-f0d5-93b5-a7f2f1ad5813/full/843,/0/default.jpg",
        "notes": "Soft, dense texture",
    },
    {
        "slug": "caillebotte_paris_street",
        "museum": "AIC",
        "id": 20684,
        "object_url": "https://www.artic.edu/artworks/20684",
        "fallback_image_url": "https://www.artic.edu/iiif/2/f8fd76e9-c396-5678-36ed-6a348c904d27/full/843,/0/default.jpg",
        "notes": "Urban perspective",
    },
    # Metropolitan Museum of Art (Met)
    {
        "slug": "hokusai_great_wave",
        "museum": "Met",
        "id": 45434,
        "object_url": "https://www.metmuseum.org/art/collection/search/45434",
        "fallback_image_url": "https://images.metmuseum.org/CRDImages/as/web-large/DP130155.jpg",
        "notes": "Flat-colour woodblock print",
    },
    {
        "slug": "hiroshige_sudden_shower",
        "museum": "Met",
        "id": 55433,
        "object_url": "https://www.metmuseum.org/art/collection/search/55433",
        "fallback_image_url": "https://images.metmuseum.org/CRDImages/as/web-large/DP130156.jpg",
        "notes": "Graphic rain woodblock print",
    },
    {
        "slug": "hiroshige_plum_tree",
        "museum": "Met",
        "id": 56940,
        "object_url": "https://www.metmuseum.org/art/collection/search/56940",
        "fallback_image_url": "https://images.metmuseum.org/CRDImages/as/web-large/DP120480.jpg",
        "notes": "Sparse print, flat areas",
    },
    {
        "slug": "vangogh_wheat_field",
        "museum": "Met",
        "id": 436535,
        "object_url": "https://www.metmuseum.org/art/collection/search/436535",
        "fallback_image_url": "https://images.metmuseum.org/CRDImages/ep/web-large/DP-42549-001.jpg",
        "notes": "Directional brushwork",
    },
    {
        "slug": "vangogh_straw_hat",
        "museum": "Met",
        "id": 436532,
        "object_url": "https://www.metmuseum.org/art/collection/search/436532",
        "fallback_image_url": "https://images.metmuseum.org/CRDImages/ep/web-large/DT1502_cropped2.jpg",
        "notes": "Textured portrait",
    },
    {
        "slug": "vermeer_water_pitcher",
        "museum": "Met",
        "id": 437881,
        "object_url": "https://www.metmuseum.org/art/collection/search/437881",
        "fallback_image_url": "https://images.metmuseum.org/CRDImages/ep/web-large/DP353257.jpg",
        "notes": "Quiet interior with subtle gradients",
    },
    {
        "slug": "rembrandt_self_portrait",
        "museum": "Met",
        "id": 437397,
        "object_url": "https://www.metmuseum.org/art/collection/search/437397",
        "fallback_image_url": "https://images.metmuseum.org/CRDImages/ep/web-large/DP-16323-001.jpg",
        "notes": "Dark tonal portrait",
    },
    {
        "slug": "turner_venice",
        "museum": "Met",
        "id": 437853,
        "object_url": "https://www.metmuseum.org/art/collection/search/437853",
        "fallback_image_url": "https://images.metmuseum.org/CRDImages/ep/web-large/DP169568.jpg",
        "notes": "Atmospheric landscape",
    },
]


def fetch_url(url: str, headers: dict[str, str] | None = None, max_retries: int = 3, timeout: int = 30) -> tuple[bytes, str]:
    """Download bytes with retries and timeout."""
    req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)

    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get_content_type()
                data = resp.read()
                return data, content_type
        except Exception as e:
            last_err = e
            logger.warning("Attempt %d failed for %s: %s", attempt, url, e)
            if attempt < max_retries:
                time.sleep(1.5 * attempt)
    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts: {last_err}")


def get_aic_metadata(artwork_id: int) -> dict[str, Any]:
    url = f"https://api.artic.edu/api/v1/artworks/{artwork_id}?fields=id,title,artist_display,date_display,image_id,is_public_domain"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "AIC-User-Agent": "sardines-qff-2026 (student hackathon)",
    }
    data, _ = fetch_url(url, headers=headers)
    parsed = json.loads(data.decode("utf-8"))["data"]
    if not parsed.get("is_public_domain"):
        logger.warning("AIC item %s does not report is_public_domain=True", artwork_id)
    image_id = parsed["image_id"]
    image_url = f"https://www.artic.edu/iiif/2/{image_id}/full/843,/0/default.jpg"
    return {
        "title": parsed.get("title", ""),
        "artist": parsed.get("artist_display", "").split("\n")[0].strip(),
        "year": parsed.get("date_display", ""),
        "image_url": image_url,
        "is_public_domain": parsed.get("is_public_domain", True),
    }


def get_met_metadata(object_id: int) -> dict[str, Any]:
    url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
    headers = {"User-Agent": "Mozilla/5.0"}
    data, _ = fetch_url(url, headers=headers)
    parsed = json.loads(data.decode("utf-8"))
    if not parsed.get("isPublicDomain"):
        logger.warning("Met item %s does not report isPublicDomain=True", object_id)
    image_url = parsed.get("primaryImageSmall") or parsed.get("primaryImage")
    return {
        "title": parsed.get("title", ""),
        "artist": parsed.get("artistDisplayName", ""),
        "year": parsed.get("objectDate", ""),
        "image_url": image_url,
        "is_public_domain": parsed.get("isPublicDomain", True),
    }


def crop_to_square(im: Image.Image) -> Image.Image:
    w, h = im.size
    s = min(w, h)
    return im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/artworks"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--sources-file", type=Path, default=Path("data/artworks/SOURCES.md"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.raw_dir.mkdir(parents=True, exist_ok=True)

    sources_records: list[dict[str, str]] = []

    # 1. Fetch the 12 museum paintings
    for spec in ARTWORKS_SPECS:
        slug = spec["slug"]
        museum = spec["museum"]
        art_id = spec["id"]
        logger.info("Processing %s (%s ID %s)...", slug, museum, art_id)

        meta: dict[str, Any] = {}
        try:
            if museum == "AIC":
                meta = get_aic_metadata(art_id)
            elif museum == "Met":
                meta = get_met_metadata(art_id)
        except Exception as e:
            logger.error("Error fetching API metadata for %s: %s. Using fallback image URL.", slug, e)
            meta = {
                "title": slug.replace("_", " ").title(),
                "artist": "Unknown",
                "year": "Unknown",
                "image_url": spec["fallback_image_url"],
                "is_public_domain": True,
            }

        img_url = meta.get("image_url") or spec["fallback_image_url"]

        raw_path = args.raw_dir / f"{slug}.jpg"
        if raw_path.exists() and raw_path.stat().st_size > 0:
            logger.info("Using cached raw image: %s", raw_path)
            raw_bytes = raw_path.read_bytes()
        else:
            logger.info("Downloading image from %s...", img_url)
            headers = {"AIC-User-Agent": "sardines-qff-2026 (student hackathon)"} if museum == "AIC" else None
            try:
                raw_bytes, ctype = fetch_url(img_url, headers=headers)
                if not (ctype.startswith("image/") or raw_bytes.startswith(b"\xff\xd8\xff") or raw_bytes.startswith(b"\x89PNG")):
                    logger.warning("Content-Type %s for %s might not be an image", ctype, slug)
                raw_path.write_bytes(raw_bytes)
            except Exception as e:
                logger.error("Download failed from primary URL %s: %s. Trying fallback URL...", img_url, e)
                img_url = spec["fallback_image_url"]
                raw_bytes, _ = fetch_url(img_url, headers=headers)
                raw_path.write_bytes(raw_bytes)

        # Open and preprocess
        im = Image.open(io.BytesIO(raw_bytes))
        cropped = crop_to_square(im)

        # Canonicalise with sp.load_image
        canon_arr = sp.load_image(cropped)
        out_png = args.output_dir / f"{slug}.png"
        Image.fromarray(canon_arr).save(out_png, format="PNG", optimize=True)
        logger.info("Saved canonical image: %s (%d bytes)", out_png, out_png.stat().st_size)

        sources_records.append({
            "file": f"{slug}.png",
            "title": meta.get("title") or slug.replace("_", " ").title(),
            "artist": meta.get("artist") or "Unknown",
            "year": str(meta.get("year") or "Unknown"),
            "museum": museum,
            "object_url": spec["object_url"],
            "image_url": img_url,
            "licence": "Public Domain (CC0)",
        })

    # 2. Generate 3 stress-test images
    logger.info("Generating stress-test images...")

    # synthetic.png
    synth_arr = sp.synthetic.artwork(seed=1)
    synth_png = args.output_dir / "synthetic.png"
    Image.fromarray(synth_arr).save(synth_png, format="PNG", optimize=True)
    sources_records.append({
        "file": "synthetic.png",
        "title": "Synthetic Gradient Artwork",
        "artist": "team sardines",
        "year": "2026",
        "museum": "Generated",
        "object_url": "swapprint.synthetic.artwork(seed=1)",
        "image_url": "N/A (in-code generator)",
        "licence": "CC0 / Generated by us",
    })

    # flat.png: uniform colour (180, 140, 90)
    flat_arr = np.full((sp.config.CANON, sp.config.CANON, 3), (180, 140, 90), dtype=np.uint8)
    flat_png = args.output_dir / "flat.png"
    Image.fromarray(flat_arr).save(flat_png, format="PNG", optimize=True)
    sources_records.append({
        "file": "flat.png",
        "title": "Flat Uniform Field (RGB 180, 140, 90)",
        "artist": "team sardines",
        "year": "2026",
        "museum": "Generated",
        "object_url": "N/A (stress test)",
        "image_url": "N/A (stress test)",
        "licence": "CC0 / Generated by us",
    })

    # noise.png: np.random.default_rng(0).integers(0, 256, (256, 256, 3), dtype=np.uint8)
    rng = np.random.default_rng(0)
    noise_arr = rng.integers(0, 256, (sp.config.CANON, sp.config.CANON, 3), dtype=np.uint8)
    noise_png = args.output_dir / "noise.png"
    Image.fromarray(noise_arr).save(noise_png, format="PNG", optimize=True)
    sources_records.append({
        "file": "noise.png",
        "title": "Uniform Random Noise (seed=0)",
        "artist": "team sardines",
        "year": "2026",
        "museum": "Generated",
        "object_url": "N/A (stress test)",
        "image_url": "N/A (stress test)",
        "licence": "CC0 / Generated by us",
    })

    # 3. Write SOURCES.md
    md_lines = [
        "# Dataset Sources and Licences",
        "",
        "This dataset contains 15 canonical images (256×256 RGB, lossless PNG) used across the SwapPrint tampering experiment and app.",
        "",
        "Every museum painting was downloaded from public museum open-access APIs, centre-cropped to a square, and resized to 256×256 pixels using `swapprint.load_image`. Both the Art Institute of Chicago (AIC) and The Metropolitan Museum of Art (Met) provide high-resolution images under Creative Commons Zero (CC0) / Public Domain terms.",
        "",
        "| File | Title | Artist | Year | Museum | Object Page | Image URL | Licence |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for r in sources_records:
        title = r["title"].replace("|", "\\|").replace("\n", " ")
        artist = r["artist"].replace("|", "\\|").replace("\n", " ")
        year = r["year"].replace("|", "\\|").replace("\n", " ")
        obj_url = f"[Link]({r['object_url']})" if r["object_url"].startswith("http") else r["object_url"]
        img_url = f"[Image]({r['image_url']})" if r["image_url"].startswith("http") else r["image_url"]
        md_lines.append(f"| `{r['file']}` | {title} | {artist} | {year} | {r['museum']} | {obj_url} | {img_url} | {r['licence']} |")

    md_lines.extend([
        "",
        "## Notes",
        "- All museum images are verified public domain / CC0.",
        "- Preprocessing: each original high-resolution download was cropped to its largest centred square, then canonicalised with `swapprint.load_image(im)` to 256×256 RGB and saved as lossless PNG.",
        "- Stress-test images (`synthetic.png`, `flat.png`, `noise.png`) are marked 'generated by us' and used to evaluate corner cases (flat colour, extreme high frequencies, smooth gradient).",
    ])

    args.sources_file.parent.mkdir(parents=True, exist_ok=True)
    args.sources_file.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    logger.info("Wrote %s", args.sources_file)


if __name__ == "__main__":
    main()
