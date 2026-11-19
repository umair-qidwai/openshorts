"""Snap clip boundaries onto sentence boundaries.

``snap_clip_to_words`` moves a cut onto the nearest *word* edge, which stops
mid-word cuts but still lets a clip open on "didn't change. So we are..." or
close on "...about the technology about the". Gemini's proposed times are
often a few seconds off, so the nearest word is frequently mid-sentence.

This module looks a few seconds either side of each proposed edge for a real
sentence boundary and moves the cut there:

* a sentence START is a word that follows terminal punctuation (. ? !) or a
  pause of at least ``pause_seconds``;
* a sentence END is a word that carries terminal punctuation or is followed
  by such a pause.

Punctuation-backed boundaries win over pause-only ones (Whisper drops
punctuation on long run-on stretches, so pauses are the fallback, not the
first choice). Duration bounds are kept; if no boundary fits, the input is
returned unchanged.

Disable with ``CLIP_SENTENCE_SNAP=0``.
"""

import os

TERMINAL = (".", "?", "!")


def sentence_snap_enabled():
    return os.environ.get("CLIP_SENTENCE_SNAP", "1").strip().lower() not in (
        "0", "false", "no", "off")


def _ends_sentence(text):
    t = str(text or "").strip().rstrip('"\'”’)]')
    return t.endswith(TERMINAL) and not t.endswith("...")


def sentence_boundaries(words, pause_seconds=0.6):
    """Return (starts, ends): lists of (time, strong) tuples.

    words: [{'w','s','e'}, ...] sorted by start. ``strong`` is True when the
    boundary is backed by punctuation, False when it rests on a pause only.
    """
    starts, ends = [], []
    n = len(words)
    for i, w in enumerate(words):
        s, e = float(w["s"]), float(w["e"])
        if i == 0:
            starts.append((s, True))
        else:
            prev = words[i - 1]
            punct = _ends_sentence(prev.get("w"))
            gap = s - float(prev["e"])
            if punct or gap >= pause_seconds:
                starts.append((s, punct))
        if i == n - 1:
            ends.append((e, True))
        else:
            punct = _ends_sentence(w.get("w"))
            gap = float(words[i + 1]["s"]) - e
            if punct or gap >= pause_seconds:
                ends.append((e, punct))
    return starts, ends


def _pick(candidates, target, back, fwd, weak_penalty):
    best = None
    for t, strong in candidates:
        if target - back <= t <= target + fwd:
            cost = abs(t - target) + (0.0 if strong else weak_penalty)
            if best is None or cost < best[0]:
                best = (cost, t)
    return None if best is None else best[1]


def snap_clip_to_sentences(start, end, words, video_duration,
                           min_duration=15.0, max_duration=60.0,
                           start_back=6.0, start_fwd=4.0,
                           end_back=6.0, end_fwd=6.0,
                           pause_seconds=0.6, weak_penalty=1.5,
                           lead=0.25, tail=0.35):
    """Move (start, end) onto the nearest sentence start / sentence end.

    Searches ``start_back``/``start_fwd`` seconds around the start and
    ``end_back``/``end_fwd`` around the end. Returns the input unchanged when
    there are no words, no boundary in range, or the result would break the
    duration bounds.
    """
    original = (round(float(start), 3), round(float(end), 3))
    if not words:
        return original
    starts, ends = sentence_boundaries(words, pause_seconds)

    s0 = _pick(starts, float(start), start_back, start_fwd, weak_penalty)
    e0 = _pick(ends, float(end), end_back, end_fwd, weak_penalty)
    new_start = float(start) if s0 is None else s0
    new_end = float(end) if e0 is None else e0

    # Keep the bounds: if a snapped edge broke them, try the next boundary
    # in the direction that repairs the duration, else give up on that edge.
    def dur():
        return new_end - new_start

    if dur() > max_duration and e0 is not None:
        earlier = [t for t, _ in ends if new_start + min_duration <= t <= new_start + max_duration]
        new_end = max(earlier) if earlier else float(end)
    if dur() < min_duration and e0 is not None:
        later = [t for t, _ in ends if new_start + min_duration <= t <= new_start + max_duration]
        new_end = min(later) if later else float(end)
    if not (min_duration <= dur() <= max_duration + 1e-6):
        return original

    # Breathe into the surrounding silence without touching neighbour words.
    prev_end = max((float(w["e"]) for w in words if float(w["e"]) <= new_start), default=None)
    next_start = min((float(w["s"]) for w in words if float(w["s"]) >= new_end), default=None)
    lead_room = lead if prev_end is None else min(lead, max(0.0, (new_start - prev_end) / 2))
    tail_room = tail if next_start is None else min(tail, max(0.0, (next_start - new_end) / 2))
    new_start = max(0.0, new_start - lead_room)
    new_end = min(float(video_duration), new_end + tail_room)
    return (round(new_start, 3), round(new_end, 3))


def _edge_kind(t, boundaries, tolerance):
    best = None
    for b, strong in boundaries:
        if abs(b - t) <= tolerance:
            kind = "sentence" if strong else "pause"
            if best is None or kind == "sentence":
                best = kind
    return best or "none"


def review_flags(start, end, words, low_confidence=0.5, pause_seconds=0.6,
                 tolerance=0.36, max_words=12):
    """Say what a human should double-check on a finished clip.

    ``start_boundary`` / ``end_boundary``: "sentence" (punctuation-backed),
    "pause" (silence only) or "none" (the cut is probably mid-sentence).
    ``low_confidence_words``: words inside the clip whose Whisper probability
    ('p') is below ``low_confidence`` (names and numbers are the usual
    culprits). Words without a probability are never flagged.
    """
    starts, ends = sentence_boundaries(words, pause_seconds) if words else ([], [])
    low = []
    for w in words or []:
        if float(start) <= float(w["s"]) < float(end):
            p = w.get("p")
            if p is not None and float(p) < low_confidence:
                low.append({"w": str(w.get("w", "")).strip(),
                            "t": round(float(w["s"]) - float(start), 2),
                            "p": round(float(p), 2)})
    low.sort(key=lambda x: x["p"])
    return {
        "start_boundary": _edge_kind(float(start), starts, tolerance),
        "end_boundary": _edge_kind(float(end), ends, tolerance),
        "low_confidence_words": low[:max_words],
    }
