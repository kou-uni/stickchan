# ミニスタックちゃん — M5Stack StickS3 の顔
#
# 形は app/avatar/make_faces.py からの移植。あちらが m5stack-avatar の
#   src/Eyes.cpp / src/Mouths.cpp / src/Effect.h を 320x240 基準で移植したもの。
#   ここではその比率を保ったまま 240x135 に落としている。
#
#   ・笑い目は「楕円を2枚と長方形で削り出す上向きの弧」
#   ・口は楕円ではなく長方形。開くほど細く高くなる（閉 90x4 → 開 50x60）
#   ・左右の目の高さが 320 基準で 3px ずれている。この非対称が表情の正体
#
# ★描画はオフスクリーンのキャンバスに全部描いてから一度に転送する。
#   直接描いていた頃は「消してから描く」の消えている瞬間が見えて、
#   呼吸を入れた途端にチラついた（2026-09-26）。push は実測 14.5ms。
#   部分的に消す方式もやめたので、「消し枠が足りずに口や頬を食う」系の
#   バグ（surprised / embarrassed で実際に起きた）は構造ごと消えている。
#
# 実機で確かめたこと:
#   画面 240x135(rotation=1) / BtnA=正面の青 / BtnB=右側 / 左側はリセット
#   タッチ無し / 明るさ・近接センサ無し / LED 0個 / スピーカーとバイブは有り
#   IMU は静止ノイズ ±0.01G
import M5, time, random, math

BG    = 0x000000
WHITE = 0xFFFFFF
BLUSH = 0xE25850

K = 0.75                      # 320x240 → 240x135 の縮尺
M_MIN_W, M_MAX_W = 50, 90     # RectMouth の寸法（320基準）
M_MIN_H, M_MAX_H = 4, 60

# 表情 → (目の形, 口の開き, マーク, 頬の赤み, 目の拡大)
TABLE = {
    'idle':        ('neutral', 0.00, None,     False, 1.00),
    'happy':       ('happy',   0.30, 'heart',  False, 1.00),
    'thinking':    ('doubt',   0.00, 'sweat',  False, 1.00),
    'sad':         ('sad',     0.10, 'chill',  False, 1.00),
    'surprised':   ('neutral', 1.00, None,     False, 1.35),
    'embarrassed': ('happy',   0.18, 'heart',  True,  1.00),
    'angry':       ('angry',   0.10, 'anger',  False, 1.00),
    'sleepy':      ('sleepy',  0.00, 'bubble', False, 1.00),
}
ORDER = ('idle', 'happy', 'embarrassed', 'thinking', 'sad', 'surprised',
         'angry', 'sleepy')


