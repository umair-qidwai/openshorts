"""Brand logo overlay for finished clips (campaign / sponsor logos).

Clipping campaigns usually require the brand's logo on screen for the whole
clip. This burns a user-supplied image (PNG/WebP with alpha, or JPG) onto a
finished clip in one FFmpeg pass and writes it as a DERIVED file,
``logo_<ts>_<input name>``, next to its input, the same way captions write
``subtitled_<ts>_...``. The input stays untouched, so the logo can be moved
or replaced by walking the prefix back (``strip_logo``).

Apply it LAST: re-captioning walks ``logo_`` and ``subtitled_`` prefixes back
to the clip without captions, which also drops the logo.

Placement is in fractions of the video so one setting works at any size:

* ``position``  one of POSITIONS (horizontal + vertical anchor)
* ``width``     logo width as a fraction of the video width
* ``x_margin``  gap from the left/right edge, fraction of the video width
* ``y_margin``  gap from the top/bottom edge, fraction of the video height
  (the 0.08 default clears the platform header on top positions)
* ``opacity``   0..1
"""

import os
import re
import subprocess

from ffmpeg_utils import video_encode_args, QUALITY, METADATA_SCRUB

POSITIONS = ("top-left", "top-center", "top-right",
             "center-left", "center", "center-right",
             "bottom-left", "bottom-center", "bottom-right")
ALLOWED_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg")
MAX_LOGO_BYTES = 10 * 1024 * 1024
PREFIX_RE = re.compile(r"^logo_\d+_(.+)$")

DEFAULTS = {"position": "top-right", "width": 0.22, "opacity": 1.0,
            "x_margin": 0.05, "y_margin": 0.08}


def _clamp(value, lo, hi):
    return max(lo, min(hi, float(value)))


def normalize(position=None, width=None, opacity=None, x_margin=None, y_margin=None):
    """Validate and clamp placement options; raises ValueError on a bad position."""
    pos = (position or DEFAULTS["position"]).strip().lower()
    if pos not in POSITIONS:
        raise ValueError(f"Unknown logo position {position!r}. Use one of: {', '.join(POSITIONS)}.")
    pick = lambda v, k: DEFAULTS[k] if v is None else v  # noqa: E731
    return {
        "position": pos,
        "width": _clamp(pick(width, "width"), 0.02, 1.0),
        "opacity": _clamp(pick(opacity, "opacity"), 0.0, 1.0),
        "x_margin": _clamp(pick(x_margin, "x_margin"), 0.0, 0.45),
        "y_margin": _clamp(pick(y_margin, "y_margin"), 0.0, 0.45),
    }


def _even(n):
    n = max(2, int(round(n)))
    return n - (n % 2)


def logo_box(vw, vh, lw, lh, opts):
    """Pixel size and top-left corner of the logo on a vw x vh frame."""
    w = _even(vw * opts["width"])
    h = _even(w * lh / float(lw))
    if h > vh:  # very tall logo: fit the height instead
        h = _even(vh * 0.9)
        w = _even(h * lw / float(lh))
    mx, my = int(vw * opts["x_margin"]), int(vh * opts["y_margin"])
    vert, _, horiz = opts["position"].partition("-")
    if opts["position"] == "center":
        vert, horiz = "center", "center"
    x = {"left": mx, "center": (vw - w) // 2, "right": vw - w - mx}[horiz]
    y = {"top": my, "center": (vh - h) // 2, "bottom": vh - h - my}[vert]
    return w, h, max(0, min(vw - w, x)), max(0, min(vh - h, y))


def logo_filter(vw, vh, lw, lh, opts, video="[0:v]", logo="[1:v]", out="[v]"):
    """filter_complex chain that overlays the logo input on the video."""
    w, h, x, y = logo_box(vw, vh, lw, lh, opts)
    return (f"{logo}format=rgba,scale={w}:{h}:flags=lanczos,"
            f"colorchannelmixer=aa={opts['opacity']:.3f}[lg];"
            f"{video}[lg]overlay=x={x}:y={y}:format=auto,format=yuv420p{out}")


def _probe_size(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
        stderr=subprocess.STDOUT, timeout=60).decode().strip().splitlines()[0]
    w, h = out.split("x")[:2]
    return int(w), int(h)


def strip_logo(output_dir, filename):
    """Walk ``logo_<ts>_`` prefixes back so a new logo replaces the old one."""
    while True:
        m = PREFIX_RE.match(filename)
        if not m or not os.path.exists(os.path.join(output_dir, m.group(1))):
            return filename
        filename = m.group(1)


def apply_logo(video_path, logo_path, output_path, **options):
    """Burn ``logo_path`` onto ``video_path``; returns the placement used."""
    opts = normalize(**options)
    vw, vh = _probe_size(video_path)
    lw, lh = _probe_size(logo_path)
    tmp = output_path + ".tmp.mp4"
    cmd = ["ffmpeg", "-y", "-i", video_path, "-i", logo_path,
           "-filter_complex", logo_filter(vw, vh, lw, lh, opts),
           "-map", "[v]", "-map", "0:a?", "-c:a", "copy",
           *video_encode_args(QUALITY), *METADATA_SCRUB,
           "-movflags", "+faststart", tmp]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=1800)
        os.replace(tmp, output_path)
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or b"").decode(errors="replace")[-600:]
        raise RuntimeError(f"Logo overlay failed: {tail}") from e
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    w, h, x, y = logo_box(vw, vh, lw, lh, opts)
    return {**opts, "box": {"x": x, "y": y, "w": w, "h": h}}
