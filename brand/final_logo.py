"""Topo logo, round 4: one landform.

The T is a mesa (a flat top inside steep cliffs), the "opo" is a massif of three summits that share
their outer contours, and the land around the word keeps going, so its lower contours run out across
the frame and fade with distance from the word.

    python3 -I brand/final_logo.py brand/explorations/final   # the round-4 variants
    python3 -I brand/final_logo.py export brand/logo          # the shippable SVG set
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script's folder off the path
import contour_logo as cl  # noqa: E402

# ---------- canvas ----------
W, H = 1200, 520
cl.STEP = STEP = 1.5
XS = np.arange(0, W + STEP, STEP)
YS = np.arange(0, H + STEP, STEP)
cl.GX, cl.GY = np.meshgrid(XS, YS)

# ---------- letters (x-height 160, o radius 80) ----------
DX, DY = 150, 70
BASE = 270 + DY
XTOP = 110 + DY
R = (BASE - XTOP) / 2
CY = XTOP + R
O1, P, O2 = 330 + DX, 532 + DX, 734 + DX
T_X, T_TOP, T_W, T_BAR, T_STEM = 168 + DX, 40 + DY, 156, 40, 42

LIGHT = dict(bg="#ecebe4", word="#1a2226", word_lo="#1a2226", field="#1a2226", tee="#1a2226", pin="#2346cc", glow=False)
DARK = dict(bg="#0a0e14", word="#c4cfff", word_lo="#5f78f0", field="#3653d6", tee="#f3f5fa", pin="#ffffff", glow=True)


def sd_box(cx, cy, hw, hh, gx=None, gy=None):
    gx = cl.GX if gx is None else gx
    gy = cl.GY if gy is None else gy
    qx, qy = np.abs(gx - cx) - hw, np.abs(gy - cy) - hh
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0))
    inside = np.minimum(np.maximum(qx, qy), 0)
    return outside + inside


def sd_tee():
    bar = sd_box(T_X, T_TOP + T_BAR / 2, T_W / 2, T_BAR / 2)
    stem = sd_box(T_X, (T_TOP + BASE) / 2, T_STEM / 2, (BASE - T_TOP) / 2)
    return np.minimum(bar, stem)


def mix(c1, c2, t):
    t = min(max(t, 0), 1)
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def smooth_d(line, spacing=4.5, passes=2):
    """Resample a traced contour evenly, round it off with Chaikin passes, and write the path."""
    closed = math.dist(line[0], line[-1]) < STEP * 1.5
    pts = [line[0]]
    acc = 0.0
    for a, b in zip(line, line[1:]):
        acc += math.dist(a, b)
        if acc >= spacing:
            pts.append(b)
            acc = 0.0
    if closed:
        pts = pts[:-1] if len(pts) > 3 and math.dist(pts[-1], pts[0]) < spacing else pts
    elif pts[-1] != line[-1]:
        pts.append(line[-1])
    for _ in range(passes):
        if len(pts) < 4:
            break
        new = [] if closed else [pts[0]]
        ring = pts + [pts[0]] if closed else pts
        for p, q in zip(ring, ring[1:]):
            new += [(0.75 * p[0] + 0.25 * q[0], 0.75 * p[1] + 0.25 * q[1]),
                    (0.25 * p[0] + 0.75 * q[0], 0.25 * p[1] + 0.75 * q[1])]
        if not closed:
            new.append(pts[-1])
        pts = new
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return d + ("Z" if closed else "")


def smax(a, b, k):
    return -cl.smin(-a, -b, k)


# ---------- the landform ----------
TOP = 0.85          # mesa top level, also the first contour
STEP_LV = 0.2       # contour interval
CLIFF = 24.0        # px per level on the mesa cliffs (o hills use R = 80 px per level)
APRON, APRON_PX = 0.5, 74.0  # below the cliff the ground slopes off like the hills


def landform(seed=9, warp=6, field_px=62, crest=-0.3, tee="mesa", merge=0.3, with_opo=True, merge_po=0.9):
    t = sd_tee()
    if tee == "mesa":
        h_t = np.minimum(TOP, TOP - t / CLIFF)          # flat at TOP inside the T
    else:
        h_t = TOP - t / CLIFF                           # keeps rising inside: inline ridges
    h_t = np.maximum(h_t, APRON - np.maximum(t, 0) / APRON_PX)
    with cl.warped(seed, 320, warp):
        o1 = 1 - cl.d_hill(O1 + 6, CY - 4, 0.3, 2.5) / R
        o2 = 1 - cl.d_hill(O2 - 4, CY + 3, 0.3, -0.6) / R
        # The p: a summit plus a band hanging from each ring's left edge. With the stem line set
        # GAP px left of the summit, a ring of radius r gets a stem of half-width r - GAP whose
        # left side lines up with the ring's, so every ring wider than GAP is a p outline.
        bx, by, gap = P + 5, CY - 2, 58
        bowl = 1.08 - cl.d_hill(bx, by, 0.12, 0.9) / R
        stem = 1.08 - (cl.d_segment(bx - gap, by, bx - gap, BASE + 66) + gap) / R
        p = smax(bowl, stem, 0.06)
        opo = smax(smax(o1, p, merge), o2, merge_po)  # p and the last o share a saddle
        if not with_opo:
            opo = np.full_like(opo, -9.0)
        # the ridge the word stands on: contours below the crest run out across the frame
        wy = np.sqrt((cl.GY - (CY - 10)) ** 2 + 30 ** 2)
        ridge = crest - (wy - 30) / field_px + cl.noise(seed + 5, 700, 0.12)
    word = smax(h_t, opo, merge * 0.7)
    return smax(word, ridge, 0.35), word


def levels(lo=-4.0):
    out, lv = [], TOP
    while lv > lo:
        out.append(round(lv, 4))
        lv -= STEP_LV
    return out


def rdp(pts, tol):
    """Ramer-Douglas-Peucker: drop points that move the line by less than tol px."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-9
        best, idx = 0.0, None
        for i in range(a + 1, b):
            x0, y0 = pts[i]
            d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / norm
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def slim_d(line, tol=0.25):
    """Smooth, simplify, and write a contour as a compact relative path."""
    d = smooth_d(line)
    closed = d.endswith("Z")
    pts = [tuple(map(float, p.split(","))) for p in d.rstrip("Z")[1:].split(" L")]
    if closed and len(pts) > 4:
        half = len(pts) // 2   # simplify a ring as two open halves so its seam survives
        pts = rdp(pts[:half + 1], tol)[:-1] + rdp(pts[half:] + [pts[0]], tol)[:-1]
    else:
        pts = rdp(pts, tol)
    x0, y0 = round(pts[0][0], 1), round(pts[0][1], 1)
    out, px, py = [f"M{x0:g} {y0:g}l"], x0, y0
    for x, y in pts[1:]:
        x, y = round(x, 1), round(y, 1)
        dx, dy = round(x - px, 1), round(y - py, 1)
        out.append(f"{dx:g} {dy:g} ".replace(" -", "-"))
        px, py = x, y
    return "".join(out).rstrip() + ("z" if closed else "")


