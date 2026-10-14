"""README用のプレビュー画像を images/ に書き出す（python3 cad/render_previews.py）。"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate as g  # noqa: E402

IMG = g.ROOT / "images"
plt.rcParams["font.family"] = ["IPAGothic", "IPAPGothic", "DejaVu Sans"]

# ---------------------------------------------------------------- 簡易Zバッファレンダラ

def mesh_arrays(m):
    if isinstance(m, tuple):
        return m
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties, dtype=float)[:, :3]
    t = np.asarray(mesh.tri_verts, dtype=np.int64)
    return v, t


def feature_edges(v, t, angle_deg=35.0):
    tri = v[t]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    f = np.tile(np.arange(len(t)), 3)
    key = np.sort(e, axis=1)
    order = np.lexsort((key[:, 1], key[:, 0]))
    key, f = key[order], f[order]
    same = np.all(key[1:] == key[:-1], axis=1)
    i = np.nonzero(same)[0]
    a, b = f[i], f[i + 1]
    return key[i], n[a], n[b], np.cos(np.radians(angle_deg))


def render(objs, elev=30.0, azim=-60.0, size=(640, 480), ss=3, pad=0.06):
    """objs: [(Manifold or (verts, tris), rgb)] → RGB画像 (H, W, 3)。"""
    el, az = np.radians(elev), np.radians(azim)
    cam = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    right = np.cross([0.0, 0.0, 1.0], cam)
    right /= np.linalg.norm(right)
    up = np.cross(cam, right)
    light = 0.55 * cam + 0.65 * up - 0.45 * right
    light /= np.linalg.norm(light)

    data = [(mesh_arrays(m), np.asarray(c, float)) for m, c in objs]
    allv = np.vstack([v for (v, _), _ in data])
    P = np.stack([allv @ right, allv @ up], axis=1)
    lo, hi = P.min(0), P.max(0)
    W, H = size[0] * ss, size[1] * ss
    scale = min(W * (1 - 2 * pad) / (hi[0] - lo[0]), H * (1 - 2 * pad) / (hi[1] - lo[1]))
    off = np.array([W, H]) / 2 - (lo + hi) / 2 * scale

    def to_screen(v):
        xy = np.stack([v @ right, v @ up], axis=1) * scale + off
        xy[:, 1] = H - xy[:, 1]
        return xy, v @ cam * scale

    zbuf = np.full((H, W), -np.inf)
    img = np.ones((H, W, 3))
    edges_all = []
    for (v, t), col in data:
        xy, z = to_screen(v)
        tri = v[t]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        front = n @ cam > 0
        shade = 0.42 + 0.5 * np.clip(n @ light, 0, 1) + 0.12 * np.clip(n @ cam, 0, 1)
        for k in np.nonzero(front)[0]:
            a, b, c = t[k]
            pa, pb, pc = xy[a], xy[b], xy[c]
            x0 = max(int(np.floor(min(pa[0], pb[0], pc[0]))), 0)
            x1 = min(int(np.ceil(max(pa[0], pb[0], pc[0]))), W - 1)
            y0 = max(int(np.floor(min(pa[1], pb[1], pc[1]))), 0)
            y1 = min(int(np.ceil(max(pa[1], pb[1], pc[1]))), H - 1)
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            d = (pb[1] - pc[1]) * (pa[0] - pc[0]) + (pc[0] - pb[0]) * (pa[1] - pc[1])
            if abs(d) < 1e-12:
                continue
            w0 = ((pb[1] - pc[1]) * (gx - pc[0]) + (pc[0] - pb[0]) * (gy - pc[1])) / d
            w1 = ((pc[1] - pa[1]) * (gx - pc[0]) + (pa[0] - pc[0]) * (gy - pc[1])) / d
            w2 = 1 - w0 - w1
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not inside.any():
                continue
            zz = w0 * z[a] + w1 * z[b] + w2 * z[c]
            sub = zbuf[y0:y1 + 1, x0:x1 + 1]
            m = inside & (zz > sub)
            sub[m] = zz[m]
            img[y0:y1 + 1, x0:x1 + 1][m] = np.clip(col * shade[k], 0, 1)
        # 輪郭線（稜線＋シルエット）
        e, na, nb, cth = feature_edges(v, t)
        fa, fb = na @ cam > 0, nb @ cam > 0
        keep = ((np.sum(na * nb, axis=1) < cth) & (fa | fb)) | (fa != fb)
        edges_all.append((xy[e[keep]], z[e[keep]]))

    eps = 0.004 * (zbuf[np.isfinite(zbuf)].max() - zbuf[np.isfinite(zbuf)].min() + 1)
    for exy, ez in edges_all:
        for (p0, p1), (z0, z1) in zip(exy, ez):
            L = int(np.hypot(*(p1 - p0)) * 2) + 2
            s_ = np.linspace(0, 1, L)
            px = np.clip((p0[0] + (p1[0] - p0[0]) * s_).astype(int), 0, W - 1)
            py = np.clip((p0[1] + (p1[1] - p0[1]) * s_).astype(int), 0, H - 1)
            pz = z0 + (z1 - z0) * s_
            vis = pz >= zbuf[py, px] - eps * scale
            for dx in range(-(ss // 2), ss - ss // 2):
                for dy in range(-(ss // 2), ss - ss // 2):
                    qx = np.clip(px[vis] + dx, 0, W - 1)
                    qy = np.clip(py[vis] + dy, 0, H - 1)
                    img[qy, qx] = img[qy, qx] * 0.35 + 0.65 * np.array([0.25, 0.25, 0.27])
    return img.reshape(size[1], ss, size[0], ss, 3).mean(axis=(1, 3))


def tube(path, r, seg=14):
    """折れ線 path に沿った管の (verts, tris)。"""
    path = np.asarray(path, float)
    T = np.gradient(path, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    ref = np.array([0.0, 0.0, 1.0]) if abs(T[0][2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    N = np.cross(T[0], ref)
    N /= np.linalg.norm(N)
    rings = []
    for i, t_ in enumerate(T):
        N = N - t_ * (N @ t_)
        N /= np.linalg.norm(N)
        B = np.cross(t_, N)
        a = np.linspace(0, 2 * np.pi, seg, endpoint=False)
        rings.append(path[i] + r * (np.outer(np.cos(a), N) + np.outer(np.sin(a), B)))
    v = np.vstack(rings)
    tris = []
    for i in range(len(path) - 1):
        for j in range(seg):
            a, b = i * seg + j, i * seg + (j + 1) % seg
            c, d = a + seg, b + seg
            tris += [[a, b, d], [a, d, c]]
    # 端面
    for base, flip in ((0, True), ((len(path) - 1) * seg, False)):
        ctr = len(v)
        v = np.vstack([v, path[0 if flip else -1]])
        for j in range(seg):
            a, b = base + j, base + (j + 1) % seg
            tris.append([ctr, b, a] if flip else [ctr, a, b])
    return v, np.asarray(tris, dtype=np.int64)


PART = (0.90, 0.90, 0.86)
CABLE = (0.62, 0.62, 0.64)
ACCENT = (0.25, 0.48, 0.86)


def stopper_assembly(d, gap=5.0):
    H, W, L = g.STOPPER["H"], g.STOPPER["W"], g.STOPPER["L"]
    a = g.stopper_half(d)
    b = a.rotate((0, 180, 0)).translate((0, 0, 2 * H + gap))
    cable = g.cyl_y(d / 2, -26, 26, z=H + gap / 2)
    return a, b, cable


def zip_tie(d):
    H, W = g.STOPPER["H"], g.STOPPER["W"]
    gd, gw = g.STOPPER["groove_d"], 2.5
    inner = g.box(-W / 2 + gd, W / 2 - gd, -gw / 2, gw / 2, gd, 2 * H - gd)
    outer = g.box(-W / 2 + gd - 1.0, W / 2 - gd + 1.0, -gw / 2, gw / 2, gd - 1.0, 2 * H - gd + 1.0)
    head = g.box(W / 2 - gd + 0.8, W / 2 - gd + 5.5, -2.5, 2.5, H - 2.5, H + 2.5)
    return outer - inner + head


def holder_cable_path(d, loops=4):
    p = g.HOLDER
    D, rh, tp = p["D"], p["rh"], p["tp"]
    rc = rh + d / 2
    half = D / 2 + rh + p["anchor_gap"] + p["anchor_len"] + p["margin"]
    z0 = tp + d / 2
    pts = [[0, -half - 30, z0], [0, -D / 2 - rc - 1, z0]]
    z = z0

    def arc(yc, a0, a1, z_start, z_end, n=24):
        a = np.linspace(a0, a1, n)
        zz = np.linspace(z_start, z_end, n)
        return np.c_[rc * np.cos(a), yc + rc * np.sin(a), zz]

    pts += list(arc(-D / 2, -np.pi / 2, -np.pi, z, z))
    for i in range(loops):
        dz = d * 1.02
        pts += list(arc(D / 2, np.pi, 0, z + dz * 0.25, z + dz * 0.5))
        pts += list(arc(-D / 2, 0, -np.pi, z + dz * 0.75, z + dz))
        z += dz
    pts += list(arc(D / 2, np.pi, np.pi / 2, z + 0.3, z + 0.6, 12))
    pts += [[0, D / 2 + rc + 4, z0 + 1.5], [0, half + 30, z0]]
    return np.asarray(pts, float)


def parts_overview(d=4.0):
    fig, axes = plt.subplots(2, 2, figsize=(12, 9.2), dpi=110)
    shots = [
        ("① ケーブル径ゲージ（最初に1枚だけ）", [(g.drop_to_bed(g.cable_gauge()), PART)], 62, -90),
        (f"② ストッパー半割（印刷する向き / d={d}）", [(g.stopper_half(d), PART)], 38, -58),
        ("②を2個でケーブルを挟み、溝を結束バンドで締める",
         [(m, c) for m, c in zip(stopper_assembly(d), (PART, PART, CABLE))]
         + [(zip_tie(d).translate((0, 0, 0)), ACCENT)], 16, -32),
        (f"③ 余長ホルダー（d={d}）", [(g.slack_holder(d), PART)], 32, -38),
    ]
    a, b, cable = stopper_assembly(d, gap=0.0)
    shots[2] = (shots[2][0], [(a, PART), (b, PART), (cable, CABLE), (zip_tie(d), ACCENT)], 18, -30)
    for ax, (title, objs, el, az) in zip(axes.ravel(), shots):
        ax.imshow(render(objs, el, az, size=(620, 440)))
        ax.set_title(title, fontsize=13)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(IMG / "parts_overview.png")
    plt.close(fig)


def holder_3d(d=4.0):
    holder = g.slack_holder(d)
    cable = tube(holder_cable_path(d), d / 2)
    fig, ax = plt.subplots(figsize=(8, 6), dpi=110)
    ax.imshow(render([(holder, PART), (cable, CABLE)], 30, -30, size=(720, 540)))
    ax.set_title("余長ホルダーにケーブルを4周掛けた例（実際は縦向きに吊る）", fontsize=12)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(IMG / "holder_3d.png")
    plt.close(fig)


def holder_usage(d=4.0):
    """ホルダーにケーブルを掛けた状態（正面図）。"""
    p = g.HOLDER
    D, rh, tp = p["D"], p["rh"], p["tp"]
    rc = rh + d / 2
    fig, ax = plt.subplots(figsize=(5.2, 8.5), dpi=110)
    half = D / 2 + rh + p["anchor_gap"] + p["anchor_len"] + p["margin"]
    pw = 2 * rh + 2
    ax.add_patch(matplotlib.patches.FancyBboxPatch(
        (-pw / 2, -half), pw, 2 * half, boxstyle="round,pad=0,rounding_size=5",
        fc="#e4e4df", ec="#888", lw=1.2))
    for s in (1, -1):
        th = np.linspace(0, np.pi, 50)
        xs, ys = rh * np.cos(th), s * (D / 2 + rh * np.sin(th))
        ax.fill(np.r_[xs, [-rh, rh]], np.r_[ys, [s * (D / 2 - 3)] * 2], fc="#c9c9c3", ec="#777")
        ya = s * (D / 2 + rh + p["anchor_gap"] + p["anchor_len"] / 2)
        ax.add_patch(matplotlib.patches.Rectangle(
            (-(d / 2 + 1.8), ya - 5), d + 3.6, 10, fc="#c9c9c3", ec="#777"))

    # ケーブル：下の固定クリップ → 下フック左回り → … → 上フック → 上の固定クリップ
    loops, step = 4, 1.5
    path = [np.array([[0, -half - 25], [0, -D / 2 - rc]])]
    th = np.linspace(-np.pi / 2, -np.pi, 20)
    path.append(np.c_[rc * np.cos(th), -D / 2 + rc * np.sin(th)])
    for i in range(loops + 1):
        r = rc + i * step
        path.append(np.array([[-r, -D / 2], [-r, D / 2]]))
        last = i == loops
        th = np.linspace(np.pi, np.pi / 2 if last else 0, 40)
        path.append(np.c_[r * np.cos(th), D / 2 + r * np.sin(th)])
        if last:
            break
        path.append(np.array([[r, D / 2], [r, -D / 2]]))
        th = np.linspace(0, -np.pi, 40)
        rr = np.linspace(r, r + step, 40)  # 下フックで1段外へ（渦巻き）
        path.append(np.c_[rr * np.cos(th), -D / 2 + rr * np.sin(th)])
    path.append(np.array([[0, D / 2 + rc + loops * step], [0, half + 25]]))
    path = np.vstack(path)
    ax.plot(path[:, 0], path[:, 1], color="#8d8d8d", lw=2.2, alpha=0.9, solid_capstyle="round")
    sx, sy = p["slot"]
    for s in (1, -1):
        ax.add_patch(matplotlib.patches.Rectangle((-sx / 2, s * p["slot_y"] - sy / 2), sx, sy,
                                                  fc="white", ec="#777"))

    kw = dict(fontsize=10, ha="left", va="center")
    ax.annotate("天板の隙間（前側）へ", (0, half + 22), (6, half + 22), **kw)
    ax.annotate("電源アダプタへ", (0, -half - 22), (6, -half - 22), **kw)
    ax.annotate("固定クリップ\n（上から押し込む）", (d / 2 + 2, half - 7), (22, half - 10),
                arrowprops=dict(arrowstyle="->", lw=0.8), **kw)
    ax.annotate("フックに輪を掛ける\n（1周 約20cm）", (rc + 2, D / 2 - 20), (22, 5),
                arrowprops=dict(arrowstyle="->", lw=0.8), **kw)
    ax.annotate("スリット：必要なら\n結束バンドで固定", (2.2, -p["slot_y"]), (22, -30),
                arrowprops=dict(arrowstyle="->", lw=0.8), **kw)
    ax.set_aspect("equal")
    ax.set_xlim(-30, 62)
    ax.set_ylim(-half - 30, half + 30)
    ax.axis("off")
    ax.set_title("余長ホルダーの使い方（背面・縦向きに吊る）", fontsize=12)
    fig.tight_layout()
    fig.savefig(IMG / "holder_usage.png")
    plt.close(fig)


def install_diagram():
    """保管庫を横から見た模式図（改善前 / 改善後）。"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6.4), dpi=110)
    for ax, after in zip(axes, (False, True)):
        ax.set_xlim(-8, 108)
        ax.set_ylim(-8, 92)
        ax.set_aspect("equal")
        ax.axis("off")
        wall = dict(fc="#efefea", ec="#999", lw=1.2)
        # 筐体：左が前面、右が背面
        ax.add_patch(matplotlib.patches.Rectangle((0, 0), 100, 84, fc="none", ec="#777", lw=2))
        ax.add_patch(matplotlib.patches.Rectangle((2, 62), 66, 4, **wall))       # 配線トレイ（天井部分）
        ax.add_patch(matplotlib.patches.Rectangle((70, 4), 2, 66, **wall))       # 仕切り（背面パネル）
        ax.add_patch(matplotlib.patches.Rectangle((8, 26), 56, 34, fc="#d8d8d8", ec="#888"))  # MacBook
        ax.text(36, 43, "MacBook\n（立てて収納）", ha="center", va="center", fontsize=10)
        ax.add_patch(matplotlib.patches.Rectangle((84, 30), 9, 7, fc="white", ec="#666"))     # アダプタ
        ax.text(88.5, 26, "電源\nアダプタ", ha="center", va="top", fontsize=9)
        ax.add_patch(matplotlib.patches.Rectangle((7, 66), 3, 3, fc="white", ec="#555"))      # 既存クリップ
        ax.text(0, 88, "前面", fontsize=11, ha="left")
        ax.text(100, 88, "背面", fontsize=11, ha="right")

        cable = dict(color="#7d7d7d", lw=3, solid_capstyle="round", solid_joinstyle="round")
        if not after:
            ax.plot([88, 88, 80, 74, 72, 70, 40, 10, 2, -5, -5, 4, 8.5],
                    [37, 50, 68, 70, 70, 69, 68, 68, 66, 56, 38, 36, 52], **cable)
            # 背面の垂れ下がり
            ax.plot([88, 95, 97, 80, 78, 92, 88], [37, 20, 6, 4, 14, 10, 30], **cable)
            ax.text(36, 14, "ケーブルが既存クリップの中を前後に自由に滑る\n→ 前は輪の長さがバラバラ、背面は余りが垂れて絡む",
                    ha="center", fontsize=10.5, color="#b03030")
            ax.set_title("いま", fontsize=14)
        else:
            ax.plot([88, 88, 87, 80, 74, 72, 70, 40, 10, 6, 5, 7, 8.5],
                    [37, 44, 66, 69, 70, 70, 69, 68, 68, 66, 60, 55, 52], **cable)
            # ストッパー（クリップの前後）
            for x in (4.2, 11.2):
                ax.add_patch(matplotlib.patches.Rectangle((x, 66.3), 2.6, 4.2, fc="#2a6fdb", ec="#1b4ea0"))
            # 余長ホルダー
            ax.add_patch(matplotlib.patches.FancyBboxPatch((85.5, 44), 5, 18,
                         boxstyle="round,pad=0,rounding_size=1.5", fc="#2a6fdb", ec="#1b4ea0", alpha=0.85))
            ax.annotate("②ストッパー×2\n既存クリップを前後から挟む", (8.5, 70.5), (14, 74.5),
                        arrowprops=dict(arrowstyle="->", lw=0.9), fontsize=10, color="#1b4ea0")
            ax.annotate("③余長ホルダー\n余りはここに巻き取る", (90.5, 55), (71, 74.5),
                        arrowprops=dict(arrowstyle="->", lw=0.9), fontsize=10, color="#1b4ea0")
            ax.text(36, 14, "前面の垂れ長さが全スロットで一定に\n取り出してもケーブルは引き出されない",
                    ha="center", fontsize=10.5, color="#1b4ea0")
            ax.set_title("改善後", fontsize=14)
    fig.tight_layout()
    fig.savefig(IMG / "install_diagram.png")
    plt.close(fig)


if __name__ == "__main__":
    IMG.mkdir(exist_ok=True)
    parts_overview()
    holder_3d()
    holder_usage()
    install_diagram()
    print("wrote", sorted(p.name for p in IMG.glob("*.png")))
