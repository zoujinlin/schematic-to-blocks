#!/usr/bin/env python3
"""Render validated schematic block diagrams from a localized JSON document."""
import argparse
import copy
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.colors import HexColor
from localization import detect_locale, normalize_locale, get_legend, needs_shaping, is_rtl
from html_viewer import build as build_html
from visual_style import THEMES, SVG_CSS, theme_css, category

W,H=1600,1200
THEME='dark'
COL=dict(THEMES[THEME])
PALETTE={}
LINE_WIDTH=4.6
ARROW_LENGTH=28
ARROW_HALF_WIDTH=11
D=[]
LOCALE='en'
LEGEND=get_legend('en')
FONT_FAMILY='sans-serif'
FONT_REGULAR='DiagramRegular'
FONT_BOLD='DiagramBold'

def safe_name(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',value) or '..' in value:
        raise ValueError(f'Invalid output name or object ID: {value!r}')
    return value

def all_text(document):
    values=[document.get('title','')]+list(LEGEND.values())
    for page in D:
        values.extend([page['title'],page['subtitle']])
        for node in page['nodes']:values.extend([node['title'],node['model']]+node['lines'])
        for group in page['groups']:values.append(group['title'])
        for edge in page['edges']:values.append(edge['label'])
        values.extend(t['text'] for t in page['texts'])
        values.extend(n['text'] for n in page['notes'])
    return '\n'.join(values)

def register_fonts(args,text):
    global FONT_FAMILY,FONT_REGULAR,FONT_BOLD
    win=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    pairs=[]
    if args.font:
        pairs.append((args.font,args.bold_font or args.font))
    else:
        special={'zh-Hans':('msyh.ttc','msyhbd.ttc'),'zh-Hant':('msjh.ttc','msjhbd.ttc'),
                 'ja':('YuGothM.ttc','YuGothB.ttc'),'ko':('malgun.ttf','malgunbd.ttf')}
        if LOCALE in special:pairs.append(tuple(win/name for name in special[LOCALE]))
        if LOCALE in special:
            pairs.extend([(win/'msyh.ttc',win/'msyhbd.ttc'),
                          (Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc')),
                          (Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'),Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc')),
                          (Path('/System/Library/Fonts/PingFang.ttc'),Path('/System/Library/Fonts/PingFang.ttc'))])
        pairs.extend([(win/'arial.ttf',win/'arialbd.ttf'),
                      (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')),
                      (Path('/Library/Fonts/Arial Unicode.ttf'),Path('/Library/Fonts/Arial Unicode.ttf')),
                      (win/'msyh.ttc',win/'msyhbd.ttc')])
    errors=[]
    required={ord(c) for c in text if not c.isspace() and not unicodedata.category(c).startswith('C')}
    for regular,bold in pairs:
        if not regular.is_file():continue
        if not bold.is_file():bold=regular
        try:
            regular_name='DiagramRegular_'+hashlib.sha256(f'{regular.resolve()}:{args.font_index}'.encode()).hexdigest()[:16]
            bold_name='DiagramBold_'+hashlib.sha256(f'{bold.resolve()}:{args.font_index}'.encode()).hexdigest()[:16]
            r=TTFont(regular_name,str(regular),subfontIndex=args.font_index)
            b=TTFont(bold_name,str(bold),subfontIndex=args.font_index)
            missing=required-(set(r.face.charWidths)&set(b.face.charWidths))
            if missing:
                errors.append(f'{regular.name}: missing '+''.join(chr(c) for c in sorted(missing)[:16]));continue
            pdfmetrics.registerFont(r);pdfmetrics.registerFont(b)
            FONT_REGULAR,FONT_BOLD=regular_name,bold_name
            family=r.face.familyName
            FONT_FAMILY=family.decode('utf-8','replace') if isinstance(family,bytes) else str(family)
            return {'regular':str(regular),'bold':str(bold),'family':FONT_FAMILY}
        except Exception as exc:errors.append(f'{regular.name}: {type(exc).__name__}')
    raise ValueError('No usable font with complete glyph coverage. Provide --font and --bold-font. '+ '; '.join(errors[-4:]))

def load_document(raw):
    global D
    D=copy.deepcopy(raw.get('pages',[]))
    if not D:raise ValueError('pages must contain at least one page')
    slugs=set()
    for page in D:
        slug=safe_name(page['slug'])
        if slug in slugs:raise ValueError('Duplicate page slug: '+slug)
        slugs.add(slug)
        page.setdefault('title','');page.setdefault('subtitle','')
        for key in ('nodes','edges','groups','junctions','texts','notes'):page.setdefault(key,[])
        ids=set()
        for item in page['nodes']+page['groups']+page['junctions']:
            if item.get('id'):
                ident=safe_name(item['id'])
                if ident in ids:raise ValueError(f'{slug}: duplicate ID {ident}')
                ids.add(ident)
        for n in page['nodes']:
            for key in ('id','x','y','w','h','title'):
                if key not in n:raise ValueError(f'{slug}: node needs {key}')
            n.setdefault('kind','normal');n.setdefault('model','');n.setdefault('lines',[])
            if n['kind'] not in ('normal','external','interface','power','power_external','reference','annotation','optional'):
                raise ValueError('Unknown node kind: '+n['kind'])
        for g in page['groups']:
            g.setdefault('id',None);g.setdefault('fill',COL['group']);g.setdefault('dash',False)
        for j in page['junctions']:j.setdefault('kind','data')
        for e in page['edges']:
            for key,value in [('label',''),('kind','data'),('both',False),('end_arrow',True),('dash',False),('lx',None),('ly',None)]:e.setdefault(key,value)
            if e['kind'] not in LEGEND:raise ValueError('Invalid edge kind: '+e['kind'])
            if len(e.get('points',[]))<2:raise ValueError('Connector needs at least two points')
        for t in page['texts']:
            t.setdefault('size',24);t.setdefault('bold',False);t.setdefault('anchor','start')
            t['color']=COL.get(t.get('color','muted'),t.get('color',COL['muted']))

def write_output(path,data):
    """Atomic write; a locked destination gets a numbered alternate file."""
    path=Path(path)
    fd,temp=tempfile.mkstemp(prefix='.diagram-',suffix=path.suffix,dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data.encode('utf-8') if isinstance(data,str) else data)
        for number in range(0,100):
            target=path if number==0 else path.with_name(f'{path.stem}-{number+1}{path.suffix}')
            if number and target.exists():continue
            try:os.replace(temp,target);return target
            except PermissionError:continue
        raise PermissionError('No writable output filename for '+str(path))
    finally:
        if os.path.exists(temp):os.unlink(temp)

def measure(s,size,bold=False):return pdfmetrics.stringWidth(s,FONT_BOLD if bold else FONT_REGULAR,size)
def wrap(s,width,size,bold=False):
    if not s:return ['']
    result=[]
    for raw in s.split('\n'):
        line=''
        tokens=re.findall(r'[A-Za-z0-9_Ωµ±−–′#\.ΔΣ-]+|.',raw)
        for token in tokens:
            if measure(token,size,bold)>width:
                pieces=list(token)
            else:
                pieces=[token]
            for piece in pieces:
                if line and measure(line+piece,size,bold)>width:
                    result.append(line.rstrip());line=piece.lstrip()
                else:line+=piece
        result.append(line)
    return result
def text_layout(n):
    compact=n['h']<110
    layout=[]; y=n['y']+(10 if compact else 14)
    model_color=category(n)
    for text,size,bold,color in [(n['title'],23 if compact else 25,True,'ink'),(n['model'],21 if compact else 22,False,model_color)]+[(s,21 if compact else 22,False,'muted') for s in n['lines']]:
        if not text:
            if n['model'] or n['lines']:y+=3
            continue
        inset=56 if bold else 18
        for line in wrap(text,n['w']-inset-18,size,bold):
            layout.append((line,n['x']+inset,y,size,bold,COL[color]));y+=size*1.16
        y+=3
    if y>n['y']+n['h']-5:
        raise ValueError(f"{n['id']} text overflow: {round(y-n['y'],1)} / {n['h']}")
    return layout
def common_text(d,index):
    result=[(d['title'],45,36,39,True,COL['ink']),
            (d['subtitle'],45,99,23,False,COL['muted']),
            (f"{index+1:02d} / {len(D):02d}",1450,36,24,False,COL['muted'])]
    x=45
    for key in ('data','control','power','reference'):
        caption=LEGEND[key]
        result.append((caption,x,1164,18,False,COL[key]));x+=measure(caption,18)+65
    if x>1610:raise ValueError('Legend exceeds the footer width; shorten translated captions')
    for t in d['texts']:
        x=t['x']
        if t['anchor']=='middle':x-=measure(t['text'],t['size'],t['bold'])/2
        result.append((t['text'],x,t['y'],t['size'],t['bold'],t['color']))
    for n in d['nodes']:result+=text_layout(n)
    for n in d['notes']:
        y=n['y']
        for line in wrap(n['text'],1510,22):result.append((line,45,y,22,False,COL['muted']));y+=30
        if y-30+22>1150:raise ValueError('Note overlaps footer: '+d['slug'])
    return result

def arrow_tri(points,start=False):
    a,b=(points[1],points[0]) if start else (points[-2],points[-1])
    distance=math.hypot(b[0]-a[0],b[1]-a[1])
    length=min(ARROW_LENGTH,distance*.8)
    ux,uy=(b[0]-a[0])/distance,(b[1]-a[1])/distance
    half=ARROW_HALF_WIDTH*length/ARROW_LENGTH
    return [b,(b[0]-length*ux-half*uy,b[1]-length*uy+half*ux),
            (b[0]-length*ux+half*uy,b[1]-length*uy-half*ux)]
def arrow_ends(e):
    return ([False] if e['end_arrow'] else [])+([True] if e['both'] else [])

def shaft_points(e):
    # Stop the shaft at each arrowhead base so a flat line cap cannot blunt the apex.
    result=list(e['points'])
    for start in arrow_ends(e):
        triangle=arrow_tri(e['points'],start)
        base=((triangle[1][0]+triangle[2][0])/2,(triangle[1][1]+triangle[2][1])/2)
        result[0 if start else -1]=base
    return result

def rect_bounds(n,pad=0):return (n['x']-pad,n['y']-pad,n['x']+n['w']+pad,n['y']+n['h']+pad)
def overlaps(a,b):return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]
def segment_hits_rect(a,b,r,pad=0):
    if abs(a[0]-b[0])<.01:
        return r[0]-pad<a[0]<r[2]+pad and max(min(a[1],b[1]),r[1]-pad)<min(max(a[1],b[1]),r[3]+pad)
    if abs(a[1]-b[1])<.01:
        return r[1]-pad<a[1]<r[3]+pad and max(min(a[0],b[0]),r[0]-pad)<min(max(a[0],b[0]),r[2]+pad)
    raise ValueError('Non-orthogonal connector')
def endpoint_matches(point,item):
    if 'w' not in item:return math.dist(point,(item['x'],item['y']))<.01
    x,y=point; x0,y0,x1,y1=rect_bounds(item)
    return ((abs(x-x0)<.01 or abs(x-x1)<.01) and y0-.01<=y<=y1+.01) or ((abs(y-y0)<.01 or abs(y-y1)<.01) and x0-.01<=x<=x1+.01)

def prepare_connections(d,index):
    lookup={n['id']:n for n in d['nodes']+d['junctions']+[g for g in d['groups'] if g['id']]}
    for i,e in enumerate(d['edges']):
        for key,point in [('source',e['points'][0]),('target',e['points'][-1])]:
            if e[key] not in lookup or not endpoint_matches(point,lookup[e[key]]):
                raise ValueError(f"{d['slug']} e{i} {key}: endpoint {point} is detached from {e[key]}")
        for a,b in zip(e['points'],e['points'][1:]):
            if math.dist(a,b)<.01:raise ValueError(f"{d['slug']} e{i}: zero-length segment")
            for junction in d['junctions']:
                point=(junction['x'],junction['y'])
                if junction['id'] not in (e['source'],e['target']) and abs(math.dist(a,point)+math.dist(point,b)-math.dist(a,b))<.01:
                    raise ValueError(f"{d['slug']} e{i}: junction {junction['id']} lies inside a segment; split the edge at this junction")
            for n in d['nodes']:
                if segment_hits_rect(a,b,rect_bounds(n)):
                    raise ValueError(f"{d['slug']} e{i}: connector crosses node {n['id']}")
    blocked=[rect_bounds(n,4) for n in d['nodes']]
    for g in d['groups']:
        blocked.append((g['x']+12,g['y']-18,g['x']+measure(g['title'],22,True)+44,g['y']+22))
    node_text_positions={(p[1],p[2]) for n in d['nodes'] for p in text_layout(n)}
    for text,x,y,size,bold,color in common_text(d,index):
        if (x,y) not in node_text_positions:
            blocked.append((x-3,y-3,x+measure(text,size,bold)+3,y+size*1.25+3))
    for e in d['edges']:
        for start in arrow_ends(e):
            triangle=arrow_tri(e['points'],start)
            blocked.append((min(p[0] for p in triangle)-4,min(p[1] for p in triangle)-4,
                            max(p[0] for p in triangle)+4,max(p[1] for p in triangle)+4))
    placed=[]
    for e in d['edges']:
        if not e['label']:continue
        width=measure(e['label'],21);candidates=[]
        segments=sorted(zip(e['points'],e['points'][1:]),key=lambda pair:math.dist(*pair),reverse=True)
        for a,b in segments:
            for fraction in [.5,.35,.65,.2,.8]:
                cx=a[0]+fraction*(b[0]-a[0]);cy=a[1]+fraction*(b[1]-a[1])
                if abs(a[1]-b[1])<.01:
                    candidates.extend([(cx-width/2,cy-45),(cx-width/2,cy+17)])
                else:
                    candidates.extend([(cx+24,cy-14),(cx-width-24,cy-14)])
        if e['lx'] is not None and e['ly'] is not None:
            candidates.extend([(e['lx']-width/2,e['ly']-20),(e['lx']-width/2,e['ly'])])
        for x,y in candidates:
            bounds=(x-6,y-4,x+width+6,y+29)
            if bounds[0]<25 or bounds[2]>1575 or bounds[1]<150 or bounds[3]>1148:continue
            if any(overlaps(bounds,r) for r in blocked+placed):continue
            if any(segment_hits_rect(a,b,bounds,8) for other in d['edges'] for a,b in zip(other['points'],other['points'][1:])):continue
            e['label_pos']=[x,y];placed.append(bounds);break
        else:raise ValueError(f"{d['slug']}: no clear location for label {e['label']}")
    d['connection_check']={'bound_endpoints':2*len(d['edges']),'labels_checked':len(placed)}

def label_data(e):
    if not e['label']:return None
    x,y=e['label_pos']
    return (e['label'],x,y,21,False,COL[e['kind']])
def node_style(n):
    k=n['kind'];domain=category(n)
    fill=COL['powerfill'] if domain=='power' else COL['referencefill'] if domain=='reference' else COL['interface'] if k=='interface' else COL['node']
    return fill,COL[domain],k=='optional'

svg_ns='http://www.w3.org/2000/svg'
ET.register_namespace('',svg_ns)
def svg(d,index):
    root=ET.Element(f'{{{svg_ns}}}svg',dict(width=str(W),height=str(H),viewBox=f'0 0 {W} {H}',role='img',**{'class':'hardware-diagram','data-theme':THEME,'data-motion':'off'}))
    def element(parent,tag,attrs=None,**kw):return ET.SubElement(parent,f'{{{svg_ns}}}'+tag,{**(attrs or {}),**{k:str(v) for k,v in kw.items()}})
    element(root,'title').text=d['title'];element(root,'desc').text=d['subtitle']
    element(root,'style').text=theme_css('svg.hardware-diagram',PALETTE)+'\n'+SVG_CSS
    element(root,'rect',{'class':'diagram-paper'},width=W,height=H,fill=COL['bg'])
    grid=element(root,'g',{'class':'diagram-grid','aria-hidden':'true'})
    for x in range(0,W+1,40):element(grid,'line',{'class':'grid-line'},x1=x,y1=0,x2=x,y2=H,stroke=COL['grid'])
    for y in range(0,H+1,40):element(grid,'line',{'class':'grid-line'},x1=0,y1=y,x2=W,y2=y,stroke=COL['grid'])
    meta=element(root,'g',{'class':'page-meta'})
    footer=element(root,'g',{'class':'page-footer'})
    content=element(root,'g',{'class':'diagram-content'})
    element(meta,'rect',{'class':'diagram-paper'},x=25,y=25,width=1550,height=115,fill=COL['bg'])
    element(meta,'rect',{'class':'domain-data domain-fill'},x=25,y=36,width=5,height=46,fill=COL['data'])
    for y in (140,1157):element(meta if y==140 else footer,'line',{'class':'frame-line'},x1=45,y1=y,x2=1560,y2=y,stroke=COL['line'])
    def rect(parent,x,y,w,h,fill,stroke,dash=False,r=12,css=''):
        attrs=dict(x=str(x),y=str(y),width=str(w),height=str(h),rx=str(r),fill=fill,stroke=stroke,**{'stroke-width':'1.8','class':css})
        if dash:attrs['stroke-dasharray']='8 5'
        return element(parent,'rect',attrs)
    def text(parent,item,css=''):
        value,x,y,size,bold,color=item
        return element(parent,'text',dict(x=str(x),y=str(y+size),fill=color,**{'class':css,'font-size':str(size),'font-family':FONT_FAMILY,'font-weight':'700' if bold else '400'}))
    for g in d['groups']:
        layer=element(content,'g',{'class':'diagram-group'})
        rect(layer,g['x'],g['y'],g['w'],g['h'],g['fill'],COL['line'],g['dash'],css='group-frame')
        rect(layer,g['x']+14,g['y']-15,measure(g['title'],22,True)+28,34,COL['bg'],COL['line'],r=5,css='group-tag')
        text(layer,(g['title'],g['x']+28,g['y']-11,22,True,COL['muted']),'text-muted').text=g['title']
    for n in d['nodes']:
        domain=category(n)
        layer=element(content,'g',{'class':f'diagram-node domain-{domain} kind-{n["kind"]}','data-node':n['id'],'role':'button','tabindex':'0','aria-label':n['title']})
        element(layer,'title').text=n['title']+' · '+n['model']
        rect(layer,n['x'],n['y'],n['w'],n['h'],*node_style(n),css='node-card')
        rect(layer,n['x']+15,n['y']+14,29,29,COL['node'],COL[domain],r=7,css='node-icon-bg')
        icon=element(layer,'g',{'class':'node-icon'},transform=f'translate({n["x"]+22} {n["y"]+21})')
        element(icon,'rect',x=0,y=0,width=15,height=15,rx=2)
        for offset in (4,10):
            for x1,y1,x2,y2 in [(-4,offset,0,offset),(15,offset,19,offset),(offset,-4,offset,0),(offset,15,offset,19)]:
                element(icon,'line',x1=x1,y1=y1,x2=x2,y2=y2)
        for item in text_layout(n):
            css='text-ink' if item[4] else 'text-muted' if item[-1]==COL['muted'] else 'domain-text'
            text(layer,item,css).text=item[0]
    for i,e in enumerate(d['edges']):
        layer=element(content,'g',{'class':f'diagram-edge domain-{e["kind"]}','data-edge':str(i),'role':'button','tabindex':'0','aria-label':e['label'] or e['kind']})
        attrs={'points':' '.join(f'{x},{y}' for x,y in shaft_points(e)),'fill':'none','stroke':COL[e['kind']],'stroke-width':str(LINE_WIDTH),'stroke-linejoin':'round','stroke-linecap':'butt','class':'edge-shaft'}
        if e['dash']:attrs['stroke-dasharray']='10 7'
        element(layer,'polyline',attrs)
        for start in arrow_ends(e):
            element(layer,'polygon',{'class':'edge-head','points':' '.join(f'{x},{y}' for x,y in arrow_tri(e['points'],start)),'fill':COL[e['kind']]})
        if e['end_arrow'] and not e['both']:
            element(layer,'polyline',{'class':'edge-flow','points':attrs['points']})
        element(layer,'polyline',{'class':'edge-hit','points':' '.join(f'{x},{y}' for x,y in e['points'])})
        item=label_data(e)
        if item:
            label,x,y,size,bold,color=item
            rect(layer,x-7,y-4,measure(label,size)+14,size*1.4+2,COL['bg'],COL[e['kind']],r=4,css='edge-label-bg')
            text(layer,item,'domain-text').text=label
    for j in d['junctions']:element(content,'circle',{'class':f'domain-{j["kind"]} domain-fill'},cx=j['x'],cy=j['y'],r=5,fill=COL[j['kind']])
    node_positions={(p[1],p[2]) for n in d['nodes'] for p in text_layout(n)}
    for item in common_text(d,index):
        if (item[1],item[2]) in node_positions:continue
        css='text-ink' if item[4] else 'text-muted'
        for key in LEGEND:
            if item[-1]==COL[key]:css=f'domain-{key} domain-text'
        text(meta if item[2]<150 else footer if item[2]>1050 else content,item,css).text=item[0]
    root.set('lang',LOCALE)
    root.set('{http://www.w3.org/XML/1998/namespace}lang',LOCALE)
    for element in root.iter(f'{{{svg_ns}}}text'):
        if is_rtl(element.text or ''):
            element.set('direction','rtl');element.set('unicode-bidi','plaintext')
            element.set('x',str(float(element.get('x'))+measure(element.text,float(element.get('font-size')),element.get('font-weight')=='700')))
    return ET.tostring(root,encoding='unicode')

def draw_pdf(d,index,c):
    pw,ph=landscape(A3);scale=min((pw-32)/W,(ph-32)/H);ox=(pw-W*scale)/2;oy=(ph-H*scale)/2
    c.setFillColor(HexColor(COL['bg']));c.rect(0,0,pw,ph,fill=1,stroke=0)
    c.saveState();c.translate(ox,oy);c.scale(scale,scale)
    c.setStrokeColor(HexColor(COL['grid']));c.setLineWidth(.8)
    for x in range(0,W+1,40):c.line(x,0,x,H)
    for y in range(0,H+1,40):c.line(0,y,W,y)
    c.setFillColor(HexColor(COL['bg']));c.rect(25,H-140,1550,115,fill=1,stroke=0)
    c.setFillColor(HexColor(COL['data']));c.rect(25,H-82,6,46,fill=1,stroke=0)
    c.setStrokeColor(HexColor(COL['line']));c.setLineWidth(1.2)
    for y in (140,1157):c.line(45,H-y,1560,H-y)
    def rect(x,y,w,h,fill,stroke,dash=False):
        c.setFillColor(HexColor(fill));c.setStrokeColor(HexColor(stroke));c.setLineWidth(2.2)
        c.setDash([8,5] if dash else []);c.roundRect(x,H-y-h,w,h,12,fill=1,stroke=1);c.setDash([])
    for g in d['groups']:
        rect(g['x'],g['y'],g['w'],g['h'],g['fill'],COL['line'],g['dash'])
        rect(g['x']+14,g['y']-15,measure(g['title'],22,True)+28,34,COL['bg'],COL['line'])
        c.setFont(FONT_BOLD,22);c.setFillColor(HexColor(COL['muted']));c.drawString(g['x']+28,H-g['y']-11,g['title'])
    for n in d['nodes']:
        rect(n['x'],n['y'],n['w'],n['h'],*node_style(n))
        color=COL[category(n)];rect(n['x']+15,n['y']+14,29,29,COL['node'],color)
        x,y=n['x']+22,n['y']+21
        c.setLineWidth(1.8);c.setStrokeColor(HexColor(color));c.roundRect(x,H-y-15,15,15,2,fill=0,stroke=1)
        for offset in (4,10):
            for x1,y1,x2,y2 in [(-4,offset,0,offset),(15,offset,19,offset),(offset,-4,offset,0),(offset,15,offset,19)]:c.line(x+x1,H-y-y1,x+x2,H-y-y2)
    for e in d['edges']:
        c.setStrokeColor(HexColor(COL[e['kind']]));c.setFillColor(HexColor(COL[e['kind']]));c.setLineWidth(LINE_WIDTH);c.setLineCap(0);c.setLineJoin(1);c.setDash([10,7] if e['dash'] else [])
        shaft=shaft_points(e)
        p=c.beginPath();p.moveTo(shaft[0][0],H-shaft[0][1])
        for x,y in shaft[1:]:p.lineTo(x,H-y)
        c.drawPath(p);c.setDash([])
        for start in arrow_ends(e):
            tri=arrow_tri(e['points'],start);p=c.beginPath()
            p.moveTo(tri[0][0],H-tri[0][1])
            for x,y in tri[1:]:p.lineTo(x,H-y)
            p.close();c.drawPath(p,fill=1,stroke=0)
    for j in d['junctions']:
        c.setFillColor(HexColor(COL[j['kind']]));c.circle(j['x'],H-j['y'],5,fill=1,stroke=0)
    labels=[label_data(e) for e in d['edges'] if e['label']]
    for item in common_text(d,index)+labels:
        text,x,y,size,bold,color=item
        if item in labels:
            c.setFillColor(HexColor(COL['bg']));c.setStrokeColor(HexColor(color));c.setLineWidth(.8);c.roundRect(x-7,H-y-size*1.4+2,measure(text,size)+14,size*1.4+2,4,fill=1,stroke=1)
        c.setFont(FONT_BOLD if bold else FONT_REGULAR,size);c.setFillColor(HexColor(color));c.drawString(x,H-y-size,text)
    c.restoreState();c.showPage()

def drawio():
    mx=ET.Element('mxfile',host='app.diagrams.net',version='24.7.17',type='device')
    for index,d in enumerate(D):
        diagram=ET.SubElement(mx,'diagram',id=d['slug'],name=d['title'])
        model=ET.SubElement(diagram,'mxGraphModel',dx='1600',dy='1200',grid='1',page='1',pageScale='1',pageWidth='1600',pageHeight='1200',background=COL['bg'])
        root=ET.SubElement(model,'root');ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
        seq=0
        def cell(value,x,y,w,h,style,id=None):
            nonlocal seq
            seq+=1
            e=ET.SubElement(root,'mxCell',id=('n-'+id) if id else 'x'+str(seq),value=value,style=style,vertex='1',parent='1')
            ET.SubElement(e,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})
        for g in d['groups']:
            cell(g['title'],g['x'],g['y'],g['w'],g['h'],f"rounded=1;arcSize=4;whiteSpace=wrap;html=0;fillColor={g['fill']};strokeColor={COL['line']};strokeWidth=2.2;fontColor={COL['muted']};fontSize=25;align=left;verticalAlign=top;spacing=15;dashed={int(g['dash'])};fontFamily={FONT_FAMILY};",g['id'])
        for n in d['nodes']:
            fill,stroke,dash=node_style(n)
            value='\n'.join([n['title']]+([n['model']] if n['model'] else [])+n['lines'])
            cell(value,n['x'],n['y'],n['w'],n['h'],f"rounded=1;arcSize=4;whiteSpace=wrap;html=0;fillColor={fill};strokeColor={stroke};strokeWidth=2.2;fontColor={COL['ink']};fontSize=23;fontFamily={FONT_FAMILY};align=left;verticalAlign=middle;spacing=15;dashed={int(dash)};",n['id'])
        for j in d['junctions']:
            cell('',j['x']-5,j['y']-5,10,10,f"ellipse;fillColor={COL[j['kind']]};strokeColor=none;",j['id'])
        for i,e in enumerate(d['edges']):
            attrs=dict(id='e'+str(i),edge='1',parent='1',value='',style=f"edgeStyle=none;html=0;endArrow={'block' if e['end_arrow'] else 'none'};startArrow={'block' if e['both'] else 'none'};endSize={ARROW_LENGTH};startSize={ARROW_LENGTH};endFill=1;startFill=1;strokeColor={COL[e['kind']]};strokeWidth={LINE_WIDTH};rounded=0;lineJoin=miter;exitPerimeter=0;entryPerimeter=0;")
            lookup={n['id']:n for n in d['nodes']+[g for g in d['groups'] if g['id']]}
            lookup.update({j['id']:dict(x=j['x']-5,y=j['y']-5,w=10,h=10) for j in d['junctions']})
            for key,point,prefix in [('source',e['points'][0],'exit'),('target',e['points'][-1],'entry')]:
                if e[key] and e[key] in lookup:
                    n=lookup[e[key]]
                    rx=(point[0]-n['x'])/n['w'];ry=(point[1]-n['y'])/n['h']
                    if -.01<=rx<=1.01 and -.01<=ry<=1.01:
                        attrs[key]='n-'+e[key]
                        attrs['style']+=f'{prefix}X={rx};{prefix}Y={ry};{prefix}Dx=0;{prefix}Dy=0;'
            el=ET.SubElement(root,'mxCell',attrs);geo=ET.SubElement(el,'mxGeometry',relative='1',**{'as':'geometry'})
            for point,name in [(e['points'][0],'sourcePoint'),(e['points'][-1],'targetPoint')]:ET.SubElement(geo,'mxPoint',x=str(point[0]),y=str(point[1]),**{'as':name})
            arr=ET.SubElement(geo,'Array',**{'as':'points'})
            for x,y in e['points'][1:-1]:ET.SubElement(arr,'mxPoint',x=str(x),y=str(y))
        texts=common_text(d,index)+[label_data(e) for e in d['edges'] if e['label']]
        # Node captions are already in the editable vertex labels.
        node_text_positions={(p[1],p[2]) for n in d['nodes'] for p in text_layout(n)}
        for text,x,y,size,bold,color in texts:
            if (x,y) in node_text_positions:continue
            cell(text,x,y,measure(text,size,bold)+12,size*1.55,f"text;html=0;strokeColor=none;fillColor=none;align=left;verticalAlign=top;whiteSpace=wrap;fontFamily={FONT_FAMILY};fontSize={size};fontColor={color};fontStyle={int(bold)};")
    return ET.tostring(mx,encoding='unicode')

