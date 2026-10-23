"""Behavioral validation of multilingual output, geometry and packaging."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import render_diagrams as renderer
from localization import detect_locale,get_legend,LEGENDS
from pypdf import PdfReader

CAPTIONS={
 'en': ('Architecture overview','Synthetic acquisition interface','Sensor input','Differential voltage','Signal acquisition','Sampling and conversion','Controller interface','Data transfer','Data','Config','Synthetic example; no project data.'),
 'zh-Hans': ('硬件架构总览','合成采集接口样例','传感器输入','差分电压信号','信号采集','采样与模数转换','主控接口','转换数据传输','数据','配置','合成测试样例，不包含实际项目资料。'),
 'de': ('Hardware-Architektur','Synthetische Erfassungsschnittstelle','Sensoreingang','Differenzspannung','Signalerfassung','Abtastung und Wandlung','Steuerungsschnittstelle','Datenübertragung','Daten','Konfig.','Synthetisches Beispiel ohne Projektdaten.'),
 'ar': ('نظرة عامة على العتاد','مثال اصطناعي','دخل المستشعر','إشارة الجهد','اكتساب الإشارة','أخذ العينات','واجهة التحكم','نقل البيانات','بيانات','تحكم','مثال اصطناعي فقط'),
}
def fixture(locale):
    title,subtitle,it,ir,at,ar,ht,hr,data,control,note=CAPTIONS[locale]
    def n(id,x,w,title,model,role):return dict(id=id,x=x,y=310,w=w,h=230,title=title,model=model,lines=[role])
    return {'name':'localized-example','locale':locale,'title':title,'pages':[
      {'slug':'00-overview','title':title,'subtitle':subtitle,
       'nodes':[n('sensor',40,300,it,'J1 / VIN+',ir),n('adc',550,390,at,'U1 · ADC_GENERIC',ar),n('host',1160,400,ht,'J2 / SPI',hr)],
       'edges':[dict(source='sensor',target='adc',points=[[340,400],[550,400]],label=data),dict(source='adc',target='host',points=[[940,400],[1160,400]],label=data),dict(source='host',target='adc',points=[[1160,485],[940,485]],label=control,kind='control')],
       'notes':[dict(text=note,y=1080)]}]}

class RendererTests(unittest.TestCase):
    def setUp(self):
        parent=Path(os.environ.get('DIAGRAM_TEST_TMP',str(Path.cwd()/'tmp/diagram-tests')))
        parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.base=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def run_diagram(self,doc,formats='svg,pdf,drawio',out=None):
        spec=self.base/'input.json';spec.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):return renderer.main([str(spec),'--out',str(out or self.base/'out'),'--formats',formats])
    def test_request_language_detection(self):
        cases={'Analyze this schematic and draw hardware diagrams.':'en','请分析原理图并绘制硬件框图。':'zh-Hans','請分析這個電路圖並繪製硬體框圖。':'zh-Hant','この回路図を解析してください。':'ja','회로도를 분석해 주세요.':'ko','Erstelle ein Blockdiagramm aus diesem Schaltplan.':'de','Analysez ce schéma avec chaque circuit.':'fr','Analiza este esquema y crea un diagrama.':'es','Analise este esquemático elétrico.':'pt','Analizza questo schema per favore.':'it','Проанализируйте эту схему.':'ru','حلل هذا المخطط.':'ar','נתח את התרשים הזה.':'he'}
        for request,locale in cases.items():
            with self.subTest(locale=locale):self.assertEqual(detect_locale(request),locale)
        for locale in LEGENDS:self.assertEqual(set(get_legend(locale)),{'data','control','power','reference'})
    def test_localized_pdf_and_editable_connections(self):
        for locale in ('en','zh-Hans','de'):
            with self.subTest(locale=locale):
                result=self.run_diagram(fixture(locale),out=self.base/locale)
                self.assertEqual(result['locale'],locale);self.assertEqual(result['bound_endpoints'],6)
                pdf=PdfReader(next(p for p in result['files'] if p.endswith('.pdf')))
                self.assertEqual(len(pdf.pages),1);text=pdf.pages[0].extract_text()
                self.assertIn(CAPTIONS[locale][0],text);self.assertIn('ADC_GENERIC',text)
                for label in get_legend(locale).values():self.assertIn(label,text)
                graph=ET.parse(next(p for p in result['files'] if p.endswith('.drawio')))
                cells=graph.findall('.//mxCell');ids={c.get('id') for c in cells}
                for cell in cells:
                    if cell.get('edge')=='1':
                        self.assertIn(cell.get('source'),ids);self.assertIn(cell.get('target'),ids);self.assertIn('endFill=1;',cell.get('style'))
    def test_solid_apex_and_trimmed_shaft(self):
        result=self.run_diagram(fixture('en'),'svg,drawio')
        svg=ET.parse(next(p for p in result['files'] if p.endswith('.svg')));ns={'s':'http://www.w3.org/2000/svg'}
        heads=svg.findall('.//s:polygon',ns);shafts=svg.findall('.//s:polyline[@class="edge-shaft"]',ns)
        self.assertEqual(len(heads),3);self.assertEqual(heads[0].get('points').split()[0],'550,400')
        self.assertNotEqual(shafts[0].get('points').split()[-1],'550,400');self.assertEqual(heads[0].get('fill'),result['palette']['data'])
    def test_prompt_language_overrides_stale_document_locale(self):
        doc=fixture('zh-Hans');doc['locale']='en'
        spec=self.base/'input.json';spec.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
        prompt=self.base/'prompt.txt';prompt.write_text('请分析原理图并绘制框图。',encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            result=renderer.main([str(spec),'--out',str(self.base/'prompt-result'),'--prompt-file',str(prompt),'--formats','svg,drawio'])
        self.assertEqual(result['locale'],'zh-Hans')
    def test_detached_endpoint_rejected_before_output(self):
        doc=fixture('en');doc['pages'][0]['edges'][0]['points'][-1]=[540,400]
        with self.assertRaisesRegex(ValueError,'detached'):self.run_diagram(doc)
        self.assertFalse((self.base/'out').exists())
    def test_device_crossing_rejected(self):
        doc=fixture('en');doc['pages'][0]['nodes'].append(dict(id='obstacle',x=420,y=370,w=80,h=100,title='X'))
        with self.assertRaisesRegex(ValueError,'crosses node'):self.run_diagram(doc)
    def test_text_overflow_rejected(self):
        doc=fixture('en');doc['pages'][0]['nodes'][0]['lines']=['Long description']*20
        with self.assertRaisesRegex(ValueError,'overflow'):self.run_diagram(doc)
    def test_zip_excludes_unrelated_files(self):
        out=self.base/'out';out.mkdir();(out/'unrelated-private.txt').write_text('do not package',encoding='utf-8')
        result=self.run_diagram(fixture('en'),out=out)
        with zipfile.ZipFile(result['archive']) as archive:
            self.assertNotIn('unrelated-private.txt',archive.namelist());self.assertIn('manifest.json',archive.namelist())
    def test_locked_destination_preserved(self):
        target=self.base/'locked.pdf';target.write_bytes(b'original');original=renderer.os.replace
        def replace(source,destination):
            if Path(destination)==target:raise PermissionError('reader lock')
            original(source,destination)
        with patch.object(renderer.os,'replace',side_effect=replace):actual=renderer.write_output(target,b'new drawing')
        self.assertEqual(target.read_bytes(),b'original');self.assertEqual(actual.read_bytes(),b'new drawing');self.assertNotEqual(actual,target)
    def test_rtl_svg_and_pdf_shaping_guard(self):
        result=self.run_diagram(fixture('ar'),'svg,drawio');svg_path=next(p for p in result['files'] if p.endswith('.svg'))
        svg=ET.parse(svg_path);self.assertEqual(svg.getroot().get('lang'),'ar')
        self.assertTrue(any(e.get('direction')=='rtl' for e in svg.getroot().iter()));self.assertIn('ADC_GENERIC',Path(svg_path).read_text(encoding='utf-8'))
        with self.assertRaisesRegex(ValueError,'cannot shape'):self.run_diagram(fixture('ar'),'pdf')
    def test_output_path_traversal_rejected(self):
        doc=fixture('en');doc['name']='../unexpected'
        with self.assertRaisesRegex(ValueError,'Invalid output name'):self.run_diagram(doc)

if __name__=='__main__':unittest.main()
