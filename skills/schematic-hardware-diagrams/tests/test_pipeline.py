"""Format evidence, standalone viewer and last-good delivery behavior."""
import argparse
import contextlib
import io
import json
import re
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import inspect_schematic as intake
import schematic
import render_diagrams as renderer
from test_renderer import fixture


KICAD = '''(kicad_sch (version 20250114) (generator "synthetic-test")
 (symbol (lib_id "Connector_Generic:Conn_01x02") (at 10 20 0) (unit 1) (uuid "component-1")
   (property "Reference" "J1") (property "Value" "INPUT"))
 (wire (pts (xy 10 20) (xy 30 20)))
 (label "VIN+" (at 30 20 0))
 (sheet (uuid "child-1") (property "Sheetfile" "child.kicad_sch")))'''
EAGLE = '''<?xml version="1.0"?><!DOCTYPE eagle SYSTEM "eagle.dtd"><eagle version="9.6.2"><drawing><schematic>
 <parts><part name="U1" library="synthetic" deviceset="ADC_GENERIC" device="" value="ADC_GENERIC"/>
 <part name="J1" library="synthetic" deviceset="INPUT" value="INPUT"/></parts><sheets><sheet><nets>
 <net name="VIN+"><segment><pinref part="U1" gate="G$1" pin="IN+"/><pinref part="J1" gate="G$1" pin="1"/></segment></net>
 </nets></sheet></sheets></schematic></drawing></eagle>'''
NETLIST = '''<export version="E"><components><comp ref="U1"><value>ADC_GENERIC</value><sheetpath names="/" tstamps="/root/"/></comp></components>
 <nets><net code="1" name="VIN+"><node ref="U1" pin="1" pinfunction="IN+"/></net></nets></export>'''
