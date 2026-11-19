"""Tests for sentence_snap. Run: python -c "import test_sentence_snap as t; t.run()"."""

from sentence_snap import (review_flags, sentence_boundaries,
                           snap_clip_to_sentences)


def _words(spec):
    """spec: list of (text, start, end)."""
    return [{"w": w, "s": s, "e": e} for w, s, e in spec]


# "Hello there. So we are consistent. That is it." with tight timing.
W = _words([
    ("Hello", 0.0, 0.4), ("there.", 0.4, 0.8),
    ("So", 1.0, 1.2), ("we", 1.2, 1.4), ("are", 1.4, 1.6), ("consistent.", 1.6, 2.2),
    ("That", 2.4, 2.6), ("is", 2.6, 2.8), ("it.", 2.8, 3.2),
])


def test_boundaries_from_punctuation():
    starts, ends = sentence_boundaries(W)
    assert (1.0, True) in starts and (2.4, True) in starts
    assert (2.2, True) in ends and (3.2, True) in ends


def test_mid_sentence_start_moves_back_to_sentence_start():
    s, e = snap_clip_to_sentences(1.4, 3.2, W, 10, min_duration=1, max_duration=5)
    assert 0.8 <= s <= 1.0, s


def test_mid_sentence_end_moves_to_sentence_end():
    s, e = snap_clip_to_sentences(1.0, 2.7, W, 10, min_duration=1, max_duration=5)
    assert 2.2 <= e <= 2.4 or 3.2 <= e <= 3.6, e


def test_pause_counts_when_no_punctuation():
    w = _words([("and", 0, 0.3), ("then", 0.3, 0.6), ("we", 1.6, 1.8), ("left", 1.8, 2.2)])
    starts, ends = sentence_boundaries(w)
    assert (1.6, False) in starts and (0.6, False) in ends


def test_punctuation_beats_nearer_pause():
    w = _words([("a.", 0, 0.5), ("b", 0.6, 1.0), ("c", 2.0, 2.4), ("d", 2.4, 3.0)])
    s, _ = snap_clip_to_sentences(1.9, 3.0, w, 10, min_duration=0.5, max_duration=5,
                                  weak_penalty=1.5)
    assert s <= 0.6, s  # strong start at 0.6 beats pause start at 2.0


def test_respects_duration_bounds_and_falls_back():
    s, e = snap_clip_to_sentences(1.4, 2.7, W, 10, min_duration=30, max_duration=60)
    assert (s, e) == (1.4, 2.7)


def test_no_words_is_identity():
    assert snap_clip_to_sentences(5, 20, [], 100) == (5.0, 20.0)


def test_review_flags():
    w = [dict(x) for x in W]
    w[3]["p"] = 0.2
    f = review_flags(1.0, 3.2, w)
    assert f["start_boundary"] == "sentence" and f["end_boundary"] == "sentence"
    assert f["low_confidence_words"][0]["w"] == "we"
    f2 = review_flags(1.4, 2.7, W)
    assert f2["start_boundary"] == "none"


def run():
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
    print(f"{n} passed")


if __name__ == "__main__":
    run()
