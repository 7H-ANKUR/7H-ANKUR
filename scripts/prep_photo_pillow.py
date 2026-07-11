"""
Fallback portrait prep — uses only Pillow + NumPy (no rembg / opencv).
Since we can't remove the background automatically, we:
  1. Crop to face region (center-weighted square crop)
  2. Convert to grayscale
  3. Apply CLAHE-equivalent local contrast via tile histogram equalization
  4. Apply gamma lift so face lands in sparser part of ascii ramp
  5. Boost global contrast
  6. Save as source-prepped.png for make_ascii_svg.py

Run: python scripts/prep_photo_pillow.py <input> [output]
"""
import os
import sys
import numpy as np
from PIL import Image, ImageEnhance, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
INP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "source-photo.jpg")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "source-prepped.png")

# ---- load & convert to grayscale ----
img = Image.open(INP).convert("RGB")
w, h = img.size
print(f"Input: {w}x{h}")

# ---- smart crop: take the upper 80% (face usually top-center) ----
# crop to a square from center-top area
crop_size = min(w, h)
left = (w - crop_size) // 2
# bias toward top (face) — take top 90% vertically
top = int(h * 0.0)
top = max(0, min(top, h - crop_size))
img = img.crop((left, top, left + crop_size, top + crop_size))
print(f"Cropped to: {img.size}")

# ---- convert to grayscale ----
gray = img.convert("L")

# ---- CLAHE-equivalent: tile-based histogram equalization ----
arr = np.array(gray, dtype=np.float32)
tile_h, tile_w = arr.shape[0] // 8, arr.shape[1] // 8

def clahe_tile(patch, clip_limit=2.5):
    """Apply clipped histogram equalization to a single tile."""
    flat = patch.flatten()
    hist, bins = np.histogram(flat, bins=256, range=(0, 256))
    # clip
    clip = int(clip_limit * flat.size / 256)
    excess = np.sum(np.maximum(hist - clip, 0))
    hist = np.minimum(hist, clip)
    hist += excess // 256
    # cdf
    cdf = hist.cumsum()
    cdf_min = cdf[cdf > 0].min() if cdf[cdf > 0].size > 0 else 0
    total = flat.size
    lut = np.round((cdf - cdf_min) / max(total - cdf_min, 1) * 255).astype(np.uint8)
    return lut[patch.astype(np.uint8)]

# process each tile
out_arr = arr.copy().astype(np.uint8)
rows, cols = arr.shape
for ty in range(8):
    for tx in range(8):
        y0 = ty * tile_h
        y1 = y0 + tile_h if ty < 7 else rows
        x0 = tx * tile_w
        x1 = x0 + tile_w if tx < 7 else cols
        tile = arr[y0:y1, x0:x1]
        out_arr[y0:y1, x0:x1] = clahe_tile(tile, clip_limit=2.6)

result = Image.fromarray(out_arr, mode="L")

# ---- gamma lift (>1 = brighten mids → face lands in sparse chars) ----
GAMMA = 1.2
lut = [int(255 * (i / 255.0) ** (1.0 / GAMMA)) for i in range(256)]
result = result.point(lut)

# ---- global contrast boost ----
result = ImageEnhance.Contrast(result).enhance(1.25)

# ---- slight brightness lift ----
result = ImageEnhance.Brightness(result).enhance(1.08)

result.save(OUT)
print(f"wrote {OUT}  {result.size}")
