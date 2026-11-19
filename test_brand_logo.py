"""Tests for brand_logo (campaign logo overlay)."""
import os
import shutil
import subprocess

import pytest

import brand_logo


def test_normalize_defaults_and_clamps():
    o = brand_logo.normalize()
    assert o == brand_logo.DEFAULTS
    o = brand_logo.normalize("Bottom-Left", width=5, opacity=-1, x_margin=0.9, y_margin=None)
    assert o["position"] == "bottom-left"
    assert o["width"] == 1.0 and o["opacity"] == 0.0 and o["x_margin"] == 0.45
    assert o["y_margin"] == brand_logo.DEFAULTS["y_margin"]


def test_normalize_rejects_unknown_position():
    with pytest.raises(ValueError):
        brand_logo.normalize("upper-ish")


@pytest.mark.parametrize("pos,expect", [
    ("top-left", (54, 153)),
    ("top-right", (1080 - 238 - 54, 153)),
    ("top-center", ((1080 - 238) // 2, 153)),
    ("bottom-right", (1080 - 238 - 54, 1920 - 66 - 153)),
    ("center", ((1080 - 238) // 2, (1920 - 66) // 2)),
])
def test_logo_box_positions(pos, expect):
    opts = brand_logo.normalize(pos)
    w, h, x, y = brand_logo.logo_box(1080, 1920, 1993, 549, opts)
    assert (w, h) == (238, 66)
    assert (x, y) == expect
    assert w % 2 == 0 and h % 2 == 0


def test_tall_logo_fits_height():
    w, h, x, y = brand_logo.logo_box(1080, 1920, 100, 5000,
                                      brand_logo.normalize("center", width=1.0))
    assert h <= 1920 and y >= 0


def test_strip_logo_walks_back_only_existing(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"x")
    (tmp_path / "logo_1_clip.mp4").write_bytes(b"x")
    assert brand_logo.strip_logo(str(tmp_path), "logo_2_logo_1_clip.mp4") == "clip.mp4"
    assert brand_logo.strip_logo(str(tmp_path), "logo_9_gone.mp4") == "logo_9_gone.mp4"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_apply_logo_burns_pixels(tmp_path):
    video, logo, out = (str(tmp_path / n) for n in ("v.mp4", "l.png", "o.mp4"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=black:s=360x640:d=1", "-f", "lavfi", "-i",
                    "sine=d=1", "-shortest", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", video], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=white:s=200x50", "-frames:v", "1", logo], check=True)
    placed = brand_logo.apply_logo(video, logo, out, position="top-left")
    assert os.path.exists(out)
    b = placed["box"]
    px = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", out, "-frames:v", "1", "-vf",
         f"crop=2:2:{b['x'] + b['w'] // 2}:{b['y'] + b['h'] // 2}",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    assert min(px) > 200  # logo area is white on the black clip
    audio = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_type", "-of", "csv=p=0", out]).decode()
    assert "audio" in audio
