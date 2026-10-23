"""Build a self-contained interactive diagram from validated semantic SVG."""
import html
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from localization import normalize_locale, is_rtl
from visual_style import theme_css

UI_EN = dict(up='Upstream', down='Downstream', reset='Reset', export='Export', print='Print / PDF',
    search='Find component / model / net', pages='Diagram pages', canvas='Hardware diagram',
    intro='Hardware overview and module diagrams. Select a block to inspect its role and evidence.',
    function='Function', principle='Operating principle', interfaces='Interfaces', power='Power domains',
    evidence='Source evidence', uncertainty='Unresolved / limitations', page='Page', reading='Reading guide',
    select='Select a block to inspect its devices, operating principle and source evidence.',
    scope='Reach follows authored relationships. It does not establish timing, fault propagation or safety.',
    theme='Color theme', dark='Dark', light='Light', motion='Signal motion', play='Live', pause='Still',
    reduced='Motion is disabled by the reduced-motion preference.', fit='Fit diagram', zoomIn='Zoom in',
    zoomOut='Zoom out', fullscreen='Present', exitFullscreen='Exit presentation', exportSvg='Download SVG',
    exportPng='Download PNG', focus='Focus', close='Close details', overview='Overview', module='Module',
    nodes='Blocks', connections='Connections', connection='Connection', fromLabel='From', toLabel='To',
    basis_schematic='Schematic', basis_netlist='Netlist', basis_datasheet='Datasheet', basis_inferred='Inference',
    basis_ocr_candidate='OCR candidate', basis_synthetic='Synthetic example',
    exportError='Export failed. Use SVG export or browser printing.', hint='Drag to pan · Scroll to zoom · Select a block for details')
UI_ZH = dict(up='上游连接', down='下游连接', reset='复位视图', export='导出', print='打印 / PDF',
    search='查找器件 / 型号 / 网络', pages='框图页面', canvas='硬件框图',
    intro='硬件架构总览与模块框图。选择功能块可查看器件职责、工作原理和源文件证据。',
    function='承担功能', principle='工作原理', interfaces='接口信号', power='供电与参考地',
    evidence='源文件证据', uncertainty='待确认项与适用限制', page='页码', reading='阅读指引',
    select='选择功能块，查看器件型号、工作原理和源文件证据。',
    scope='连接追踪仅反映已记录的拓扑关系，不代表时序、故障传播或安全性已获得验证。',
    theme='颜色主题', dark='深色', light='浅色', motion='信号动效', play='动态', pause='静态',
    reduced='已按系统的减少动态效果设置关闭动效。', fit='适应画布', zoomIn='放大',
    zoomOut='缩小', fullscreen='演示', exitFullscreen='退出演示', exportSvg='下载 SVG',
    exportPng='下载 PNG', focus='聚焦', close='关闭详情', overview='总览', module='模块',
    nodes='功能块', connections='连接', connection='信号连接', fromLabel='来源', toLabel='去向',
    basis_schematic='原理图依据', basis_netlist='网表依据', basis_datasheet='数据手册依据', basis_inferred='工程推断',
    basis_ocr_candidate='OCR 待核对项', basis_synthetic='合成示例',
    exportError='导出未完成，请使用 SVG 导出或浏览器打印。', hint='拖动平移 · 滚轮缩放 · 选择功能块查看详情')


def build(document, pages, svg_pages, locale):
    locale = normalize_locale(locale)
    supplied = document.get('ui')
    if supplied is not None:
        missing = set(UI_EN) - set(supplied)
        extra = set(supplied) - set(UI_EN)
        if missing or extra or not all(isinstance(v, str) and v for v in supplied.values()):
            raise ValueError('HTML ui needs translated controls. Missing: '+', '.join(sorted(missing))+'; extra: '+', '.join(sorted(extra)))
        ui = supplied
    elif locale in ('en', 'zh-Hans'):
        ui = UI_ZH if locale == 'zh-Hans' else UI_EN
    else:
        raise ValueError('HTML locale requires a translated ui object; see references/languages.md')
    payload = {**document, 'locale': locale, 'pages': pages, 'ui': ui, 'svg': [], 'bounds': []}
    for page, markup in zip(pages, svg_pages):
        root = ET.fromstring(markup)
        node_ids = {n['id'] for n in page['nodes']}
        rendered = {e.get('data-node') for e in root.iter() if e.get('data-node') is not None}
        edge_ids = {e.get('data-edge') for e in root.iter() if e.get('data-edge') is not None}
        if rendered != node_ids or edge_ids != {str(i) for i in range(len(page['edges']))}:
            raise ValueError('SVG semantic node/edge identities do not match the authored graph')
        boxes = [(n['x'], n['y'], n['x']+n['w'], n['y']+n['h']) for n in page['nodes']+page['groups']]
        for edge in page['edges']:
            boxes.extend((x,y,x,y) for x,y in edge['points'])
            if edge.get('label_pos'):
                x,y=edge['label_pos'];boxes.append((x,y,x+len(edge['label'])*24,y+35))
        x0=min(b[0] for b in boxes)-60;y0=min(b[1] for b in boxes)-65
        x1=max(b[2] for b in boxes)+60;y1=max(b[3] for b in boxes)+65
        payload['bounds'].append([x0,y0,x1-x0,y1-y0])
        payload['svg'].append(ET.tostring(root,encoding='unicode'))
    data = json.dumps(payload,ensure_ascii=False).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    assets=Path(__file__).resolve().parents[1]/'assets'
    values={'LANG':html.escape(locale,quote=True),'DIR':'rtl' if is_rtl(document.get('title','')) else 'ltr',
        'TITLE':html.escape(document.get('title',document.get('name','Hardware')),quote=True),
        'THEME':html.escape(document.get('theme','dark'),quote=True),
        'CSS':theme_css('html',document.get('palette'))+'\n'+(assets/'viewer.css').read_text(encoding='utf-8'),
        'SCRIPT':(assets/'viewer.js').read_text(encoding='utf-8'),'DATA':data,
        'SEARCH':html.escape(ui['search'],quote=True),'PAGES':html.escape(ui['pages'],quote=True),
        'CANVAS':html.escape(ui['canvas'],quote=True)}
    # A single substitution pass never interprets template tokens inside user content.
    return re.sub(r'@@([A-Z]+)@@',lambda m:values[m[1]],(assets/'viewer.html').read_text(encoding='utf-8'))
