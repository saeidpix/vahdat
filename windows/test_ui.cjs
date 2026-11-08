// Regression smoke test for the Windows UI. No network/browser installation required.
// Catches syntax errors which otherwise leave the page blank and all buttons inert.
"use strict";
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");
const path = require("path");

const source = fs.readFileSync(path.join(__dirname, "ui.html"), "utf8");
assert(source.includes('id="page"'), "Missing main content region");
for (const name of ["home", "new", "scan", "list", "reports", "settings"]) {
  assert(source.includes('id="nav-' + name + '"'), "Missing navigation item " + name);
}
const match = source.match(/<script>([\s\S]*?)<\/script>/i);
assert(match, "No embedded JavaScript detected");
const script = new vm.Script(match[1], {filename: "windows/ui.html"});

const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      id,
      innerHTML: "",
      value: "",
      focused: false,
      focus() { this.focused = true; },
      addEventListener(event, cb) { this[event] = cb; }
    });
  }
  return elements.get(id);
}
const errors=[];
const context = vm.createContext({
  console,
  Intl,
  alert: (message) => errors.push(String(message)),
  document: {
    getElementById: (id) => element(id),
    querySelectorAll: () => []
  },
  window: {
    scrollTo: () => {},
    print: () => {}
  },
  fetch: async (url) => {
    let data;
    if(url.startsWith("/api/settings")) data={origin:"تهران",destinations:["قائم‌شهر"]};
    else if(url.startsWith("/api/waybills")) data={items:[]};
    else if(url.startsWith("/api/reports")) data={
      today:"۱۴۰۵/۰۸/۱۷",issued:1,received:1,delivered:0,
      total:1000,prepaid:200,post_fare:500,storage_fee:200,
      other_fee:100,collected:0,receivable:800
    };
    else throw Error("Unexpected API request: "+url);
    return {ok:true,json:async()=>data};
  }
});
async function smoke() {
  script.runInContext(context);
  // The startup IIFE awaits fetch in a separate VM realm; settle it fully first.
  await new Promise((resolve) => setTimeout(resolve, 30));
  await context.go("home");
  assert(element("page").innerHTML.includes("صدور بارنامه"), "Home buttons not rendered");

  await context.go("new");
  assert(element("page").innerHTML.includes("جمع کل کرایه"), "Issuing form did not render: "+errors.join(" | ")+" / "+element("page").innerHTML.slice(0,120));
  assert(element("page").innerHTML.includes("قائم‌شهر"), "Single destination missing");
  assert(element("page").innerHTML.includes("سایر هزینه‌ها"), "4-part fare is incomplete");

  await context.go("scan");
  assert(element("page").innerHTML.includes("qrInput"), "QR scanner input missing");
  assert(element("qrInput").focused,"Barcode scan input not focused");

  await context.go("list");
  assert(element("page").innerHTML.includes("جست‌وجو"), "Waybill list blank");

  await context.go("reports");
  assert(element("page").innerHTML.includes("وصولی‌ها"), "Financial report blank");

  await context.go("settings");
  assert(element("page").innerHTML.includes("مدیریت مقصدها"), "Settings blank");
  assert.strictEqual(errors.length,0,"UI displayed runtime error: "+errors.join(" | "));
  console.log("Windows UI smoke PASS: syntax, home, issuance, scan, list, finance, settings");
}
smoke().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
