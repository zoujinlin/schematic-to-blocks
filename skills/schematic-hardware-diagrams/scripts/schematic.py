#!/usr/bin/env python3
"""Inspect, validate and deliver schematic hardware diagrams with JSON receipts."""
import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class GateError(ValueError):
    def __init__(self, code, message, subject='document', repair=None):
        self.code, self.subject, self.repair = code, subject, repair or []
        super().__init__(message)


def read_json(path):
    def invalid(value):
        raise GateError('SPEC_NUMBER', 'Non-finite JSON number: '+value, 'number', ['Use finite coordinates'])
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=invalid)


def check_schema(raw):
    from spec_schema import validate as validate_schema, SchemaError
    try:
        validate_schema(raw, read_json(ROOT / 'references' / 'diagram.schema.json'))
    except SchemaError as error:
        subject = '/' + '/'.join(map(str, error.absolute_path))
        raise GateError('SPEC_SCHEMA', error.message, subject, ['Follow references/diagram.schema.json'])
    evidence = raw.get('evidence', [])
    evidence_ids = [e['id'] for e in evidence]
    if len(set(evidence_ids)) != len(evidence_ids):
        raise GateError('EVIDENCE_DUPLICATE', 'Evidence IDs must be unique', '/evidence', ['Assign a unique ID to each evidence record'])
    for index, ev in enumerate(evidence):
        if ev['basis'] in ('schematic', 'netlist', 'ocr-candidate') and not ev.get('sha256'):
            raise GateError('EVIDENCE_HASH', 'File evidence requires its source SHA256', f'/evidence/{index}', ['Copy the hash from inspect evidence.json'])
    for page in raw['pages']:
        for item in page['nodes'] + page['edges']:
            missing = set(item.get('evidence', [])) - set(evidence_ids)
            if missing:
                raise GateError('EVIDENCE_REFERENCE', 'Unknown evidence IDs: '+', '.join(sorted(missing)), page['slug'], ['Create the referenced evidence or correct its ID'])


def renderer_args(args, out, validate_only=False):
    result = [str(args.spec), '--out', str(out), '--formats', args.formats, '--locale', args.locale,
              '--font-index', str(args.font_index), '--theme', args.theme, '--no-archive']
    for key in ('font', 'bold_font', 'poppler_dir', 'prompt_file'):
        if getattr(args, key, None):
            result += ['--'+key.replace('_', '-'), str(getattr(args, key))]
    if validate_only:
        result.append('--validate-only')
    return result


def validate(args):
    raw = read_json(args.spec)
    check_schema(raw)
    import render_diagrams
    with contextlib.redirect_stdout(io.StringIO()):
        info = render_diagrams.main(renderer_args(args, Path.cwd(), True))
    warnings = []
    if not raw.get('evidence'):
        warnings.append('No source evidence supplied. Label the artifact illustrative; do not present it as a verified schematic analysis.')
    if any(not n.get('details', {}).get('principle') for p in raw['pages'] for n in p['nodes']):
        warnings.append('Some blocks lack an operating-principle detail card.')
    return {'ok': True, 'command': 'validate', 'schema_version': 1, 'checks': ['schema', 'evidence-references', 'geometry', 'text-glyphs', 'requested-backends'],
            'visual_review': 'required', 'warnings': warnings, **info}