EASYEDA = {'head': {'docType':'1'}, 'shape':[
 'LIB~100~200~package`SOIC8`name`ADC_GENERIC`~0~0~gge1#@$T~P~100~180~0~#000080~Arial~~~~~comment~U1~1~start~gge2#@$T~N~100~190~0~#000080~Arial~~~~~comment~ADC_GENERIC~1~start~gge3',
 'W~100 200 150 200~#008800~2~0~none~gge4', 'N~150~200~0~#000080~VIN+~gge5']}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        base = Path.cwd()/'tmp'/'pipeline-tests';base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base);self.base=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def inspect(self, name, data):
        source=self.base/name
        source.write_text(data, encoding='utf-8')
        parser=argparse.ArgumentParser();intake.add_options(parser)
        args=parser.parse_args([str(source),'--out',str(self.base/(name+'-evidence'))])
        return intake.inspect_file(source,args.out,args)

    def cli(self, command):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            status=schematic.main(command)
        return status,json.loads(output.getvalue())

    def spec(self, doc=None):
        path=self.base/'spec.json';path.write_text(json.dumps(doc or fixture('en')),encoding='utf-8');return path

    def test_kicad_inventory_not_guessed_nets(self):
        result=self.inspect('board.kicad_sch', KICAD)
        self.assertEqual(result['format'],'kicad');self.assertEqual(result['components'][0]['ref'],'J1')
        self.assertEqual(result['components'][0]['model'],'INPUT');self.assertEqual(result['labels'][0]['name'],'VIN+')
        self.assertEqual(result['connectivity'],'unresolved');self.assertEqual(result['nets'],[])
        self.assertEqual(result['sheets'][0]['properties']['Sheetfile'],'child.kicad_sch')

    def test_legacy_and_eagle_same_extension_detected_by_content(self):
        result=self.inspect('legacy.sch','EESchema Schematic File Version 4\n$Comp\nL Device:R R1\nF 0 "R1" H 0 0 50 0000 C CNN\nF 1 "10k" H 0 0 50 0000 C CNN\n$EndComp\n')
        self.assertEqual(result['components'][0]['model'],'10k')
        result=self.inspect('eagle.sch',EAGLE)
        self.assertEqual(result['format'],'eagle');self.assertEqual(result['connectivity'],'explicit-net-membership')
        self.assertEqual(result['nets'][0]['pins'][0],{'ref':'U1','gate':'G$1','pin':'IN+'})

    def test_eagle_hierarchy_is_reported_partial(self):
        result=self.inspect('hierarchy.sch',EAGLE.replace('<parts>','<modules><module name="M"/></modules><parts>'))
        self.assertEqual(result['connectivity'],'partial')

    def test_native_xml_netlist(self):
        result=self.inspect('board.net',NETLIST)
        self.assertEqual(result['components'][0]['model'],'ADC_GENERIC')
        self.assertEqual(result['nets'][0]['pins'][0]['pinfunction'],'IN+')

    def test_easyeda_and_multisheet_container(self):
        for name,data in [('standard.json',EASYEDA),('project.json',{'schematics':[{'dataStr':json.dumps(EASYEDA)}]})]:
            result=self.inspect(name,json.dumps(data))
            self.assertEqual(result['components'][0]['ref'],'U1');self.assertEqual(result['components'][0]['model'],'ADC_GENERIC')
            self.assertEqual(len(result['wires']),1);self.assertEqual(result['connectivity'],'unresolved')

    def test_vendor_binary_requires_export(self):
        path=self.base/'board.SchDoc';path.write_bytes(b'\xd0\xcf\x11\xe0')
        status,result=self.cli(['inspect',str(path),'--out',str(self.base/'out')])
        self.assertEqual(status,1);self.assertEqual(result['issues'][0]['code'],'EXPORT_REQUIRED')
        self.assertFalse((self.base/'out').exists())

    def test_xml_entities_and_incomplete_sexpr_rejected(self):
        with self.assertRaisesRegex(intake.InputError,'entity'):
            self.inspect('bad.sch',EAGLE.replace('<!DOCTYPE eagle SYSTEM "eagle.dtd">','<!DOCTYPE eagle [<!ENTITY x "private">]>'))
        with self.assertRaises(intake.InputError):
            self.inspect('bad.kicad_sch',KICAD[:-1])

    def test_multipage_image_evidence(self):
        from PIL import Image
        path=self.base/'scan.tiff'
        Image.new('RGB',(200,100),'white').save(path,save_all=True,append_images=[Image.new('RGB',(300,150),'white')])
        status,result=self.cli(['inspect',str(path),'--out',str(self.base/'scan')])
        self.assertEqual(status,0);self.assertEqual(result['format'],'image')
        evidence=json.loads((self.base/'scan/evidence.json').read_text())
        self.assertEqual(len(evidence['pages']),2);self.assertEqual(evidence['pages'][1]['width'],300)
        self.assertEqual(len(evidence['source']['sha256']),64)

    def test_pdf_text_evidence(self):
        from reportlab.pdfgen.canvas import Canvas
        path=self.base/'text.pdf';c=Canvas(str(path));c.drawString(30,500,'U1 ADC_GENERIC VIN+');c.showPage();c.save()
        status,result=self.cli(['inspect',str(path),'--out',str(self.base/'pdf')])
        self.assertEqual(status,0);ev=json.loads((self.base/'pdf/evidence.json').read_text())
        self.assertIn('ADC_GENERIC',(self.base/'pdf'/ev['pages'][0]['text_file']).read_text())
        self.assertTrue(ev['pages'][0]['ocr_candidate'])

    def test_schema_and_evidence_fail_closed(self):
        doc=fixture('en');doc['pages'][0]['nodes'][0]['x']='10'
        status,result=self.cli(['validate',str(self.spec(doc)),'--formats','svg'])
        self.assertEqual(status,1);self.assertEqual(result['issues'][0]['code'],'SPEC_SCHEMA')
        doc=fixture('en');doc['pages'][0]['nodes'][0]['evidence']=['missing']
        status,result=self.cli(['validate',str(self.spec(doc)),'--formats','svg'])
        self.assertEqual(status,1);self.assertEqual(result['issues'][0]['code'],'EVIDENCE_REFERENCE')

    def test_bundled_schema_rejects_invalid_typed_values(self):
        cases=[('w',True),('w',0),('kind','unknown'),('id','../escape'),('lines','not-an-array'),('details',{'unexpected':'value'})]
        for key,value in cases:
            with self.subTest(key=key,value=value):
                doc=fixture('en');doc['pages'][0]['nodes'][0][key]=value
                status,result=self.cli(['validate',str(self.spec(doc)),'--formats','svg'])
                self.assertEqual(status,1);self.assertEqual(result['issues'][0]['code'],'SPEC_SCHEMA')

    def test_delivery_portable_manifest_and_archive(self):
        path=self.spec();out=self.base/'out'
        status,result=self.cli(['deliver',str(path),'--out',str(out),'--formats','html,svg,drawio'])
        self.assertEqual(status,0,result);release=Path(result['release'])
        self.assertTrue(Path(result['entrypoint']).is_file())
        manifest=json.loads((release/'manifest.json').read_text())
        self.assertTrue(all(Path(f).name==f for f in manifest['files']))
        with zipfile.ZipFile(result['archive']) as archive:
            archived=json.loads(archive.read('manifest.json'));self.assertEqual(archived['release'],release.name)
        pointer=json.loads((out/'latest.json').read_text());self.assertEqual(pointer['release'],release.name)
        for name,digest in pointer['sha256'].items():
            import hashlib
            self.assertEqual(hashlib.sha256((release/name).read_bytes()).hexdigest(),digest)

    def test_failed_geometry_preserves_last_good(self):
        path=self.spec();out=self.base/'out'
        self.assertEqual(self.cli(['deliver',str(path),'--out',str(out),'--formats','html,svg'])[0],0)
        before=(out/'latest.json').read_bytes();directories=set(out.iterdir())
        doc=fixture('en');doc['pages'][0]['edges'][0]['points'][-1]=[540,400]
        status,result=self.cli(['deliver',str(self.spec(doc)),'--out',str(out),'--formats','html,svg'])
        self.assertEqual(status,1);self.assertEqual(result['issues'][0]['code'],'CONNECTOR_ENDPOINT')
        self.assertEqual(before,(out/'latest.json').read_bytes());self.assertEqual(directories,set(out.iterdir()))

    def test_renderer_failure_does_not_publish_partial_release(self):
        path=self.spec();out=self.base/'out'
        self.assertEqual(self.cli(['deliver',str(path),'--out',str(out),'--formats','html,svg'])[0],0)
        before=(out/'latest.json').read_bytes();directories=set(out.iterdir())
        original=renderer.main
        def fail_on_render(args):
            if '--validate-only' not in args:
                (Path(args[args.index('--out')+1])/'partial.svg').write_text('partial')
                raise OSError('simulated backend failure')
            return original(args)
        with patch.object(renderer,'main',side_effect=fail_on_render):
            status,result=self.cli(['deliver',str(path),'--out',str(out),'--formats','html,svg'])
        self.assertEqual(status,1);self.assertTrue(result['last_good_preserved'])
        self.assertEqual(before,(out/'latest.json').read_bytes());self.assertEqual(directories,set(out.iterdir()))

    def test_html_data_cannot_escape_script(self):
        doc=fixture('en');doc['pages'][0]['nodes'][0]['details']={'principle':'</script><script>alert(1)</script>'}
        path=self.spec(doc)
        status,result=self.cli(['deliver',str(path),'--out',str(self.base/'out'),'--formats','html,svg'])
        self.assertEqual(status,0,result)
        markup=Path(result['entrypoint']).read_text(encoding='utf-8')
        self.assertNotIn('<script>alert(1)</script>',markup);self.assertIn('\\u003c/script',markup)
        payload=json.loads(re.search(r'<script type="application/json" id="document">(.*?)</script>',markup,re.S)[1])
        self.assertIn('data-node="sensor"',payload['svg'][0]);self.assertIn('data-edge="0"',payload['svg'][0])
        self.assertIn("default-src 'none'",markup)

    def test_validation_has_no_filesystem_side_effect(self):
        path=self.spec();before=set(self.base.iterdir())
        status,result=self.cli(['validate',str(path),'--formats','html,svg','--json'])
        self.assertEqual(status,0,result);self.assertEqual(before,set(self.base.iterdir()))

    def test_node_overlap_and_nonfinite_rejected(self):
        doc=fixture('en');doc['pages'][0]['nodes'][1]['x']=200
        status,result=self.cli(['validate',str(self.spec(doc)),'--formats','svg'])
        self.assertEqual(status,1);self.assertEqual(result['issues'][0]['code'],'NODE_OVERLAP')
        doc=fixture('en');doc['pages'][0]['nodes'][0]['x']=float('nan')
        status,result=self.cli(['validate',str(self.spec(doc)),'--formats','svg'])
        self.assertEqual(status,1);self.assertEqual(result['issues'][0]['code'],'SPEC_NUMBER')

    def test_bus_junction_must_be_an_authored_endpoint(self):
        doc=fixture('en');doc['pages'][0]['junctions']=[{'id':'tap','x':400,'y':400}]
        status,result=self.cli(['validate',str(self.spec(doc)),'--formats','svg'])
        self.assertEqual(status,1);self.assertEqual(result['issues'][0]['code'],'CONNECTOR_JUNCTION')

    def test_non_builtin_html_locale_requires_translated_controls(self):
        doc=fixture('de')
        status,result=self.cli(['validate',str(self.spec(doc)),'--formats','html'])
        self.assertEqual(status,1);self.assertIn('translated ui',result['issues'][0]['evidence'])

    def test_agent_translated_german_html_preserves_part_identifiers(self):
        doc=fixture('de');doc['ui']={
            'up':'Vorgänger','down':'Nachfolger','reset':'Zurücksetzen','export':'SVG exportieren','print':'Drucken / PDF',
            'search':'Bauteil / Modell / Netz suchen','pages':'Diagrammseiten','canvas':'Hardwarediagramm',
            'intro':'Hardwareübersicht und Moduldiagramme.','function':'Funktion','principle':'Funktionsprinzip',
            'interfaces':'Schnittstellen','power':'Versorgungsbereiche','evidence':'Quellennachweis',
            'uncertainty':'Offene Punkte','page':'Seite','reading':'Lesehilfe','select':'Wählen Sie einen Block aus.',
            'scope':'Die Verfolgung verwendet nur die eingezeichneten Verbindungen.'}
        doc['ui'].update(theme='Farbthema',dark='Dunkel',light='Hell',motion='Signalbewegung',play='Animiert',pause='Statisch',
            reduced='Bewegung ist gemäß Systemeinstellung deaktiviert.',fit='Diagramm einpassen',zoomIn='Vergrößern',zoomOut='Verkleinern',
            fullscreen='Präsentieren',exitFullscreen='Präsentation beenden',exportSvg='SVG herunterladen',exportPng='PNG herunterladen',
            focus='Fokus',close='Details schließen',overview='Übersicht',module='Modul',nodes='Blöcke',connections='Verbindungen',
            connection='Verbindung',fromLabel='Von',toLabel='Nach',basis_schematic='Schaltplan',basis_netlist='Netzliste',
            basis_datasheet='Datenblatt',basis_inferred='Annahme',basis_ocr_candidate='OCR zur Prüfung',basis_synthetic='Synthetisches Beispiel',
            exportError='Export fehlgeschlagen. Verwenden Sie SVG oder die Druckfunktion.',hint='Ziehen zum Verschieben · Scrollen zum Zoomen')
        status,result=self.cli(['deliver',str(self.spec(doc)),'--out',str(self.base/'de'),'--formats','html,svg'])
        self.assertEqual(status,0,result)
        markup=Path(result['entrypoint']).read_text(encoding='utf-8')
        self.assertIn('lang="de"',markup);self.assertIn('Funktionsprinzip',markup);self.assertIn('ADC_GENERIC',markup)

    def test_missing_file_hash_rejected(self):
        doc=fixture('en');doc['evidence']=[{'id':'source','source':'board.pdf','basis':'schematic','page':1}]
        status,result=self.cli(['validate',str(self.spec(doc)),'--formats','svg'])
        self.assertEqual(status,1);self.assertEqual(result['issues'][0]['code'],'EVIDENCE_HASH')

    def test_ocr_adapter_marks_unverified_coordinates(self):
        parser=argparse.ArgumentParser();intake.add_options(parser)
        args=parser.parse_args(['scan.png','--out',str(self.base),'--ocr'])
        with patch.object(intake,'program',return_value='tesseract'),patch.object(intake.subprocess,'run') as run:
            result=intake.ocr_image(self.base/'scan.png',self.base/'ocr-001',args)
        self.assertEqual(result['basis'],'ocr-candidate');self.assertTrue(result['requires_visual_confirmation'])
        self.assertEqual(run.call_args[0][0][-2:],['tsv','txt'])

    def test_demo_theme_overrides_reach_all_artifacts(self):
        for theme in ('dark','light'):
            status,result=self.cli(['demo',str(self.base/theme),'--theme',theme,'--formats','html,svg,drawio'])
            self.assertEqual(status,0,result)
            release=Path(result['release']);manifest=json.loads((release/'manifest.json').read_text())
            self.assertEqual(manifest['theme'],theme)
            graph=ET.parse(release/'00-overview.svg');root=graph.getroot();self.assertEqual(root.get('data-theme'),theme)
            nodes=[e for e in root.iter() if e.get('data-node') is not None];self.assertEqual(len(nodes),6)
            self.assertTrue(all(e.tag.endswith('g') and e.get('role')=='button' for e in nodes))
            html=Path(result['entrypoint']).read_text(encoding='utf-8');self.assertIn('data-theme="'+theme+'"',html)
            self.assertTrue((release/'example-hardware-architecture.drawio').is_file())

    def test_template_token_in_user_text_remains_literal(self):
        doc=fixture('en');doc['title']='Literal @@DATA@@ and @@CSS@@'
        status,result=self.cli(['deliver',str(self.spec(doc)),'--out',str(self.base/'tokens'),'--formats','html,svg'])
        self.assertEqual(status,0,result)
        html=Path(result['entrypoint']).read_text(encoding='utf-8');self.assertIn('<title>Literal @@DATA@@ and @@CSS@@</title>',html)


if __name__=='__main__':unittest.main()
