"""Function-specific vector symbols shared by every diagram backend.

Coordinates use a 44 x 32 viewport. Circuit symbols (amplifiers, sources,
passives) and labeled functional notation (A/D, D/A, DC/DC, REF, CTRL) are
deliberately distinct. Selection is authored from circuit evidence, never
guessed from a translated caption, device reference or color category.
"""
import base64
from urllib.parse import quote
import xml.etree.ElementTree as ET
import zlib

WIDTH, HEIGHT = 44, 32
STROKE_WIDTH = 1.8


def path(*commands):
    return {'tag': 'path', 'commands': commands}


def label(value, size=10):
    return {'tag': 'text', 'x': 22, 'y': 16, 'size': size, 'value': value}


LEADS = path(('M', 0, 16), ('L', 8, 16), ('M', 36, 16), ('L', 44, 16))
BOX = {'tag': 'rect', 'x': 8, 'y': 3, 'width': 28, 'height': 26}
SYMBOLS = {
    'none': (),
    'connector': (
        path(('M', 0, 9), ('L', 17, 9), ('M', 0, 23), ('L', 17, 23),
             ('M', 27, 9), ('L', 44, 9), ('M', 27, 23), ('L', 44, 23)),
        {'tag': 'circle', 'cx': 22, 'cy': 9, 'r': 5},
        {'tag': 'circle', 'cx': 22, 'cy': 23, 'r': 5}),
    'amplifier': (
        path(('M', 10, 2), ('L', 10, 30), ('L', 36, 16), ('Z',),
             ('M', 0, 16), ('L', 10, 16), ('M', 36, 16), ('L', 44, 16)),),
    'op-amp': (
        path(('M', 10, 2), ('L', 10, 30), ('L', 36, 16), ('Z',),
             ('M', 0, 9), ('L', 10, 9), ('M', 0, 23), ('L', 10, 23),
             ('M', 36, 16), ('L', 44, 16),
             ('M', 14, 10), ('L', 18, 10), ('M', 16, 8), ('L', 16, 12),
             ('M', 14, 22), ('L', 18, 22)),),
    'adc': (LEADS, BOX, label('A/D')),
    'dac': (LEADS, BOX, label('D/A')),
    'isolation': (
        path(('M', 20, 1), ('L', 20, 31), ('M', 24, 1), ('L', 24, 31),
             ('M', 0, 22), ('L', 4, 22), ('L', 4, 10), ('L', 11, 10), ('L', 11, 22), ('L', 16, 22),
             ('M', 28, 22), ('L', 32, 22), ('L', 32, 10), ('L', 39, 10), ('L', 39, 22), ('L', 44, 22)),),
    'dc-dc': (
        LEADS, BOX,
        path(('M', 8, 29), ('L', 36, 3),
             ('M', 12, 9), ('L', 22, 9), ('M', 12, 12), ('L', 15, 12), ('M', 19, 12), ('L', 22, 12),
             ('M', 23, 21), ('L', 32, 21), ('M', 23, 24), ('L', 26, 24), ('M', 29, 24), ('L', 32, 24))),
    'dc-source': (
        path(('M', 0, 16), ('L', 10, 16), ('M', 34, 16), ('L', 44, 16),
             ('M', 13, 16), ('L', 21, 16), ('M', 17, 12), ('L', 17, 20),
             ('M', 25, 16), ('L', 31, 16)),
        {'tag': 'circle', 'cx': 22, 'cy': 16, 'r': 12}),
    'voltage-reference': (LEADS, BOX, label('REF', 9)),
    'controller': (LEADS, BOX, label('CTRL', 8)),
    'low-pass-filter': (
        LEADS, BOX,
        path(('M', 12, 11), ('L', 23, 11), ('L', 32, 24))),
    'clock': (
        path(('M', 0, 23), ('L', 6, 23), ('L', 6, 9), ('L', 17, 9),
             ('L', 17, 23), ('L', 28, 23), ('L', 28, 9), ('L', 39, 9), ('L', 39, 23), ('L', 44, 23)),),
    'resistor': (
        path(('M', 0, 16), ('L', 7, 16), ('L', 10, 10), ('L', 16, 22),
             ('L', 22, 10), ('L', 28, 22), ('L', 34, 10), ('L', 37, 16), ('L', 44, 16)),),
    'capacitor': (
        path(('M', 0, 16), ('L', 18, 16), ('M', 18, 3), ('L', 18, 29),
             ('M', 26, 3), ('L', 26, 29), ('M', 26, 16), ('L', 44, 16)),),
    'inductor': (
        path(('M', 0, 20), ('L', 6, 20),
             ('C', 6, 6, 14, 6, 14, 20), ('C', 14, 6, 22, 6, 22, 20),
             ('C', 22, 6, 30, 6, 30, 20), ('C', 30, 6, 38, 6, 38, 20), ('L', 44, 20)),),
    'switch': (
        path(('M', 0, 23), ('L', 10, 23), ('M', 12, 21), ('L', 32, 6),
             ('M', 34, 23), ('L', 44, 23)),
        {'tag': 'circle', 'cx': 12, 'cy': 23, 'r': 2},
        {'tag': 'circle', 'cx': 32, 'cy': 23, 'r': 2}),
}


