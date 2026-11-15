# README design system

[← TwinSite](../../README.md) · [Verification](VERIFICATION.md) · [Asset source](build_assets.py)

The visual direction draws from [desagencydes-rgb](https://github.com/desagencydes-rgb): warm cosmic accents, large editorial artwork, image-based navigation and constellation-like diagrams. The cover is the TwinSite team banner (warm orange and gold on near-black); every generated diagram uses the same palette so the page reads as one system. The cover is illustrative: its feature icons, coordinates and branch label are decorative, not application output or a scientific map. Decorative planets are not to scale.

## GitHub rendering contract

The README uses relative image/file links, standard Markdown, HTML image/link/picture tags, tables, anchors and `details`/`summary`. These keep navigation and expandable catalogs inside GitHub. The architecture has both a static SVG and Mermaid source.

There is no JavaScript, WebGL, iframe, embedded custom stylesheet or HTML canvas in the README. Actual interactive 3D is supplied by the existing application when run locally. No public demo or hosted 3D URL is invented.

Motion is a small looping GIF, not an SVG animation dependency. A `picture` source requests the still PNG for `prefers-reduced-motion: reduce`; an explicit still-image link works if the renderer ignores that media query. The GIF does not contain essential information that is absent from text. Static SVGs use intrinsic dark backgrounds so the design remains legible in GitHub light and dark themes.

GitHub documentation: [images and picture](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax), [collapsed sections](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/organizing-information-with-collapsed-sections), [diagrams](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams), [image-rendering limitations](https://docs.github.com/en/repositories/working-with-files/using-files/working-with-non-code-files). Rendering may differ between GitHub, local Markdown viewers and mobile clients; do not rely on SVG scripting/animation.

## Assets

| Files | Purpose |
| :--- | :--- |
| `assets/twinsite-cover.jpg` | 1672 × 941 team cover artwork (supplied raster, not generated) |
| `assets/telemetry.svg` | 1600 × 230 “what ships today” counts strip |
| `assets/nav-*.svg` | Four 780 × 330 linked navigation cards |
| `assets/section-01.svg` … `section-05.svg` | Five section banners |
| `assets/architecture.svg` | 1600 × 640 data-flow illustration |
| `assets/signal.gif` | 1280 × 180, 48 frames, 80 ms/frame, infinite loop |
| `assets/signal-static.png` | Animation's still counterpart |
| `build_assets.py` | Deterministic illustration/GIF generator; no network or application imports |

Rebuild from the repository root with Python and Pillow:

```bash
python docs/readme/build_assets.py
```

SVGs use Arial/Helvetica/sans-serif fallbacks. The GIF generator uses Arial on macOS and Pillow's default font elsewhere; pixel-identical text across operating systems is not promised. The committed images require no build step or scheduled workflow to display. The badge row uses static shields.io images; if that service is unavailable only the badges disappear, and their text is repeated elsewhere in the README. The telemetry counts come from the implementation audit and must be updated with it.

The documentation's working count and route inventory should be checked against Flask registrations when routes change. Update source claims, the atlas and the file manifest together. Keep generated artwork and helper scripts under `docs/readme/`; application code and scientific data are outside this redesign's change scope.