def main(argv=None):
    global LOCALE,LEGEND,THEME,PALETTE
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec',type=Path);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--locale',default='auto');parser.add_argument('--prompt-file',type=Path)
    parser.add_argument('--formats',default='html,svg,pdf,drawio')
    parser.add_argument('--theme',choices=('auto','dark','light'),default='auto')
    parser.add_argument('--validate-only',action='store_true')
    parser.add_argument('--font',type=Path);parser.add_argument('--bold-font',type=Path)
    parser.add_argument('--font-index',type=int,default=0);parser.add_argument('--poppler-dir',type=Path)
    parser.add_argument('--scale-to',type=int,default=1800);parser.add_argument('--no-archive',action='store_true')
    args=parser.parse_args(argv)
    raw=json.loads(args.spec.read_text(encoding='utf-8-sig'))
    chosen=args.locale if args.locale!='auto' else (detect_locale(args.prompt_file.read_text(encoding='utf-8-sig')) if args.prompt_file else raw.get('locale'))
    if not chosen or chosen=='auto':chosen='en'
    LOCALE=normalize_locale(chosen);LEGEND=get_legend(LOCALE,raw.get('legend'))
    THEME=raw.get('theme','dark') if args.theme=='auto' else args.theme
    if THEME not in THEMES:raise ValueError('Theme must be dark or light')
    COL.clear();COL.update(THEMES[THEME]);PALETTE=raw.get('palette',{})
    for key,value in raw.get('palette',{}).items():
        if key not in LEGEND or not re.fullmatch(r'#[0-9a-fA-F]{6}',value):raise ValueError('Palette needs known keys and #RRGGBB values')
        COL[key]=value
    load_document(raw)
    text=all_text(raw)
    formats=set(args.formats.split(','))
    if not formats or formats-{'html','svg','pdf','drawio','png'}:raise ValueError('formats: html,svg,pdf,drawio,png')
    if formats&{'pdf','png'} and needs_shaping(text):
        raise ValueError('PDF/PNG backend cannot shape this script. Generate SVG/drawio, then use browser/native-shaping PDF export.')
    fonts=register_fonts(args,text)
    for i,page in enumerate(D):
        for obj in page['nodes']+page['groups']:
            if obj['w']<=0 or obj['h']<=0 or obj['x']<0 or obj['y']<0 or obj['x']+obj['w']>W or obj['y']+obj['h']>H:
                raise ValueError(f"{page['slug']}: rectangle outside page bounds")
        for j,node in enumerate(page['nodes']):
            for other in page['nodes'][j+1:]:
                if overlaps(rect_bounds(node),rect_bounds(other)):
                    raise ValueError(f"{page['slug']}: overlapping nodes {node['id']} and {other['id']}")
        for edge in page['edges']:
            if any(not(0<=x<=W and 0<=y<=H) for x,y in edge['points']):
                raise ValueError(f"{page['slug']}: connector outside page bounds")
        for caption,x,y,size,bold,color in common_text(page,i):
            if x<0 or y<0 or x+measure(caption,size,bold)>W or y+size>H:
                raise ValueError(f"{page['slug']}: text outside page bounds: {caption}")
        prepare_connections(page,i)
    svg_pages=[svg(page,i) for i,page in enumerate(D)]
    html_content=build_html({**raw,'theme':THEME,'legend':LEGEND},D,svg_pages,LOCALE) if 'html' in formats else None
    if 'png' in formats:
        exe=(args.poppler_dir/('pdftoppm.exe' if os.name=='nt' else 'pdftoppm')) if args.poppler_dir else shutil.which('pdftoppm')
        if not exe or not Path(exe).is_file():raise ValueError('PNG output requires pdftoppm on PATH or --poppler-dir')
    if args.validate_only:
        result={'locale':LOCALE,'theme':THEME,'pages':len(D),'fonts':fonts,'validation':'geometry, glyphs and requested backends passed; visual review required'}
        print(json.dumps(result,ensure_ascii=False));return result
    args.out.mkdir(parents=True,exist_ok=True);out=args.out.resolve()
    basename=safe_name(raw.get('name','hardware-architecture'));files=[]
    if html_content is not None:files.append(write_output(out/(basename+'.html'),html_content))
    if 'svg' in formats:
        for i,page in enumerate(D):files.append(write_output(out/(page['slug']+'.svg'),svg(page,i)))
    pdf_bytes=None
    if formats&{'pdf','png'}:
        stream=BytesIO();c=canvas.Canvas(stream,pagesize=landscape(A3))
        c.setTitle(raw.get('title',basename));c.setAuthor('Schematic Hardware Diagrams')
        for i,page in enumerate(D):
            c.bookmarkPage(page['slug']);c.addOutlineEntry(page['title'],page['slug'],level=0);draw_pdf(page,i,c)
        c.save();pdf_bytes=stream.getvalue()
        if 'pdf' in formats:files.append(write_output(out/(basename+'.pdf'),pdf_bytes))
    if 'drawio' in formats:files.append(write_output(out/(basename+'.drawio'),drawio()))
    if 'png' in formats:
        exe=(args.poppler_dir/('pdftoppm.exe' if os.name=='nt' else 'pdftoppm')) if args.poppler_dir else shutil.which('pdftoppm')
        if not exe or not Path(exe).is_file():raise ValueError('PNG output requires pdftoppm on PATH or --poppler-dir')
        with tempfile.TemporaryDirectory(prefix='diagram-preview-',dir=out) as working:
            working=Path(working);pdf_path=working/'preview.pdf';pdf_path.write_bytes(pdf_bytes)
            subprocess.run([str(exe),'-scale-to',str(args.scale_to),'-png',str(pdf_path),str(working/'page')],check=True)
            raster=sorted(working.glob('page-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
            if len(raster)!=len(D):raise ValueError('PNG page count mismatch')
            for page,path in zip(D,raster):files.append(write_output(out/(page['slug']+'.png'),path.read_bytes()))
    files.append(write_output(out/'diagram-data.json',json.dumps({**raw,'locale':LOCALE,'theme':THEME,'pages':D},ensure_ascii=False,indent=2)))
    manifest={'locale':LOCALE,'theme':THEME,'pages':len(D),'fonts':fonts,'palette':{k:COL[k] for k in LEGEND},
              'legend':LEGEND,'connectors':sum(len(d['edges']) for d in D),
              'bound_endpoints':sum(d['connection_check']['bound_endpoints'] for d in D),
              'labels_checked':sum(d['connection_check']['labels_checked'] for d in D),
              'validation':'geometry and glyph checks passed; visual review required',
              'files':[str(p) for p in files]}
    manifest_path=write_output(out/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2));files.append(manifest_path)
    if not args.no_archive:
        buffer=BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in files:archive.write(path,path.name)
        archive_path=write_output(out/(basename+'.zip'),buffer.getvalue())
        manifest['archive']=str(archive_path)
    print(json.dumps(manifest,ensure_ascii=False))
    return manifest

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,FileNotFoundError,subprocess.CalledProcessError) as exc:
        raise SystemExit(f'Diagram error: {exc}')