def geometry(symbol):
    try:
        return SYMBOLS[symbol]
    except (KeyError, TypeError):
        raise ValueError('Unknown electrical symbol: ' + repr(symbol)) from None


def svg_elements(parent, symbol, namespace):
    """Append unfilled primitives; color and width are inherited from the group."""
    for primitive in geometry(symbol):
        tag = primitive['tag']
        if tag == 'path':
            attrs = {'d': ' '.join(' '.join(map(str, c)) for c in primitive['commands'])}
        elif tag == 'text':
            attrs = {'x': str(primitive['x']), 'y': str(primitive['y'] + primitive['size'] * .35),
                     'font-size': str(primitive['size']), 'text-anchor': 'middle',
                     'font-weight': '700', 'stroke': 'none', 'class': 'symbol-label'}
        else:
            attrs = {k: str(v) for k, v in primitive.items() if k != 'tag'}
        element = ET.SubElement(parent, '{'+namespace+'}'+tag, attrs)
        if tag == 'text':
            element.text = primitive['value']


def pdf_symbol(canvas, symbol, x, y, page_height, regular_font):
    """Draw identical geometry in PDF's bottom-up coordinate system."""
    canvas.saveState()
    canvas.setLineWidth(STROKE_WIDTH)
    canvas.setLineCap(0)
    canvas.setLineJoin(1)
    for primitive in geometry(symbol):
        tag = primitive['tag']
        if tag == 'path':
            drawing = canvas.beginPath()
            for op, *values in primitive['commands']:
                if op == 'M': drawing.moveTo(x+values[0], page_height-y-values[1])
                elif op == 'L': drawing.lineTo(x+values[0], page_height-y-values[1])
                elif op == 'C': drawing.curveTo(*[x+v if i % 2 == 0 else page_height-y-v for i, v in enumerate(values)])
                elif op == 'Z': drawing.close()
            canvas.drawPath(drawing, stroke=1, fill=0)
        elif tag == 'rect':
            canvas.rect(x+primitive['x'], page_height-y-primitive['y']-primitive['height'],
                        primitive['width'], primitive['height'], stroke=1, fill=0)
        elif tag == 'circle':
            canvas.circle(x+primitive['cx'], page_height-y-primitive['cy'], primitive['r'], stroke=1, fill=0)
        elif tag == 'text':
            canvas.setFont(regular_font, primitive['size'])
            canvas.drawCentredString(x+primitive['x'], page_height-y-primitive['y']-primitive['size']*.35, primitive['value'])
    canvas.restoreState()


def stencil_xml(symbol):
    """Editable draw.io stencil using the same paths, circles and labels."""
    shape = ET.Element('shape', name=symbol, w=str(WIDTH), h=str(HEIGHT), aspect='fixed', strokewidth='inherit')
    foreground = ET.SubElement(shape, 'foreground')
    for primitive in geometry(symbol):
        tag = primitive['tag']
        if tag == 'text':
            ET.SubElement(foreground, 'fontsize', size=str(primitive['size']))
            ET.SubElement(foreground, 'fontstyle', style='1')
            ET.SubElement(foreground, 'text', str=primitive['value'], x=str(primitive['x']), y=str(primitive['y']), align='center', valign='middle')
            continue
        if tag == 'path':
            target = ET.SubElement(foreground, 'path')
            for op, *values in primitive['commands']:
                keys = {'M': ('x', 'y'), 'L': ('x', 'y'), 'C': ('x1', 'y1', 'x2', 'y2', 'x3', 'y3'), 'Z': ()}[op]
                ET.SubElement(target, {'M': 'move', 'L': 'line', 'C': 'curve', 'Z': 'close'}[op],
                              {k: str(v) for k, v in zip(keys, values)})
        elif tag == 'rect':
            ET.SubElement(foreground, 'rect', x=str(primitive['x']), y=str(primitive['y']), w=str(primitive['width']), h=str(primitive['height']))
        elif tag == 'circle':
            r = primitive['r']
            ET.SubElement(foreground, 'ellipse', x=str(primitive['cx']-r), y=str(primitive['cy']-r), w=str(2*r), h=str(2*r))
        ET.SubElement(foreground, 'stroke')
    return ET.tostring(shape, encoding='unicode')


def drawio_shape(symbol):
    # Inline-stencil encoding specified by draw.io Graph.compress. The outer
    # diagram stays plain XML; the geometry remains editable via Edit Shape.
    encoded = quote(stencil_xml(symbol), safe="~()*!.'-").encode('ascii')
    compressor = zlib.compressobj(wbits=-15)
    return 'stencil('+base64.b64encode(compressor.compress(encoded)+compressor.flush()).decode('ascii')+')'
