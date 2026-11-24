"""Native rounded word backings; fixed italic text, animated vector layer only."""
import math


def validate_style(style):
    """Reject conflicting rounded typography rather than silently falling back."""
    if style.get('effect') != 'rounded':
        return
    if style.get('font_name') != 'Barlow Condensed Black':
        raise ValueError('rounded requires bundled Barlow Condensed Black italic font')
    if (style.get('style', 'karaoke') != 'karaoke' or
            style.get('bg_opacity', 0) != 0 or style.get('base_opacity', 1) != 1):
        raise ValueError('rounded requires karaoke, bg_opacity=0 and base_opacity=1')


def rounded_path(width, height, radius):
    """Closed cubic ASS p1 path, local origin at the upper-left corner."""
    if not all(math.isfinite(v) for v in (width, height, radius)) or min(width, height) <= 0:
        raise ValueError('Rounded rectangle needs finite positive dimensions')
    r = max(0, min(radius, width / 2, height / 2))
    k = r * (1 - 0.5522847498)
    w, h = width, height
    return (f'm {r:.3f} 0 l {w-r:.3f} 0 '
            f'b {w-k:.3f} 0 {w:.3f} {k:.3f} {w:.3f} {r:.3f} '
            f'l {w:.3f} {h-r:.3f} '
            f'b {w:.3f} {h-k:.3f} {w-k:.3f} {h:.3f} {w-r:.3f} {h:.3f} '
            f'l {r:.3f} {h:.3f} '
            f'b {k:.3f} {h:.3f} 0 {h-k:.3f} 0 {h-r:.3f} '
            f'l 0 {r:.3f} b 0 {k:.3f} {k:.3f} 0 {r:.3f} 0 c')


def generate(transcript, clip_start, clip_end, output_path, *, max_chars,
             max_duration, alignment, fontsize, font_name, font_color,
             border_color, border_width, highlight_color, uppercase,
             margin_v, split_ranges, shadow, base_opacity, reveal):
    """Layout on the existing 162x288 canvas. Only backing settles <=70ms.

    Fixed bundled italic face keeps text geometry and libass font selection
    deterministic. Existing style knobs still control size/color/position.
    """
    import subtitles as s
    if font_name != 'Barlow Condensed Black' or s._font_metric(font_name) is None:
        raise ValueError('rounded requires bundled Barlow Condensed Black italic font')
    size = max(10, int(s._clamp_number(fontsize, 10, 200, 40) * .85))
    pad_x, pad_y = size * .10, size * .055
    edge = s._clamp_number(border_width, 0, 3, 1)
    shadow = s._clamp_number(shadow, 0, 3, 1)
    fits = s.line_fitter(font_name, size, uppercase=uppercase,
                         padding=pad_x + size * .12 + edge + shadow)
    blocks = s._collect_word_blocks(transcript, clip_start, clip_end,
                                   max_chars, max_duration, fits=fits,
                                   sentence_aware=True)
    if not blocks:
        return False
    font, em, _ = s._font_metric(font_name)
    unit = em * size / 1000
    ascent, descent = font.getmetrics()
    text_color = s.hex_to_ass_color(font_color)
    box_color = s._hex_to_ass_inline_color(highlight_color, 'E52336')
    outline = s.hex_to_ass_color(border_color, fallback='000000')
    header = (
        '[Script Info]\nScriptType: v4.00+\nPlayResX: 162\nPlayResY: 288\n'
        'WrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n'
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, '
        'OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, '
        'ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, '
        'Alignment, MarginL, MarginR, MarginV, Encoding\n'
        f'Style: Default,{font_name},{size},{text_color},{text_color},'
        f'{outline},&H80000000,-1,-1,0,0,100,100,0,0,1,{edge},{shadow},7,0,0,0,1\n'
        '\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
    events = []
    limit = clip_end - clip_start
    for block_index, block in enumerate(blocks):
        shown = [w['word'].upper() if uppercase else w['word'] for w in block]
        widths = [s.line_width(font_name, size, text) for text in shown]
        gap = max(s.line_width(font_name, size, ' '),
                  pad_x + 2*edge + shadow + size*.03)
        total = sum(widths) + gap * (len(block)-1)
        scale = min(1., fits.budget / max(total, .001))
        height = (ascent+descent)*unit*scale
        margin = s._clamp_number(margin_v, 0, 200, 43)
        top = {'top': margin, 'middle': (288-height)/2,
               'bottom': 288-margin-height}.get(alignment, 288-margin-height)
        if any(a <= block[0]['start'] < b for a,b in (split_ranges or [])):
            top = (288-height)/2
        x = (162 - total*scale)/2
        start = max(0, block[0]['start'])
        end = min(limit, max(w['end'] for w in block))
        if block_index + 1 < len(blocks):
            end = min(end, blocks[block_index + 1][0]['start'])
        if start >= end:
            continue
        for i, (word, text, width) in enumerate(zip(block, shown, widths)):
            a = max(start, word['start'])
            b = min(end, block[i+1]['start']) if i+1 < len(block) else end
            left, ink_top, right, ink_bottom = font.getbbox(text, anchor='ls')
            bx = x + left*unit*scale - (pad_x+edge)*scale
            by = top + (ascent+ink_top)*unit*scale - (pad_y+edge)*scale
            bw = (right-left)*unit*scale + 2*(pad_x+edge)*scale
            bh = (ink_bottom-ink_top)*unit*scale + 2*(pad_y+edge)*scale
            if b > a:
                ms = max(1, min(70, round((b-a)*1000)))
                path = rounded_path(bw, bh, min(bh*.22, size*.16*scale))
                tags = (f'{{\\an5\\pos({bx+bw/2:.3f},{by+bh/2:.3f})'
                        f'\\bord0\\shad0\\1c{box_color}\\fscx94\\fscy98'
                        f'\\t(0,{ms},\\fscx100\\fscy100)\\p1}}')
                events.append(f'Dialogue: 0,{s._ass_time(a)},{s._ass_time(b)},Default,,0,0,0,,{tags}{path}')
            text_start = a if reveal else start
            if text_start < end:
                tags = f'{{\\an7\\pos({x:.3f},{top:.3f})\\fscx{scale*100:.3f}\\fscy{scale*100:.3f}}}'
                events.append(f'Dialogue: 1,{s._ass_time(text_start)},{s._ass_time(end)},Default,,0,0,0,,{tags}{s._escape_ass_text(text)}')
            x += (width + gap)*scale
    if not events:
        return False
    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(header + '\n'.join(events) + '\n')
    return True
