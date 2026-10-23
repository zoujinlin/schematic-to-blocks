#!/usr/bin/env python3
"""Extract page text and word positions; optionally render pages for visual analysis."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--poppler-dir', type=Path)
    parser.add_argument('--scale-to', type=int, default=2400)
    args = parser.parse_args()
    source = args.pdf.resolve(strict=True)
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        import pdfplumber
    except ImportError as exc:
        raise SystemExit('pdfplumber is required; use the host dependency runtime or requirements.txt') from exc
    result = {'source': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'pages': [],
              'coordinate_system': 'word boxes: x0/top/x1/bottom, PDF points from top-left',
              'warning': 'Text and labels do not establish connectivity; inspect rendered pages.'}
    with pdfplumber.open(source) as document:
        for number, page in enumerate(document.pages, 1):
            text = page.extract_text(layout=False) or ''
            words = page.extract_words() or []
            text_path = args.out / f'page-{number:03d}.txt'
            text_path.write_text(text, encoding='utf-8')
            result['pages'].append({'page': number, 'width': float(page.width), 'height': float(page.height),
                                    'text_file': text_path.name, 'characters': len(text.strip()),
                                    'ocr_candidate': len(text.strip()) < 80,
                                    'words': [{k: w[k] for k in ('text', 'x0', 'top', 'x1', 'bottom')} for w in words]})
    (args.out / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.render:
        exe = (args.poppler_dir / ('pdftoppm.exe' if __import__('os').name == 'nt' else 'pdftoppm')) if args.poppler_dir else shutil.which('pdftoppm')
        if not exe or not Path(exe).is_file():
            raise SystemExit('Rendering needs pdftoppm on PATH or --poppler-dir. Extracted text was preserved.')
        subprocess.run([str(exe), '-scale-to', str(args.scale_to), '-png', str(source), str(args.out / 'page')], check=True)
    print(json.dumps({'pages': len(result['pages']), 'ocr_candidates': [p['page'] for p in result['pages'] if p['ocr_candidate']], 'output': str(args.out.resolve())}, ensure_ascii=False))

if __name__ == '__main__':
    main()
