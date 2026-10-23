# Electrical symbols and function identifiers

Assign `symbol` after identifying the circuit function from schematic/netlist evidence and, where necessary, the manufacturer's documentation. The field is independent of language, package, node `kind`, domain color and model string. Translate explanatory prose; retain the ASCII symbol ID.

```json
{"id": "gain", "x": 350, "y": 350, "w": 270, "h": 240,
 "title": "Gain stage", "model": "U4 · PGA_MODEL", "symbol": "amplifier",
 "lines": ["Programmable gain"], "evidence": ["gain-circuit"]}
```

| ID | Representation | Select when the circuit performs |
|---|---|---|
| `connector` | Contact circles and leads | Physical signal or power connection |
| `amplifier` | Single-input gain triangle | Amplification; internal differential topology is not established |
| `op-amp` | Triangle with +/− inputs | Operational amplification with identified non-inverting/inverting inputs |
| `adc` | A/D conversion block | Analog-to-digital conversion |
| `dac` | D/A conversion block | Digital-to-analog conversion |
| `isolation` | Logic waveforms separated by a double barrier | Digital signal transfer between galvanically separated domains |
| `dc-dc` | Diagonally divided block, DC marks on both sides | DC-to-DC power conversion; isolation requires separate evidence |
| `dc-source` | Voltage-source circle with +/− | External DC source, not a generic power input connector |
| `voltage-reference` | REF functional block | Precision voltage reference generation |
| `controller` | CTRL functional block | Digital control/processing; does not imply a particular CPU or MCU |
| `low-pass-filter` | Flat response with high-frequency roll-off | Verified low-pass filtering |
| `clock` | Square-wave trace | Clock or oscillator generation |
| `resistor` | Zigzag resistor | A resistive element or explicitly modeled resistive function |
| `capacitor` | Parallel plates | A non-polarized capacitor |
| `inductor` | Winding | An inductive element |
| `switch` | Open contact and movable arm | A switching contact; not a generic semiconductor switch or relay coil |
| `none` | Text-only block | Function remains unresolved or no suitable representation is available |

Electrical symbols and functional block notation serve different abstraction levels. A/D, D/A, REF and CTRL name a module function; they are not detailed device pin symbols. This library does not claim complete IEC/IEEE symbol-standard compliance. Compact leads/contact pairs do not specify actual pin/channel count. Do not infer interface direction from these glyphs; authored edges carry direction.

For a composite overview block, select the principal function and list the remaining functions in its captions/cards. Separate them in a module view. Do not depict a PGA/ADC chain as an op amp alone, a digital isolator as a transformer, or a power connector as a voltage source. If a known function has no suitable entry, use a clear functional caption with `none` and record the limitation. Extend the shared geometry and schema together when adding a reusable symbol; do not add an arbitrary Unicode/emoji glyph or a backend-only icon.

`scripts/electrical_symbols.py` defines vector paths, circles, rectangles and technical labels once. SVG inherits domain/theme colors; PDF draws the same primitives; draw.io uses an inline editable stencil attached to its parent node. These symbols require no icon font or network asset.

References for notation and export structure: [TI: op-amp schematic symbol and terminals](https://www.ti.com/document-viewer/lit/html/SSZT348), [TI: digital isolation and separate power paths](https://www.ti.com/document-viewer/lit/html/slla553), [draw.io: custom shapes](https://www.drawio.com/docs/tutorials/custom-shapes/), [draw.io: inline stencil encoding](https://github.com/jgraph/drawio/wiki/Shapes-and-Stencils).