def render(theme, field=True, tee="mesa", pin=True, frame="oval", with_opo=True, view=None,
           weight=1.0, every=1, offset=0, bg=True, page=None):
    """page: the SVG's own viewBox when it should be larger than the drawn area (social images)."""
    h, _ = landform(tee=tee, with_opo=with_opo)
    lvls = levels() if field else [lv for lv in levels() if lv > -0.35]
    lvls = lvls[offset::every]
    hi, lo = lvls[0], lvls[-1]
    view = view or ((0, 0, W, H) if field else (160, 50, 880, 420))
    vx, vy, vw, vh = page or view
    defs, body = [], []
    if theme["glow"]:
        defs.append('<filter id="glow" x="-10%" y="-10%" width="120%" height="120%">'
                    '<feGaussianBlur stdDeviation="3" result="b"/>'
                    '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    word_groups, field_groups = [], []
    for i, lv in enumerate(lvls):
        in_word = lv > -0.35
        t = (lv - lo) / (hi - lo) if hi != lo else 1
        if in_word:
            wt = (lv + 0.35) / (TOP + 0.35)
            color, width, op = mix(theme["word_lo"], theme["word"], wt), (2.8 if i % 3 == 0 else 1.8) * weight, 1.0
        else:
            color, width = theme["field"], 1.8
            op = 0.18 + 0.62 * t ** 1.4
        ds = []
        for line in cl.contours(h, lv):
            xs, ys = [q[0] for q in line], [q[1] for q in line]
            if max(xs) - min(xs) < 18 and max(ys) - min(ys) < 18:
                continue  # stray fragment where two slopes meet
            if max(xs) < vx - 10 or min(xs) > vx + vw + 10 or max(ys) < vy - 10 or min(ys) > vy + vh + 10:
                continue  # outside the crop
            ds.append(slim_d(line))
        if ds:
            opa = "" if op >= 0.999 else f' opacity="{op:.2f}"'
            g = f'<path d="{"".join(ds)}" stroke="{color}" stroke-width="{width:g}"{opa}/>'
            (word_groups if in_word else field_groups).append(g)
    stroke_attrs = 'fill="none" stroke-linejoin="round" stroke-linecap="round"'
    tee_svg = ""
    if tee == "mesa":
        tee_d = "".join(slim_d(l, 0.2) for l in cl.contours(-sd_tee(), -0.0))
        tee_svg = f'<path d="{tee_d}" fill="{theme["tee"]}"/>'
    if field and frame == "oval":
        defs.append('<radialGradient id="fade" cx="50%" cy="50%" r="50%">'
                    '<stop offset="55%" stop-color="#fff"/><stop offset="100%" stop-color="#000"/></radialGradient>'
                    f'<mask id="m"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>')
        body.append(f'<g mask="url(#m)" {stroke_attrs}>{"".join(field_groups)}</g>')
    elif field_groups:
        body.append(f'<g {stroke_attrs}>{"".join(field_groups)}</g>')
    glow = ' filter="url(#glow)"' if theme["glow"] else ""
    body.append(f'<g{glow} {stroke_attrs}>{"".join(word_groups)}</g>')
    body.append(tee_svg)
    if pin:
        body.append(f'<circle cx="{P + 5}" cy="{CY - 2}" r="7" fill="{theme["pin"]}"{glow}/>')
    rect = f'<rect x="{vx:g}" y="{vy:g}" width="{vw:g}" height="{vh:g}" fill="{theme["bg"]}"/>' if bg else ""
    defs_svg = f'<defs>{"".join(defs)}</defs>' if defs else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:g} {vy:g} {vw:g} {vh:g}" '
            f'width="{vw:g}" height="{vh:g}">{defs_svg}{rect}{"".join(body)}</svg>')


