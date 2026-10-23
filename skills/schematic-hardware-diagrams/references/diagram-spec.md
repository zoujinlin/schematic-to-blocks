# Diagram JSON

One UTF-8 document defines a drawing set. Use stable ASCII object IDs. The default canvas is 1600 × 1200 drawing units. Translation is the agent's responsibility.

The canonical machine schema is [diagram.schema.json](diagram.schema.json). `schematic.py validate` applies it before rendering. `schema_version: 1`, localized `summary`, `unresolved` strings and source `evidence` records may accompany the drawing set.

The bundled standard-library validator implements the keyword subset used by this fixed schema. It does not accept external schemas/references or need a separate validation package. The schema is also readable by Draft 2020-12 tools.

```json
{
  "name": "board-architecture", "locale": "en", "title": "Hardware architecture",
  "pages": [{
    "slug": "00-overview", "title": "Architecture overview", "subtitle": "Signal flow",
    "nodes": [
      {"id": "input", "x": 60, "y": 300, "w": 320, "h": 190, "title": "Sensor input", "model": "J1", "lines": ["Differential signal"], "kind": "external"},
      {"id": "adc", "x": 600, "y": 300, "w": 360, "h": 190, "title": "Acquisition", "model": "U1 · ADC_MODEL", "lines": ["Conversion and filtering"]}
    ],
    "edges": [{"source": "input", "target": "adc", "points": [[380,395],[600,395]], "kind": "data", "label": "Analog"}]
  }]
}
```

- `name`: safe output basename, no directories. CLI can override `locale`.
- `theme`: `dark` (default) or `light`; `--theme` overrides it for all requested formats. Theme tokens and semantic SVG classes keep HTML and static exports consistent. Use light for paper-oriented output.
- Optional `legend`: translated captions keyed by `data/control/power/reference`. Optional `palette`: overrides for these four hex colors.
- Page: unique `slug`, `title`, `subtitle`, arrays below. Keep provenance in a separate evidence record or non-rendered metadata.
- Node: `id/x/y/w/h/title`, optional `model/lines/kind`. Kinds: `normal`, `external`, `interface`, `power`, `power_external`, `reference`, `annotation`, `optional`. Uncertainty needs explicit prose, not only a dashed frame.
- Optional node `category`: `data/control/power/reference` for its semantic color; otherwise derived from power/reference kind or defaults to data. SVG nodes and edges use stable `data-node` / `data-edge` group identities; do not reconstruct the graph from drawing order.
- Node `details`: localized `function` and `principle` strings, `interfaces` and `power` string arrays, and `uncertainty` string. These form the HTML device card. `evidence` arrays on nodes/edges refer to top-level evidence IDs.
- Top-level `evidence`: records with unique `id`, `source` (basename or manufacturer URL), `basis` (`schematic/netlist/datasheet/inferred/ocr-candidate/synthetic`), optional `page`, `locator`, `note`. File-based schematic/netlist/OCR records require exact source `sha256`; locators retain page region, symbol UUID or net/pins. Synthetic examples must be labeled synthetic. Inferences remain explicitly marked even when they reference a source hash.
- Group: `x/y/w/h/title`, optional `id/fill/dash`. An identified group can intentionally receive a shared service.
- Junction: `id/x/y/kind`; drawn as a filled dot.
- Split bus edges at every explicit junction: a visible dot inside an unsplit edge is rejected because it would leave interactive graph traversal inconsistent with the drawing.
- Edge: bound `source/target`, orthogonal `points`, optional `label/kind/both/end_arrow`. `both` adds a source head; `end_arrow` defaults true. Use false for plain bus trunks. Endpoints must match borders or junction coordinates.
- `texts`: annotations with `text/x/y`, optional `size/color/bold/anchor`. Color is a palette key or hex; anchor is `start` or `middle`.
- `notes`: `text/y`; reserve footer below y=1150. Notes wrap within page width.

Edge labels are placed automatically in clear space. For a failed placement, widen gaps, shorten a label without losing meaning, or put detail in the device block. Do not disable checks or omit connections. Keep model strings intact; enlarge blocks or break intentionally between identifiers.

```text
python scripts/render_diagrams.py diagram.json --out output/hardware-diagrams --locale en --formats svg,pdf,drawio,png --poppler-dir /path/to/poppler/bin
python scripts/render_diagrams.py diagram.json --out output/hardware-diagrams --locale auto --prompt-file request.txt --formats svg,drawio
```

Outputs: per-page SVG, multi-page PDF and draw.io, optional PNG, manifest, and a ZIP containing only artifacts from this run. Locked files receive numbered alternate names recorded in the manifest. Source PDFs, runtimes and unrelated files are never packaged.

Dependencies: Python 3.10+, ReportLab; inspection uses pdfplumber/pypdf; PNG uses `pdftoppm`. See `requirements.txt`. Scripts do not install dependencies automatically.

For new work, use the schema-checked publication commands in [delivery.md](delivery.md):

```text
python <skill>/scripts/schematic.py validate diagram.json --formats html,svg,pdf,drawio
python <skill>/scripts/schematic.py deliver diagram.json --out work/deliveries --theme dark --formats html,svg,pdf,drawio,png --poppler-dir /path/to/poppler/bin
python <skill>/scripts/schematic.py demo work/demo --locale en --theme light
```

The low-level renderer also accepts `html` and `--validate-only`. Only the high-level CLI applies JSON Schema and evidence gates and publishes complete releases. UI localization is documented in [languages.md](languages.md).
