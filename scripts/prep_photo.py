"""
Prepare a portrait photo for clean ASCII conversion:
  1. detect the face and crop to a HEAD-AND-SHOULDERS portrait (so a full-body
     photo doesn't become a tiny unrecognizable head)
  2. remove the background (rembg) so the subject is isolated
  3. boost LOCAL contrast (CLAHE) so a flatly-lit face gains highlights and
     shadows -- this is what turns a dark blob into a recognizable face
  4. composite onto pure white and pad to a square so the ascii is centered

Output: source-prepped.png (grayscale), consumed by make_ascii_svg.py.
Run once whenever the source photo changes; the ascii SVG itself is static.

    python scripts/prep_photo.py <input.png> [output.png]

Tuning knobs via env vars (all optional):
    FACE_UP=0.9   headroom above the face, in face-heights
    FACE_DOWN=3.0 how far below the face to include (shoulders/chest)
    FACE_WIDE=2.7 crop width, in face-widths
    NO_FACE=1     skip face detection, use the whole subject
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image
from rembg import remove

HERE = os.path.dirname(os.path.abspath(__file__))
INP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "source-image.png")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "source-prepped.png")

UP = float(os.environ.get("FACE_UP", 0.6))
DOWN = float(os.environ.get("FACE_DOWN", 3.0))
WIDE = float(os.environ.get("FACE_WIDE", 2.7))


def portrait_crop(pil_img):
    """Find the largest face and return a head-and-shoulders crop box, or None."""
    if os.environ.get("NO_FACE"):
        return None
    g = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    m = max(40, min(g.shape[:2]) // 12)
    faces = cascade.detectMultiScale(g, scaleFactor=1.15, minNeighbors=6,
                                     minSize=(m, m))
    if len(faces) == 0:
        print("  (no face detected -> using whole subject)", file=sys.stderr)
        return None
    fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
    cx = fx + fw / 2.0
    half = WIDE * fw / 2.0
    left, right = cx - half, cx + half
    top, bottom = fy - UP * fh, fy + DOWN * fh
    H, W = g.shape[:2]
    box = (max(0, int(left)), max(0, int(top)),
           min(W, int(right)), min(H, int(bottom)))
    print(f"  face @ {(fx, fy, fw, fh)} -> crop {box}", file=sys.stderr)
    return box


# 1. head-and-shoulders crop around the face
src = Image.open(INP).convert("RGB")
box = portrait_crop(src)
if box:
    src = src.crop(box)

# 2. cut out the subject
cut = remove(src.convert("RGBA"))
rgb = np.array(cut.convert("RGB"))
alpha = np.array(cut.split()[-1])                 # 0 = background

# 2a. keep only the largest connected blob -> drops stray bits rembg leaves
#     floating around the subject (e.g. a lamppost bracket behind the head)
nlbl, lbls, stats, _ = cv2.connectedComponentsWithStats((alpha > 24).astype(np.uint8), 8)
if nlbl > 2:
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    alpha = np.where(lbls == biggest, alpha, 0).astype(np.uint8)

# 2b. tighten to the subject's bounding box (+ small margin)
ys, xs = np.where(alpha > 24)
if len(xs) and len(ys):
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    mx = int(0.05 * (x1 - x0)); my = int(0.05 * (y1 - y0))
    x0 = max(0, x0 - mx); y0 = max(0, y0 - my)
    x1 = min(alpha.shape[1], x1 + mx); y1 = min(alpha.shape[0], y1 + my)
    rgb = rgb[y0:y1, x0:x1]
    alpha = alpha[y0:y1, x0:x1]

# 3. local-contrast the luminance (CLAHE)
gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
clahe = cv2.createCLAHE(clipLimit=2.6, tileGridSize=(8, 8))
gray = clahe.apply(gray)

# a touch of global lift so the face sits in the sparse end of the ramp
gray = cv2.convertScaleAbs(gray, alpha=1.05, beta=18)

# paste onto white using the alpha mask (feathered a hair to avoid a halo)
mask = (alpha.astype(np.float32) / 255.0)
mask = cv2.GaussianBlur(mask, (0, 0), 1.0)
out = gray.astype(np.float32) * mask + 255.0 * (1.0 - mask)
out = np.clip(out, 0, 255).astype(np.uint8)

# 4. pad to a SQUARE canvas (centered) on white. The ascii art area is ~square
# (100 cols x 8px vs 53 rows x 15px), so a square input keeps the face
# undistorted and horizontally centered.
h, w = out.shape
side = max(h, w)
canvas = np.full((side, side), 255, dtype=np.uint8)
oy, ox = (side - h) // 2, (side - w) // 2
canvas[oy:oy + h, ox:ox + w] = out
out = canvas

Image.fromarray(out, mode="L").save(OUT)
print("wrote", OUT, out.shape)
