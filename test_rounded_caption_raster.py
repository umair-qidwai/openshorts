"""Real libass ink/backing masks: no Pillow-derived expected bounds."""
from pathlib import Path
import tempfile
import subprocess
import unittest
import numpy as np
import subtitles as s

def render(header, row, white=False):
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'c.ass'; p.write_text(header+row+'\n')
        vf=s.subtitles_filter(str(p))
        r=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color={"white" if white else "black"}:s=720x1280:r=100:d=0.10','-vf',vf,'-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True)
        assert r.returncode==0,r.stderr
        return np.frombuffer(r.stdout,np.uint8).reshape(-1,1280,720,3)
def pair_masks(content,index):
    """Rasterize exactly one text event and its backing independently."""
    header=content.split('Dialogue:')[0]
    texts=[r for r in content.splitlines() if r.startswith('Dialogue: 1,')]
    boxes=[r for r in content.splitlines() if r.startswith('Dialogue: 0,')]
    def zero(row):
        parts=row.split(',',9); parts[1]='0:00:00.00'; parts[2]='0:00:00.10'; return ','.join(parts)
    # Black fill on white captures the complete glyph + outline + shadow
    # silhouette without selecting pixels from any neighboring word.
    text=render(header,zero(texts[index]).replace(r'\an7', r'\1c&H000000&\an7'),True)
    box=render(header,zero(boxes[index]))
    return np.min(text,axis=3)<248, box[:,:,:,0]>120

def metrics(ink,back):
    """Measure containment and clearance against the rounded raster, not its bbox."""
    y,x=np.where(ink); by,bx=np.where(back)
    sides=[int(x.min()-bx.min()),int(y.min()-by.min()),int(bx.max()-x.max()),int(by.max()-y.max())]
    missing=int(np.count_nonzero(ink&~back))
    clearance=0
    for r in range(1,30):
        if y.min()<r or x.min()<r or y.max()+r>=back.shape[0] or x.max()+r>=back.shape[1]: break
        if not all(back[y+dy,x+dx].all() for dx,dy in [(r,0),(-r,0),(0,r),(0,-r),(r,r),(-r,r),(r,-r),(-r,-r)]): break
        clearance=r
    return {'sides_px':sides,'outside_pixels':missing,'square_clearance_px':clearance,'ink_bounds':[int(x.min()),int(y.min()),int(x.max()),int(y.max())]}


class RoundedRasterTests(unittest.TestCase):
    def test_actual_italic_outline_shadow_has_clearance_through_animation(self):
        opts=dict(s.CAPTION_PRESETS['rounded_red']); opts.pop('style')
        opts['fontsize']=opts.pop('font_size')
        tr={'segments':[{'words':[{'word':' '+w,'start':i*.3,'end':(i+1)*.3}
                                  for i,w in enumerate(['IT','ALWAYS','LOOKS','JUST','DESCRIBE','IT'])]}]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'c.ass'; s.generate_ass(tr,0,2,str(p),**opts)
            content=p.read_text(encoding='utf-8-sig')
        for index in (1,4):
            ink,box=pair_masks(content,index)
            self.assertTrue(np.array_equal(ink[0],ink[7]), 'text must stay fixed')
            for frame in (0,3,7):
                with self.subTest(word=index,ms=frame*10):
                    observed=metrics(ink[frame],box[frame])
                    self.assertEqual(0,observed['outside_pixels'],observed)
                    self.assertGreaterEqual(observed['square_clearance_px'],3,observed)

    def test_narrowed_and_extreme_sizes_retain_real_pixel_clearance(self):
        for size in (10,28,70,200):
            for word in ('I','W?!','ALWAYS','DESCRIBE','jgy!', 'W'*60+'?!'):
                opts=dict(s.CAPTION_PRESETS['rounded_red']); opts.pop('style')
                opts['fontsize']=size; opts.pop('font_size'); opts['uppercase']=False
                tr={'segments':[{'words':[{'word':' '+word,'start':0,'end':1}]}]}
                with tempfile.TemporaryDirectory() as d:
                    p=Path(d)/'c.ass'; s.generate_ass(tr,0,1,str(p),**opts)
                    content=p.read_text(encoding='utf-8-sig')
                ink,box=pair_masks(content,0)
                for frame in (0,3,7):
                    with self.subTest(size=size,word=word,ms=frame*10):
                        observed=metrics(ink[frame],box[frame])
                        self.assertEqual(0,observed['outside_pixels'],observed)
                        self.assertGreaterEqual(observed['square_clearance_px'],1,observed)
                        y,x=np.where(box[frame])
                        self.assertGreater(x.min(),0)
                        self.assertLess(x.max(),719)
                        self.assertGreater(y.min(),0)
                        self.assertLess(y.max(),1279)

    def test_backing_does_not_cover_individually_rasterized_neighbors(self):
        opts=dict(s.CAPTION_PRESETS['rounded_red']); opts.pop('style')
        opts['fontsize']=opts.pop('font_size'); opts['max_duration']=5
        tr={'segments':[{'words':[{'word':' '+w,'start':i*.3,'end':(i+1)*.3}
                                  for i,w in enumerate(['IT','ALWAYS','LOOKS'])]}]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'c.ass'; s.generate_ass(tr,0,1,str(p),**opts)
            content=p.read_text(encoding='utf-8-sig')
        masks=[pair_masks(content,i) for i in range(3)]
        for i,(_,back) in enumerate(masks):
            for j,(ink,_) in enumerate(masks):
                if i != j:
                    self.assertFalse(np.any(back[7]&ink[7]), (i,j))

    def test_original_sample_phrase_does_not_shrink_to_pay_padding_twice(self):
        opts=dict(s.CAPTION_PRESETS['rounded_red']); opts.pop('style')
        opts['fontsize']=opts.pop('font_size')
        tr={'segments':[{'words':[{'word':' '+w,'start':i*.3,'end':(i+1)*.3}
                                  for i,w in enumerate(['IT','ALWAYS','LOOKS'])]}]}
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'c.ass'; s.generate_ass(tr,0,1,str(p),**opts)
            rows=[r for r in p.read_text().splitlines() if r.startswith('Dialogue: 1,')]
        self.assertEqual(3,len(rows))
        self.assertTrue(all(r'\fscx100.000\fscy100.000' in row for row in rows),rows)

if __name__=='__main__': unittest.main()
