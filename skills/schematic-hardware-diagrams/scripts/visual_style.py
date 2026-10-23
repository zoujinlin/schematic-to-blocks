"""Shared theme tokens for standalone SVG, the HTML viewer and static exports."""
THEMES = {
    'dark': dict(bg='#07111f', ink='#e8f1fa', muted='#91a7bc', line='#334d65', grid='#102236',
        node='#102235', group='#0b1b2b', interface='#102a3b', powerfill='#281c29', referencefill='#201d37',
        data='#66b4ff', control='#f5b34b', power='#ff6974', reference='#bc9bff', optional='#a0adbd'),
    'light': dict(bg='#f5f8fc', ink='#192f45', muted='#5b7085', line='#b6c8d9', grid='#e6edf5',
        node='#ffffff', group='#eef3f9', interface='#edf6ff', powerfill='#fff1f2', referencefill='#f3effd',
        data='#126ca6', control='#a36700', power='#c62828', reference='#7953a0', optional='#74849a'),
}


def category(node):
    if node.get('category'):
        return node['category']
    if node.get('kind') in ('power', 'power_external'):
        return 'power'
    return 'reference' if node.get('kind') == 'reference' else 'data'


def theme_css(selector, overrides=None):
    rules=[]
    for name, tokens in THEMES.items():
        values={**tokens, **(overrides or {})}
        rules.append(selector+'[data-theme="'+name+'"]{'+''.join('--'+key+':'+value+';' for key,value in values.items())+'}')
    return '\n'.join(rules)


SVG_CSS = '''
.diagram-paper{fill:var(--bg)}.grid-line{stroke:var(--grid);stroke-width:.8}
.frame-line{stroke:var(--line);fill:none}.text-ink{fill:var(--ink)}.text-muted{fill:var(--muted)}
.domain-data{--domain:var(--data)}.domain-control{--domain:var(--control)}
.domain-power{--domain:var(--power)}.domain-reference{--domain:var(--reference)}
.domain-text{fill:var(--domain)}.domain-stroke{stroke:var(--domain)}.domain-fill{fill:var(--domain)}
.group-frame{fill:var(--group);stroke:var(--line)}.group-tag{fill:var(--bg);stroke:var(--line)}
.node-card{fill:var(--node);stroke:var(--domain);stroke-opacity:.65;stroke-width:1.8}
.kind-interface .node-card{fill:var(--interface)}.domain-power .node-card{fill:var(--powerfill)}
.domain-reference .node-card{fill:var(--referencefill)}.node-icon{fill:none;stroke:var(--domain);stroke-width:1.8}
.node-icon-bg{fill:var(--domain);fill-opacity:.09;stroke:var(--domain);stroke-opacity:.3}
.edge-shaft{fill:none;stroke:var(--domain);stroke-linejoin:round;stroke-linecap:butt}
.edge-head{fill:var(--domain)}.edge-hit{fill:none;stroke:transparent;stroke-width:20;pointer-events:stroke}
.edge-label-bg{fill:var(--bg);stroke:var(--domain);stroke-opacity:.35;stroke-width:1}
.edge-flow{fill:none;stroke:var(--domain);stroke-width:2;stroke-dasharray:5 22;stroke-linecap:round;opacity:.7;animation:flow 2.2s linear infinite}
svg[data-motion="off"] .edge-flow{display:none}
@keyframes flow{to{stroke-dashoffset:-54}}
@media(prefers-reduced-motion:reduce){.edge-flow{display:none}}
'''
