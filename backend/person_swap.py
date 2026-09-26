"""AI person swap for Thumbnail Studio - runs fully locally.

1. rembg (U²-Net human segmentation) finds the person in the original
   thumbnail and in the user's photo.
2. LaMa (big-lama, TorchScript) erases the original person and fills in the
   background behind them. Falls back to OpenCV inpainting if LaMa can't load.
3. The user's cut-out is color matched to the original person and placed at
   the same position and size.

Models are downloaded on first use (~170 MB + ~200 MB) and cached in
~/.tldr-video/models (rembg keeps its model in ~/.rembg or ~/.u2net).
"""
import base64
import io
import logging
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

CANVAS_W, CANVAS_H = 1280, 720
MODELS_DIR = Path.home() / ".tldr-video" / "models"
LAMA_URL = "https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt"
SEGMENT_MODEL = "u2net_human_seg"
LAMA_MAX_SIDE = 1024

_lock = threading.Lock()
_segment_session = None
_lama = None  # (model, device) once loaded, False if unavailable


class PersonSwapUnavailable(Exception):
    """Required packages are not installed."""


class NoPersonFound(Exception):
    """No person was detected; the message names which image."""


def _require_packages():
    try:
        import cv2  # noqa: F401
        import rembg  # noqa: F401
    except ImportError as e:
        raise PersonSwapUnavailable(
            "AI person swap needs extra packages. Run: ./venv/bin/pip install -r backend/requirements.txt"
        ) from e


# ---------- Segmentation ----------

def _person_mask(img: Image.Image) -> np.ndarray:
    """Soft person mask (H, W) in 0..1."""
    global _segment_session
    import rembg
    if _segment_session is None:
        _segment_session = rembg.new_session(SEGMENT_MODEL)
    mask = rembg.remove(img, session=_segment_session, only_mask=True)
    return np.asarray(mask.convert("L"), dtype=np.float32) / 255.0


def _main_person(mask: np.ndarray, which: str):
    """Mask and bounding box (x0, y0, x1, y1) of the largest person."""
    import cv2
    binary = (mask > 0.5).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if count <= 1:
        raise NoPersonFound(f"No person found in {which}.")
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[largest, cv2.CC_STAT_AREA] < mask.size * 0.01:
        raise NoPersonFound(f"No person found in {which}.")
    x, y, w, h = stats[largest, :4]
    # Keep the soft edges of the largest person only
    component = cv2.dilate((labels == largest).astype(np.uint8), np.ones((9, 9), np.uint8))
    return mask * component, (int(x), int(y), int(x + w), int(y + h))


# ---------- Inpainting ----------

def _load_lama():
    """Load big-lama once; returns (model, device) or None if unavailable."""
    global _lama
    if _lama is not None:
        return _lama or None
    try:
        import torch
        import httpx

        path = MODELS_DIR / "big-lama.pt"
        if not path.exists():
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            logger.info("Downloading LaMa inpainting model (~200 MB)...")
            with httpx.stream("GET", LAMA_URL, follow_redirects=True, timeout=600) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            tmp.rename(path)

        model = torch.jit.load(str(path), map_location="cpu").eval()
        device = "cpu"
        if torch.backends.mps.is_available():
            try:
                mps_model = model.to("mps")
                with torch.inference_mode():
                    mps_model(torch.zeros(1, 3, 64, 64, device="mps"), torch.zeros(1, 1, 64, 64, device="mps"))
                model, device = mps_model, "mps"
            except Exception as e:  # some ops may be unsupported on MPS
                logger.info("LaMa on MPS failed (%s); using CPU", e)
                model = model.to("cpu")
        _lama = (model, device)
    except Exception as e:
        logger.warning("LaMa unavailable, using OpenCV inpainting instead: %s", e)
        _lama = False
    return _lama or None


def _lama_inpaint(lama, rgb: np.ndarray, hole: np.ndarray) -> np.ndarray:
    import torch
    model, device = lama
    h, w = hole.shape
    pad_h, pad_w = (8 - h % 8) % 8, (8 - w % 8) % 8
    img = np.pad(rgb, ((0, pad_h), (0, pad_w), (0, 0)), mode="symmetric")
    msk = np.pad(hole, ((0, pad_h), (0, pad_w)), mode="symmetric")
    img_t = torch.from_numpy(img).permute(2, 0, 1)[None].float().div(255).to(device)
    msk_t = torch.from_numpy((msk > 0).astype(np.float32))[None, None].to(device)
    with torch.inference_mode():
        out = model(img_t, msk_t)[0].permute(1, 2, 0).clamp(0, 1).mul(255)
    return out.byte().cpu().numpy()[:h, :w]


