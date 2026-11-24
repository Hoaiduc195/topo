# Topo logo

The word as one landform: the T is a mesa, the "opo" three summits, the p and the last o sharing a
saddle, with a cobalt pin on the highest point. Every line is a contour of one height field, drawn by
[`../final_logo.py`](../final_logo.py).

## Which file

| Use | File |
| --- | --- |
| README header, site hero, slides | `svg/topo-logo-light.svg`, `svg/topo-logo-dark.svg` (1200 × 520, with background and fading terrain) |
| On any background, small or busy places | `svg/topo-wordmark-light.svg` (for light grounds), `svg/topo-wordmark-dark.svg` (for dark grounds); transparent, readable down to about 110 px wide |
| App icon, avatar | `svg/topo-icon-light.svg`, `svg/topo-icon-dark.svg`; PNG at 512 and 1024 |
| A top bar or nav, 30–36 px tall | `svg/topo-bar-wordmark.svg`: every contour of the logo's word, wobble included, drawn with fixed screen-width lines (non-scaling strokes) so it stays crisp at 34–42 px. The viewer's top bar and its PNG export use these paths (`bar_word` in `final_logo.py`); change them there and paste into `viewer/shell.html` |
| Mark on its own, 16–24 px | `svg/topo-mark.svg`: the T mesa in two clean rings. The viewer's favicon uses these paths (`mark_paths`); paste changes into the icon link in `viewer/topo.template.html` |
| Browser tab | `svg/favicon.svg` (follows the browser's light or dark theme), `favicon.ico` (16, 32, 48) |
| Home-screen and PWA icons | `png/apple-touch-icon.png` (180), `png/icon-192.png`, `png/icon-512.png` |
| Link previews, GitHub social preview | `png/topo-social-light.png`, `png/topo-social-dark.png` (1280 × 640) |

PNG copies of the logo and wordmark come at 1× and @2×.

## Colours

| | Light | Dark |
| --- | --- | --- |
| Ground | `#ecebe4` | `#0a0e14` |
| Lines, T | `#1a2226` | lines `#5f78f0` → `#c4cfff` by height, T `#f3f5fa` |
| Pin | `#2346cc` | `#ffffff` |

These are the viewer's paper, ink and cobalt. The dark palette comes from the A02 concept.

## In a page head

```html
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta property="og:image" content="/topo-social-light.png">
```

## In a README

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="brand/logo/svg/topo-logo-dark.svg">
  <img alt="Topo" src="brand/logo/svg/topo-logo-light.svg" width="600">
</picture>
```

## Rebuilding

```bash
python3 -I brand/final_logo.py export brand/logo
```

That writes the SVGs. For the PNGs, run `python3 -I brand/rasterize.py` (a local server on port 4182
that saves what the page sends back), open `http://127.0.0.1:4182/rasterize.html` in a browser and
wait for "done", then pack the ICO:

```bash
python3 -I brand/rasterize.py ico
```
