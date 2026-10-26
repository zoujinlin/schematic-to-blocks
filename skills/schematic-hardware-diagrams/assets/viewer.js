'use strict';
const doc=JSON.parse(document.getElementById('document').textContent),ui=doc.ui;
const $=id=>document.getElementById(id);
const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let pageIndex=0,selected=null,theme=doc.theme||'dark',motion=!reduced,box=null,drag=null,suppressClick=false;
const buttons=['up','down','reset','export','print','focus','exportSvg','exportPng'];
buttons.forEach(id=>$(id).textContent=ui[id]);
$('search').placeholder=ui.search;$('intro').textContent=doc.summary||ui.intro;
$('hint').textContent=ui.hint;$('close').title=ui.close;
$('zoom-in').title=ui.zoomIn;$('zoom-out').title=ui.zoomOut;$('fit').title=ui.fit;
$('motion').title=reduced?ui.reduced:ui.motion;$('motion').disabled=reduced;
$('pages').setAttribute('aria-label',ui.pages);
doc.pages.forEach((page,index)=>{
  const option=document.createElement('option');option.value=String(index);option.textContent=String(index+1).padStart(2,'0')+' · '+page.title;$('pages').append(option);
  const button=document.createElement('button');button.className='nav-page';button.dataset.page=String(index);button.title=page.title;
  const number=document.createElement('span'),title=document.createElement('span');number.textContent=String(index+1).padStart(2,'0');title.textContent=page.title;
  button.append(number,title);button.onclick=()=>{pageIndex=index;showPage()};$('module-nav').append(button);
});
function svgRoot(){return $('canvas').querySelector('svg')}
function applyTheme(){
  document.documentElement.dataset.theme=theme;
  if(svgRoot())svgRoot().dataset.theme=theme;
  $('theme').textContent=theme==='dark'?'◐ '+ui.dark:'◑ '+ui.light;$('theme').title=ui.theme;
}
function applyMotion(){if(svgRoot())svgRoot().dataset.motion=motion?'on':'off';$('motion').textContent=motion?'◉ '+ui.play:'○ '+ui.pause;$('motion').setAttribute('aria-pressed',String(motion))}
function addSection(title,value){
  if(!value||(Array.isArray(value)&&!value.length))return;
  const h=document.createElement('h3'),p=document.createElement('p');h.textContent=title;p.textContent=Array.isArray(value)?value.join('\n'):value;$('details').append(h,p);
}
function showEvidence(ids){
  const records=(ids||[]).map(id=>(doc.evidence||[]).find(e=>e.id===id)).filter(Boolean);
  if(!records.length)return;
  const heading=document.createElement('h3');heading.textContent=ui.evidence;$('details').append(heading);
  for(const ev of records){
    const record=document.createElement('details'),summary=document.createElement('summary'),body=document.createElement('p');
    record.className='evidence-record';summary.textContent=(ui['basis_'+ev.basis.replaceAll('-','_')]||ev.basis)+' · '+ev.id;
    body.textContent=[ev.source,ev.page?ui.page+' '+ev.page:'',ev.locator,ev.note,ev.sha256?'SHA256 '+ev.sha256:''].filter(Boolean).join('\n');record.append(summary,body);$('details').append(record);
  }
}
function allNodes(){return [...$('canvas').querySelectorAll('[data-node]')]}
function allEdges(){return [...$('canvas').querySelectorAll('[data-edge]')]}
function clearHighlight(){[...allNodes(),...allEdges()].forEach(e=>e.classList.remove('dim','selected','active-edge'))}
function setActions(enabled){['up','down','focus'].forEach(id=>$(id).disabled=!enabled)}
function selectNode(id){
  if(suppressClick)return;selected=id;clearHighlight();const node=doc.pages[pageIndex].nodes.find(n=>n.id===id);if(!node)return;
  document.body.dataset.details='open';allNodes().find(e=>e.dataset.node===id).classList.add('selected');
  $('card-kind').textContent=ui.nodes+' / '+id;$('card-title').textContent=node.title;$('summary').textContent=node.model||'';$('details').replaceChildren();
  addSection(ui.function,node.details?.function||node.lines);addSection(ui.principle,node.details?.principle);addSection(ui.interfaces,node.details?.interfaces);
  addSection(ui.power,node.details?.power);addSection(ui.uncertainty,node.details?.uncertainty);showEvidence(node.evidence);setActions(true);
}
function selectEdge(index){
  if(suppressClick)return;selected=null;clearHighlight();const page=doc.pages[pageIndex],edge=page.edges[index];document.body.dataset.details='open';
  allEdges().find(e=>Number(e.dataset.edge)===index).classList.add('selected');$('card-kind').textContent=ui.connection+' / '+String(index+1).padStart(2,'0');
  $('card-title').textContent=edge.label||doc.legend[edge.kind];$('summary').textContent=doc.legend[edge.kind];$('details').replaceChildren();
  const name=id=>page.nodes.find(n=>n.id===id)?.title||id;addSection(ui.fromLabel,name(edge.source));addSection(ui.toLabel,name(edge.target));showEvidence(edge.evidence);setActions(false);
}
function updateView(){
  svgRoot().setAttribute('viewBox',box.join(' '));const zoom=doc.bounds[pageIndex][2]/box[2];$('fit').textContent=Math.round(zoom*100)+'%';
}
function fit(){box=[...doc.bounds[pageIndex]];updateView()}
function scaleBox(current,factor,fx=.5,fy=.5){const [x,y,w,h]=current;return[x+w*fx-w/factor*fx,y+h*fy-h/factor*fy,w/factor,h/factor]}
function zoom(factor,fx=.5,fy=.5){
  const current=doc.bounds[pageIndex][2]/box[2],next=Math.max(.25,Math.min(6,current*factor));box=scaleBox(box,next/current,fx,fy);updateView();
}
function viewportMetrics(current=box){const rect=$('canvas').getBoundingClientRect(),scale=Math.min(rect.width/current[2],rect.height/current[3]);return{rect,scale,left:rect.left+(rect.width-current[2]*scale)/2,top:rect.top+(rect.height-current[3]*scale)/2}}
function graphReach(page,start,direction){
  const ids=new Set([start]),edges=new Set();let changed=true;
  while(changed){changed=false;page.edges.forEach((edge,index)=>{
    const arcs=[];if(edge.end_arrow||!edge.both)arcs.push([edge.source,edge.target]);if(edge.both||!edge.end_arrow)arcs.push([edge.target,edge.source]);
    for(const [source,target] of arcs){const a=direction==='down'?source:target,b=direction==='down'?target:source;
      if(ids.has(a)){edges.add(index);if(!ids.has(b)){ids.add(b);changed=true}}
    }
  })}return{ids,edges};
}
function highlight(ids,edges){clearHighlight();allNodes().forEach(e=>e.classList.toggle('dim',!ids.has(e.dataset.node)));allEdges().forEach(e=>{const active=edges.has(Number(e.dataset.edge));e.classList.toggle('dim',!active);e.classList.toggle('active-edge',active)});if(selected)allNodes().find(e=>e.dataset.node===selected)?.classList.add('selected')}
function reach(direction){if(selected){const result=graphReach(doc.pages[pageIndex],selected,direction);highlight(result.ids,result.edges)}}
function focus(){
  if(!selected)return;const ids=new Set([selected]),edges=new Set();doc.pages[pageIndex].edges.forEach((e,i)=>{if(e.source===selected||e.target===selected){ids.add(e.source);ids.add(e.target);edges.add(i)}});highlight(ids,edges);
}
function showLegend(){
  $('legend').replaceChildren();for(const key of ['data','control','power','reference']){
    const item=document.createElement('span'),dot=document.createElement('span'),label=document.createElement('span');item.className='legend-item';dot.className='legend-dot';
    item.style.setProperty('--legend-color','var(--'+key+')');label.textContent=doc.legend[key];item.append(dot,label);$('legend').append(item);
  }
}
function showPage(){
  selected=null;const page=doc.pages[pageIndex];$('canvas').innerHTML=doc.svg[pageIndex];svgRoot().setAttribute('role','group');$('pages').value=String(pageIndex);document.body.dataset.details='open';
  $('module-nav').querySelectorAll('button').forEach(e=>{
    const active=Number(e.dataset.page)===pageIndex;e.setAttribute('aria-current',active?'page':'false');
    if(active)e.scrollIntoView?.({block:'nearest',inline:'nearest'});
  });
  $('pages').title=page.title;
  $('card-kind').textContent=(pageIndex?ui.module:ui.overview)+' / '+String(pageIndex+1).padStart(2,'0');$('card-title').textContent=page.title;$('summary').textContent=page.subtitle||'';$('details').replaceChildren();
  addSection(ui.reading,ui.select);addSection(ui.uncertainty,doc.unresolved);setActions(false);$('search').value='';$('status').textContent=ui.scope;
  $('counts').textContent=page.nodes.length+' '+ui.nodes+' / '+page.edges.length+' '+ui.connections;
  for(const e of allNodes()){e.addEventListener('click',()=>selectNode(e.dataset.node));e.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();selectNode(e.dataset.node)}})}
  for(const e of allEdges()){e.addEventListener('click',()=>selectEdge(Number(e.dataset.edge)));e.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();selectEdge(Number(e.dataset.edge))}})}
  applyTheme();applyMotion();showLegend();fit();
}
function exportMarkup(){
  const root=svgRoot().cloneNode(true);root.setAttribute('viewBox','0 0 1600 1200');root.setAttribute('width','1600');root.setAttribute('height','1200');root.setAttribute('role','img');root.dataset.theme=theme;root.dataset.motion='off';root.querySelectorAll('[tabindex]').forEach(e=>e.removeAttribute('tabindex'));
  root.querySelectorAll('.dim,.selected,.active-edge').forEach(e=>e.classList.remove('dim','selected','active-edge'));root.querySelectorAll('.edge-hit,.edge-flow').forEach(e=>e.remove());return new XMLSerializer().serializeToString(root);
}
function download(blob,name){const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function exportSvg(){download(new Blob([exportMarkup()],{type:'image/svg+xml'}),doc.pages[pageIndex].slug+'.svg')}
async function exportPng(){
  const url=URL.createObjectURL(new Blob([exportMarkup()],{type:'image/svg+xml'}));
  try{const image=new Image();await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src=url});const canvas=document.createElement('canvas');canvas.width=2400;canvas.height=1800;canvas.getContext('2d').drawImage(image,0,0,2400,1800);const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw Error('PNG encoder');download(blob,doc.pages[pageIndex].slug+'.png')}
  catch{$('status').textContent=ui.exportError}finally{URL.revokeObjectURL(url)}
}
function togglePresentation(){document.body.classList.toggle('present');$('present').textContent=document.body.classList.contains('present')?ui.exitFullscreen:ui.fullscreen}
$('theme').onclick=()=>{theme=theme==='dark'?'light':'dark';applyTheme()};$('motion').onclick=()=>{if(!reduced){motion=!motion;applyMotion()}};
$('present').textContent=ui.fullscreen;$('present').onclick=togglePresentation;
$('pages').onchange=()=>{pageIndex=Number($('pages').value);showPage()};$('up').onclick=()=>reach('up');$('down').onclick=()=>reach('down');$('focus').onclick=focus;
$('reset').onclick=showPage;$('close').onclick=()=>{document.body.dataset.details='closed'};
$('zoom-in').onclick=()=>zoom(1.2);$('zoom-out').onclick=()=>zoom(1/1.2);$('fit').onclick=fit;
$('search').oninput=()=>{const query=$('search').value.trim().toLocaleLowerCase();clearHighlight();const ids=new Set(doc.pages[pageIndex].nodes.filter(n=>JSON.stringify(n).toLocaleLowerCase().includes(query)).map(n=>n.id));allNodes().forEach(e=>e.classList.toggle('dim',!ids.has(e.dataset.node)))};
$('export').onclick=()=>{$('export-menu').hidden=!$('export-menu').hidden;$('export').setAttribute('aria-expanded',String(!$('export-menu').hidden))};
$('exportSvg').onclick=exportSvg;$('exportPng').onclick=exportPng;
$('print').onclick=()=>{const current=[...box],states=[...allNodes(),...allEdges()].map(e=>[e,e.getAttribute('class')]);clearHighlight();svgRoot().dataset.motion='off';svgRoot().setAttribute('viewBox','0 0 1600 1200');try{window.print()}finally{box=current;updateView();applyMotion();states.forEach(([e,value])=>e.setAttribute('class',value))}};
$('canvas').addEventListener('wheel',event=>{event.preventDefault();const m=viewportMetrics();zoom(event.deltaY<0?1.12:1/1.12,(event.clientX-m.left)/(box[2]*m.scale),(event.clientY-m.top)/(box[3]*m.scale))},{passive:false});
$('canvas').addEventListener('pointerdown',event=>{if(event.button!==0)return;drag={id:event.pointerId,x:event.clientX,y:event.clientY,box:[...box],moved:false}});
$('canvas').addEventListener('pointermove',event=>{if(!drag||event.pointerId!==drag.id)return;const dx=event.clientX-drag.x,dy=event.clientY-drag.y;if(!drag.moved&&Math.hypot(dx,dy)>4){drag.moved=true;$('canvas').setPointerCapture?.(event.pointerId)}if(!drag.moved)return;const m=viewportMetrics(drag.box);box=[drag.box[0]-dx/m.scale,drag.box[1]-dy/m.scale,drag.box[2],drag.box[3]];$('canvas').classList.add('dragging');updateView()});
function endDrag(event){if(!drag||event.pointerId!==drag.id)return;suppressClick=drag.moved;drag=null;$('canvas').classList.remove('dragging');if($('canvas').hasPointerCapture?.(event.pointerId))$('canvas').releasePointerCapture(event.pointerId);setTimeout(()=>suppressClick=false,0)}
$('canvas').addEventListener('pointerup',endDrag);$('canvas').addEventListener('pointercancel',endDrag);
document.addEventListener('keydown',event=>{
  if(['INPUT','SELECT','TEXTAREA'].includes(event.target.tagName))return;
  if(event.key==='t'||event.key==='T')$('theme').click();else if(event.key==='m'||event.key==='M')$('motion').click();
  else if(event.key==='f'||event.key==='F')togglePresentation();else if(event.key==='0')fit();
  else if(event.key==='+'||event.key==='=')zoom(1.2);else if(event.key==='-')zoom(1/1.2);else if(event.key==='Escape'){if(document.body.classList.contains('present'))togglePresentation();showPage();$('export-menu').hidden=true}
});
showPage();
