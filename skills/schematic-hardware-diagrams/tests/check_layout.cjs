'use strict';
// Use synthetic circuit data only. This checks CSS layout in a real browser,
// including the min-content width regression that a DOM parser cannot detect.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../../..'),out=path.join(root,'output/layout-review');
const sizes=[[1920,1080],[1366,768],[1280,720],[1024,768],[768,1024],[640,400],[390,844],[320,740]];
function fixture(locale){
  let markup=fs.readFileSync(path.join(root,`examples/acquisition.${locale}.html`),'utf8');
  const pattern=/<script type="application\/json" id="document">([\s\S]*?)<\/script>/;
  const data=JSON.parse(markup.match(pattern)[1]),original=structuredClone(data);
  const title=locale==='zh-Hans'?'硬件功能模块：器件型号、接口控制与供电路径':'Hardware module: device models, interface controls and power paths';
  data.pages=[];data.svg=[];data.bounds=[];
  for(let i=0;i<13;i++){
    const p=structuredClone(original.pages[i%original.pages.length]);
    p.title=`${String(i+1).padStart(2,'0')} · ${title}`;
    if(i===12)p.title+=' · '+('LongTranslatedModuleTitleWithoutSpaces'.repeat(4));
    data.pages.push(p);data.svg.push(original.svg[i%original.svg.length]);data.bounds.push(original.bounds[i%original.bounds.length]);
  }
  const encoded=JSON.stringify(data).replaceAll('&','\\u0026').replaceAll('<','\\u003c').replaceAll('>','\\u003e');
  markup=markup.replace(pattern,()=>`<script type="application/json" id="document">${encoded}</script>`);
  // Stress the header independently of the circuit diagrams.
  markup=markup.replace(/<h1>[^<]*<\/h1>/,`<h1>${title} · ${title}</h1>`);
  return{markup,data};
}
async function noHorizontalOverflow(page,label){
  const size=await page.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
  assert(size.scroll<=size.width+1,`${label}: document width ${size.scroll} exceeds viewport ${size.width}`);
}
async function inViewport(page,selector,{vertical=true}={}){
  const rect=await page.locator(selector).boundingBox(),viewport=page.viewportSize();
  assert(rect&&rect.width>0&&rect.height>0,`${selector}: hidden or empty`);
  assert(rect.x>=-1&&rect.x+rect.width<=viewport.width+1,`${selector}: outside viewport horizontally ${JSON.stringify(rect)}`);
  if(vertical)assert(rect.y>=-1&&rect.y+rect.height<=viewport.height+1,`${selector}: outside viewport vertically ${JSON.stringify(rect)}`);
}
(async()=>{
  fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch(),results=[];
  try{
    for(const locale of ['en','zh-Hans']){
      const {markup,data}=fixture(locale);
      const context=await browser.newContext({reducedMotion:'reduce'});
      // Delivered HTML is self-contained. No source documents or online services.
      await context.route('**/*',route=>route.abort());
      const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
      for(const [width,height] of sizes){
        await page.setViewportSize({width,height});
        await page.setContent(markup,{waitUntil:'load'});
        assert.equal(await page.locator('#pages option').count(),13);
        for(const index of [12,0,6,12]){
          await page.locator('#pages').selectOption(String(index));
          assert.equal(await page.locator('#card-title').textContent(),data.pages[index].title);
          assert.equal(await page.locator('.nav-page[aria-current="page"]').getAttribute('data-page'),String(index));
        }
        await noHorizontalOverflow(page,`${locale} ${width}x${height}`);
        for(const selector of ['#theme','#export','#pages'])await inViewport(page,selector);
        // The details pane stacks below the canvas on phones; ordinary vertical
        // scrolling is expected there and on very short screens.
        await page.locator('#search').scrollIntoViewIfNeeded();
        await inViewport(page,'#search');await inViewport(page,'aside',{vertical:width>760&&height>500});
        await page.locator('#search').fill('THIS_MODEL_DOES_NOT_EXIST');
        assert.equal(await page.locator('#canvas [data-node]:not(.dim)').count(),0);
        await page.locator('#search').fill('');
        await page.locator('#theme').click();assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
        await page.locator('#export').click();await inViewport(page,'#export-menu');
        const button=await page.locator('#export').boundingBox(),menu=await page.locator('#export-menu').boundingBox();
        assert(menu.y>=button.y+button.height-1,'Export menu overlaps its trigger after wrapping');
        await page.screenshot({path:path.join(out,`${locale}-${width}-light.png`),fullPage:true});
        await page.locator('#export').click();await page.locator('#theme').click();
        if(width>1100){
          const nav=await page.locator('#module-nav').boundingBox(),tab=await page.locator('.nav-page[aria-current="page"]').boundingBox();
          assert(tab.x>=nav.x-1&&tab.x+tab.width<=nav.x+nav.width+1,'Selected tab is outside its own scroll area');
          await page.locator('.nav-page').first().click();assert.equal(await page.locator('#pages').inputValue(),'0');
        }
        await noHorizontalOverflow(page,`${locale} ${width} after interactions`);
        await page.screenshot({path:path.join(out,`${locale}-${width}-dark.png`),fullPage:true});
        results.push({locale,width,height,pages:13,ok:true});
      }
      assert.deepEqual(errors,[]);await context.close();
    }
  }finally{await browser.close()}
  fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({ok:true,results},null,2));
  console.log(JSON.stringify({ok:true,cases:results.length,modules:13,checks:['no document overflow','module selector','active tab visibility','search and details','wrapped header controls','anchored export menu','dark and light themes']}));
})().catch(error=>{console.error(error);process.exitCode=1});
