# GOTEET 0.5.0 — reference concepts and implementation

Sources reviewed 21 October 2026. Upstream READMEs describe their capabilities, not verified GOTEET capabilities.

| Source | Adapted in GOTEET | Boundary |
|---|---|---|
| [PdfCraft](https://github.com/storytold/pdfcraft), d695bc5 | In-app page navigation, zoom, extractable page text | Renderer is PDF.js, not PdfCraft Rust engine. No PDF editing/signing. |
| [WordCraft](https://github.com/storytold/wordcraft), e3bb06a | Readable document page, heading navigation, paragraph search, bold/italic and tables | Custom bounded DOCX reader. No pagination fidelity, embedded images, review or editing. |
| [FilmCraft](https://github.com/storytold/filmcraft), 70f0fc7 | In-app video transport, ±10 seconds and playback speed | Electron-supported codecs only; no timeline editing/export. |
| [LightCraft](https://github.com/storytold/lightcraft) | Original-preserving image viewing, zoom and rotation | View-only rotation. No RAW development or image processing engine. |
| [Craft AI integrations](https://github.com/storytold/craft-ai-integrations) | Reviewed shared model connections, capability routing, consent and job status against existing Models/Agents | Rust adapter layer not installed. Provider-by-tool routing remains a future integration. Upstream itself reports hosted providers unverified. |
| [Mailspring](https://github.com/Foundry376/Mailspring) | Folder/search/message list/reading pane | GOTEET uses read-only Gmail OAuth. No GPL code or sync engine copied, no send or attachment downloads. |
| [Plane](https://github.com/makeplane/plane) | Compact workspace navigation, appearance/density choices; existing project status/charts retained | Reuses the day-difference helper in src/vendor/plane-dates.ts from Plane commit 6c16585c81bac84d8ce67110c70a69b1bf07f10b under AGPL-3.0; license included in public/licenses. Calendar grid and status board adapted to GOTEET data. No claim of Plane feature parity. |

PDF.js 6.4.299 is integrated and lazy-loaded. Apache 2.0 license ships at `dist/licenses/pdfjs-LICENSE.txt`. ArtCraft brands/assets are not copied. Original GOTEET branding retained.

Drive: native Google docs/sheets/slides export to PDF; supported binary files open in the shared viewer. Maximum 50 MB per preview; private cache capped at 500 MB. No cloud writes. File contents require `drive.readonly` consent. Existing metadata snapshots remain distinguishable from downloaded contents.

Appearance: Graphite, Midnight and Paper themes, four accent presets/custom color, density, reduced-motion preference. Existing Inter typography deliberately retained despite generic-font detector warning because it is the established desktop design. Imported mail is plain text with remote images/scripts suppressed; sensitive-subject exclusions remain. These exclusions are best-effort subject matching, not a classifier guarantee.

## CAD import in 0.5.3

STEP/IGES/BREP conversion uses [occt-import-js 0.0.23](https://github.com/kovacsv/occt-import-js), under LGPL-2.1, with its OpenCascade dependencies. `scripts/prepare_cad.cjs` copies the runtime and license notices from the installed npm package into the app on build. Worker conversion is bounded to 25 MB and 30 seconds. The README screenshots use the upstream simple-basic-cube fixture. Three.js renders the result without rewriting source geometry. Storytold remains a concept reference, not the document rendering engine.
