'use strict';
// Local models only. No CDN or automatic language-model download.
const fs = require('node:fs');
const path = require('node:path');
async function main() {
  const [image, output, ...rest] = process.argv.slice(2);
  const opts = {lang: 'eng'};
  if (!image || !output || rest.length % 2) throw Error('INPUT OUTPUT --tessdata DIR [--module PACKAGE_DIR] [--lang eng+chi_sim]');
  for (let i = 0; i < rest.length; i += 2) {
    const key = rest[i].replace(/^--/, '');
    if (!['lang', 'tessdata', 'module'].includes(key)) throw Error('Unknown option: ' + key);
    opts[key] = rest[i + 1];
  }
  if (!/^[a-z_]+(?:\+[a-z_]+)*$/.test(opts.lang) || !opts.tessdata) throw Error('Local language models are required');
  for (const lang of opts.lang.split('+')) fs.accessSync(path.join(opts.tessdata, lang + '.traineddata'));
  const modulePath = opts.module ? path.resolve(opts.module) : 'tesseract.js';
  const {createWorker, OEM} = require(modulePath);
  const worker = await createWorker(opts.lang, OEM.LSTM_ONLY, {langPath: path.resolve(opts.tessdata), gzip: false, cacheMethod: 'none'});
  try {
    await worker.setParameters({tessedit_pageseg_mode: '11', preserve_interword_spaces: '1'});
    const {data} = await worker.recognize(path.resolve(image), {}, {text: true, blocks: true});
    fs.writeFileSync(output + '.txt', data.text || '', 'utf8');
    fs.writeFileSync(output + '.json', JSON.stringify({confidence: data.confidence, blocks: data.blocks, basis: 'ocr-candidate'}, null, 2));
  } finally { await worker.terminate(); }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
