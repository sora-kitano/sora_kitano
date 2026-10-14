"""MacBook充電保管庫のケーブル整理パーツ生成スクリプト

生成する部品
  - cable_gauge          : ケーブル径を実物で確かめるゲージ（最初に1枚だけ印刷）
  - stopper_front_half   : 既存クリップの「前」に付ける小型ストッパー（同じ部品2個＋2.5mm結束バンド1本で1組）
  - stopper_rear_half    : 既存クリップの「後ろ」に付ける主ストッパー。シリコンチューブを挟み込む
                           （同じ部品2個＋シリコンチューブ19mm＋3.6mm結束バンド2本で1組）
  - stopper_rear_noliner : チューブが手に入らないとき用の後ろストッパー（樹脂リブで直接挟む）
  - slack_holder         : 背面で余ったケーブルを2本のフックに掛けて収納するホルダー
  - slip_test_jig        : 机にクランプして、ストッパーが滑らないかを荷重で確かめる試験板
  - tube_cut_guide       : シリコンチューブを19mmに切りそろえるガイド

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


# ---------------------------------------------------------------- 2. 半割ストッパー（前用・後ろ用）
#
# どちらも「同じ部品2個でケーブルを挟み、溝に結束バンドを巻いて締める」構造。
# 割り面を上（z=H）、ケーブル軸をYにして、印刷する向きでモデル化している。
# ピンと穴は対角に置いてあり、もう1個を裏返して重ねれば（どちら向きに裏返しても）噛み合う。
#
#   前用（STOPPER_FRONT）: 既存クリップの前に付ける小型品。受ける力は余りケーブルの重さ程度（1N未満）。
#   後ろ用（STOPPER_REAR）: クリップの後ろ（庫内側）に付け、MacBookを引き出すときの力をすべて受ける。
#       シリコンチューブ（肉厚1mm、縦に切れ目を入れてケーブルに巻く）を内側のポケットに入れ、
#       半割の合わせ目が閉じた時点でチューブが決まった量（0.25mm）だけ潰れるようにしてある。
#       締め付け力が「結束バンドの締め具合」ではなく「寸法」で決まり、ゴムなので滑りにくく、
#       樹脂や結束バンドが温度で少しずつ緩んでも締め付け力が残りやすい（Oリング溝と同じ考え方）。
#       liner_t=0 にするとチューブなしの代替品（樹脂リブで直接挟む）になる。

STOPPER_FRONT = dict(
    L=12.0, W=17.0, H=7.0,   # ケーブル方向の長さ / 幅 / 半割1個の高さ（合わせて14mm）
    edge=2.5,                # 底側の角の45°面取り（丸めより印刷がきれい）
    lip_clear=0.15,          # ケーブル穴の半径方向すき間（穴径 d+0.3）
    liner_t=0.0, relief_clear=0.15,
    lip_len=0.0,
    squeeze=0.25,            # リブの食い込み（片側）: リブ部の穴径 d-0.5
    rib_w=1.2, rib_ys=(-3.8, 0.0, 3.8),
    seam_chamfer=0.3,        # 割り面の縁の面取り（ケーブルを挟み込んで傷めない）
    groove_w=3.8, groove_d=1.3, groove_ys=(0.0,),   # 結束バンド溝（2.5mm幅のバンド用）
    pin_r=1.2, pin_h=1.8, hole_r=1.45, hole_h=2.4, pin_x=5.6, pin_y=3.3,
    chamfer=0.7,             # ケーブル出入口の面取り
)

STOPPER_REAR = dict(
    L=26.0, W=20.0, H=7.5,   # 組み立て後 26 x 20 x 15 mm
    edge=2.5,
    lip_len=3.0,             # 両端3mmはチューブなしの穴（d+0.3）。チューブの抜け止め
    lip_clear=0.15,
    liner_t=1.0,             # シリコンチューブの肉厚
    relief_clear=0.4,        # リブ間の逃げ（潰れたゴムの行き場。充填率を85%以下に保つ）
    squeeze=0.25,            # 合わせ目が閉じたときのチューブの潰れ量（片側、肉厚の25%）
    rib_w=1.6, rib_ys=(-7.5, -2.5, 2.5, 7.5),
    seam_chamfer=0.3,
    groove_w=4.2, groove_d=1.3, groove_ys=(-7.5, 7.5),  # 3.6mm幅の結束バンド2本（外側リブの真上）
    pin_r=1.2, pin_h=1.8, hole_r=1.45, hole_h=2.4, pin_x=7.0, pin_y=2.8,
    chamfer=0.7,
)

# チューブなしで作る場合の後ろ用（チューブが手に入らないときの代替）
STOPPER_REAR_NOLINER = dict(STOPPER_REAR, liner_t=0.0, relief_clear=0.15)

# ケーブル径（ゲージの読み）→ 使うシリコンチューブ（内径x外径, 肉厚1mm）
def liner_tube_for(d: float) -> str:
    if d <= 4.0 + 1e-9:
        return "3x5"
    if d <= 5.0 + 1e-9:
        return "4x6"
    return "5x7"


def _stopper_profile(p) -> CrossSection:
    """半割の断面（XZ）。底側の角は45°面取り、上（割り面）はそのまま。"""
    W, H, e = p["W"], p["H"], p["edge"]
    top = H + 2.0
    return CrossSection([np.array([
        [-W / 2 + e, 0.0], [W / 2 - e, 0.0], [W / 2, e], [W / 2, top], [-W / 2, top], [-W / 2, e]])])


def stopper_half(d: float, p=STOPPER_FRONT) -> Manifold:
    L, W, H = p["L"], p["W"], p["H"]
    t = p["liner_t"]
    r_lip = d / 2 + p["lip_clear"]                 # 両端（チューブなし部分）の穴
    r_rel = d / 2 + t + p["relief_clear"]          # ポケット（リブ間）
    r_rib = d / 2 + t - p["squeeze"]               # リブ先端
    yp = L / 2 - p["lip_len"]                      # ポケットの半長

    prof = _stopper_profile(p)
    body = extrude_xz(prof ^ rect2(-W, W, -1.0, H), -L / 2, L / 2)

    # 結束バンド溝（底面と両側面）
    inner = prof.offset(-p["groove_d"], JoinType.Miter, 4.0)
    for yg in p["groove_ys"]:
        body -= extrude_xz(prof - inner, yg - p["groove_w"] / 2, yg + p["groove_w"] / 2)

    # ケーブル穴 + 出入口の面取り
    c = p["chamfer"]
    body -= cyl_y(r_lip, -L / 2 - 1, L / 2 + 1, z=H)
    body -= cyl_y(r_lip + c + 1.0, -L / 2 - 1.0, -L / 2 + c, z=H, r1=r_lip)
    body -= cyl_y(r_lip, L / 2 - c, L / 2 + 1.0, z=H, r1=r_lip + c + 1.0)
    # ポケット（チューブ入り）
    if r_rel > r_lip + 1e-6:
        body -= cyl_y(r_rel, -yp, yp, z=H)

    # リブ（半リング）
    ring = cyl_y(r_rel + 0.05, -L, L, z=H) - cyl_y(r_rib, -L, L, z=H)
    for y in p["rib_ys"]:
        body += ring ^ box(-W, W, y - p["rib_w"] / 2, y + p["rib_w"] / 2, 0, H)

    # 割り面の縁の面取り（穴の縁とリブ先端の縁）
    sc = p["seam_chamfer"]
    for r, y0, y1 in ((r_rel, -yp, yp), (r_rib, -yp, yp), (r_lip, -L / 2 - 1, L / 2 + 1)):
        tri = CrossSection([np.array([[-r - sc, H + 0.01], [-r, H - sc], [r, H - sc], [r + sc, H + 0.01]])])
        body -= extrude_xz(tri, y0, y1)

    # 位置合わせピンと穴（対角）
    px, py, pr, ph = p["pin_x"], p["pin_y"], p["pin_r"], p["pin_h"]
    for sx, sy in ((1, 1), (-1, -1)):
        body += cyl_z(pr, H - 0.01, H + ph - 0.4, sx * px, sy * py)
        body += cyl_z(pr, H + ph - 0.4, H + ph, sx * px, sy * py, r1=pr - 0.4)
    hr = p["hole_r"]
    for sx, sy in ((-1, 1), (1, -1)):
        body -= cyl_z(hr, H - p["hole_h"], H + 0.1, sx * px, sy * py)
        body -= cyl_z(hr, H - 0.4, H + 0.01, sx * px, sy * py, r1=hr + 0.41)   # 0.4mmの面取り
    return body


def stopper_front_half(d: float) -> Manifold:
    return stopper_half(d, STOPPER_FRONT)


def stopper_rear_half(d: float, liner: bool = True) -> Manifold:
    return stopper_half(d, STOPPER_REAR if liner else STOPPER_REAR_NOLINER)


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


# ---------------------------------------------------------------- 4. 試験・作業用の治具

JIG = dict(
    Lx=150.0, Wy=60.0, T=6.0, r=5.0,
    slots=((8.0, -1), (10.0, +1)),  # (スロット幅, どちらの端か)。既存クリップの穴（写真から8〜10mmと推定）を模す
    c_edge=20.0,      # 板の端 → ケーブル中心（スロット奥の半円の中心）
    lead=2.0,         # スロット入口の45°ガイド
    ch=0.8,           # スロット上下の縁の45°面取り（ケーブルを角に当てない）
    desk_line=40.0,   # 机の縁に合わせる線（端から40mm → ケーブルは机から20mm外に出る）
    hole_d=4.5, hole_x=15.0,  # M4ボルト/木ねじ用の穴
    engrave=0.6,
)


def _jig_slot_parts(w, sign, p, grow=0.0):
    """U字スロットを凸形状2つ（直線部＋奥の半円 / 入口のガイド）に分けて返す（面取りのhull用）。"""
    Lx = p["Lx"]
    xe = sign * Lx / 2
    xc = sign * (Lx / 2 - p["c_edge"])
    hw = w / 2 + grow
    lead = p["lead"]
    xo = xe + sign * 2.0
    x0, x1 = sorted((xo, xc))
    u = rect2(x0, x1, -hw, hw) + CrossSection.circle(hw, SEG).translate((xc, 0.0))
    pts = [(xo, -(hw + lead + 2.0)), (xo, hw + lead + 2.0), (xe - sign * lead, hw), (xe - sign * lead, -hw)]
    if sign < 0:
        pts = pts[::-1]
    return [u, CrossSection([np.array(pts)])]


def slip_test_jig(p=JIG) -> Manifold:
    """机にクランプして使う引張試験用の板。スロットにケーブルを通し、ストッパーを板の上に当てて下から荷重をかける。"""
    Lx, Wy, T = p["Lx"], p["Wy"], p["T"]
    body = rounded_rect2(Lx, Wy, p["r"]).extrude(T)
    ch = p["ch"]
    for w, sgn in p["slots"]:
        parts = _jig_slot_parts(w, sgn, p)
        body -= (parts[0] + parts[1]).extrude(T + 2).translate((0, 0, -1))
        for z_wide, z_narrow in ((-0.01, ch), (T + 0.01, T - ch)):
            for k in range(2):
                wide = _jig_slot_parts(w, sgn, p, ch + 0.01)[k].extrude(0.01).translate((0, 0, z_wide - 0.005))
                narrow = parts[k].extrude(0.01).translate((0, 0, z_narrow - 0.005))
                body -= Manifold.batch_hull([wide, narrow])
        lx = sgn * (Lx / 2 - p["c_edge"])
        body -= text2(f"{w:.1f}", 6.0, lx, 19.0).extrude(p["engrave"] + 0.01).translate((0, 0, T - p["engrave"]))
        x = sgn * (Lx / 2 - p["desk_line"])
        body -= rect2(x - 0.5, x + 0.5, -Wy / 2 - 1, Wy / 2 + 1).extrude(p["engrave"] + 0.01) \
            .translate((0, 0, T - p["engrave"]))
    for sgn in (-1, 1):
        body -= cyl_z(p["hole_d"] / 2, -1, T + 1, sgn * p["hole_x"], 0)
    return body


TUBE_GUIDE = dict(L=40.0, wall=3.5, stop=3.0, floor=4.0, cut_len=19.0, slot_w=0.8, bridge=2.5)
TUBE_SIZES = {"3x5": 5.0, "4x6": 6.0, "5x7": 7.0}   # 内径x外径 → 外径


def tube_cut_guide(od: float, label: str, p=TUBE_GUIDE) -> Manifold:
    """シリコンチューブを19mmに切りそろえるガイド。チューブを溝に入れて端を突き当て、スリットにカッターを通す。"""
    cw = od + 0.3
    W = cw + 2 * p["wall"]
    Hh = p["floor"] + od
    body = box(0, p["L"], -W / 2, W / 2, 0, Hh)
    body -= box(p["stop"], p["L"] + 1, -cw / 2, cw / 2, p["floor"], Hh + 1)
    xs = p["stop"] + p["cut_len"]
    body -= box(xs, xs + p["slot_w"], -W / 2 - 1, W / 2 + 1, p["bridge"], Hh + 1)
    # 側面にチューブサイズを彫り込む（XY平面の文字を立てて -Y 側の面へ）
    lab = text2(label, 3.5, 0, 0).extrude(0.6).rotate((90, 0, 0))
    body -= lab.translate((p["stop"] + p["cut_len"] + (p["L"] - p["stop"] - p["cut_len"]) / 2,
                           -W / 2 + 0.59, Hh / 2))
    return body


# ---------------------------------------------------------------- 出力

def main() -> None:
    parts = {}
    parts["cable_gauge.stl"] = drop_to_bed(cable_gauge())
    parts["slip_test_jig.stl"] = drop_to_bed(slip_test_jig())
    for label, od in TUBE_SIZES.items():
        parts[f"tube_cut_guide_{label}.stl"] = drop_to_bed(tube_cut_guide(od, label))
    for d in CABLE_SIZES:
        tag = f"d{d:.1f}"
        parts[f"{tag}/stopper_front_half_{tag}.stl"] = drop_to_bed(stopper_front_half(d))
        parts[f"{tag}/stopper_rear_half_{tag}.stl"] = drop_to_bed(stopper_rear_half(d))
        parts[f"{tag}/stopper_rear_noliner_half_{tag}.stl"] = drop_to_bed(stopper_rear_half(d, liner=False))
        parts[f"{tag}/slack_holder_{tag}.stl"] = drop_to_bed(slack_holder(d))

    for rel, m in parts.items():
        assert m.status().name == "NoError", (rel, m.status())
        assert len(m.decompose()) == 1, rel
        write_stl(m, STL_DIR / rel, rel)
        (x0, y0, z0, x1, y1, z1) = m.bounding_box()
        print(f"{rel:46s} {x1 - x0:6.1f} x {y1 - y0:6.1f} x {z1 - z0:5.1f} mm"
              f"  vol {m.volume() / 1000:5.2f} cm3")


if __name__ == "__main__":
    main()
