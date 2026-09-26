# ミニスタックちゃん — 電源を入れたら顔を出す
#
# これは UiFlow2 の /flash/main.py を置き換えたもの。
# boot.py の boot_option を 0（main.py を直接実行）にしてある。
#
# ★UiFlow2 のランチャーに戻す方法（2つある）
#   1) 正面の青ボタンを押しながらリセット   ← boot.py が用意している物理的な逃げ道
#   2) REPL から:
#        import esp32
#        nvs = esp32.NVS('uiflow'); nvs.set_u8('boot_option', 1); nvs.commit()
#
# 顔が例外で落ちても REPL は残す。文鎮にしないことを最優先にする。
try:
    import face
    # boot.py が先に起こしているのが普通。二重に start すると顔が一瞬消える
    if not face._running:
        face.start(timeout_s=180, log_every_s=60)
except Exception as e:
    try:
        import M5
        M5.begin()
        M5.Lcd.setRotation(1)
        M5.Lcd.fillScreen(0x000000)
        M5.Lcd.setTextColor(0xFFFFFF)
        M5.Lcd.setTextSize(2)
        M5.Lcd.setCursor(4, 4)
        M5.Lcd.print('face NG')
    except Exception:
        pass
    import sys
    sys.print_exception(e)
