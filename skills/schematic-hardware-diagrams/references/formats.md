# Format adapters and evidence limits

Contents select the reader; `.sch` can mean KiCad, EAGLE XML or proprietary binary data.

| Input | Direct extraction | Connectivity / additional step |
|---|---|---|
| PDF, including scans | Text, word boxes, dimensions, SHA256; optional PNG rendering and OCR | Visually trace wires, junctions and scoped net labels |
| PNG/JPEG/TIFF/BMP/WebP | Normalized images, dimensions, SHA256; optional OCR; separate image frames | Visual evidence only |
| KiCad 6+ `.kicad_sch` | Top-level symbol properties, wires, labels, child-sheet names | Inventory/geometry only; optional native KiCad CLI XML export resolves net membership |
| Legacy KiCad `.sch` | Component inventory | Upgrade/export in KiCad; combine PDF and XML netlist |
| EAGLE XML `.sch` | Parts, sheets, explicit net pinrefs | Gate/pin membership; hierarchical modules reported partial, requiring flattened export |
| EasyEDA **Std** JSON | LIB captions/properties, wires, raw labels; single sheet or `schematics[].dataStr` | Pin transforms, net flags and bus aliases are not solved; inspect PDF or add checked netlist |
| KiCad XML `.net` / `.xml` | Components, sheet paths, named-net pin members | Explicit membership; no inferred signal direction |
| Altium `.SchDoc`, OrCAD `.dsn/.opj`, EasyEDA Pro `.epro/.eprj`, legacy binary EAGLE | Detected as requiring export | Export schematic PDF in original EDA tool; include a pin-level netlist when available |

Native geometry is not a resolved circuit graph. Child-sheet files are listed, not recursively opened. Inspect each required file and prefer the native root-project netlist to resolve libraries, hidden power pins, bus members and hierarchical instances. Keep EAGLE sheet scope when reconciling labels. Do not infer package-pad mapping from gate pin names. XML entity declarations are rejected; ordinary EAGLE DTD references are not fetched.

```text
python <skill>/scripts/schematic.py inspect board.kicad_sch --out work/source --kicad-cli /path/to/kicad-cli
python <skill>/scripts/schematic.py inspect board.sch --out work/source
python <skill>/scripts/schematic.py inspect easyeda.json --out work/source
python <skill>/scripts/schematic.py inspect board.net --out work/netlist
```

Native export uses `kicad-cli sch export netlist --format kicadxml --output native-netlist.xml input.kicad_sch`. To produce the visual reference, use the installed version's `kicad-cli sch export pdf --help`, retaining root-project libraries. Original schematic files are not modified.

## Offline OCR

Native Tesseract is the default engine. Install it and relevant language data separately. Poppler renders PDF pages. Only PDF pages with fewer than 80 extracted characters are selected for OCR; mixed text/raster pages can be rasterized separately and inspected as images.

```text
python <skill>/scripts/schematic.py inspect scan.tiff --out work/scan --ocr --ocr-lang eng+chi_sim --tessdata /local/tessdata
python <skill>/scripts/schematic.py inspect scan.pdf --out work/scan --render --ocr --poppler-dir /path/to/poppler/bin
```

Use `--tesseract-dir` if the executable is not on PATH. Tesseract.js is also supported when already installed:

```text
python <skill>/scripts/schematic.py inspect scan.png --out work/ocr --ocr --ocr-engine js --node /path/to/node --tesseract-js /path/to/node_modules/tesseract.js --tessdata /local/tessdata --ocr-lang eng+chi_sim
```

The JS adapter requires local uncompressed `.traineddata` models. No models, fonts or updates are downloaded by this package. OCR records candidate text/coordinates; inspect ambiguous characters, polarity, decimal values, net suffixes and pin numbers against image crops. OCR never automatically confirms a connection.

## Authoritative references

- [KiCad schematic specification](https://dev-docs.kicad.org/en/file-formats/sexpr-schematic/), [CLI](https://docs.kicad.org/master/en/cli/cli.html)
- [EAGLE XML storage](https://help.autodesk.com/cloudhelp/ENU/Fusion-ECAD/files/ECD-ULP-OBJECT-TYPES.htm), [net pin references](https://help.autodesk.com/cloudhelp/ENU/Fusion-ECAD/files/ECD-ULP-NET.htm)
- [EasyEDA Std format](https://docs.easyeda.com/en/DocumentFormat/EasyEDA-Document-Format/index.html)
