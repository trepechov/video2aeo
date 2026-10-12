const { JSDOM } = require('jsdom');
const fs = require('fs');
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'https://example.org' });
const g = globalThis;
for (const k of ['window','document','navigator','Node','HTMLElement','Element','DOMParser','MutationObserver','getComputedStyle','CustomEvent','Event','KeyboardEvent','requestAnimationFrame','cancelAnimationFrame','matchMedia','localStorage']) {
  try { if (dom.window[k] !== undefined && g[k] === undefined) Object.defineProperty(g, k, { value: dom.window[k], configurable: true, writable: true }); } catch {}
}
g.window.matchMedia = g.window.matchMedia || (() => ({ matches:false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} }));
g.matchMedia = g.window.matchMedia;
g.requestAnimationFrame = g.requestAnimationFrame || (cb => setTimeout(cb, 0));
const blocks = require('@wordpress/blocks');
const lib = require('@wordpress/block-library');
lib.registerCoreBlocks();
const html = fs.readFileSync(process.argv[2], 'utf8');
const parsed = blocks.parse(html);
let bad = 0;
const walk = (bs, depth=0) => bs.forEach(b => {
  if (!b.name) return;
  if (!b.isValid) { bad++; console.log('INVALID', b.name, JSON.stringify(b.validationIssues?.map(i=>i.args?.slice?.(0,3))).slice(0,600)); }
  walk(b.innerBlocks, depth+1);
});
walk(parsed);
const count = (bs) => bs.reduce((n,b)=> n + (b.name?1:0) + count(b.innerBlocks), 0);
console.log(`blocks: ${count(parsed)}, invalid: ${bad}, top-level first: ${parsed.find(b=>b.name)?.name}`);
