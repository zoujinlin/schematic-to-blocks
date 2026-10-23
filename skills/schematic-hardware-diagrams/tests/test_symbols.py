"""Regression checks for circuit-function symbols and consistent exports."""
import base64
import contextlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import electrical_symbols as symbols
import render_diagrams as renderer
import spec_schema
from pypdf import PdfReader

NS={'s':'http://www.w3.org/2000/svg'}


def gallery():
    names=[name for name in symbols.SYMBOLS if name!='none']
    nodes=[dict(id='part-'+name,x=30+(i%4)*390,y=180+(i//4)*210,w=350,h=180,
                title=name,model='U'+str(i+1),symbol=name,
                category=('data','control','power','reference')[i%4]) for i,name in enumerate(names)]
    return dict(name='symbol-gallery',locale='en',title='Electrical functions',
                pages=[dict(slug='functions',title='Electrical functions',nodes=nodes,edges=[])])


class SymbolTests(unittest.TestCase):
    def setUp(self):
        parent=Path.cwd()/'tmp'/'symbol-tests';parent.mkdir(parents=True,exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(dir=parent);self.base=Path(self.temporary.name)

    def tearDown(self):self.temporary.cleanup()

    def render(self,document,formats='svg,pdf,drawio,html',theme='dark'):
        spec=self.base/'input.json';spec.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            return renderer.main([str(spec),'--out',str(self.base/'out'),'--formats',formats,'--theme',theme])

    def test_all_symbols_export_to_editable_child_stencils_and_pdf(self):
        document=gallery()
        schema=json.loads((ROOT/'references/diagram.schema.json').read_text(encoding='utf-8'))
        spec_schema.validate(document,schema)
        self.assertEqual(set(schema['$defs']['node']['properties']['symbol']['enum']),set(symbols.SYMBOLS))
        result=self.render(document)
        files={Path(p).suffix:Path(p) for p in result['files']}
        svg=ET.parse(files['.svg'])
        drawn=svg.findall('.//s:g[@data-symbol]',NS)
        self.assertEqual({g.get('data-symbol') for g in drawn},set(symbols.SYMBOLS)-{'none'})
        self.assertFalse(svg.findall('.//s:g[@class="node-icon"]',NS))
        graph=ET.parse(files['.drawio'])
        stencils=[c for c in graph.findall('.//mxCell') if c.get('data-symbol')]
        self.assertEqual(len(stencils),len(drawn))
        for cell in stencils:
            name=cell.get('data-symbol')
            self.assertEqual(cell.get('parent'),'n-part-'+name)
            self.assertEqual(cell.get('connectable'),'0')
            style=cell.get('style');self.assertNotIn('image=',style)
            packed=re.search(r'shape=stencil\(([^)]+)\)',style)[1]
            decoded=unquote(zlib.decompress(base64.b64decode(packed),-15).decode('ascii'))
            stencil=ET.fromstring(decoded)
            self.assertEqual(stencil.get('name'),name)
            self.assertTrue(stencil.find('foreground') is not None)
            self.assertEqual(cell.find('mxGeometry').get('x'),'16')
        pdf=PdfReader(files['.pdf']);text=pdf.pages[0].extract_text()
        for mark in ('A/D','D/A','REF','CTRL'):self.assertIn(mark,text)
        self.assertIn(b' c',pdf.pages[0].get_contents().get_data())  # Winding curves survive PDF export.
        html=files['.html'].read_text(encoding='utf-8')
        self.assertIn('data-symbol',html);self.assertNotIn('node-icon-bg',html)

    def test_explicit_function_wins_over_caption_model_kind_and_color(self):
        document=gallery();node=document['pages'][0]['nodes'][0]
        document['pages'][0]['nodes']=[node]
        node.update(title='ADC',model='U1 · ADC_GENERIC',kind='power',category='power',symbol='amplifier')
        result=self.render(document,'svg,drawio')
        root=ET.parse(next(p for p in result['files'] if p.endswith('.svg')))
        self.assertEqual([g.get('data-symbol') for g in root.findall('.//s:g[@data-symbol]',NS)],['amplifier'])
        self.assertIn('ADC_GENERIC',ET.tostring(root.getroot(),encoding='unicode'))

    def test_missing_or_none_symbol_uses_text_and_reclaims_title_space(self):
        document=gallery();document['pages'][0]['nodes']=document['pages'][0]['nodes'][:2]
        del document['pages'][0]['nodes'][0]['symbol']
        document['pages'][0]['nodes'][1]['symbol']='none'
        result=self.render(document,'svg,drawio')
        root=ET.parse(next(p for p in result['files'] if p.endswith('.svg')))
        self.assertFalse(root.findall('.//s:g[@data-symbol]',NS))
        for layer,node in zip(root.findall('.//s:g[@data-node]',NS),document['pages'][0]['nodes']):
            title=layer.find('s:text',NS)
            self.assertEqual(float(title.get('x')),node['x']+18)

    def test_unknown_symbol_rejected_before_writing_in_both_entrypoints(self):
        document=gallery();document['pages'][0]['nodes'][0]['symbol']='generic-chip'
        schema=json.loads((ROOT/'references/diagram.schema.json').read_text(encoding='utf-8'))
        with self.assertRaises(spec_schema.SchemaError):spec_schema.validate(document,schema)
        with self.assertRaisesRegex(ValueError,'Unknown electrical symbol'):self.render(document,'svg')
        self.assertFalse((self.base/'out').exists())

    def test_examples_select_function_not_package_and_survive_theme_change(self):
        expected=[['connector','adc','isolation','controller','connector','dc-dc'],
                  ['connector','amplifier','adc','connector','voltage-reference']]
        for locale in ('en','zh-Hans'):
            document=json.loads((ROOT/f'assets/example.{locale}.json').read_text(encoding='utf-8'))
            self.assertEqual([[n['symbol'] for n in p['nodes']] for p in document['pages']],expected)
            for theme in ('dark','light'):
                result=self.render(document,'svg,html',theme)
                roots=[ET.parse(p) for p in result['files'] if p.endswith('.svg')]
                self.assertEqual([[g.get('data-symbol') for g in r.findall('.//s:g[@data-symbol]',NS)] for r in roots],expected)
                for root in roots:
                    self.assertEqual(root.getroot().get('data-theme'),theme)
                    self.assertTrue(root.findall('.//s:text[@class="symbol-label"]',NS))

    def test_digital_isolation_symbol_keeps_channel_conductors_separate(self):
        # A continuous horizontal conductor across the barrier would imply a short.
        previous=None
        for primitive in symbols.geometry('isolation'):
            for op,*point in primitive['commands']:
                if op=='L' and previous:
                    if previous[1]==point[1]:
                        self.assertFalse(min(previous[0],point[0])<20 and max(previous[0],point[0])>24)
                previous=point


if __name__=='__main__':unittest.main()
