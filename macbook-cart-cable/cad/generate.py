"""MacBook充電保管庫のケーブル整理パーツ生成スクリプト

生成する部品
  - cable_gauge      : ケーブル径を実物で確かめるゲージ（最初に1枚だけ印刷）
  - stopper_half     : 前面の既存クリップの前後を挟んでケーブルの前後移動を止める半割ストッパー
                       （同じ部品2個＋結束バンド1本で1組）
  - slack_holder     : 背面で余ったケーブルを2本のフックに掛けて収納するホルダー

使い方
  pip install manifold3d numpy matplotlib
  python3 cad/generate.py            # stl/ 以下を全部作り直す

寸法の単位はすべて mm。ケーブル径 d ごとに stl/d<径>/ へ出力する。
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

import numpy as np
from manifold3d import CrossSection, FillRule, JoinType, Manifold

SEG = 72  # 円の分割数

ROOT = Path(__file__).resolve().parent.parent
STL_DIR = ROOT / "stl"

# ゲージのスロット幅とSTLを出力するケーブル径（同じ刻みにして「ゲージの数字＝フォルダ名」にする）
CABLE_SIZES = [round(3.4 + 0.2 * i, 1) for i in range(11)]  # 3.4 〜 5.4


# ---------------------------------------------------------------- 共通ヘルパー

def extrude_xz(cs: CrossSection, y0: float, y1: float) -> Manifold:
    """XZ平面の断面 cs を Y方向 [y0, y1] に押し出す。"""
    m = cs.extrude(y1 - y0)            # (u, v, w) w∈[0, L]
    m = m.rotate((90.0, 0.0, 0.0))      # -> (u, -w, v)
    return m.translate((0.0, y1, 0.0))


def cyl_y(r: float, y0: float, y1: float, x: float = 0.0, z: float = 0.0,
          r1: float | None = None) -> Manifold:
    """Y軸方向の円柱（r1 を与えると y0側 r → y1側 r1 の円錐台）。"""
    r1 = r if r1 is None else r1
    m = Manifold.cylinder(y1 - y0, r, r1, SEG)  # Z方向 [0, h]
    m = m.rotate((-90.0, 0.0, 0.0))              # (x,y,z) -> (x, z, -y): Z+ が Y+ へ
    return m.translate((x, y0, z))


def cyl_z(r: float, z0: float, z1: float, x: float = 0.0, y: float = 0.0,
          r1: float | None = None) -> Manifold:
    r1 = r if r1 is None else r1
    return Manifold.cylinder(z1 - z0, r, r1, SEG).translate((x, y, z0))


def box(x0, x1, y0, y1, z0, z1) -> Manifold:
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def rect2(x0, x1, y0, y1) -> CrossSection:
    return CrossSection.square((x1 - x0, y1 - y0)).translate((x0, y0))


def rounded_rect2(w: float, h: float, r: float) -> CrossSection:
    """中心原点の角丸長方形。"""
    return CrossSection.square((w - 2 * r, h - 2 * r), center=True).offset(
        r, JoinType.Round, 2.0, SEG)


def text2(s: str, size: float, cx: float, cy: float, rot_deg: float = 0.0,
          mirror_x: bool = False) -> CrossSection:
    """文字列の2D形状（中心 (cx, cy)）。matplotlib のフォントアウトラインを使う。"""
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath

    tp = TextPath((0, 0), s, size=size,
                  prop=FontProperties(family="DejaVu Sans", weight="bold"))
    polys = [np.asarray(p, dtype=float) for p in tp.to_polygons(closed_only=True)]
    polys = [p[:-1] if np.allclose(p[0], p[-1]) else p for p in polys]
    cs = CrossSection(polys, FillRule.EvenOdd)
    (x0, y0), (x1, y1) = np.asarray(cs.bounds()).reshape(2, 2)
    cs = cs.translate((-(x0 + x1) / 2, -(y0 + y1) / 2))
    if mirror_x:
        cs = cs.mirror((1.0, 0.0))
    if rot_deg:
        cs = cs.rotate(rot_deg)
    return cs.translate((cx, cy))


def write_stl(m: Manifold, path: Path, name: str) -> None:
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties, dtype=np.float32)[:, :3]
    t = np.asarray(mesh.tri_verts, dtype=np.int64)
    tri = v[t]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = np.zeros(len(t), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"] = n
    rec["v"] = tri
    with open(path, "wb") as f:
        f.write(name.encode("ascii")[:80].ljust(80, b" "))
        f.write(struct.pack("<I", len(t)))
        f.write(rec.tobytes())


def drop_to_bed(m: Manifold) -> Manifold:
    (x0, y0, z0, x1, y1, z1) = m.bounding_box()
    return m.translate((-(x0 + x1) / 2, -(y0 + y1) / 2, -z0))


# ---------------------------------------------------------------- 1. ケーブル径ゲージ

def cable_gauge(sizes=CABLE_SIZES) -> Manifold:
    """縁から切り込んだU字スロット。ケーブルを横から押し込んで径を確かめる。"""
    pitch, t, depth, height, emboss = 9.5, 3.0, 10.0, 26.0, 0.6
    n = len(sizes)
    length = n * pitch + 8.0
    plate = rounded_rect2(length, height, 3.0).translate((length / 2, height / 2))
    cut = CrossSection()
    labels = CrossSection()
    for i, s in enumerate(sizes):
        cx = 4.0 + pitch * (i + 0.5)
        straight = depth - s / 2
        cut += rect2(cx - s / 2, cx + s / 2, -1.0, straight)
        cut += CrossSection.circle(s / 2, SEG).translate((cx, straight))
        # 入口の面取り
        cut += CrossSection([np.array([[cx - s / 2 - 0.7, -0.01], [cx + s / 2 + 0.7, -0.01],
                                       [cx + s / 2, 0.7], [cx - s / 2, 0.7]])])
        labels += text2(f"{s:.1f}", 3.6, cx, depth + 4.2)
    labels += text2("MagSafe cable gauge  [mm]", 3.4, length / 2, height - 5.0)
    body = (plate - cut).extrude(t)
    return body + labels.extrude(emboss).translate((0, 0, t))


# ---------------------------------------------------------------- 2. 半割ストッパー

STOPPER = dict(
    L=12.0,          # ケーブル方向の長さ
    W=17.0,          # 幅（既存クリップの穴より十分大きくする）
    H=7.0,           # 半割1個の高さ（2個合わせて14mm）
    rc=3.0,          # 外側の角R
    clearance=0.15,  # 穴の半径方向すき間
    rib_h=0.4,       # 内側リブの高さ（ケーブルに食い込ませて滑り止め）
    rib_w=1.2,
    rib_ys=(-3.8, 0.0, 3.8),
    groove_w=3.8,    # 結束バンド溝（2.5〜3.6mm幅のバンド用）
    groove_d=1.3,
    pin_r=1.2, pin_h=1.8, hole_r=1.45, hole_h=2.4,
    pin_x=5.6, pin_y=3.3,
    chamfer=0.7,     # 穴の出入口の面取り（ケーブルに角を当てない）
)


def stopper_half(d: float, p=STOPPER) -> Manifold:
    """割り面を上にして印刷する向きでモデル化（割り面 z=H、ケーブル軸はY）。

    もう1個を裏返して重ねるとピンと穴が噛み合う（2個とも同じSTL）。
    """
    L, W, H, rc = p["L"], p["W"], p["H"], p["rc"]
    rb = d / 2 + p["clearance"]

    def profile(inset: float) -> CrossSection:
        w = W - 2 * inset
        r = max(rc - inset, 0.4)
        top = H + 2.0
        cs = rect2(-w / 2, w / 2, inset + r, top)
        cs += rect2(-w / 2 + r, w / 2 - r, inset, top)
        for sx in (-1, 1):
            cs += CrossSection.circle(r, SEG).translate((sx * (w / 2 - r), inset + r))
        return cs

    outer = profile(0.0) ^ rect2(-W, W, -1.0, H)
    body = extrude_xz(outer, -L / 2, L / 2)

    # 結束バンド溝（底面と両側面をぐるっと一周）
    gw = p["groove_w"]
    body -= extrude_xz(profile(0.0) - profile(p["groove_d"]), -gw / 2, gw / 2)

    # ケーブル穴（半円溝）＋出入口の面取り
    c = p["chamfer"]
    body -= cyl_y(rb, -L / 2 - 1, L / 2 + 1, z=H)
    body -= cyl_y(rb + c + 1.0, -L / 2 - 1.0, -L / 2 + c, z=H, r1=rb)
    body -= cyl_y(rb, L / 2 - c, L / 2 + 1.0, z=H, r1=rb + c + 1.0)

    # 内側リブ
    ring = cyl_y(rb + 0.05, -L, L, z=H) - cyl_y(rb - p["rib_h"], -L, L, z=H)
    for y in p["rib_ys"]:
        body += ring ^ box(-W, W, y - p["rib_w"] / 2, y + p["rib_w"] / 2, 0, H)

    # 位置合わせピンと穴（対角配置で、180°回した相手と噛み合う）
    px, py = p["pin_x"], p["pin_y"]
    pr, ph = p["pin_r"], p["pin_h"]
    for sx, sy in ((1, 1), (-1, -1)):
        body += cyl_z(pr, H - 0.01, H + ph - 0.4, sx * px, sy * py)
        body += cyl_z(pr, H + ph - 0.4, H + ph, sx * px, sy * py, r1=pr - 0.4)
    for sx, sy in ((-1, 1), (1, -1)):
        body -= cyl_z(p["hole_r"], H - p["hole_h"], H + 0.1, sx * px, sy * py)
        body -= cyl_z(p["hole_r"] + 0.3, H - 0.3, H + 0.01, sx * px, sy * py,
                      r1=p["hole_r"] + 0.6)
    return body


# ---------------------------------------------------------------- 3. 余長ホルダー

HOLDER = dict(
    D=70.0,       # 上下フックの中心間距離（1周 ≒ 2D + 2π(rh + d/2)）
    rh=7.5,       # フック外半径（ケーブルの曲げ半径 ≒ rh + d/2 ≒ 9.5mm）
    hh=34.0,      # フック高さ（プレート上面から）。d=4.4〜5.0で6周＝約1.2m
    lip=1.8,      # フック先端の返しの張り出し
    tp=3.0,       # プレート厚
    plate_r=5.0,
    anchor_len=10.0,
    anchor_gap=2.0,
    anchor_wall=1.2,
    anchor_open=0.84,  # 固定クリップの開口 = d × これ（壁の曲げひずみ約2.5%）
    margin=1.5,
    slot=(4.4, 2.2),   # 結束バンド/面ファスナー用スリット
    slot_y=13.0,
)


def _dshape(yc: float, outward: int, R: float, flat: float = 3.0) -> CrossSection:
    """外側が半円、内側が平らなD字形（凸形状）。"""
    a = np.linspace(0, math.pi, SEG // 2 + 1)
    arc = np.stack([R * np.cos(a), outward * R * np.sin(a)], axis=1)
    pts = np.vstack([arc, [[-R, -outward * flat], [R, -outward * flat]]])
    if outward < 0:
        pts = pts[::-1]
    return CrossSection([pts]).translate((0.0, yc))


def slack_holder(d: float, p=HOLDER) -> Manifold:
    D, rh, hh, tp = p["D"], p["rh"], p["hh"], p["tp"]
    la, gap, margin = p["anchor_len"], p["anchor_gap"], p["margin"]
    pw = 2 * rh + 2.0
    half = D / 2 + rh + gap + la + margin

    body = rounded_rect2(pw, 2 * half, p["plate_r"]).extrude(tp)

    # フック（根元に補強の面取り、先端に返し）
    top = tp + hh
    lip = p["lip"]
    for s in (1, -1):
        yc = s * D / 2
        body += _dshape(yc, s, rh).extrude(hh + 0.01).translate((0, 0, tp - 0.01))
        layers = [(_dshape(yc, s, rh + 1.2), tp - 0.01), (_dshape(yc, s, rh), tp + 1.2)]
        body += Manifold.batch_hull([cs.extrude(0.01).translate((0, 0, z)) for cs, z in layers])
        layers = [(_dshape(yc, s, rh), top - 2 * lip), (_dshape(yc, s, rh + lip), top - lip),
                  (_dshape(yc, s, rh + lip), top - lip + 0.4), (_dshape(yc, s, rh + 0.3), top)]
        body += Manifold.batch_hull([cs.extrude(0.01).translate((0, 0, z - 0.01))
                                     for cs, z in layers])

    # 両端のケーブル固定クリップ（上から押し込むとパチッと入る）
    cw = d + 0.3
    tw = p["anchor_wall"]
    lp = (cw - p["anchor_open"] * d) / 2
    z0 = tp + d + 0.2
    post = CrossSection([np.array([
        [cw / 2, tp - 0.01], [cw / 2 + tw, tp - 0.01], [cw / 2 + tw, z0 + lp],
        [cw / 2, z0 + lp], [cw / 2 - lp, z0], [cw / 2, z0 - lp]])])
    posts = post + post.mirror((1.0, 0.0))
    for s in (1, -1):
        yc = s * (D / 2 + rh + gap + la / 2)
        body += extrude_xz(posts, yc - la / 2, yc + la / 2)

    # 取り付け用スリット（結束バンドや面ファスナーを通す）
    sx, sy = p["slot"]
    for s in (1, -1):
        body -= box(-sx / 2, sx / 2, s * p["slot_y"] - sy / 2, s * p["slot_y"] + sy / 2, -1, tp + 1)

    # 中央にサイズ表示（彫り込み）
    body -= text2(f"{d:.1f}", 4.0, 0.0, 0.0, rot_deg=90).extrude(0.8).translate((0, 0, tp - 0.6))
    return body


# ---------------------------------------------------------------- 出力

def main() -> None:
    parts = {}
    parts["cable_gauge.stl"] = drop_to_bed(cable_gauge())
    for d in CABLE_SIZES:
        tag = f"d{d:.1f}"
        parts[f"{tag}/stopper_half_{tag}.stl"] = drop_to_bed(stopper_half(d))
        parts[f"{tag}/slack_holder_{tag}.stl"] = drop_to_bed(slack_holder(d))

    for rel, m in parts.items():
        assert m.status().name == "NoError", (rel, m.status())
        assert m.genus() >= 0
        write_stl(m, STL_DIR / rel, rel)
        (x0, y0, z0, x1, y1, z1) = m.bounding_box()
        print(f"{rel:42s} {x1 - x0:6.1f} x {y1 - y0:6.1f} x {z1 - z0:5.1f} mm"
              f"  vol {m.volume() / 1000:5.2f} cm3  tris {m.num_tri()}")


if __name__ == "__main__":
    main()
