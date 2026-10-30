"""Re-render a short visual segment while preserving the finished human soundtrack."""
import argparse,json,subprocess
from pathlib import Path
import numpy as np
import finish


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--segment',required=True)
    parser.add_argument('--human-manifest',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    options=argparse.Namespace(human_manifest=args.human_manifest,no_tts=False,reference_tts=False)
    segments,captions,total=finish.build(options)
    segment=next(x for x in segments if x.id==args.segment)
    first=int(np.floor(segment.start*finish.FPS))
    last=int(np.ceil((segment.start+segment.dur)*finish.FPS))
    enc=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24',
        '-s',f'{finish.W}x{finish.H}','-r',str(finish.FPS),'-i','-',
        '-vf','scale=out_color_matrix=bt709:out_range=tv,format=yuv420p',
        '-c:v','libx264','-preset','medium','-crf','16','-colorspace','bt709',
        '-color_primaries','bt709','-color_trc','bt709','-color_range','tv',str(args.out)],stdin=subprocess.PIPE)
    for i in range(first,last):
        frame=finish.frame_at(segments,captions,i/finish.FPS)
        enc.stdin.write(np.clip(frame+.5,0,255).astype(np.uint8).tobytes())
    enc.stdin.close()
    if enc.wait()!=0: raise RuntimeError('Patch encoder failed')
    args.out.with_suffix('.json').write_text(json.dumps({'segment':args.segment,'start':first/finish.FPS,
        'end':last/finish.FPS,'total':total},indent=2),encoding='utf-8')
    print('Wrote',args.out,flush=True)


if __name__=='__main__': main()
