# Receipts and complete drawing-set publication

`schematic.py` emits one JSON receipt and exits 0 on success, 1 on operation failure. `--json` is accepted anywhere; JSON is always the format. Invalid CLI syntax uses argparse's standard usage and exit 2.

`validate` checks JSON Schema, source hash/reference requirements, glyphs, node geometry, bound orthogonal connectors, device crossings and label clearance without writing files. It preflights the requested backends. It does not establish source truth or visual quality; `visual_review: required` remains explicit.

`deliver --out <directory>` validates, renders all requested files in staging, builds the manifest/ZIP, renames the complete set into an immutable timestamp/UUID directory, then atomically updates `latest.json`. Rendering failure cleans staging and preserves the old entry. Source schematics are not copied; authored evidence/notes are included, so review them before sharing. ZIPs include only this run's generated artifacts, with relative basenames in the manifest.

Open the receipt's absolute `entrypoint`. `latest.json` is a machine pointer, not an HTML redirect. Older release folders remain available. If pointer replacement fails due to locks/permissions, the new complete release remains, the old pointer is preserved, and the command reports an error. No force-delete or background watcher is used. Low-level `render_diagrams.py` retains per-file atomic writes/numbered locked-file alternates; use `schematic.py deliver` for complete-set publication.

HTML uses semantic SVG layers with the shared dark/light theme tokens. It supports module navigation, keyboard/click node and connection cards, evidence, search, direct-neighbor focus, authored upstream/downstream reach, pointer pan, bounded cursor-anchored zoom, presentation mode and optional connection motion. Reduced-motion preferences disable animation. Motion represents authored arrow direction only; it is not observed hardware activity.

HTML SVG/PNG exports include the complete current diagram in the selected theme, clearing temporary selection/reach/pan/zoom state. Browser print fits the entire current page; direct PDF/draw.io contain all pages. Raster export depends on the browser's SVG/canvas support; a failure leaves SVG and printing available. Keys: T theme, M motion, F presentation, +/− zoom, 0 fit, Escape reset. No external CSS/JS/fonts or services are required to view the artifact. Matching local glyph coverage is still needed for the chosen language.

Sources are text locators, not embedded documents or fetched network links. The JSON script payload is escaped and detail text uses textContent. The source assets `viewer.html`, `viewer.css` and `viewer.js` are inlined into one delivered HTML; no sibling asset files are needed to open it.

| Issue code | Repair |
|---|---|
| `SPEC_SCHEMA`, `SPEC_NUMBER` | Correct indicated JSON path/type/non-finite value |
| `EVIDENCE_HASH`, `EVIDENCE_DUPLICATE`, `EVIDENCE_REFERENCE` | Fix hash, unique IDs or missing evidence records |
| `CONNECTOR_ENDPOINT` | Bind endpoint coordinates to source/target border or junction |
| `CONNECTOR_CROSSING`, `CONNECTOR_ORTHOGONAL`, `CONNECTOR_ZERO_LENGTH` | Repair orthogonal waypoints without changing circuit meaning |
| `LABEL_CLEARANCE`, `TEXT_OVERFLOW`, `NODE_OVERLAP`, `CANVAS_BOUNDS` | Increase space or move details into cards |
| `FONT_COVERAGE`, `SCRIPT_SHAPING` | Supply matching font or use browser-shaped HTML/SVG |
| `EXPORT_REQUIRED`, `FORMAT_UNSUPPORTED`, `DEPENDENCY_MISSING` | Use a supported export or install missing dependency |
| `OPERATION_FAILED` | Inspect evidence message and repair the underlying operation |

Each issue contains `code`, `subject`, `evidence`, and supported `repair` suggestions. Schema failures identify a JSON path; geometry messages include page/edge/node and coordinates where available. Preserve stable IDs, evidence and unrelated layouts during revisions. Rerun gates, then visually review the new artifact; a passing receipt alone does not certify electrical correctness.
