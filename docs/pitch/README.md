# TwinSite NASA Space Apps 2026 pitch

- `TwinSite_NASA_Space_Apps_2026.pptx`: editable deck, 14 main slides plus 4 technical appendix slides.
- `TwinSite_NASA_Space_Apps_2026.pdf`: visual preview.
- `contact_sheet.png`: overview of all slides.
- `speaker_script.md`: main presentation script and optional appendix notes.
- `SOURCES.md`: imagery, scientific evidence, implementation sources and caveats.
- `source/`: generation code and pinned evidence snapshots.
- `assets/`: NASA images and real application screenshots, including composed crops.
- `rendered/`: full-size slide previews.

## Rebuild on this workstation

The source uses the bundled `@oai/artifact-tool`, `sharp`, and the installed Presentations skill finalizer. Arial and Georgia are the selected fonts. Geometry is 1280 × 720 pixels (16:9). All text, scientific charts, tables and architecture shapes remain editable. Images are embedded.

Run `source/prepare_assets.mjs`, then `source/build_deck.mjs` with the bundled Node runtime. The `source/node_modules` symlink points to that runtime's packages. `build_deck.mjs` contains the installed skill/runtime paths, which need updating on another workstation. Preserve evidence JSON and the original screenshots to reproduce the exact scientific claims and image crops. The finalizer deliberately refuses to overwrite an existing final deck; use a new output filename when rebuilding a revision.

The local application's recorded run may not persist on another machine. The included screenshots and evidence snapshots make the presentation independent of the live service. The public image links and attribution are in `SOURCES.md`.
