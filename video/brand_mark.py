"""Add the original team pixel mark to the title and end of an approved-size cut.

The small mark fades in/out on identity cards only; it never covers the demo,
scientific evidence, subtitles or QR. Audio is copied unchanged.
"""
import argparse
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


def raster_mark(path):
    """Rasterise this deliberately tiny, rectilinear SVG at integer pixel scale."""
    import re
    svg = ET.parse(HERE/'assets/sardine-pixel.svg').getroot()
    image = Image.new('RGBA', (128, 64))
    draw = ImageDraw.Draw(image)
    for element in svg:
        if element.tag.endswith('path'):
            for x, y, width, height in re.findall(r'M(\d+) (\d+)h(\d+)v(\d+)H\d+z', element.attrib['d']):
                x,y,width,height = map(int,(x,y,width,height))
                draw.rectangle((x*8,y*8,(x+width)*8-1,(y+height)*8-1),fill=element.attrib['fill'])
    image.save(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--timeline',type=Path,default=HERE/'out/timeline_resolved.json')
    parser.add_argument('--chart-patch',type=Path)
    args=parser.parse_args()
    if args.input.resolve()==args.output.resolve():
        parser.error('Keep the original rendered cut; choose a different output')
    plan=json.loads(args.timeline.read_text(encoding='utf-8'))
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(args.input)]))
    if abs(float(info['format']['duration'])-plan['total'])>.15:
        raise ValueError('Resolved timeline does not match the input cut')
    mark=HERE/'out/sardine-pixel.png';raster_mark(mark)
    title=next(s for s in plan['segments'] if s['id']=='title')
    end=next(s for s in plan['segments'] if s['id']=='end')
    inputs=['-i',str(args.input),'-loop','1','-framerate','30','-i',str(mark)]
    filters=['[1:v]format=rgba,split=2[t][e]']
    base='0:v'
    if args.chart_patch:
        patch=json.loads(args.chart_patch.with_suffix('.json').read_text())
        inputs+=['-i',str(args.chart_patch)]
        filters += [f"[2:v]setpts=PTS-STARTPTS+{patch['start']}/TB[chart]",
                    f"[0:v][chart]overlay=x=0:y=0:eof_action=pass:enable='between(t,{patch['start']},{patch['end']-.001})'[base]"]
        base='base'
    for label,segment in [('t',title),('e',end)]:
        start=segment['start']+.45
        stop=segment['start']+segment['dur']-.4
        filters.append(f'[{label}]fade=t=in:st={start}:d=0.3:alpha=1,fade=t=out:st={stop}:d=0.3:alpha=1[{label}f]')
    filters.extend([
        f"[{base}][tf]overlay=x=1640:y=860:shortest=1:enable='between(t,{title['start']},{title['start']+title['dur']})'[v1]",
        f"[v1][ef]overlay=x=1640:y=630:enable='between(t,{end['start']},{plan['total']})':shortest=1[v]",
    ])
    subprocess.run(['ffmpeg','-y','-loglevel','warning','-progress','pipe:1','-stats_period','10',*inputs,
                    '-filter_complex',';'.join(filters),'-map','[v]','-map','0:a','-c:v','libx264','-preset','medium',
                    '-crf','16','-pix_fmt','yuv420p','-colorspace','bt709','-color_primaries','bt709',
                    '-color_trc','bt709','-color_range','tv','-c:a','copy','-t',str(plan['total']),
                    '-movflags','+faststart',str(args.output)],check=True)
    print('Wrote',args.output,flush=True)


if __name__=='__main__':
    main()
