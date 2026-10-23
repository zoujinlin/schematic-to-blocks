'use strict';
// Parse the real generated document; exercise its runtime without network access.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let parseHTML;
try{({parseHTML}=require('linkedom'))}catch(error){if(process.argv.includes('--probe'))process.exit(2);throw error}
if(process.argv.includes('--probe'))process.exit(0);
const markup=fs.readFileSync(process.argv[2],'utf8');
const payload=JSON.parse(markup.match(/<script type="application\/json" id="document">([\s\S]*?)<\/script>/)[1]);
const runtime=markup.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
function setup(reduced=false){
  const {window,document}=parseHTML(markup),timers=[],downloads=[];
  // LinkeDOM omits the native select.value setter; supply that browser primitive.
  const pages=document.getElementById('pages');Object.defineProperty(pages,'value',{
    get(){return(this.querySelector('option[selected]')||this.firstElementChild)?.getAttribute('value')||''},
    set(value){[...this.children].forEach(o=>o.toggleAttribute('selected',o.getAttribute('value')===String(value)))}
  });
  window.matchMedia=()=>({matches:reduced});window.print=()=>{};
  const URLMock={createObjectURL(blob){downloads.push(blob);return'blob:unit'},revokeObjectURL(){}};
  class Serializer{serializeToString(node){return node.toString()}}
  const context=vm.createContext({document,window,Blob,URL:URLMock,XMLSerializer:Serializer,setTimeout:fn=>timers.push(fn)});
  document.getElementById('canvas').getBoundingClientRect=()=>({left:0,top:0,width:1000,height:600});
  vm.runInContext(runtime,context);
  return{window,document,context,timers,downloads,$:id=>document.getElementById(id)};
}
const env=setup(),{document,window,context,$}=env;
function click(element){element.dispatchEvent(new window.Event('click',{bubbles:true}))}
function nodes(){return[...$('canvas').querySelectorAll('[data-node]')]}
function view(){return $('canvas').querySelector('svg').getAttribute('viewBox').split(' ').map(Number)}
for(const end of [false,true])for(const both of [false,true]){
  const page={edges:[{source:'a',target:'b',end_arrow:end,both}]},reach=vm.runInContext('graphReach',context);
  assert.equal(reach(page,'a','down').ids.has('b'),end||!both);assert.equal(reach(page,'b','down').ids.has('a'),both||!end);
}
assert.equal($('pages').children.length,payload.pages.length);assert.equal($('up').disabled,true);
let count=0;
for(let index=0;index<payload.pages.length;index++){
  $('pages').value=String(index);$('pages').dispatchEvent(new window.Event('change'));
  assert.equal(nodes().length,payload.pages[index].nodes.length);
  for(const node of nodes()){
    click(node);const record=payload.pages[index].nodes.find(n=>n.id===node.dataset.node);
    assert.equal($('up').disabled,false);assert.equal($('card-title').textContent,record.title);
    click($('down'));click($('up'));click($('focus'));count++;
  }
  const edge=$('canvas').querySelector('[data-edge]');if(edge){click(edge);assert.equal($('up').disabled,true);assert($('details').textContent.includes(payload.ui.fromLabel))}
  $('search').value='THIS_MODEL_DOES_NOT_EXIST';$('search').dispatchEvent(new window.Event('input'));assert(nodes().every(n=>n.classList.contains('dim')));
  click($('reset'));assert.equal($('search').value,'');assert.equal($('up').disabled,true);
}
$('pages').value='0';$('pages').dispatchEvent(new window.Event('change'));
const power=nodes().find(n=>n.dataset.node==='power');
if(power){click(power);click($('down'));for(const id of ['power','acquisition','isolation'])assert(!nodes().find(n=>n.dataset.node===id).classList.contains('dim'));assert(nodes().find(n=>n.dataset.node==='sensor').classList.contains('dim'))}
const initialTheme=document.documentElement.dataset.theme;click($('theme'));assert.notEqual(document.documentElement.dataset.theme,initialTheme);assert.equal($('canvas').querySelector('svg').dataset.theme,document.documentElement.dataset.theme);
const initialMotion=$('canvas').querySelector('svg').dataset.motion;click($('motion'));assert.notEqual($('canvas').querySelector('svg').dataset.motion,initialMotion);
click($('fit'));const fitted=view();click($('zoom-in'));assert(view()[2]<fitted[2]);click($('zoom-out'));assert(Math.abs(view()[2]-fitted[2])<1e-8);
click($('present'));assert(document.body.classList.contains('present'));click($('present'));assert(!document.body.classList.contains('present'));
click($('close'));assert.equal(document.body.dataset.details,'closed');click(nodes()[0]);assert.equal(document.body.dataset.details,'open');
function pointer(type,values){const event=new window.Event(type,{bubbles:true});Object.assign(event,values);$('canvas').dispatchEvent(event)}
let captures=0,releases=0;$('canvas').setPointerCapture=()=>captures++;$('canvas').hasPointerCapture=()=>captures>releases;$('canvas').releasePointerCapture=()=>releases++;
pointer('pointerdown',{button:0,pointerId:1,clientX:100,clientY:100});pointer('pointerup',{pointerId:1,clientX:100,clientY:100});click(nodes()[0]);assert.equal(captures,0);assert.equal($('card-title').textContent,payload.pages[0].nodes[0].title);
pointer('pointerdown',{button:0,pointerId:2,clientX:100,clientY:100});pointer('pointermove',{pointerId:2,clientX:180,clientY:130});pointer('pointerup',{pointerId:2});assert.equal(captures,1);assert.equal(releases,1);assert(view()[0]<fitted[0]);env.timers.splice(0).forEach(fn=>fn());
const scaled=vm.runInContext('scaleBox',context)([10,20,1000,600],2,.2,.7);assert.equal(scaled[0]+scaled[2]*.2,210);assert.equal(scaled[1]+scaled[3]*.7,440);
const exported=vm.runInContext('exportMarkup()',context),parsed=parseHTML(exported).document;
const svg=parsed.querySelector('svg');assert.equal(svg.getAttribute('viewBox'),'0 0 1600 1200');assert.equal(svg.dataset.motion,'off');assert.equal(svg.querySelectorAll('[data-node]').length,payload.pages[0].nodes.length);assert.equal(svg.querySelectorAll('.dim,.selected,.active-edge,.edge-flow,.edge-hit').length,0);
const reduced=setup(true);assert.equal(reduced.$('motion').disabled,true);assert.equal(reduced.$('canvas').querySelector('svg').dataset.motion,'off');
console.log(JSON.stringify({ok:true,pages:payload.pages.length,cardsChecked:count,checks:['semantic SVG identities','page switching','node and connection cards','search','reach and focus','themes','reduced motion','zoom','pan','presentation','complete SVG export'],mode:'parsed DOM runtime; no browser rasterization'}));
