"""Draw Topo wordmark explorations: the "opo" made of contour lines.

Each letter is a skeleton (points, circles, segments). A height field falls off with distance
from the skeletons, and the logo's lines are that field's contours, traced with marching squares.

    python3 -I brand/contour_logo.py brand/explorations/svg
"""
import math
import sys
from pathlib import Path

import numpy as np

INK, PAPER, ACCENT = "#1a2226", "#ecebe4", "#2346cc"
INK_D, PAPER_D, ACCENT_D = "#e4e8e6", "#0d1214", "#8ea4ff"

W, H = 1000, 400
STEP = 1.5  # grid spacing in px
XS = np.arange(0, W + STEP, STEP)
YS = np.arange(0, H + STEP, STEP)
GX, GY = np.meshgrid(XS, YS)

# Letter geometry: x-height 100..260, o radius 80, descender to 350.
BASE, XTOP = 270, 110
R = (BASE - XTOP) / 2
CY = XTOP + R
O1, P, O2 = 330, 532, 734  # bowl centres
VIEW = (60, 14, 860, 372)


# ---------- fields ----------

def d_point(cx, cy):
    return np.hypot(GX - cx, GY - cy)


def d_hill(cx, cy, ecc=0.3, phi=0.0):
    """Distance whose contours are circles that crowd on one side: a hill with a steep face."""
    dx, dy = GX - cx, GY - cy
    th = np.arctan2(dy, dx)
    return np.hypot(dx, dy) / (1 + ecc * np.cos(th - phi))


class warped:
    """Within this block every distance function samples a gently warped plane."""
    def __init__(self, seed, scale, amp):
        self.seed, self.scale, self.amp = seed, scale, amp

    def __enter__(self):
        global GX, GY
        self.saved = GX, GY
        nx, ny = noise(self.seed, self.scale, self.amp), noise(self.seed + 1, self.scale, self.amp)
        GX, GY = GX + nx, GY + ny

    def __exit__(self, *exc):
        global GX, GY
        GX, GY = self.saved


def d_circle(cx, cy, r):
    return np.abs(d_point(cx, cy) - r)


