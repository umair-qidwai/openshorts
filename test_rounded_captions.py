"""Native rounded captions; runnable with stdlib unittest in backend."""
import unittest
import tempfile
from pathlib import Path
import subtitles as s

class RoundedTests(unittest.TestCase):
    def test_rounded_geometry_is_bounded(self):
        from rounded_captions import rounded_path
        for w,h,r in [(10,8,2),(3,4,90),(100,20,0)]:
            path = rounded_path(w,h,r)
            self.assertIn('b ',path)
            nums = [float(x) for x in path.split() if x not in ('m','l','b','c')]
            self.assertTrue(all(0 <= x <= w for x in nums[::2]))
            self.assertTrue(all(0 <= y <= h for y in nums[1::2]))
        for w,h,r in [(0,4,1),(-1,4,2),(4,float('nan'),1)]:
            with self.assertRaises(ValueError): rounded_path(w,h,r)

    def test_native_preset_generates_sentence_aware_word_layers(self):
        self.assertIn('rounded_red', s.CAPTION_PRESETS)
        preset = dict(s.CAPTION_PRESETS['rounded_red'])
        preset['fontsize'] = preset.pop('font_size')
        preset.pop('style')
        tr = {'segments': [{'words': [
            {'word':' YOU.', 'start':0, 'end':.4},
            {'word':' NOTHING', 'start':.4, 'end':.8},
            {'word':' IS', 'start':.8, 'end':1.2}]}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'captions.ass'
            self.assertTrue(s.generate_ass(tr,0,1.2,str(p),**preset))
            text = p.read_text(encoding='utf-8-sig')
        self.assertIn('PlayResX: 162',text)
        self.assertIn('Barlow Condensed Black',text)
        self.assertIn(r'\p1', text)
        self.assertIn(r'\t(', text)
        self.assertNotIn('YOU. NOTHING',text)
        lines = [x for x in text.splitlines() if x.startswith('Dialogue: 1,')]
        self.assertEqual(3,len(lines))
        self.assertTrue(all(r'\t(' not in x for x in lines)) # text never bounces

    def test_rounded_style_rejects_unmeasurable_or_conflicting_options(self):
        from rounded_captions import validate_style
        base = dict(s.CAPTION_PRESETS['rounded_red'])
        validate_style(base)
        for change in ({'font_name':'Unknown'}, {'bg_opacity':.4}, {'base_opacity':.5}, {'style':'classic'}):
            with self.assertRaises(ValueError): validate_style({**base, **change})
        # API must validate the merged preset before any I/O/metering.
        import ast
        tree = ast.parse(Path('app.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'add_subtitles')
        src = ast.unparse(fn)
        self.assertLess(src.index('validate_style('), src.index('await require_managed_entitlement'))

    def test_rasterized_backing_contains_italic_ink_and_settles_only_box(self):
        import subprocess
        import numpy as np
        opts = dict(s.CAPTION_PRESETS['rounded_red']); opts.pop('style')
        opts['fontsize'] = opts.pop('font_size')
        tr = {'segments':[{'words':[{'word':' HELLO', 'start':0, 'end':.2}]}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'c.ass'; s.generate_ass(tr,0,.2,str(p),**opts)
            vf = s.subtitles_filter(str(p))
            r = subprocess.run(['ffmpeg','-v','info','-f','lavfi','-i','color=black:s=360x640:r=100:d=0.2',
                                '-vf',vf,'-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True)
            self.assertEqual(0,r.returncode,r.stderr.decode()[-1500:])
            frames = np.frombuffer(r.stdout,dtype=np.uint8).reshape(-1,640,360,3)
            red_bounds=[]; white_bounds=[]
            for im in frames[[0,4,10]]:
                red=(im[:,:,0]>120)&(im[:,:,1]<80)&(im[:,:,2]<110)
                white=(im.min(axis=2)>200)
                ry,rx=np.where(red); wy,wx=np.where(white)
                self.assertGreater(len(rx),50); self.assertGreater(len(wx),50)
                red_bounds.append((rx.min(),ry.min(),rx.max(),ry.max()))
                white_bounds.append((wx.min(),wy.min(),wx.max(),wy.max()))
                self.assertGreaterEqual(wy.min(),ry.min())
                self.assertLessEqual(wy.max(),ry.max())
                self.assertGreaterEqual(wx.min(),rx.min())
                self.assertLessEqual(wx.max(),rx.max())
            self.assertEqual(white_bounds[0],white_bounds[-1])
            self.assertLess(red_bounds[0][2]-red_bounds[0][0],red_bounds[-1][2]-red_bounds[-1][0])
            log=r.stderr.decode()
            self.assertIn('BarlowCondensed-BlackItalic',log)

    def test_ui_registers_native_effect_without_misleading_remotion_preview(self):
        src = Path('dashboard/src/components/SubtitleModal.jsx').read_text()
        self.assertIn("id: 'rounded_red'",src)
        self.assertIn("rounded: 'rounded'",src)
        self.assertIn("useRemotionPreview && effect !== 'rounded'",src)
        self.assertIn('native render',src.lower())

    def test_blocks_never_overlap_or_run_beyond_clip_end(self):
        import re
        opts=dict(s.CAPTION_PRESETS['rounded_red']); opts.pop('style')
        opts['fontsize']=opts.pop('font_size'); opts['max_chars']=1
        tr={'segments':[{'words':[
            {'word':' FIRST.', 'start':-.1, 'end':.6},
            {'word':' SECOND', 'start':.5, 'end':2.0}]}]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'c.ass'; s.generate_ass(tr,0,1,str(p),**opts)
            rows=[x.split(',') for x in p.read_text().splitlines() if x.startswith('Dialogue: 1,')]
        self.assertEqual(2,len(rows))
        self.assertEqual(rows[0][2], rows[1][1])
        self.assertEqual('0:00:01.00',rows[-1][2])

    def test_padding_does_not_touch_neighbouring_word_ink(self):
        import re
        opts=dict(s.CAPTION_PRESETS['rounded_red']); opts.pop('style')
        opts['fontsize']=opts.pop('font_size'); opts['max_duration']=5
        tr={'segments':[{'words':[{'word':' '+w,'start':i*.3,'end':(i+1)*.3} for i,w in enumerate(['IT','ALWAYS','LOOKS'])]}]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'c.ass'; s.generate_ass(tr,0,1,str(p),**opts)
            rows=[x for x in p.read_text().splitlines() if x.startswith('Dialogue: 1,')]
        positions=[float(re.search(r'\\pos\(([^,]+)',x).group(1)) for x in rows]
        size=int(opts['fontsize']*.85)
        gap=positions[1]-positions[0]-s.line_width(opts['font_name'],size,'IT')
        self.assertGreaterEqual(gap,size*.1+2*opts['border_width']+opts['shadow'])

    def test_long_word_backing_keeps_edge_clearance_at_every_size(self):
        import re
        for size in (10,28,70,200):
            opts=dict(s.CAPTION_PRESETS['rounded_red']); opts.pop('style')
            opts['fontsize']=size; opts.pop('font_size')
            tr={'segments':[{'words':[{'word':' '+('W'*60)+'?!','start':0,'end':1}]}]}
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'c.ass'; s.generate_ass(tr,0,1,str(p),**opts)
                row=next(x for x in p.read_text().splitlines() if x.startswith('Dialogue: 0,'))
            cx=float(re.search(r'\\pos\(([^,]+)',row).group(1))
            coords=[float(x) for x in row.split('}')[1].split() if x not in ('m','l','b','c')]
            width=max(coords[::2])
            self.assertGreaterEqual(cx-width/2,9)
            self.assertLessEqual(cx+width/2,153)

    def test_sentence_endings_split_with_closing_brackets_and_quotes(self):
        for ending in ('STOP!]', 'STOP!)', 'STOP.', 'STOP?', 'STOP!',
                       'STOP!\"', "STOP!'", 'STOP!”', 'STOP!’', 'STOP!)]'):
            with self.subTest(ending=ending):
                tr = {'segments': [{'words': [
                    {'word': ' ' + ending, 'start': 0, 'end': .3},
                    {'word': ' NEXT', 'start': .3, 'end': .6}]}]}
                blocks = s._collect_word_blocks(tr, 0, 1, max_chars=100,
                                                max_duration=5, sentence_aware=True)
                self.assertEqual([[ending], ['NEXT']],
                                 [[word['word'] for word in block] for block in blocks])
                # Opt-in only: legacy grouping must remain unchanged.
                legacy = s._collect_word_blocks(tr, 0, 1, max_chars=100, max_duration=5)
                self.assertEqual([[ending, 'NEXT']],
                                 [[word['word'] for word in block] for block in legacy])

    def test_direct_generator_rejects_unsupported_background(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                s.generate_ass({'segments':[{'words':[{'word':' hi','start':0,'end':1}]}]},
                               0,1,str(Path(d)/'x.ass'),effect='rounded',
                               font_name='Barlow Condensed Black',bg_opacity=.5)

if __name__ == '__main__': unittest.main()