ICON = (T_X - 230, (T_TOP + BASE) / 2 - 230, 460, 460)


def build(outdir):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    jobs = {
        "F1-mesa-field-light": dict(theme=LIGHT),
        "F2-mesa-field-dark": dict(theme=DARK),
        "F3-ridge-field-light": dict(theme=LIGHT, tee="ridge"),
        "F4-ridge-field-dark": dict(theme=DARK, tee="ridge"),
        "F5-mesa-compact-light": dict(theme=LIGHT, field=False, weight=2.0, every=2, offset=1),
        "F6-mesa-compact-dark": dict(theme=DARK, field=False, weight=2.0, every=2, offset=1),
        "F7-mesa-field-edge-light": dict(theme=LIGHT, frame="edge"),
        "F8-icon-light": dict(theme=LIGHT, frame="edge", with_opo=False, pin=False, view=ICON),
        "F9-icon-dark": dict(theme=DARK, frame="edge", with_opo=False, pin=False, view=ICON),
    }
    for name, kw in jobs.items():
        (out / f"{name}.svg").write_text(render(**kw))
        print(name)


MID_T = (T_TOP + BASE) / 2
FAVICON = (T_X - 176, MID_T - 176, 352, 352)
SOCIAL = (-40, -60, 1280, 640)   # GitHub social preview and Open Graph size, the logo centred


def favicon_svg(fixed=None):
    """The icon pared down for 16-32 px: the T and two rings close around it, drawn heavy.

    By default it follows the browser's light or dark theme; fixed="dark" bakes in the dark palette
    (used for the PNG and ICO files, where a theme switch isn't possible).
    """
    svg = render(LIGHT, field=False, with_opo=False, pin=False, every=2, offset=2, weight=6.5, view=FAVICON)
    svg = (svg.replace(f'fill="{LIGHT["bg"]}"', 'class="bg"')
              .replace(f'stroke="{LIGHT["word"]}"', 'class="ln"')
              .replace(f'fill="{LIGHT["tee"]}"', 'class="tee"'))
    light = ".bg{fill:#ecebe4}.ln{stroke:#1a2226}.tee{fill:#1a2226}"
    dark = ".bg{fill:#0a0e14}.ln{stroke:#8ea4ff}.tee{fill:#f3f5fa}"
    css = dark if fixed == "dark" else light + "@media (prefers-color-scheme:dark){" + dark + "}"
    return svg.replace(">", f"><style>{css}</style>", 1)


def mark_paths(size=24.0, cap=10.6, rings=(2.55, 5.1)):
    """The bar mark: the T and two contour rings around it, in a size x size box.

    Drawn without the warp, so the rings are clean at 16-24 px. Rings come first and the T last, the
    order the viewer's export expects (it strokes the rings and fills the last path, the T).
    """
    s = cap / (BASE - T_TOP)
    t = sd_tee()
    cx, cy = T_X, MID_T

    def scaled(line):
        pts = [((x - cx) * s + size / 2, (y - cy) * s + size / 2) for x, y in line]
        half = len(pts) // 2   # a ring starts and ends at one point: simplify it as two halves
        pts = rdp(pts[:half + 1], 0.04)[:-1] + rdp(pts[half:], 0.04)[:-1]
        return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + "Z"

    out = []
    for r in sorted(rings, reverse=True):
        line = max(cl.contours(-t, -r / s), key=len)
        out.append(scaled(line))
    out.append(scaled(max(cl.contours(-t, 0.0), key=len)))
    return out


