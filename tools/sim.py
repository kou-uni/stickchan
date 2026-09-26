#!/usr/bin/env python3
"""face.py を Mac 上で描いて PNG にする。

実機の M5.Lcd を PIL に差し替えて、**face.py をそのまま読み込む**。
移植版を別に書くと本物とずれるので、描画コードは1本にしておく。

    python3 tools/sim.py happy embarrassed idle
"""
import sys, types, math, random
from pathlib import Path
from PIL import Image, ImageDraw

W, H = 240, 135
ROOT = Path(__file__).resolve().parent.parent


def rgb(c):
    return ((c >> 16) & 255, (c >> 8) & 255, c & 255)


class Lcd:
    def __init__(self):
        self.im = Image.new('RGB', (W, H), (0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def setRotation(self, r): pass
    def width(self):  return W
    def height(self): return H
    def fillScreen(self, c):
        self.d.rectangle([0, 0, W, H], fill=rgb(c))
    def fillRect(self, x, y, w, h, c):
        self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=rgb(c))
    def fillEllipse(self, x, y, rx, ry, c):
        self.d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=rgb(c))
    def fillCircle(self, x, y, r, c):
        self.d.ellipse([x - r, y - r, x + r, y + r], fill=rgb(c))
    def drawCircle(self, x, y, r, c):
        self.d.ellipse([x - r, y - r, x + r, y + r], outline=rgb(c), width=2)
    def fillTriangle(self, x0, y0, x1, y1, x2, y2, c):
        self.d.polygon([(x0, y0), (x1, y1), (x2, y2)], fill=rgb(c))

    # 実機と同じく、裏に描いて push で転送する形にしておく。
    # ここを「同じ画像に描くだけ」にすると、実機とずれて意味がなくなる。
    def newCanvas(self, w, h, bpp=16, psram=True):
        cv = Lcd()
        cv._parent = self
        return cv

    def push(self, x, y):
        self._parent.im.paste(self.im, (x, y))


class _Stub:
    def __getattr__(self, name):
        return lambda *a, **k: None


def install_fake_m5():
    m5 = types.ModuleType('M5')
    m5.Lcd = Lcd()
    m5.begin = lambda: None
    m5.update = lambda: None
    m5.Power = _Stub()
    m5.BtnA = m5.BtnB = _Stub()
    m5.Imu = _Stub()
    sys.modules['M5'] = m5

    import time as _t
    _t.sleep_ms = lambda ms: None
    _t.ticks_ms = lambda: 0
    _t.ticks_add = lambda a, b: a + b
    _t.ticks_diff = lambda a, b: a - b
    return m5


def main(names, zoom=3):
    m5 = install_fake_m5()
    sys.path.insert(0, str(ROOT))
    import face

    f = face.Face()
    outs = []
    for n in names:
        m5.Lcd.im.paste((0, 0, 0), [0, 0, W, H])
        f.set(n)
        out = ROOT / 'out' / f'sim_{n}.png'
        out.parent.mkdir(exist_ok=True)
        m5.Lcd.im.resize((W * zoom, H * zoom), Image.NEAREST).save(out)
        outs.append(out)
        print(out)

    if len(outs) > 1:
        sheet = Image.new('RGB', (W * zoom, H * zoom * len(outs)), (20, 22, 26))
        for i, o in enumerate(outs):
            sheet.paste(Image.open(o), (0, i * H * zoom))
        s = ROOT / 'out' / 'sim_sheet.png'
        sheet.save(s)
        print(s)


if __name__ == '__main__':
    main(sys.argv[1:] or ['idle', 'happy', 'embarrassed'])