def d_segment(x1, y1, x2, y2):
    px, py = GX - x1, GY - y1
    dx, dy = x2 - x1, y2 - y1
    t = np.clip((px * dx + py * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(px - t * dx, py - t * dy)


def smin(a, b, k):
    """Smooth minimum; k is the blend radius in px."""
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def noise(seed, scale, amp):
    """Smooth value noise, sum of a few random low-frequency waves."""
    rng = np.random.default_rng(seed)
    out = np.zeros_like(GX)
    for octave in range(4):
        f = (2 ** octave) / scale
        for _ in range(3):
            a = rng.uniform(0, 2 * math.pi)
            ph = rng.uniform(0, 2 * math.pi)
            out += np.sin((GX * math.cos(a) + GY * math.sin(a)) * f * 2 * math.pi + ph) / (2 ** octave)
    return out * amp / 3


# ---------- marching squares ----------

def contours(field, level):
    """Return polylines (lists of (x,y)) where field == level."""
    f = field
    a, b, c, d = f[:-1, :-1], f[:-1, 1:], f[1:, 1:], f[1:, :-1]  # tl tr br bl
    idx = ((a > level) * 8 + (b > level) * 4 + (c > level) * 2 + (d > level) * 1).astype(np.int8)
    rows, cols = np.nonzero((idx != 0) & (idx != 15))
    segs = []

    def lerp(v1, v2):
        return 0.5 if v2 == v1 else (level - v1) / (v2 - v1)

    for r, cc in zip(rows.tolist(), cols.tolist()):
        va, vb, vc, vd = a[r, cc], b[r, cc], c[r, cc], d[r, cc]
        x0, y0 = cc * STEP, r * STEP
        top = (x0 + lerp(va, vb) * STEP, y0)
        right = (x0 + STEP, y0 + lerp(vb, vc) * STEP)
        bottom = (x0 + lerp(vd, vc) * STEP, y0 + STEP)
        left = (x0, y0 + lerp(va, vd) * STEP)
        k = idx[r, cc]
        table = {
            1: [(left, bottom)], 2: [(bottom, right)], 3: [(left, right)], 4: [(top, right)],
            5: [(left, top), (bottom, right)], 6: [(top, bottom)], 7: [(left, top)],
            8: [(left, top)], 9: [(top, bottom)], 10: [(left, bottom), (top, right)],
            11: [(top, right)], 12: [(left, right)], 13: [(bottom, right)], 14: [(left, bottom)],
        }
        segs.extend(table[k])
    return link(segs)


def link(segs):
    key = lambda p: (round(p[0], 3), round(p[1], 3))
    ends = {}
    for i, (p, q) in enumerate(segs):
        ends.setdefault(key(p), []).append(i)
        ends.setdefault(key(q), []).append(i)
    used = [False] * len(segs)
    lines = []
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        line = [segs[i][0], segs[i][1]]
        for direction in (1, -1):
            while True:
                tip = line[-1] if direction == 1 else line[0]
                nxt = None
                for j in ends.get(key(tip), []):
                    if not used[j]:
                        nxt = j
                        break
                if nxt is None:
                    break
                used[nxt] = True
                p, q = segs[nxt]
                other = q if key(p) == key(tip) else p
                if direction == 1:
                    line.append(other)
                else:
                    line.insert(0, other)
        lines.append(line)
    return [l for l in lines if len(l) > 6]


def simplify(line, every=2):
    closed = math.dist(line[0], line[-1]) < STEP * 1.5
    pts = line[::every]
    if closed and pts[-1] != pts[0]:
        pts.append(pts[0])
    return pts, closed


def path_d(line):
    pts, closed = simplify(line)
    s = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return s + ("Z" if closed else "")


# ---------- letters ----------

def T_path(x=168, top=40, base=BASE, w=150, stem=36, bar=36):
    l, r = x - w / 2, x + w / 2
    sl, sr = x - stem / 2, x + stem / 2
    return (f"M{l},{top} H{r} V{top + bar} H{sr} V{base} H{sl} V{top + bar} H{l} Z")


def letters_summit(width=R):
    """o as a cone summit, p as a summit with a ridge stem. Normalised distance (0 at peak)."""
    o1 = d_point(O1, CY) / width
    o2 = d_point(O2, CY) / width
    bowl = d_point(P, CY) / width
    stem = d_segment(P - R + 14, CY, P - R + 14, 350) / 30
    return o1, smin(bowl, stem, 0.15), o2


def letters_terrain(width=R, ecc=0.32):
    """Summits with steep faces pointing different ways, so each o reads as a real hill."""
    o1 = d_hill(O1 + 6, CY - 4, ecc, 2.5) / width
    o2 = d_hill(O2 - 4, CY + 3, ecc, -0.6) / width
    bowl = d_hill(P + 5, CY - 2, ecc * 0.8, 0.9) / width
    stem = d_segment(P - R + 16, CY + 10, P - R + 16, 352) / 30
    return o1, smin(bowl, stem, 0.3), o2


def letters_ridge(stroke=26):
    """Every letter as a ridge running along its stroke, like an inline typeface."""
    o1 = d_circle(O1, CY, R - stroke) / stroke
    o2 = d_circle(O2, CY, R - stroke) / stroke
    p = np.minimum(d_circle(P, CY, R - stroke), d_segment(P - R + stroke, XTOP + stroke, P - R + stroke, 350 - stroke)) / stroke
    return o1, p, o2


# ---------- svg ----------

def svg(body, bg, size=(W, H), view=None):
    vx, vy, vw, vh = view or VIEW
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx} {vy} {vw} {vh}" '
            f'width="{vw}" height="{vh}"><rect x="{vx}" y="{vy}" width="{vw}" height="{vh}" fill="{bg}"/>'
            f"{body}</svg>")


def strokes(field, levels, color, width, index_every=0, index_width=None, opacity=1.0):
    out = []
    for i, lv in enumerate(levels):
        wdt = index_width if index_every and i % index_every == 0 else width
        for line in contours(field, lv):
            out.append(f'<path d="{path_d(line)}" fill="none" stroke="{color}" stroke-width="{wdt}" '
                       f'stroke-linejoin="round" stroke-linecap="round" opacity="{opacity}"/>')
    return "".join(out)