def bar_word(height=42.0):
    """The logo's own word for the viewer's top bar: every contour of the word, with the wobble.

    Returns (viewBox, width, height, lines, T path, pin). Lines are (d, level 0..1, index line?,
    cliff?) in the logo's own coordinates; the viewer draws them at fixed screen widths (non-scaling
    strokes) so they stay crisp at bar size, and colours them by level the way the logo does.
    Cliff lines are the three that hug the T within about 10 px: at bar size they sit under a
    pixel apart, so light mode hides them and the filled T keeps clear paper around it.
    """
    _, word = landform()
    lvls = [lv for lv in levels() if lv > -0.35]
    t_right = T_X + T_W / 2 + 30
    lines = []
    for i, lv in enumerate(lvls):
        for l in cl.contours(word, lv):
            if max(q[0] for q in l) - min(q[0] for q in l) < 18 and max(q[1] for q in l) - min(q[1] for q in l) < 18:
                continue
            cliff = lv >= 0.45 - 1e-9 and min(q[0] for q in l) < t_right
            lines.append((l, round((lv + 0.35) / (TOP + 0.35), 2), i % 3 == 0, cliff))
    xs = [q[0] for l, *_ in lines for q in l]
    ys = [q[1] for l, *_ in lines for q in l]
    pad = 8
    x0, y0, x1, y1 = min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
    s = height / (y1 - y0)
    view = (round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1))
    out = [(slim_d(l, 0.6), t, idx, cliff) for l, t, idx, cliff in lines]
    # the T filled a little inside its edge, so a band of paper parts it from the rings at bar size
    tee = "".join(slim_d(l, 0.3) for l in cl.contours(-sd_tee(), 6.0))
    return view, round((x1 - x0) * s, 2), height, out, tee, (P + 5, CY - 2, 8)


def mark_svg(stroke="#1a2226", width=1.3):
    paths = mark_paths()
    rings = "".join(f'<path d="{d}"/>' for d in paths[:-1])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{stroke}" '
            f'stroke-width="{width}" stroke-linejoin="round">{rings}'
            f'<path d="{paths[-1]}" fill="{stroke}" stroke="none"/></svg>')


def export(outdir):
    """The shippable set: full logo, wordmark on any background, icon, favicon, social image."""
    out = Path(outdir) / "svg"
    out.mkdir(parents=True, exist_ok=True)
    jobs = {
        "topo-logo-light": dict(theme=LIGHT),
        "topo-logo-dark": dict(theme=DARK),
        "topo-wordmark-light": dict(theme=LIGHT, field=False, weight=2.0, every=2, offset=1, bg=False),
        "topo-wordmark-dark": dict(theme=DARK, field=False, weight=2.0, every=2, offset=1, bg=False),
        "topo-icon-light": dict(theme=LIGHT, frame="edge", with_opo=False, pin=False, view=ICON),
        "topo-icon-dark": dict(theme=DARK, frame="edge", with_opo=False, pin=False, view=ICON),
        "topo-social-light": dict(theme=LIGHT, page=SOCIAL),
        "topo-social-dark": dict(theme=DARK, page=SOCIAL),
    }
    for name, kw in jobs.items():
        (out / f"{name}.svg").write_text(render(**kw))
        print(name)
    (out / "favicon.svg").write_text(favicon_svg())
    (out / "favicon-dark.svg").write_text(favicon_svg(fixed="dark"))
    (out / "topo-mark.svg").write_text(mark_svg())
    print("mark (the viewer's favicon uses these paths)")
    view, w, h, lines, tee, (px, py, pr) = bar_word()
    paths = "".join(f'<path d="{d}" stroke-width="{1.25 if idx else 0.8}"/>' for d, _, idx, cliff in lines if not cliff)
    (out / "topo-bar-wordmark.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{" ".join(map(str, view))}" width="{w}" height="{h:g}">'
        f'<g fill="none" stroke="#1a2226" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke">'
        f'{paths.replace("<path ", "<path vector-effect=\"non-scaling-stroke\" ")}</g>'
        f'<path d="{tee}" fill="#1a2226"/><circle cx="{px}" cy="{py}" r="{pr}" fill="#2346cc"/></svg>')
    print("bar wordmark (the viewer's top bar and its export use these paths)")
    print("favicon")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        export(sys.argv[2] if len(sys.argv) > 2 else "brand/logo")
    else:
        build(sys.argv[1] if len(sys.argv) > 1 else "brand/explorations/final")
