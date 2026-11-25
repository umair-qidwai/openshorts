# Native `rounded_red` captions (opt-in)

`rounded_red` adds fixed, uppercase Barlow Condensed Black Italic text with a
thin dark outline/shadow and an independently drawn red rounded active-word
backing. Only that backing settles from 94% to 100% width (98% to 100% height)
over at most 70 ms. Text and camera never bounce. This is an approximation of
the supplied Arcade caption treatment, not an exact font or animation clone.
The existing auto/default, pill, pop and other presets are unchanged.

## Use

Select **Rounded red** in the subtitle modal, then **apply to this clip**.
This preset uses the native ASS renderer; the modal explicitly shows the
current video, not a misleading Remotion approximation. Apply and play the
rendered result to review it. Selecting this preset does not change defaults.

REST `POST /api/subtitle`:

```json
{"job_id":"YOUR_JOB","clip_index":0,"preset":"rounded_red","position":"bottom"}
```

The existing edited `words` array (`text`, `startMs`, `endMs`) is supported.
Retained caption styles survive native hook/edit reapplication. Start from
OpenShorts' clean sibling, not a previously captioned export.

Existing overrides supported: `font_size` (default 28), `highlight_color`
(default `#E52336`), `font_color`, `border_color`, `border_width` (clamped 0–3),
`shadow` (clamped 0–3), `position`, `uppercase`, `reveal`, `max_chars` (default
18), `max_duration` (default 1.4 seconds). The font is deliberately fixed to
`Barlow Condensed Black`, with the bundled italic face. `bg_opacity` must be
0, `base_opacity` must be 1, and `style` must be `karaoke`; conflicting API
requests receive HTTP 400 before file I/O or metering. Padding, radius and
transition duration are bounded internal proportions, not injectable ASS.
No new arbitrary drawing or filter inputs are exposed.

## Layout and timing

The renderer reuses the measured native line fitter (162×288 virtual portrait
canvas), reserves padding and italic overhang, and uniformly shrinks a lone
oversized word to maintain edge clearance. Phrases split after terminal
`.`, `!`, `?` (including closing quotes/brackets). This heuristic is not a
language-aware sentence parser (abbreviations can split). Whitespace and ASS
control characters are sanitized by the existing text helper.

Backing measurements match libass's unkerned advances and Windows ascender,
not Pillow's default kerning/hhea baseline. Geometry includes the full outline
and positive-offset shadow in final script units (ASS glyph scaling does not
scale those strokes). Minimum padding exists at the initial animation frame;
the settled box expands from that safe envelope. Narrowed words keep at least
one script unit of padding. The complete settled envelope and neighboring
word ink participate in fitting, so neither corners nor adjacent words consume
the clearance.

Within a phrase the backing runs to the next word's onset; the final backing
ends at the phrase end, capped to the clip and next phrase onset. Real pauses
between phrases remain blank. Overlapping word intervals switch emphasis at
the next onset. Distinct words sharing an identical onset cannot each have a
nonzero separate highlight interval; text remains present in their phrase.

Text measurement/layout and libass vector composition run on CPU, like the
existing native caption renderer; media decode/encode can use NVDEC/NVENC.
This is not a GPU text rasterizer. No transcription/reframing is required for
a restyle. The font directory is already supplied to libass, so no system
font install or Docker rebuild is required.

## Font provenance

Unmodified `BarlowCondensed-BlackItalic.ttf` and its SIL OFL 1.1 license are
bundled under `fonts/`, from the Google Fonts repository:

- `https://github.com/google/fonts/tree/main/ofl/barlowcondensed`
- `https://github.com/jpt/barlow` (copyright holder's project)

The reference font is unidentified. Barlow is a freely licensed visual
approximation; production checks must verify libass selects
`BarlowCondensed-BlackItalic`, not a system fallback.

## Tests

```sh
python -m unittest -v test_rounded_captions test_rounded_caption_raster
```

Includes geometry bounds, phrase boundaries, timing overlaps, long words at
multiple sizes, style validation, UI registration and real multi-timepoint
libass raster checks (FFmpeg, Pillow and NumPy are in the backend image).
Existing relevant pytest functions can also be run with the repository's
normal test environment. The deployment's current backend has no pytest;
review evidence distinguishes direct invocation from a full pytest run.