def deliver(args):
    receipt = validate(args)
    import render_diagrams
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    release_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    release = out / release_id
    with tempfile.TemporaryDirectory(prefix='.candidate-', dir=out) as working:
        stage = Path(working)
        with contextlib.redirect_stdout(io.StringIO()):
            result = render_diagrams.main(renderer_args(args, stage))
        files = [Path(p) for p in result['files']]
        names = [p.name for p in files]
        if 'manifest.json' not in names:
            names.append('manifest.json')
        manifest = {**result, 'files': names, 'release': release_id, 'spec_sha256': hashlib.sha256(args.spec.read_bytes()).hexdigest(),
                    'visual_review': 'required'}
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        archive_name = read_json(args.spec)['name'] + '.zip'
        with zipfile.ZipFile(stage / archive_name, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                archive.write(stage / name, name)
        hashes = {name: hashlib.sha256((stage / name).read_bytes()).hexdigest() for name in names + [archive_name]}
        # Publish the entire immutable release only after every requested renderer succeeds.
        os.replace(stage, release)
    entrypoint = next((name for name in names if name.endswith('.html')), None)
    pointer = {'release': release_id, 'entrypoint': entrypoint, 'files': names, 'sha256': hashes,
               'archive': archive_name, 'visual_review': 'required'}
    fd, temp = tempfile.mkstemp(prefix='.latest-', suffix='.json', dir=out)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(pointer, stream, ensure_ascii=False, indent=2)
        os.replace(temp, out / 'latest.json')
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return {**receipt, 'command': 'deliver', 'release': str(release),
            'entrypoint': str(release / entrypoint) if entrypoint else None,
            'archive': str(release / archive_name), 'latest': str(out / 'latest.json'), 'sha256': hashes}


def doctor(_args):
    modules = {name: importlib.util.find_spec(name) is not None for name in ('reportlab', 'pdfplumber', 'pypdf', 'PIL')}
    return {'ok': all(modules.values()), 'command': 'doctor', 'python': sys.version.split()[0],
            'modules': modules, 'optional_tools': {name: shutil.which(name) for name in ('pdftoppm', 'kicad-cli', 'tesseract', 'node')},
            'notes': ['Optional tools may also be supplied as explicit paths.', 'OCR models are local and are never fetched by this package.',
                      'Inspect extracts evidence. The agent determines operating principles and authors the block diagram JSON.']}


def format_args(parser, with_spec=True):
    if with_spec:parser.add_argument('spec', type=Path)
    parser.add_argument('--formats', default='html,svg,pdf,drawio')
    parser.add_argument('--locale', default='auto')
    parser.add_argument('--prompt-file', type=Path)
    parser.add_argument('--font', type=Path)
    parser.add_argument('--bold-font', type=Path)
    parser.add_argument('--font-index', type=int, default=0)
    parser.add_argument('--poppler-dir', type=Path)
    parser.add_argument('--theme', choices=('auto','dark','light'), default='auto')


def demo(args):
    from localization import normalize_locale
    locale='en' if args.locale=='auto' else normalize_locale(args.locale)
    if locale not in ('en','zh-Hans'):
        raise GateError('EXAMPLE_LOCALE','Built-in demos: en, zh-Hans. Author a localized JSON for other languages.')
    args.spec=ROOT/'assets'/('example.'+locale+'.json')
    return {**deliver(args),'command':'demo'}


def error_receipt(exc, command):
    message = str(exc)
    if isinstance(exc, GateError):
        code, subject, repair = exc.code, exc.subject, exc.repair
    else:
        rules = [('detached', 'CONNECTOR_ENDPOINT', ['Bind both ends to node borders or explicit junctions']),
                 ('lies inside a segment', 'CONNECTOR_JUNCTION', ['Split the edge at the explicit junction so geometry and graph agree']),
                 ('crosses node', 'CONNECTOR_CROSSING', ['Move connector waypoints outside node rectangles']),
                 ('Non-orthogonal', 'CONNECTOR_ORTHOGONAL', ['Use horizontal and vertical segments']),
                 ('zero-length', 'CONNECTOR_ZERO_LENGTH', ['Remove duplicate consecutive waypoints']),
                 ('overlapping nodes', 'NODE_OVERLAP', ['Separate node rectangles']),
                 ('overflow', 'TEXT_OVERFLOW', ['Increase node height/width or shorten its visible caption']),
                 ('no clear location', 'LABEL_CLEARANCE', ['Increase spacing or move connector waypoints']),
                 ('outside page', 'CANVAS_BOUNDS', ['Keep geometry within 1600 by 1200']),
                 ('font', 'FONT_COVERAGE', ['Provide a font covering all output glyphs']),
                 ('cannot shape', 'SCRIPT_SHAPING', ['Use HTML/SVG and browser print for complex scripts'])]
        code, repair = next(((c, r) for token, c, r in rules if token in message), ('OPERATION_FAILED', ['Read the error evidence and repair the input or dependency']))
        if isinstance(exc, ImportError):
            code, repair = 'DEPENDENCY_MISSING', ['Install requirements.txt into the selected Python environment']
        if hasattr(exc, 'code'):
            code = exc.code
        subject = 'document'
    return {'ok': False, 'command': command, 'issues': [{'code': code, 'subject': subject, 'evidence': message, 'repair': repair}],
            'last_good_preserved': command in ('deliver', 'validate', 'demo')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('doctor').set_defaults(run=doctor)
    inspection = subs.add_parser('inspect')
    from inspect_schematic import add_options, inspect_file
    add_options(inspection)
    def inspect(args):
        data = inspect_file(args.source, args.out, args)
        return {'ok': True, 'command': 'inspect', 'format': data['format'], 'connectivity': data['connectivity'],
                'output': str(args.out.resolve()), 'components': len(data['components']), 'warnings': data['warnings']}
    inspection.set_defaults(run=inspect)
    check = subs.add_parser('validate');format_args(check);check.set_defaults(run=validate)
    delivery = subs.add_parser('deliver');format_args(delivery)
    delivery.add_argument('--out', type=Path, required=True);delivery.set_defaults(run=deliver)
    demonstration=subs.add_parser('demo');demonstration.add_argument('out',type=Path)
    format_args(demonstration,with_spec=False);demonstration.set_defaults(run=demo)
    # Receipts are always JSON. --json is accepted anywhere for familiar agent usage.
    argv = [a for a in (sys.argv[1:] if argv is None else argv) if a != '--json']
    args = parser.parse_args(argv)
    try:
        receipt = args.run(args)
    except Exception as exc:
        receipt = error_receipt(exc, args.command)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
