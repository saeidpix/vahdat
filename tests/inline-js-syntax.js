'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('app/index.html','utf8');
const scripts=[...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];
let checked=0;
scripts.forEach((m,index)=>{
 if(/\bsrc=/.test(m[1]) || /\btype=["'](?:application\/json|importmap)/.test(m[1]))return;
 new vm.Script(m[2],{filename:'app/index.html:script-'+index});
 checked++;
});
assert(checked>5,'expected inline JavaScript scripts');
assert(html.includes('<script src="waybill-audit.js"></script>'));
assert(html.includes('<script src="hid-scanner.js"></script>'));
assert(!html.includes('id="hidScannerStatus"'));
console.log('Barresan inline JS parsing passed ('+checked+' scripts).');
