"""Native rounded word backings; fixed italic text, animated vector layer only."""
import math
import struct


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
    line_padding = pad_x + size * .12 + edge + shadow
    fits = s.line_fitter(font_name, size, uppercase=uppercase, padding=line_padding)
    # layout() includes the complete backing envelope: do not charge the
    # fitter's reserved padding a second time or shrink otherwise-fitting type.
    envelope_budget = fits.budget + 2*line_padding
    blocks = s._collect_word_blocks(transcript, clip_start, clip_end,
                                   max_chars, max_duration, fits=fits,
                                   sentence_aware=True)
    if not blocks:
        return False
    font, em, _ = s._font_metric(font_name)
    unit = em * size / 1000
    ascent, descent = font.getmetrics()
    # libass an7 uses the Windows ascender, not FreeType/Pillow's hhea
    # ascender. Keep the text anchor unchanged; align only the backing.
    with open(font.path, 'rb') as fh:
        data = fh.read()
    for n in range(struct.unpack_from('>H', data, 4)[0]):
        tag, _, offset, _ = struct.unpack_from('>4sIII', data, 12 + 16*n)
        if tag == b'OS/2':
            win_ascent = struct.unpack_from('>H', data, offset + 74)[0]
            break
    else:
        raise ValueError('rounded font requires Windows vertical metrics')
    text_color = s.hex_to_ass_color(font_color)
    box_color = s._hex_to_ass_inline_color(highlight_color, 'E52336')
    outline = s.hex_to_ass_color(border_color, fallback='000000')
    header = (
        '[Script Info]\nScriptType: v4.00+\nPlayResX: 162\nPlayResY: 288\n'
        'WrapStyle: 2\nKerning: no\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n'
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
        # ASS defaults to Kerning: no. Match that shaping in both advances
        # and ink bounds (ALWAYS otherwise loses almost 200 font units).
        widths = [font.getlength(text, features=['-kern'])*unit for text in shown]
        inks = [font.getbbox(text, anchor='ls', features=['-kern']) for text in shown]
        # fscx/fscy scale glyphs, NOT ASS borders or shadows. Fit the whole
        # visible backing/ink envelope in final script units, including a
        # one-unit padding floor for very long, narrowed words.
        space_width = s.line_width(font_name, size, ' ')

        def layout(scale):
            boxes = []
            for left, ink_top, right, ink_bottom in inks:
                px, py = max(1., pad_x*scale), max(1., pad_y*scale)
                bw = ((right-left)*unit*scale + 2*(px+edge) + shadow)/.94
                bh = ((ink_bottom-ink_top)*unit*scale + 2*(py+edge) + shadow)/.98
                cx = (left+right)*unit*scale/2 + shadow/2
                cy = (win_ascent+(ink_top+ink_bottom)/2)*unit*scale + shadow/2
                boxes.append((cx-bw/2, cy-bh/2, bw, bh))
            gap = max(space_width*scale,
                      pad_x*scale + 2*edge + shadow + size*.03*scale)
            gaps = [max(gap,
                        boxes[i][0]+boxes[i][2]-widths[i]*scale
                        - (inks[i+1][0]*unit*scale-edge),
                        inks[i][2]*unit*scale+edge+shadow-widths[i]*scale
                        - boxes[i+1][0]) + size*.03*scale
                    for i in range(len(block)-1)]
            total = sum(widths)*scale + sum(gaps)
            left = min(0., boxes[0][0])
            right = max(total, total-widths[-1]*scale+boxes[-1][0]+boxes[-1][2])
            return boxes, gaps, left, right

        scale = 1.
        boxes, gaps, line_left, line_right = layout(scale)
        if line_right-line_left > envelope_budget:
            low, high = 0., 1.
            for _ in range(24):
                mid = (low+high)/2
                _, _, left, right = layout(mid)
                if right-left <= envelope_budget:
                    low = mid
                else:
                    high = mid
            scale = low
            boxes, gaps, line_left, line_right = layout(scale)
        height = (ascent+descent)*unit*scale
        margin = s._clamp_number(margin_v, 0, 200, 43)
        top = {'top': margin, 'middle': (288-height)/2,
               'bottom': 288-margin-height}.get(alignment, 288-margin-height)
        if any(a <= block[0]['start'] < b for a,b in (split_ranges or [])):
            top = (288-height)/2
        x = (162 - (line_right-line_left))/2 - line_left
        start = max(0, block[0]['start'])
        end = min(limit, max(w['end'] for w in block))
        if block_index + 1 < len(blocks):
            end = min(end, blocks[block_index + 1][0]['start'])
        if start >= end:
            continue
        for i, (word, text, width) in enumerate(zip(block, shown, widths)):
            a = max(start, word['start'])
            b = min(end, block[i+1]['start']) if i+1 < len(block) else end
            left, box_top, width_box, height_box = boxes[i]
            bx, by = x + left, top + box_top
            bw, bh = width_box, height_box
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
            x += width*scale + (gaps[i] if i < len(gaps) else 0)
    if not events:
        return False
    with open(output_path, 'w', encoding='utf-8-sig') as f:
        f.write(header + '\n'.join(events) + '\n')
    return True
