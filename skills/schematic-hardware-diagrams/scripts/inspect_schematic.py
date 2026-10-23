#!/usr/bin/env python3
"""Read schematic evidence without claiming inferred electrical connectivity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import xml.etree.ElementTree as ET


class InputError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def sexpr(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    stack, roots = [], []
    for token in tokens:
        if token == '(':
            node = []
            (stack[-1] if stack else roots).append(node)
            stack.append(node)
            if len(stack) > 100:
                raise InputError('INPUT_DEPTH', 'S-expression nesting exceeds 100')
        elif token == ')':
            if not stack:
                raise InputError('INPUT_SYNTAX', 'Unexpected closing parenthesis')
            stack.pop()
        else:
            if not stack:
                raise InputError('INPUT_SYNTAX', 'Atom outside S-expression')
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if stack or len(roots) != 1:
        raise InputError('INPUT_SYNTAX', 'Incomplete S-expression')
    return roots[0]


def children(node, key):
    return [v for v in node if isinstance(v, list) and v and v[0] == key]


def child(node, key, default=None):
    values = children(node, key)
    return values[0][1:] if values else default


def detect(path):
    data = path.read_bytes()
    head = data[:1000000].lstrip(b'\xef\xbb\xbf \r\n\t')
    suffix = path.suffix.lower()
    if head.startswith(b'%PDF-'):
        return 'pdf'
    if head.startswith(b'(kicad_sch'):
        return 'kicad'
    if head.startswith(b'EESchema Schematic File Version'):
        return 'kicad-legacy'
    if b'<eagle' in head[:3000]:
        return 'eagle'
    if b'<export' in head[:3000] and suffix in ('.xml', '.net'):
        return 'kicad-netlist'
    if suffix in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'):
        return 'image'
    if head.startswith((b'{', b'[')):
        raw = json.loads(data.decode('utf-8-sig'))
        if isinstance(raw, dict) and ('shape' in raw or 'schematics' in raw):
            return 'easyeda'
    vendor = {'.schdoc': 'Altium Designer', '.dsn': 'OrCAD Capture', '.opj': 'OrCAD Capture',
              '.epro': 'EasyEDA Pro', '.eprj': 'EasyEDA Pro', '.sch': 'legacy binary EDA'}
    if suffix in vendor:
        raise InputError('EXPORT_REQUIRED', f'{vendor[suffix]}: export a schematic PDF and, if available, a pin-level netlist from the original application. Native binary parsing is not implemented.')
    raise InputError('FORMAT_UNSUPPORTED', 'Unrecognized format. Use schematic PDF, raster image, KiCad, EAGLE XML, EasyEDA Std JSON, or KiCad XML netlist.')


def base_record(path, kind):
    return {'schema_version': 1, 'format': kind,
            'source': {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()},
            'components': [], 'sheets': [], 'wires': [], 'labels': [], 'nets': [], 'warnings': [],
            'connectivity': 'unresolved', 'unresolved': []}


def kicad(path, result):
    root = sexpr(path.read_text(encoding='utf-8-sig'))
    result['version'] = child(root, 'version')
    for symbol in children(root, 'symbol'):
        props = {v[1]: v[2] for v in children(symbol, 'property') if len(v) >= 3}
        result['components'].append({'ref': props.get('Reference', ''), 'model': props.get('Value', ''),
            'library_id': child(symbol, 'lib_id'), 'uuid': child(symbol, 'uuid'),
            'unit': child(symbol, 'unit'), 'at': child(symbol, 'at'), 'properties': props,
            'locator': {'symbol_uuid': child(symbol, 'uuid')}})
    for wire in children(root, 'wire'):
        pts = child(wire, 'pts', [])
        result['wires'].append({'points': [v[1:] for v in pts if isinstance(v, list) and v[0] == 'xy']})
    for tag in ('label', 'global_label', 'hierarchical_label'):
        for label in children(root, tag):
            result['labels'].append({'name': label[1], 'kind': tag, 'at': child(label, 'at')})
    for sheet in children(root, 'sheet'):
        props = {v[1]: v[2] for v in children(sheet, 'property') if len(v) >= 3}
        result['sheets'].append({'properties': props, 'uuid': child(sheet, 'uuid')})
    result['warnings'].append('Inventory and wire/label geometry only. Resolve library pins, power symbols, buses and hierarchical instances with KiCad CLI XML netlist export before asserting pin connectivity. Child sheet files are listed but not recursively opened.')


def legacy(path, result):
    text = path.read_text(encoding='utf-8-sig')
    for block in re.findall(r'\$Comp\s*(.*?)\$EndComp', text, re.S):
        props, lib, ref = {}, '', ''
        for line in block.splitlines():
            parts = shlex.split(line)
            if parts and parts[0] == 'L' and len(parts) >= 3:
                lib, ref = parts[1:3]
            if len(parts) >= 3 and parts[0] == 'F':
                props[parts[1]] = parts[2]
        result['components'].append({'ref': props.get('0', ref), 'model': props.get('1', ''), 'library_id': lib})
    for line in text.splitlines():
        if line.startswith(('Text Label ', 'Text GLabel ', 'Text HLabel ')):
            result['labels'].append({'locator': line})
    result['warnings'].append('Legacy KiCad inventory only; use KiCad to upgrade/export PDF and XML netlist. No library pin or wire connectivity resolution.')


def xml_root(path):
    data = path.read_bytes()
    if b'<!ENTITY' in data.upper():
        raise InputError('XML_ENTITY', 'XML entity declarations are not accepted')
    return ET.fromstring(data)


def eagle(path, result):
    root = xml_root(path)
    schematic = root.find('./drawing/schematic')
    if schematic is None:
        raise InputError('NOT_SCHEMATIC', 'EAGLE XML does not contain a schematic')
    for part in schematic.findall('./parts/part'):
        result['components'].append({'ref': part.get('name'), 'model': part.get('value', ''),
            'library': part.get('library'), 'deviceset': part.get('deviceset'), 'device': part.get('device')})
    for number, sheet in enumerate(schematic.findall('./sheets/sheet'), 1):
        result['sheets'].append({'sheet': number})
        for net in sheet.findall('./nets/net'):
            result['nets'].append({'name': net.get('name'), 'sheet': number,
                'pins': [{'ref': p.get('part'), 'gate': p.get('gate'), 'pin': p.get('pin')}
                         for p in net.findall('./segment/pinref')]})
    result['connectivity'] = 'explicit-net-membership'
    if schematic.find('./modules/module') is not None or schematic.findall('.//moduleinst'):
        result['connectivity'] = 'partial'
        result['warnings'].append('Hierarchical modules are not expanded; export a flattened netlist for module-instance connectivity.')
    result['warnings'].append('EAGLE gate/pin names are preserved. Package pad mapping and electrical flow direction are not inferred.')


def netlist(path, result):
    root = xml_root(path)
    for comp in root.findall('./components/comp'):
        result['components'].append({'ref': comp.get('ref'), 'model': comp.findtext('value', ''),
            'sheet': comp.find('sheetpath').attrib if comp.find('sheetpath') is not None else {}})
    for net in root.findall('./nets/net'):
        result['nets'].append({'name': net.get('name'), 'code': net.get('code'),
            'pins': [dict(p.attrib) for p in net.findall('node')]})
    result['connectivity'] = 'explicit-net-membership'
    result['warnings'].append('Net membership has no signal direction or operating principle; determine these from circuit context and manufacturer data.')


def easyeda(path, result):
    raw = json.loads(path.read_text(encoding='utf-8-sig'))
    docs = raw.get('schematics', [{'dataStr': raw}])
    unknown = set()
    for number, entry in enumerate(docs, 1):
        doc = entry.get('dataStr', entry)
        if isinstance(doc, str):
            doc = json.loads(doc)
        head = doc.get('head', {})
        doctype = str(head.get('docType', '1')) if isinstance(head, dict) else str(head).split('~')[0]
        if doctype != '1':
            raise InputError('NOT_SCHEMATIC', 'EasyEDA document is not a standard schematic (docType 1)')
        if not isinstance(doc.get('shape'), list):
            raise InputError('EASYEDA_VARIANT', 'Expected EasyEDA Std compressed shape array; export Std source JSON or PDF')
        result['sheets'].append({'sheet': number})
        for index, shape in enumerate(doc['shape']):
            fields = shape.split('#@$')[0].split('~')
            tag = fields[0]
            locator = {'sheet': number, 'shape_index': index}
            if tag == 'LIB':
                attrs = fields[3].split('`')
                props = dict(zip(attrs[::2], attrs[1::2]))
                captions = [s.split('~') for s in shape.split('#@$')[1:] if s.startswith('T~')]
                ref = next((s[12] for s in captions if len(s) > 12 and s[1] == 'P'), '')
                model = next((s[12] for s in captions if len(s) > 12 and s[1] == 'N'), props.get('name', ''))
                result['components'].append({'ref': ref, 'model': model, 'properties': props,
                    'at': fields[1:3], 'locator': locator, 'raw_shape': shape})
            elif tag == 'W':
                coords = fields[1].split()
                result['wires'].append({'points': list(zip(coords[::2], coords[1::2])), 'locator': locator})
            elif tag in ('N', 'F'):
                result['labels'].append({'kind': tag, 'raw_shape': shape, 'locator': locator})
            elif tag not in ('J', 'O', 'T', 'PL', 'PG', 'R', 'A', 'E', 'Pimage', 'I', 'B', 'BE'):
                unknown.add(tag)
    result['warnings'].append('EasyEDA Std inventory/geometry only; compressed pin transforms, net flags and bus aliases are not resolved into electrical nets. Verify visually or supply an exported netlist.')
    if unknown:
        result['warnings'].append('Unprocessed shape commands: ' + ', '.join(sorted(unknown)))


def program(name, directory=None):
    candidate = Path(directory) / (name + ('.exe' if os.name == 'nt' else '')) if directory else shutil.which(name)
    if candidate and Path(candidate).is_file():
        return str(candidate)
    raise InputError('DEPENDENCY_MISSING', f'{name} is required for this operation; add to PATH or provide its directory')


def ocr_image(image, base, args):
    if args.ocr_engine == 'tesseract':
        exe = program('tesseract', args.tesseract_dir)
        command = [exe, str(image), str(base), '-l', args.ocr_lang, '--psm', '11']
        if args.tessdata:
            command += ['--tessdata-dir', str(args.tessdata)]
        subprocess.run(command + ['tsv', 'txt'], check=True, capture_output=True, timeout=180)
        return {'text_file': base.with_suffix('.txt').name, 'coordinates_file': base.with_suffix('.tsv').name,
                'basis': 'ocr-candidate', 'coordinate_system': 'pixels from top-left', 'requires_visual_confirmation': True}
    node = program('node') if not args.node else str(args.node)
    script = Path(__file__).with_name('ocr_image.cjs')
    command = [node, str(script), str(image), str(base), '--lang', args.ocr_lang]
    if not args.tessdata:
        raise InputError('DEPENDENCY_MISSING', 'Tesseract.js requires --tessdata with local .traineddata files; no models are downloaded automatically')
    command += ['--tessdata', str(args.tessdata)]
    if args.tesseract_js:
        command += ['--module', str(args.tesseract_js)]
    subprocess.run(command, check=True, capture_output=True, timeout=180)
    return {'text_file': base.with_suffix('.txt').name, 'coordinates_file': base.with_suffix('.json').name,
            'basis': 'ocr-candidate', 'coordinate_system': 'pixels from top-left', 'requires_visual_confirmation': True}


def inspect_file(source, out, args):
    source = Path(source).resolve(strict=True)
    kind = detect(source)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = base_record(source, kind)
    if kind in ('kicad', 'kicad-legacy', 'eagle', 'easyeda', 'kicad-netlist'):
        {'kicad': kicad, 'kicad-legacy': legacy, 'eagle': eagle, 'easyeda': easyeda, 'kicad-netlist': netlist}[kind](source, result)
    elif kind == 'pdf':
        import pdfplumber
        result['pages'] = []
        with pdfplumber.open(source) as pdf:
            for number, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ''
                text_file = f'page-{number:03d}.txt'
                (out / text_file).write_text(text, encoding='utf-8')
                item = {'page': number, 'width': float(page.width), 'height': float(page.height),
                    'text_file': text_file, 'ocr_candidate': len(text.strip()) < 80,
                    'coordinate_system': 'PDF points from top-left',
                    'words': [{k: w[k] for k in ('text', 'x0', 'top', 'x1', 'bottom')} for w in page.extract_words()]}
                result['pages'].append(item)
                if args.render or (args.ocr and item['ocr_candidate']):
                    prefix = out / f'page-{number:03d}'
                    subprocess.run([program('pdftoppm', args.poppler_dir), '-f', str(number), '-l', str(number),
                        '-scale-to', str(args.scale_to), '-singlefile', '-png', str(source), str(prefix)],
                        check=True, capture_output=True, timeout=180)
                    item['image'] = prefix.with_suffix('.png').name
                    if args.ocr and item['ocr_candidate']:
                        item['ocr'] = ocr_image(prefix.with_suffix('.png'), out / f'ocr-{number:03d}', args)
        result['warnings'].append('Text/OCR does not establish connectivity; inspect rendered pages and trace wires/net labels. OCR selection by text count is heuristic; rasterize a mixed page separately if OCR is needed there.')
    elif kind == 'image':
        from PIL import Image, ImageOps
        result['pages'] = []
        with Image.open(source) as image:
            for index in range(getattr(image, 'n_frames', 1)):
                image.seek(index)
                frame = ImageOps.exif_transpose(image).convert('RGB')
                output = out / f'page-{index+1:03d}.png'
                frame.save(output)
                item = {'page': index+1, 'width': frame.width, 'height': frame.height, 'image': output.name,
                    'ocr_candidate': True, 'coordinate_system': 'pixels from top-left'}
                if args.ocr:
                    item['ocr'] = ocr_image(output, out / f'ocr-{index+1:03d}', args)
                result['pages'].append(item)
        result['warnings'].append('Raster evidence; OCR strings and all electrical connections require visual confirmation.')
    if args.kicad_cli and kind in ('kicad', 'kicad-legacy'):
        netpath = out / 'native-netlist.xml'
        subprocess.run([str(args.kicad_cli), 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '--output', str(netpath), str(source)], check=True, capture_output=True, timeout=180)
        exported = base_record(netpath, 'kicad-netlist')
        netlist(netpath, exported)
        result['nets'] = exported['nets']
        result['connectivity'] = exported['connectivity']
        result['netlist_source'] = exported['source']
    result['unresolved'].append('Operating principles, circuit roles and signal direction require engineering analysis; this helper extracts evidence only.')
    (out / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def add_options(parser):
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--poppler-dir', type=Path)
    parser.add_argument('--scale-to', type=int, default=3200)
    parser.add_argument('--ocr', action='store_true')
    parser.add_argument('--ocr-engine', choices=('tesseract', 'js'), default='tesseract')
    parser.add_argument('--ocr-lang', default='eng')
    parser.add_argument('--tesseract-dir', type=Path)
    parser.add_argument('--tessdata', type=Path)
    parser.add_argument('--tesseract-js', type=Path)
    parser.add_argument('--node', type=Path)
    parser.add_argument('--kicad-cli', type=Path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    add_options(parser)
    args = parser.parse_args()
    result = inspect_file(args.source, args.out, args)
    print(json.dumps({'format': result['format'], 'output': str(args.out.resolve()),
                      'connectivity': result['connectivity']}, ensure_ascii=False))
