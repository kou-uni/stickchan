#!/usr/bin/env python3
"""まばたきと呼吸が顔を壊していないかを、画素で確かめる。

不変条件はこれ1つ:
  **まばたきを1周して目を開いたら、描き直した顔と1ピクセルも違わない。**

「目の周りは除外する」ような検査にしてはいけない。壊れるのは、
まさに目の消し枠が口に届く境目で、そこは除外範囲の中に入ってしまう
（実際、最初にそう書いて surprised のバグを見落としかけた）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim import install_fake_m5, W, H
from PIL import Image

m5 = install_fake_m5()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import face

BLINK = (0.65, 0.3, 0.0, 0.3, 0.65, 1.0)

def main():
    f = face.Face()
    bad = []
    for name in face.ORDER:
        f.set(name)
        fresh = m5.Lcd.im.copy()          # 描き直した正解
        for r in BLINK:
            f.open_ratio = r
            f.render()
        # 呼吸も1周させる。戻ったら元通りでなければならない
        for oy in (1, 2, 3, 2, 1, 0, -1, -2, -3, -2, -1, 0):
            f.oy = oy
            f.render()
        after = m5.Lcd.im.copy()          # まばたき＋呼吸1周のあと
        diff = [(x, y) for y in range(H) for x in range(W)
                if fresh.getpixel((x, y)) != after.getpixel((x, y))]
        mark = 'OK ' if not diff else 'NG '
        print(f'{mark}{name:12s} 差分 {len(diff):4d} px  {diff[:5]}')
        if diff:
            bad.append((name, fresh, after))

    if bad:
        Z = 2
        sheet = Image.new('RGB', (W*Z*2, H*Z*len(bad)), (20, 22, 26))
        for i, (n, a, b) in enumerate(bad):
            sheet.paste(a.resize((W*Z, H*Z), Image.NEAREST), (0, i*H*Z))
            sheet.paste(b.resize((W*Z, H*Z), Image.NEAREST), (W*Z, i*H*Z))
        out = Path(__file__).resolve().parent.parent / 'out' / 'blink_broken.png'
        out.parent.mkdir(exist_ok=True)
        sheet.save(out)
        print('壊れた表情の比較:', out)
    print('結果:', '全表情で差分なし' if not bad else f'壊れている: {[n for n,_,_ in bad]}')
    return 1 if bad else 0

if __name__ == '__main__':
    raise SystemExit(main())