class Face:
    def __init__(self):
        M5.begin()
        M5.Lcd.setRotation(1)
        self.w = M5.Lcd.width()
        self.h = M5.Lcd.height()
        self.cx = self.w // 2
        self.cv = M5.Lcd.newCanvas(self.w, self.h, 16, True)
        self.g = self.cv                 # 描き先。実機画面には直接描かない

        # 見た目の調整つまみ。走らせたまま変えられる
        self.eye_r   = 15
        self.eye_dx  = 42
        self.eye_y   = 52
        self.mouth_y = 100
        self.mouth_k = 0.78              # 口は目と別倍率（揃えると画面を覆う）
        self.blink_min = 1800
        self.blink_max = 5200
        self.breath_px = 3               # 呼吸の振れ幅(px)。0 で止まる
        self.breath_ms = 3600            # 呼吸1周期(ms)

        self.idle_timeout_ms = 180000
        self.log_every_ms = 0
        self.bright = 127
        self.asleep = False
        self.pinned = False
        self.sound = True        # 青の長押しで切り替え
        self.volume = 80

        # 振る／撫でるの区別（ジャイロ）
        self.shake_dps = 320     # この回転速度(deg/s)を超えたら「振られた」
        # 置き方（加速度Z）。実測: 画面を上に水平で z=+1.0
        self.facedown_z = -0.60  # これより下向きなら伏せたと見なす
        self.facedown_ms = 1200  # その姿勢が続いたら寝る
        self._down_since = None
        self._slept_by_pose = False
        # 電池が減ったら動きが重くなる
        self.low_batt = 25       # % 未満で眠りやすくなる
        self._batt = 100
        # 寝ていた時間。久しぶりに起こされたら喜ぶ
        self._slept_at = None
        self.longsleep_ms = 1800000   # 30分
        self.drowsy = 0          # 0=ふつう 1=眠そう 2=うとうと
        self._awake_name = None  # 眠くなる前の表情。起きたら戻す

        # 視線。起動時の姿勢を「まっすぐ」の基準にする。
        #   ★水平を基準に決め打ちしない。実測したら、机の上に置いた状態が
        #     (0.01, 0.73, 0.67) ＝ 45度傾いて立っていた（2026-09-26）。
        #     どんな置き方でも成立するように、基準はその場で取る。
        # ★5px では見えなかった（2026-09-26）。目の直径が30pxあり、呼吸で
        #   顔全体が±3px動くので、その中に紛れる。数字上は振り切っていた。
        self.gaze_px = 10       # 目そのものが動く最大px。0 で止まる
        # ★瞳（白目の中の黒点）も作って見たが、白い塊に穴が空いたようにしか
        #   見えなかった（2026-09-26）。スタックチャンの目は白い塊そのものが
        #   瞳なので、中を抜くと欠けて見える。本家に瞳が無いのはこのため。
        #   残してあるが既定は 0（描かない）。
        self.pupil_r = 0
        self.gaze_span = 0.70   # これだけ傾けたら振り切る(G)。実測 2.5G 振れた
        self.gaze_lag = 0.18    # 0に近いほど遅れて追いつく（慣性が出る）
        # 実機で確かめて反転（2026-09-26）。傾けた側に目が寄るのが自然だった
        self.gaze_sign_h = -1
        self.gaze_sign_v = -1
        self.gaze_h = 0.0
        self.gaze_v = 0.0
        self.gx = self.gy = 0
        self._base = None
        self.recenter()

        self.oy = 0
        self.open_ratio = 1.0
        self.mouth_open = None           # None なら表情の既定値
        self.name = 'idle'

        self._next_blink = time.ticks_add(time.ticks_ms(), 2000)

    # --- 視線 ------------------------------------------------------
    def recenter(self):
        """いまの姿勢を「まっすぐ前を見ている」ことにする。"""
        try:
            ax = ay = 0.0
            for _ in range(8):
                a = M5.Imu.getAccel(); ax += a[0]; ay += a[1]
                time.sleep_ms(10)
            self._base = (ax / 8, ay / 8)
        except Exception:
            self._base = (0.0, 0.0)
        self.gaze_h = self.gaze_v = 0.0
        self.gx = self.gy = 0
        return self._base

    def tick_gaze(self, now):
        if not self.gaze_px or self._base is None:
            return
        try:
            a = M5.Imu.getAccel()
        except Exception:
            return
        s = self.gaze_span
        th = max(-1.0, min(1.0, (a[0] - self._base[0]) / s)) * self.gaze_sign_h
        tv = max(-1.0, min(1.0, (a[1] - self._base[1]) / s)) * self.gaze_sign_v
        # 一次遅れ。すぐ追従させると機械に見える。遅れるから目に見える
        self.gaze_h += (th - self.gaze_h) * self.gaze_lag
        self.gaze_v += (tv - self.gaze_v) * self.gaze_lag
        gx = int(round(self.gaze_h * self.gaze_px))
        gy = int(round(self.gaze_v * self.gaze_px))
        if gx == self.gx and gy == self.gy:
            return
        self.gx, self.gy = gx, gy
        self.render()

    # --- 部品 -----------------------------------------------------
    def _eye(self, cx, cy, is_left, ratio, expr, grow):
        g = self.g
        rx = ry = self.eye_r * grow

        if ratio == 0 or expr == 'sleepy':
            hh = max(2, int(4 * K * (self.eye_r / 8.0)) // 2)
            g.fillRect(int(cx - rx), int(cy - hh + ry / 2),
                       int(rx * 2), int(hh * 2), WHITE)
            return

        if expr == 'happy':
            # 楕円2枚と長方形で上向きの弧を削り出す（Eyes.cpp の happy 分岐）
            base_y = cy + ry / 2
            th = rx / 2
            g.fillEllipse(int(cx), int(base_y), int(rx), int(ry / 2 + th), WHITE)
            g.fillEllipse(int(cx), int(base_y + th), int(rx - th),
                          int(ry / 2 + th), BG)
            g.fillRect(int(cx - rx), int(base_y + th / 2), int(rx * 2 + 1),
                       int(ry / 2 + th / 2 + 3), BG)
            return

        ry_now = max(1, int(ry * ratio))
        g.fillEllipse(int(cx), int(cy), int(rx), ry_now, WHITE)

        # 瞳。白目は動かさず瞳だけ動かすほうが「見ている」が読み取りやすい。
        # 目そのものの移動（gaze_px）と足し合わせず、内側の余白いっぱいを使う。
        pr = self.pupil_r
        if pr and ry_now > pr:
            room_x = int(rx) - pr - 1
            room_y = ry_now - pr - 1
            g.fillEllipse(int(cx + self.gaze_h * room_x),
                          int(cy + self.gaze_v * room_y),
                          pr, min(pr, ry_now - 1), BG)

        x0, x1 = int(cx - rx), int(cx + rx)
        y0 = int(cy - ry_now)
        ymid = int(cy - ry_now / 2)
        if expr == 'angry':
            g.fillTriangle(x0, y0, x1, y0, x0 if is_left else x1, ymid, BG)
        elif expr == 'sad':
            g.fillTriangle(x0, y0, x1, y0, x1 if is_left else x0, ymid, BG)
        elif expr == 'doubt':
            g.fillRect(x0, y0, x1 - x0, ymid - y0, BG)

    def _mouth(self, open_ratio):
        k = self.mouth_k
        h = (M_MIN_H + (M_MAX_H - M_MIN_H) * open_ratio) * k
        w = (M_MIN_W + (M_MAX_W - M_MIN_W) * (1 - open_ratio)) * k
        cx = self.cx + 2                 # 本家の口は中心から 3px 右（320基準）
        self.g.fillRect(int(cx - w / 2), int(self.mouth_y + self.oy - h / 2),
                        max(1, int(w)), max(1, int(h)), WHITE)

    def _blush(self):
        ew = self.eye_r * 2
        rx, ry = int(ew * 0.66), int(ew * 0.40)
        for dx, sx in ((-self.eye_dx, -1), (self.eye_dx, +1)):
            cx = self.cx + dx + sx * ew * 1.25
            cy = self.eye_y + ew * 0.9 + self.oy
            self.g.fillEllipse(int(cx), int(cy), rx, ry, BLUSH)

    def _mark(self, kind):
        if not kind:
            return
        g = self.g
        x, y = int(0.85 * self.w), int(0.23 * self.h)
        r = int(0.062 * self.w)
        if kind == 'heart':
            g.fillCircle(x - r // 2, y, r // 2, WHITE)
            g.fillCircle(x + r // 2, y, r // 2, WHITE)
            a = (math.sqrt(2) * r) / 4.0
            g.fillTriangle(x, y, int(x - r / 2 - a), int(y + a),
                           int(x + r / 2 + a), int(y + a), WHITE)
            g.fillTriangle(x, int(y + r / 2 + 2 * a), int(x - r / 2 - a),
                           int(y + a), int(x + r / 2 + a), int(y + a), WHITE)
        elif kind == 'sweat':
            g.fillCircle(x, y, r, WHITE)
            a = (math.sqrt(3) * r) / 2
            g.fillTriangle(x, int(y - r * 2), int(x - a), int(y - r * 0.5),
                           int(x + a), int(y - r * 0.5), WHITE)
        elif kind == 'anger':
            t = 2
            g.fillRect(int(x - r / 3), y - r, int(r * 2 / 3), r * 2, WHITE)
            g.fillRect(x - r, int(y - r / 3), r * 2, int(r * 2 / 3), WHITE)
            g.fillRect(int(x - r / 3 + t), y - r, int(r * 2 / 3 - t * 2), r * 2, BG)
            g.fillRect(x - r, int(y - r / 3 + t), r * 2, int(r * 2 / 3 - t * 2), BG)
        elif kind == 'chill':
            w = 4
            for dx, kk in ((-r * 0.55, 0.55), (0, 0.8), (r * 0.55, 1.0)):
                g.fillRect(int(x + dx - w / 2), y, w, int(r * kk * 1.6), WHITE)
        elif kind == 'bubble':
            g.drawCircle(x, y, r, WHITE)
            g.drawCircle(int(x - r / 2), int(y - r / 2), max(2, r // 4), WHITE)

    # --- 1枚描いて転送する -----------------------------------------
    def render(self):
        expr, m_open, mark, blush, grow = TABLE[self.name]
        g = self.g
        g.fillScreen(BG)
        y = self.eye_y + self.oy + self.gy
        self._eye(self.cx - self.eye_dx + self.gx, y,     False, self.open_ratio, expr, grow)
        self._eye(self.cx + self.eye_dx + self.gx, y + 2, True,  self.open_ratio, expr, grow)
        self._mouth(m_open if self.mouth_open is None else self.mouth_open)
        if blush:
            self._blush()                # 目の後。笑い目の削り(黒)に貫かれない
        self._mark(mark)
        if self.pinned:
            g.fillCircle(self.w - 6, self.h - 6, 3, WHITE)
        self.cv.push(0, 0)

    def set(self, name):
        if name not in TABLE:
            raise ValueError(name)
        self.name = name
        self.open_ratio = 1.0
        self.mouth_open = None
        self.render()

    # --- まばたき --------------------------------------------------
    def blink(self):
        if TABLE[self.name][0] in ('happy', 'sleepy'):
            return               # 弧の目・横棒の目は閉じても変化が見えない
        seq = [(0.65, 30), (0.3, 30), (0.0, 70), (0.3, 30), (0.65, 30), (1.0, 0)]
        if random.randint(0, 4) == 0:                 # たまに二度瞬き
            seq += [(1.0, 120), (0.3, 25), (0.0, 60), (0.3, 25), (1.0, 0)]
        for r, ms in seq:
            self.open_ratio = r
            self.render()
            if ms:
                time.sleep_ms(ms)

    def tick_blink(self, now):
        if time.ticks_diff(now, self._next_blink) < 0:
            return
        self.blink()
        self._next_blink = time.ticks_add(
            now, random.randint(self.blink_min, self.blink_max))

    # --- 呼吸 ------------------------------------------------------
    # 止まっている顔は、止まった瞬間に物になる。ゆっくり上下させるだけで
    # 生き物に見える。本家 Avatar にも breath がある。
    def tick_breath(self, now):
        if not self.breath_px:
            return
        phase = (now % self.breath_ms) / self.breath_ms
        oy = int(round(math.sin(phase * 6.283185) * self.breath_px))
        if oy == self.oy:
            return
        self.oy = oy
        self.render()

    # --- 音 --------------------------------------------------------
    # tone は非同期（1msで戻る）。長さぶん自分で待つと音が繋がる。
    def tone(self, *notes):
        """(周波数Hz, 長さms) の並び。周波数0は休符。消音中は何もしない。"""
        if not self.sound:
            return
        try:
            M5.Speaker.setVolume(self.volume)
            for hz, ms in notes:
                if hz:
                    M5.Speaker.tone(hz, ms)
                time.sleep_ms(ms)
        except Exception:
            pass

    def _sound_badge(self, on):
        """音の入切を目で見せる。聞こえない状態の切り替えは、音では伝えられない。"""
        g = self.g
        x, y = 8, self.h - 10
        if on:
            for i, hgt in enumerate((4, 7, 10)):
                g.fillRect(x + i * 5, y - hgt, 3, hgt, WHITE)
        else:
            g.fillRect(x, y - 4, 3, 4, WHITE)
            for i in range(9):
                g.fillRect(x + 4 + i, y - 4 - i, 2, 2, WHITE)
        self.cv.push(0, 0)
        time.sleep_ms(800)
        self.render()

    def toggle_sound(self):
        if self.sound:
            self.tone((880, 70), (440, 110))    # 切る前に鳴らす。切った後では聞こえない
            self.sound = False
        else:
            self.sound = True
            self.tone((440, 70), (880, 110))
        self._sound_badge(self.sound)
        return self.sound

    # --- 振られた／伏せられた --------------------------------------
    def dizzy(self):
        """目を回す。振り回されたときの反応。"""
        back = self.name
        self.name = 'surprised'
        self.tone((880, 60), (740, 60), (620, 60), (520, 60), (440, 90))
        _buzz((200, 80), (0, 40), (200, 80))
        for i in range(14):
            a = i / 14.0 * 6.283185 * 2          # 2周まわす
            self.gaze_h = math.cos(a)
            self.gaze_v = math.sin(a)
            self.gx = int(self.gaze_h * self.gaze_px)
            self.gy = int(self.gaze_v * self.gaze_px)
            self.render()
            time.sleep_ms(55)
        self.gaze_h = self.gaze_v = 0.0
        self.gx = self.gy = 0
        self.set('thinking')                      # くらくらの余韻
        time.sleep_ms(700)
        self.set('idle' if back == 'surprised' else back)
        self._next_blink = time.ticks_add(time.ticks_ms(), 1000)

    def tick_shake(self, now):
        """回転の速さで「乱暴に振られた」を拾う。

        ★傾き（加速度）だけでは、ゆっくり傾けたのか振り回したのか分からない。
          ジャイロは回転の速さそのものなので、そこが区別できる。
        """
        if not self.shake_dps:
            return False
        try:
            g = M5.Imu.getGyro()
        except Exception:
            return False
        if abs(g[0]) + abs(g[1]) + abs(g[2]) < self.shake_dps:
            return False
        self.dizzy()
        return True

    def tick_pose(self, now):
        """伏せたら寝る。3分待たずに「しまった」を表現できる。"""
        if not self.facedown_z:
            return
        try:
            z = M5.Imu.getAccel()[2]
        except Exception:
            return
        if z < self.facedown_z:
            if self._down_since is None:
                self._down_since = now
            elif not self.asleep and \
                    time.ticks_diff(now, self._down_since) > self.facedown_ms:
                self._slept_by_pose = True
                self.sleep()
        else:
            self._down_since = None
            if self.asleep and self._slept_by_pose and z > 0.3:
                self._slept_by_pose = False
                self.wake()

    # --- 声を聞く（押している間だけ）--------------------------------
    # ★常時マイクを回さない。電池を食ううえ、周囲の会話を拾い続けることになる。
    #   聞いている間は画面に印を出す。録っていることが見えない録音はしない。
    def listen(self, held):
        try:
            M5.Speaker.end()          # I2S を明け渡す
            M5.Mic.begin()
        except Exception:
            return
        buf = bytearray(512)
        floor = None
        try:
            for i in range(3):        # begin 直後の数発はゴミ（実測 RMS 25904）
                M5.Mic.record(buf, 16000)
                time.sleep_ms(30)
            while held():
                M5.Mic.record(buf, 16000)
                time.sleep_ms(25)
                s = 0
                for j in range(0, 512, 2):
                    v = buf[j] | (buf[j + 1] << 8)
                    if v > 32767:
                        v -= 65536
                    s += v * v
                rms = (s / 256) ** 0.5
                floor = rms if floor is None else min(floor * 1.02 + 1, rms * 0.9 + floor * 0.1)
                # 静けさからの差で口を開く。環境が変わっても効く
                self.mouth_open = max(0.0, min(1.0, (rms - floor) / 900.0))
                self.render()
                self._mic_badge()
        finally:
            try:
                M5.Mic.end()
                M5.Speaker.begin()
            except Exception:
                pass
            self.mouth_open = None
            self.render()

    def _mic_badge(self):
        self.g.fillCircle(10, 10, 4, 0xFF4444)
        self.cv.push(0, 0)

    # --- 眠くなる ---------------------------------------------------
    # ★いきなり真っ暗になると「壊れた」に見える。眠る過程を見せておけば
    #   同じ消灯が「寝た」に見える。機能ではなく期待値の設計。
    def yawn(self):
        self.tone((330, 220), (294, 260))              # ふぁ〜（下がる）
        back = self.mouth_open
        for o, e in ((0.25, 0.8), (0.55, 0.5), (0.85, 0.25), (1.0, 0.15)):
            self.mouth_open = o
            self.open_ratio = e
            self.render()
            time.sleep_ms(95)
        time.sleep_ms(280)
        for o, e in ((0.8, 0.3), (0.45, 0.6), (0.15, 0.9), (0.0, 1.0)):
            self.mouth_open = o
            self.open_ratio = e
            self.render()
            time.sleep_ms(85)
        self.mouth_open = back
        self.open_ratio = 1.0
        self.render()

    def tick_batt(self):
        """残量を表情に出す。数字を見せるより、様子で気づいてもらう。"""
        try:
            lv = M5.Power.getBatteryLevel()
        except Exception:
            return
        self._batt = self._batt * 0.9 + lv * 0.1     # %は電圧推定でノイズが大きい
        return self._batt

    def _weary(self):
        """電池が少ないときの重さ。1.0=ふつう、大きいほどだるい。"""
        if self._batt >= self.low_batt:
            return 1.0
        return 1.0 + (self.low_batt - self._batt) / self.low_batt

    def set_drowsy(self, level):
        if level == self.drowsy:
            return
        self.drowsy = level
        if level == 0:
            w = self._weary()
            self.blink_min = int(1800 * w)
            self.blink_max = int(5200 * w)
            if self._awake_name:
                name, self._awake_name = self._awake_name, None
                self.set(name)
            return
        if self._awake_name is None:
            self._awake_name = self.name
        if level == 1:
            w = self._weary()
            self.blink_min, self.blink_max = int(900 * w), int(2400 * w)
            self.yawn()
        elif level == 2:
            self.set('sleepy')

    # --- 省電力 ----------------------------------------------------
    # バックライトを落とすだけ。ディープスリープだと復帰が再起動になり、
    # 押してから顔が出るまで待たされる。「押したらすぐ戻る」を優先した。
    def _fade(self, frm, to, ms=600):
        steps = 12
        for i in range(steps + 1):
            M5.Lcd.setBrightness(int(frm + (to - frm) * i / steps))
            time.sleep_ms(ms // steps)

    def sleep(self):
        if self.asleep:
            return
        self.bright = M5.Lcd.getBrightness() or self.bright
        self.tone((392, 140), (294, 200))              # おやすみ
        self.open_ratio = 0.0            # 目を閉じてから暗くする
        self.render()
        time.sleep_ms(320)
        self._fade(self.bright, 0)
        M5.Lcd.fillScreen(BG)
        self.asleep = True
        self._slept_at = time.ticks_ms()

    def wake(self):
        if not self.asleep:
            return
        self.asleep = False
        M5.Lcd.setBrightness(0)
        self.set_drowsy(0)               # 表情を戻す
        self.open_ratio = 1.0
        self.render()                    # 真っ暗のうちに描いてから明るくする
        self.tone((523, 90), (784, 130))               # おはよう
        self._fade(0, self.bright)
        self._next_blink = time.ticks_add(time.ticks_ms(), 900)
        # ★「前回会ってから」は測れない。RTC は電源を切ると 1970 に戻るため。
        #   代わりに「寝ていた時間」を見る。鞄の中で何時間も寝て取り出される
        #   のが実際の場面で、その間は通電したままなので正確に測れる。
        if self._slept_at is not None:
            slept = time.ticks_diff(time.ticks_ms(), self._slept_at)
            self._slept_at = None
            if slept > self.longsleep_ms:
                time.sleep_ms(250)
                self.tone((523, 80), (659, 80), (784, 80), (1047, 180))
                self.rejoice(vibrate=True)

    # --- モーション ------------------------------------------------
    def rejoice(self, vibrate=True):
        back = self.name
        self.set('happy')
        self.tone((660, 70), (880, 70), (1320, 130))   # 上がる3音
        if vibrate:
            _buzz((180, 90), (0, 60), (180, 90))
        for o in (0.30, 0.55, 0.30, 0.50, 0.30):
            self.mouth_open = o
            self.render()
            time.sleep_ms(95)
        time.sleep_ms(520)
        self.set('idle' if back == 'happy' else back)
        self._next_blink = time.ticks_add(time.ticks_ms(), 1200)

    def be_shy(self, vibrate=True):
        back = self.name
        self.name = 'embarrassed'
        self.open_ratio = 1.0
        self.mouth_open = 0.18
        self.render()
        self.tone((1180, 60), (990, 60), (1320, 90))   # ひゅるっ
        time.sleep_ms(160)
        if vibrate:
            _buzz((110, 140),)
        for o in (0.18, 0.30, 0.18):
            self.mouth_open = o
            self.render()
            time.sleep_ms(150)
        time.sleep_ms(900)
        self.set('idle' if back == 'embarrassed' else back)
        self._next_blink = time.ticks_add(time.ticks_ms(), 1200)


def _buzz(*steps):
    """(強さ, 保持ms) の並び。バイブが無い個体でも落ちない。"""
    try:
        for level, ms in steps:
            M5.Power.setVibration(level)
            if ms:
                time.sleep_ms(ms)
        M5.Power.setVibration(0)
    except Exception:
        pass


def _log(f, t0):
    """電池の記録を1行足す。1分に1回なのでフラッシュの摩耗は問題にならない。

    ★持ち出し中は Mac に繋がっていない。実機に残さないと測定そのものが消える。
    """
    try:
        with open('/flash/battery.csv', 'a') as fp:
            fp.write('%d,%d,%d,%d,%d,%s\n' % (
                time.ticks_diff(time.ticks_ms(), t0) // 1000,
                M5.Power.getBatteryVoltage(), M5.Power.getBatteryLevel(),
                1 if f.asleep else 0, 1 if f.pinned else 0, f.name))
    except Exception:
        pass


# --- 出しっぱなしで回す ---------------------------------------------
# ボタン（実機で確認: BtnA=正面の青 / BtnB=右側 / 左側はリセット）
#   青 シングル   … 寝ていれば起こす。起きていれば喜ぶ
#   青 ダブル     … 固定モードの入切（固定中は消灯しない）
#   青 長押し     … 音の入切
#   右 シングル   … 表情を巡回
#   右 ダブル     … 恥ずかしがる
#   右 長押し     … 押している間だけ声を聞いて口が動く（離すと止まる）
#
# 触らなくても反応するもの
#   傾ける        … 目がそちらへ寄る（遅れて追いつく）
#   速く振る      … 目を回す（ジャイロ。ゆっくり傾けるのとは別物）
#   画面を伏せる  … 1.2秒で寝る。戻すと起きる
#   放置          … 6割であくび、8.5割でうとうと、満了で暗転
#   電池が減る    … まばたきが重くなり、早く眠くなる
#   長く寝たあと  … 起こされると喜ぶ
_running = False
_face = None

def _loop():
    f = _face
    idx = 0
    last_active = t0 = next_log = time.ticks_ms()
    next_slow = t0                      # 重い見張りは間引く
    while _running:
        M5.update()
        now = time.ticks_ms()
        acted = False

        if M5.BtnA.wasHold():                 # 青 長押し → 音の入切
            if f.asleep:
                f.wake()
            f.toggle_sound()
            acted = True
        elif M5.BtnA.wasDoubleClicked():      # 青 ダブル → 固定モード
            f.pinned = not f.pinned
            if f.asleep:
                f.wake()
            else:
                f.render()
            if f.pinned:
                _buzz((150, 60),)
            acted = True
        elif M5.BtnA.wasSingleClicked():      # 青 シングル
            if f.asleep:
                f.wake()      # 寝ていたときは起こすだけ。いきなり喜ばない
            else:
                f.rejoice()
            acted = True
        elif M5.BtnB.wasHold():               # 右 長押し → 押している間だけ聞く
            if f.asleep:
                f.wake()
            f.listen(lambda: M5.update() or M5.BtnB.isPressed())
            acted = True
        elif M5.BtnB.wasDoubleClicked():      # 右 ダブル → 恥ずかしがる
            if f.asleep:
                f.wake()
            else:
                f.be_shy()
            acted = True
        elif M5.BtnB.wasSingleClicked():      # 右 シングル → 表情を巡回
            if f.asleep:
                f.wake()
            else:
                idx = (idx + 1) % len(ORDER)
                f.set(ORDER[idx])
            acted = True

        if acted:
            last_active = now
            f.set_drowsy(0)

        if f.log_every_ms and time.ticks_diff(now, next_log) >= 0:
            _log(f, t0)
            next_log = time.ticks_add(now, f.log_every_ms)

        # 姿勢と電池は毎回見なくていい。500ms に1回で足りる
        if time.ticks_diff(now, next_slow) >= 0:
            next_slow = time.ticks_add(now, 500)
            f.tick_batt()
            f.tick_pose(now)

        if f.asleep:
            time.sleep_ms(120)       # 寝ている間は見張りをゆっくりにする
            continue

        if not f.pinned and f.tick_shake(now):    # 振られたら目を回す
            last_active = now
            continue

        idle_ms = time.ticks_diff(now, last_active)
        if f.pinned:
            f.set_drowsy(0)
        elif idle_ms > f.idle_timeout_ms:
            f.sleep()
            continue
        elif idle_ms > f.idle_timeout_ms * 85 // 100:
            f.set_drowsy(2)
        elif idle_ms > f.idle_timeout_ms * 60 // 100:
            f.set_drowsy(1)
        else:
            f.set_drowsy(0)

        f.tick_blink(now)
        f.tick_breath(now)
        f.tick_gaze(now)
        time.sleep_ms(20)

def start(timeout_s=180, log_every_s=0):
    global _running, _face
    stop()
    import _thread
    _face = Face()
    for b in (M5.BtnA, M5.BtnB):
        b.setHoldThresh(700)         # 既定だと長すぎて気づけない
    _face.idle_timeout_ms = int(timeout_s * 1000)
    _face.log_every_ms = int(log_every_s * 1000)
    _face.tick_batt()
    _face.set('idle')
    _running = True
    _thread.start_new_thread(_loop, ())
    return _face

def stop():
    global _running
    if _running:
        _running = False
        time.sleep_ms(200)
    return 'stopped'
