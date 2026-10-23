"""Exercise viewer logic against generated artifacts without a browser/network."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import schematic


class ViewerTests(unittest.TestCase):
    def test_generated_english_and_chinese_interactions(self):
        node=os.environ.get('SCHEMATIC_NODE') or shutil.which('node')
        if not node:self.skipTest('Node.js is optional; set SCHEMATIC_NODE to test viewer runtime')
        probe=subprocess.run([node,str(ROOT/'tests/check_viewer.cjs'),'--probe'],capture_output=True)
        if probe.returncode==2:self.skipTest('Run npm ci to install the development-only DOM parser')
        self.assertEqual(probe.returncode,0,probe.stderr)
        parent=Path.cwd()/'tmp'/'viewer-tests';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as working:
            for locale in ('en','zh-Hans'):
                with contextlib.redirect_stdout(io.StringIO()) as stream:
                    status=schematic.main(['deliver',str(ROOT/f'assets/example.{locale}.json'),'--out',str(Path(working)/locale),'--formats','html,svg'])
                receipt=json.loads(stream.getvalue());self.assertEqual(status,0,receipt)
                run=subprocess.run([node,str(ROOT/'tests/check_viewer.cjs'),receipt['entrypoint']],capture_output=True,text=True,encoding='utf-8')
                self.assertEqual(run.returncode,0,run.stderr)
                result=json.loads(run.stdout);self.assertTrue(result['ok']);self.assertEqual(result['cardsChecked'],11)


if __name__=='__main__':unittest.main()
