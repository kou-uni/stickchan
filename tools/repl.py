#!/usr/bin/env python3
"""StickS3 の MicroPython REPL にコードを流す。

  repl.py --exec "print(1)"        1行だけ実行
  repl.py --run FILE               ファイルを paste mode で実行（保存しない）
  repl.py --put FILE DEST          ファイルを本体に保存
  repl.py --port /dev/cu.xxx       ポート指定（省略時は自動検出）
"""
import argparse, glob, sys, time
import serial

def find_port():
    ps = sorted(glob.glob('/dev/cu.usbmodem*'))
    if not ps:
        sys.exit("NOT CONNECTED: /dev/cu.usbmodem* が見つかりません")
    return ps[0]

class Repl:
    def __init__(self, port):
        self.s = serial.Serial(port, 115200, timeout=0.05)
        time.sleep(0.2)
        self.s.write(b'\x03\x03')      # 走っているものを止める
        time.sleep(0.4)
        self.s.reset_input_buffer()

    def _read_until_prompt(self, limit=20.0):
        """paste mode 実行後、>>> が返るまで読む。空読みで待たない。"""
        out = b''
        t0 = time.time()
        while time.time() - t0 < limit:
            chunk = self.s.read(self.s.in_waiting or 1)
            if chunk:
                out += chunk
                if out.rstrip().endswith(b'>>>'):
                    return out.decode(errors='replace')
        return out.decode(errors='replace') + '\n[TIMEOUT]'

    def exec(self, code, limit=20.0):
        """paste mode で送る。複数行でもインデントが壊れない。"""
        self.s.write(b'\x05')          # Ctrl-E: paste mode
        time.sleep(0.05)
        self.s.read(self.s.in_waiting or 1)
        self.s.write(code.replace('\n', '\r\n').encode() + b'\r\n')
        self.s.write(b'\x04')          # Ctrl-D: 実行
        self.s.flush()
        return self._read_until_prompt(limit)

    def close(self):
        self.s.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port')
    ap.add_argument('--limit', type=float, default=20.0,
                    help='実機の応答を待つ上限(秒)。長く走らせるときは伸ばす')
    ap.add_argument('--exec')
    ap.add_argument('--run')
    ap.add_argument('--put', nargs=2, metavar=('FILE', 'DEST'))
    ap.add_argument('--get', nargs=2, metavar=('DEVICE', 'LOCAL'),
                    help='実機のファイルを取り出す。base64 で運ぶのでエコーが混ざらない')
    a = ap.parse_args()

    r = Repl(a.port or find_port())
    try:
        if a.exec:
            print(r.exec(a.exec, a.limit))
        elif a.run:
            print(r.exec(open(a.run).read(), a.limit))
        elif a.put:
            src, dest = a.put
            body = open(src, 'rb').read()
            r.exec(f"f = open({dest!r}, 'wb')")
            for i in range(0, len(body), 256):
                r.exec(f"f.write({body[i:i+256]!r})")
            r.exec("f.close()")
            # 書けたか本体側で数えて返す
            print(r.exec(
                f"import os; print('SIZE', os.stat({dest!r})[6], 'EXPECTED', {len(body)})"))
        elif a.get:
            dev, local = a.get
            # ★print で吐かせると paste mode のエコーが混ざる。
            #   2026-09-25、それで退避した boot.py が壊れ、実機に書いて起動不能にした。
            #   1行の base64 にして、目印の間だけを取る。
            out = r.exec(
                "import ubinascii\n"
                f"_f = open({dev!r}, 'rb')\n"
                "_b = ubinascii.b2a_base64(_f.read()).decode().strip()\n"
                "_f.close()\n"
                # ★目印はソース行にそのまま書かない。paste mode はコードを
                #   エコーするので、書くとエコー側が先に一致して壊れる。
                "print('<<' + 'B64>>' + _b + '<</' + 'B64>>')", 60.0)
            import base64, re
            m = re.search(r'<<B64>>(.*?)<</B64>>', out.replace('\r', '').replace('\n', ''))
            if not m:
                raise SystemExit('取り出せませんでした:\n' + out[-400:])
            data = base64.b64decode(m.group(1))
            open(local, 'wb').write(data)
            # ディスクから読み直して、実機側のサイズと突き合わせる
            n = len(open(local, 'rb').read())
            size = r.exec(f"import os; print('SZ', os.stat({dev!r})[6])")
            want = int(re.search(r'SZ (\d+)', size).group(1))
            print(f'{"OK " if n == want else "NG "}{local}: {n} bytes / 実機 {want} bytes')
        else:
            ap.error("--exec / --run / --put / --get のどれかが要ります")
    finally:
        r.close()

if __name__ == '__main__':
    main()
