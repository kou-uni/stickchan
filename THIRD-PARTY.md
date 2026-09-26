# サードパーティの表示 / Third-party notices

このリポジトリは MIT ライセンスで配布しています。
**他の MIT 成果物に由来する部分**を含むので、その著作権表示を保持します。

This repository is distributed under the MIT License. It contains portions
derived from other MIT-licensed works, whose copyright notices are retained
below.

---

## 1. `face.py` — m5stack-avatar からの移植

`face.py` の顔の形（目・口・漫画マークの描き方）は
[m5stack-avatar](https://github.com/meganetaaan/m5stack-avatar) の
`src/Eyes.cpp` / `src/Mouths.cpp` / `src/Effect.h` を
320x240 基準の寸法ごと移植したものです。

- 楕円を2枚と長方形で削り出す「上向きの弧」の笑い目
- 長方形の口（開くほど細く高くなる。閉 90x4 → 開 50x60）
- ハート / 汗 / 井桁 / 落ち込み線 / 泡 の各マーク
- 左右の目の高さを 3px ずらす非対称

```
MIT License

Copyright (c) 2019 Shinya Ishikawa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 2. `boot.py` — UiFlow2 の boot.py に追記したもの

`boot.py` は M5Stack の UiFlow2 ファームウェアに同梱されている
`/flash/boot.py` に、顔を起動するブロックを**差し込んだもの**です。
元ファイルの SPDX ヘッダをそのまま残しています。

```
SPDX-FileCopyrightText: 2024 M5Stack Technology CO LTD
SPDX-License-Identifier: MIT
```

差し込んだのは冒頭の `_ministack` ブロックだけで、
それ以外は M5Stack の原文のままです。
