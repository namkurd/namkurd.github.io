// Renders shell/icons/logo.svg to the PNG icon sizes. Run from the repo root:
//   node tools/icons/render.js
const {chromium}=require('playwright');const fs=require('fs');
const sizes={'icon-512.png':512,'icon-192.png':192,'maskable-512.png':512,'apple-touch-icon-180.png':180,'favicon-32.png':32};
(async()=>{const svg=fs.readFileSync('shell/icons/logo.svg','utf8');
const b=await chromium.launch();const p=await b.newPage();
for(const [name,s] of Object.entries(sizes)){await p.setViewportSize({width:s,height:s});
await p.setContent(`<html><body style="margin:0">${svg.replace('<svg ',`<svg width="${s}" height="${s}" `)}</body></html>`);
await p.screenshot({path:`shell/icons/${name}`});}
await b.close();})();