def _erase_person(rgb: np.ndarray, mask: np.ndarray, bbox):
    """Remove the person and fill the background. Returns (image, method)."""
    import cv2
    h, w = mask.shape
    grow = max(9, int(min(h, w) * 0.02)) | 1
    hole = cv2.dilate((mask > 0.15).astype(np.uint8), np.ones((grow, grow), np.uint8))

    # Work on a crop around the person for speed and quality
    x0, y0, x1, y1 = bbox
    mx, my = int((x1 - x0) * 0.5) + grow, int((y1 - y0) * 0.5) + grow
    cx0, cy0 = max(0, x0 - mx), max(0, y0 - my)
    cx1, cy1 = min(w, x1 + mx), min(h, y1 + my)
    crop, crop_hole = rgb[cy0:cy1, cx0:cx1], hole[cy0:cy1, cx0:cx1]

    lama = _load_lama()
    method = "lama" if lama else "opencv"
    scale = min(1.0, LAMA_MAX_SIDE / max(crop.shape[:2]))
    small = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else crop
    small_hole = cv2.resize(crop_hole, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)

    filled = None
    if lama:
        try:
            filled = _lama_inpaint(lama, small, small_hole)
        except Exception as e:
            logger.warning("LaMa inpainting failed, using OpenCV: %s", e)
            method = "opencv"
    if filled is None:
        bgr = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
        filled = cv2.cvtColor(cv2.inpaint(bgr, small_hole * 255, 9, cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB)
    if scale < 1:
        filled = cv2.resize(filled, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_CUBIC)

    # Blend with a soft edge that only extends *outside* the hole, so nothing
    # of the original person shows through inside it
    feather = cv2.dilate(crop_hole, np.ones((grow, grow), np.uint8)).astype(np.float32)
    soft = np.maximum(cv2.GaussianBlur(feather, (0, 0), grow / 3), crop_hole)[..., None]
    out = rgb.copy()
    out[cy0:cy1, cx0:cx1] = (filled * soft + crop * (1 - soft)).astype(np.uint8)
    return out, method


# ---------- Color match + placement ----------

def _match_colors(rgb: np.ndarray, alpha: np.ndarray, ref_rgb: np.ndarray, ref_mask: np.ndarray,
                  strength: float = 0.7) -> np.ndarray:
    """Shift the cut-out's Lab colors toward the original person's (Reinhard transfer)."""
    import cv2
    src = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    ref = cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    s_px, r_px = src[alpha > 0.5], ref[ref_mask > 0.5]
    if len(s_px) < 50 or len(r_px) < 50:
        return rgb
    s_mean, s_std = s_px.mean(0), s_px.std(0) + 1e-3
    r_mean, r_std = r_px.mean(0), r_px.std(0) + 1e-3
    ratio = np.clip(r_std / s_std, 0.6, 1.6)
    matched = (src - s_mean) * ratio + r_mean
    out = src + (matched - src) * strength
    return cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)


def _cover_fit(img: Image.Image) -> Image.Image:
    """Crop/scale to 1280x720 exactly like the studio canvas draws the thumbnail."""
    return ImageOps.fit(img.convert("RGB"), (CANVAS_W, CANVAS_H), Image.LANCZOS)


def _png_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def swap_person(thumbnail_path: str, photo_bytes: bytes) -> dict:
    """
    Replace the main person in the thumbnail with the person from the photo.
    Returns data URLs for the cleaned background and the placed cut-out, plus
    the cut-out's box on the 1280x720 canvas so the studio can keep it editable.
    """
    _require_packages()
    import cv2

    with _lock:  # models are shared and not thread-safe
        original = _cover_fit(Image.open(thumbnail_path))
        photo = ImageOps.exif_transpose(Image.open(io.BytesIO(photo_bytes))).convert("RGB")
        photo.thumbnail((1600, 1600), Image.LANCZOS)

        orig_rgb = np.asarray(original)
        orig_mask, orig_box = _main_person(_person_mask(original), "the original thumbnail")
        photo_rgb = np.asarray(photo)
        photo_mask, photo_box = _main_person(_person_mask(photo), "your photo")

        background, method = _erase_person(orig_rgb, orig_mask, orig_box)

        # Cut out the user's person
        px0, py0, px1, py1 = photo_box
        cut_rgb = photo_rgb[py0:py1, px0:px1]
        cut_alpha = photo_mask[py0:py1, px0:px1]
        ox0, oy0, ox1, oy1 = orig_box
        cut_rgb = _match_colors(cut_rgb, cut_alpha, orig_rgb[oy0:oy1, ox0:ox1], orig_mask[oy0:oy1, ox0:ox1])

        # Same height as the original person; don't get much wider than them
        target_w, target_h = ox1 - ox0, oy1 - oy0
        scale = target_h / cut_rgb.shape[0]
        scale = min(scale, 1.6 * target_w / cut_rgb.shape[1])
        new_w = max(1, round(cut_rgb.shape[1] * scale))
        new_h = max(1, round(cut_rgb.shape[0] * scale))
        cut_rgb = cv2.resize(cut_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        cut_alpha = cv2.resize(cut_alpha, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        cut_alpha = cv2.GaussianBlur(cut_alpha, (3, 3), 0)

        # Centre on the original person; people cut off by the frame bottom stay bottom-aligned
        x = (ox0 + ox1) / 2 - new_w / 2
        y = oy1 - new_h if oy1 >= CANVAS_H - 4 else oy0

        cutout = Image.fromarray(np.dstack([cut_rgb, (cut_alpha * 255).astype(np.uint8)]), "RGBA")
        return {
            "background": _png_data_url(Image.fromarray(background)),
            "person": _png_data_url(cutout),
            "box": {"x": round(x), "y": round(y), "w": new_w, "h": new_h},
            "inpaint_method": method,
        }
