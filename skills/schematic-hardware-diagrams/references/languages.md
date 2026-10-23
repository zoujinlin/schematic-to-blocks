# Language and fonts

The agent selects language from the request. `--locale auto --prompt-file request.txt` is a convenience detector, not an instruction interpreter: “reply in German” must be resolved by the agent and passed as `--locale de`. The source PDF language is not an output-language signal.

Legend locales: `zh-Hans`, `zh-Hant`, `en`, `ja`, `ko`, `de`, `fr`, `es`, `pt`, `it`, `ru`, `ar`, `he`. Regional aliases are accepted. For another language, supply its locale plus a `legend` object containing translated `data`, `control`, `power`, and `reference`. Translate all prose in JSON while preserving electrical identifiers.

Examples: “分析原理图并绘制框图” → `zh-Hans`; “Analyze this schematic” → `en`; “Erstelle ein Hardware-Blockdiagramm” → `de`; “请用英文输出” → `en` because explicit selection wins.

## HTML controls

English and Simplified Chinese UI captions are built in. For other languages, supply a translated top-level `ui` object with exactly the keys in `UI_EN` in [html_viewer.py](../scripts/html_viewer.py). Read that dictionary when authoring a localized HTML view; it is the single control-key reference. Include navigation, themes, motion/reduced-motion, viewport/export controls, cards, evidence-kind captions and hints. Missing translations fail explicitly rather than silently mixing languages. Translate prose in `details` and `evidence.note` too; preserve electrical/source identifiers and the stored `basis` enum values. The viewer translates those enum values for display through its `basis_*` captions.

## Font coverage

Common Windows/macOS/Linux fonts are discovered locally. Unicode output requires installed matching glyphs. Override with `--font font.ttf --bold-font bold.ttf`; TTC files accept `--font-index`. The skill does not bundle or download fonts. Missing glyphs cause an explicit error instead of empty squares. Obtain a suitable font only within the user's authorized dependency-installation scope; never change output language to bypass a font problem.

On Debian/Ubuntu, `fonts-wqy-zenhei` provides a TrueType CJK collection recognized by the renderer. Some Noto/PingFang collections contain CFF outlines that ReportLab cannot embed; provide a TrueType-outline font for direct PDF generation, or use HTML/browser print. The renderer tries available fonts and checks coverage rather than assuming every `.ttc` can be embedded.

## RTL and complex scripts

SVG includes locale and RTL direction metadata and uses browser shaping. Preserve logical identifier order. The ReportLab PDF backend refuses text requiring shaping it cannot provide. Use browser PDF export of SVG, or another native-shaping backend with matching fonts, then inspect the result. This is a backend limitation, not a language-selection limitation. Never deliver disconnected Arabic glyphs or reversed part numbers as a successful PDF. Do not mirror actual signal direction just because the page's reading direction is RTL.