def build(outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    made = []

    def save(name, text):
        (out / f"{name}.svg").write_text(text)
        made.append(name)

    T = f'<path d="{T_path()}" fill="{{c}}"/>'
    levels6 = [k / 6 for k in range(6)]

    # 01 Summit: three clean hilltops
    o1, p, o2 = letters_summit()
    f = -np.minimum(np.minimum(o1, p), o2)
    save("01-summit", svg(T.format(c=INK) + strokes(f, [-1 + k / 5 for k in range(5)][::-1] + [-0.02], INK, 3), PAPER))

    # 02 Summit dark
    save("02-summit-dark", svg(T.format(c=INK_D) + strokes(f, [-1 + k / 5 for k in range(5)] + [-0.02], ACCENT_D, 3), PAPER_D))

    # 03 Inline ridge: contour lines follow each stroke
    o1, p, o2 = letters_ridge()
    f = -np.minimum(np.minimum(o1, p), o2)
    save("03-inline-ridge", svg(T.format(c=INK) + strokes(f, [-1, -0.66, -0.33, -0.04], INK, 3), PAPER))

    # 04 Ridge range: the three summits share outer contours across saddles, with a summit marker
    o1, p, o2 = letters_summit(width=R * 1.05)
    g = smin(smin(o1, p, 0.35), o2, 0.35) + noise(7, 900, 0.03)
    f = -g
    lv = [-1.25 + k * 0.2 for k in range(7)]
    body = T.format(c=INK) + strokes(f, lv, INK, 2.6, index_every=3, index_width=4.2)
    body += f'<circle cx="{P}" cy="{CY}" r="7" fill="{ACCENT}"/>'
    save("04-ridge-range", svg(body, PAPER))

    # 05 Survey: organic wobble, index contours, sepia
    o1, p, o2 = letters_summit()
    f = -np.minimum(np.minimum(o1, p), o2) + noise(3, 500, 0.06)
    body = T.format(c="#5a3b22") + strokes(f, [-1 + k / 7 for k in range(7)] + [-0.03], "#7a5230", 2.2, index_every=4, index_width=3.8)
    save("05-survey-sepia", svg(body, "#f1e8d6"))

    # 06 Contour field: horizontal lines that swell into the letters, T knocked out
    o1, p, o2 = letters_summit(width=R * 1.25)
    bump = np.maximum(0, 1 - np.minimum(np.minimum(o1, p), o2)) ** 1.6
    field = GY / 22 - bump * 7
    lines = strokes(field, [k + 0.5 for k in range(0, 19)], INK, 2)
    mask = (f'<mask id="m"><rect width="{W}" height="{H}" fill="#fff"/>'
            f'<path d="{T_path()}" fill="#000" transform="translate(0,0)"/></mask>')
    body = f"<defs>{mask}</defs><g mask=\"url(#m)\">{lines}</g>"
    save("06-contour-field", svg(body, PAPER))

    # 07 Hypsometric tints: filled elevation bands
    o1, p, o2 = letters_summit()
    f = -np.minimum(np.minimum(o1, p), o2)
    tints = ["#c9d6b8", "#dfe3bd", "#ead9a7", "#e3bf8a", "#d9a679", "#f4efe6"]
    lv = [-1 + k / 6 for k in range(6)]
    body = T.format(c=INK)
    for lvl, tint in zip(lv, tints):
        for line in contours(f, lvl):
            body += f'<path d="{path_d(line)}" fill="{tint}" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>'
    save("07-hypsometric", svg(body, PAPER))

    # 08 Bold knockout: heavy letters, contour lines cut into them
    o1, p, o2 = letters_ridge(stroke=34)
    f = -np.minimum(np.minimum(o1, p), o2)
    body = f'<path d="{T_path(stem=50, bar=48, w=160)}" fill="{INK}"/>'
    for line in contours(f, -1):
        body += f'<path d="{path_d(line)}" fill="{INK}" fill-rule="evenodd"/>'
    body = body.replace('fill-rule="evenodd"', "")
    # fill letter shapes with even-odd so counters stay open
    shapes = "".join(path_d(l) for l in contours(f, -1))
    body = f'<path d="{T_path(stem=50, bar=48, w=160)}" fill="{INK}"/><path d="{shapes}" fill="{INK}" fill-rule="evenodd"/>'
    body += strokes(f, [-0.7, -0.4, -0.12], PAPER, 2.4)
    save("08-bold-knockout", svg(body, PAPER))

    # 09 All contour: the T too, one continuous line language
    o1, p, o2 = letters_ridge()
    tee = np.minimum(d_segment(98, 58, 238, 58), d_segment(168, 58, 168, BASE)) / 26
    f = -np.minimum(np.minimum(np.minimum(o1, p), o2), tee)
    save("09-all-contour", svg(strokes(f, [-1, -0.66, -0.33, -0.04], INK, 3), PAPER))

    # 10 Icon: one summit with a pin
    f = -(d_hill(O1, CY, 0.3, -2.2) / 88 + noise(11, 400, 0.03))
    body = strokes(f, [-1 + k / 6 for k in range(6)], INK, 4)
    body += f'<circle cx="{O1 + 4}" cy="{CY - 2}" r="10" fill="{ACCENT}"/>'
    save("10-icon-summit", svg(body, PAPER, view=(O1 - 150, CY - 150, 300, 300)))

    # 11 Icon dark, ridge o
    f = -(d_circle(O1, CY, 72) / 40)
    body = strokes(f, [-1, -0.66, -0.33, -0.05], ACCENT_D, 4)
    save("11-icon-ring-dark", svg(body, PAPER_D, view=(O1 - 150, CY - 150, 300, 300)))

    # ----- round 2: terrain (off-centre summits, warped plane) -----
    tlev = [-1 + k / 6 for k in range(6)] + [-0.04]

    def terrain(seed=5, amp=7, ecc=0.32, merge=0.0):
        with warped(seed, 260, amp):
            o1, p, o2 = letters_terrain(ecc=ecc)
        g = smin(smin(o1, p, merge), o2, merge) if merge else np.minimum(np.minimum(o1, p), o2)
        return -g

    f = terrain()
    save("12-terrain", svg(T.format(c=INK) + strokes(f, tlev, INK, 2.6, index_every=3, index_width=4.4), PAPER))
    save("13-terrain-dark", svg(T.format(c=INK_D) + strokes(f, tlev, ACCENT_D, 2.6, index_every=3, index_width=4.4), PAPER_D))

    f = terrain(seed=9, amp=9, merge=0.3)
    lv = [-1.3 + k * 0.18 for k in range(8)]
    body = T.format(c=INK) + strokes(f, lv, INK, 2.4, index_every=4, index_width=4.2)
    body += f'<circle cx="{P + 5 + 0.8 * 0.32 * 0}" cy="{CY - 2}" r="7" fill="{ACCENT}"/>'
    save("14-terrain-range", svg(body, PAPER))

    # Solid hills, contours cut in
    f = terrain(seed=5, amp=6)
    shapes = "".join(path_d(l) for l in contours(f, -1.0))
    body = (f'<path d="{T_path(stem=44, bar=44, w=156)}" fill="{INK}"/>'
            f'<path d="{shapes}" fill="{INK}" fill-rule="evenodd"/>')
    body += strokes(f, [-0.8, -0.6, -0.4, -0.2, -0.04], PAPER, 2.4)
    save("15-terrain-solid", svg(body, PAPER))

    # Tinted terrain, the summit band in accent
    f = terrain(seed=5, amp=7)
    tints = ["#dcdccd", "#cfd3c0", "#c3cab4", "#b3bda6", "#9fac98", ACCENT]
    body = T.format(c=INK)
    for lvl, tint in zip([-1 + k / 6 for k in range(6)], tints):
        for line in contours(f, lvl):
            body += f'<path d="{path_d(line)}" fill="{tint}" stroke="{INK}" stroke-width="1.4" stroke-linejoin="round"/>'
    save("16-terrain-tinted", svg(body, PAPER))

    # Monogram: T beside one hill
    with warped(21, 220, 6):
        hill = d_hill(O1 - 62, CY, 0.32, 2.4) / R
    f = -hill
    body = f'<path d="{T_path(x=150, stem=34, bar=34, w=140)}" fill="{INK}"/>' + strokes(f, tlev, INK, 3.2, index_every=3, index_width=5)
    save("17-monogram-to", svg(body, PAPER, view=(60, 0, 300, 300)))

    # ----- round 3: ridges with open counters, lines flowing through the p -----
    def ridges(seed=4, amp=5, stroke=23, merge=0.0):
        with warped(seed, 300, amp):
            o1, p, o2 = letters_ridge(stroke=stroke)
        g = smin(smin(o1, p, merge), o2, merge) if merge else np.minimum(np.minimum(o1, p), o2)
        return -g

    rlev = [-1, -0.75, -0.5, -0.25, -0.03]
    f = ridges()
    save("18-ridge-terrain", svg(T.format(c=INK) + strokes(f, rlev, INK, 2.6), PAPER))
    save("19-ridge-terrain-dark", svg(T.format(c=INK_D) + strokes(f, rlev, ACCENT_D, 2.6), PAPER_D))

    f = ridges(seed=8, amp=6, stroke=23, merge=0.9)
    lv = [-1.6, -1.3, -1, -0.75, -0.5, -0.25, -0.03]
    body = T.format(c=INK) + strokes(f, lv, INK, 2.4)
    body += f'<circle cx="{P}" cy="{CY}" r="9" fill="{ACCENT}"/>'
    save("20-ridge-range", svg(body, PAPER))

    f = ridges(seed=4, amp=5, stroke=27)
    shapes = "".join(path_d(l) for l in contours(f, -1.0))
    body = (f'<path d="{T_path(stem=50, bar=48, w=160)}" fill="{INK}"/>'
            f'<path d="{shapes}" fill="{INK}" fill-rule="evenodd"/>')
    body += strokes(f, [-0.72, -0.44, -0.16], PAPER, 2.2)
    save("21-ridge-solid", svg(body, PAPER))

    return made


if __name__ == "__main__":
    for name in build(sys.argv[1] if len(sys.argv) > 1 else "brand/explorations/svg"):
        print(name)
