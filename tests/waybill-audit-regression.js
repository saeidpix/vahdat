'use strict';
const assert=require('assert'),fs=require('fs');
const audit=require('../app/waybill-audit.js');
const ctx={reason:'اصلاح مبلغ طبق رسید مشتری',user:'کاربر صندوق ۱',userId:'u-14',at:'2026-11-17T08:45:12.345Z'};
const base={id:'12',status:'صادرشده',createdAt:'2026-11-17T06:20:00.000Z',
  senderName:'علی',recipientName:'رضا',destination:'آمل',preFare:100,postFare:0,storageFee:0,otherFee:0,total:100,
  packages:[{title:'کارتن',kind:'',qty:1,weight:'2'}]};
const saved=audit.amend(base,{...base,preFare:10,total:10},ctx);
assert.strictEqual(saved.id,'12');
assert.strictEqual(saved.preFare,10);
assert.strictEqual(base.preFare,100);
assert.strictEqual(saved.auditTrail.length,1);
const e=saved.auditTrail[0];
assert.strictEqual(e.type,'edit');
assert.strictEqual(e.reason,ctx.reason);
assert.strictEqual(e.user,ctx.user);
assert.strictEqual(e.userId,ctx.userId);
assert.strictEqual(e.at,ctx.at);
assert(e.changes.some(x=>x.f==='پیش‌کرایه'&&x.from==='۱۰۰ تومان'&&x.to==='۱۰ تومان'));
assert(e.changes.some(x=>x.f==='جمع کل'&&x.from==='۱۰۰ تومان'&&x.to==='۱۰ تومان'));
const saved2=audit.amend(saved,{...saved,preFare:100,total:100},
  {...ctx,reason:'تصحیح مجدد',at:'2026-11-17T09:03:01.007Z'});
assert.strictEqual(saved2.auditTrail.length,2);
assert(saved2.auditTrail[1].changes.some(x=>x.f==='پیش‌کرایه'&&x.from==='۱۰ تومان'&&x.to==='۱۰۰ تومان'));
assert.strictEqual(saved2.auditTrail[0].at,ctx.at);
const packing=audit.amend(base,{...base,packages:[{title:'کارتن',kind:'',qty:2,weight:'2'}]},
  {...ctx,at:'2026-11-17T08:50:00.000Z'});
assert(packing.auditTrail[0].changes.some(x=>x.f==='مشخصات بسته'));
assert.throws(()=>audit.amend(base,{...base},ctx),/هیچ تغییری/);
assert.throws(()=>audit.amend(base,{...base,id:'13',total:10},ctx),/شماره بارنامه/);
assert.throws(()=>audit.amend(base,{...base,total:10},{...ctx,reason:''}),/دلیل تغییر/);
assert.throws(()=>audit.amend({...base,handedAt:'2026-11-17T09:00:00Z'},{...base,total:10},ctx),/قابل اصلاح/);
assert.throws(()=>audit.amend({...base,status:'در مسیر'},{...base,total:10},ctx),/قابل اصلاح/);
assert.throws(()=>audit.amend({...base,receivedAt:'2026-11-17T09:00:00Z'},{...base,total:10},ctx),/قابل اصلاح/);
assert.throws(()=>audit.amend({...base,releasedAt:'2026-11-17T09:00:00Z'},{...base,total:10},ctx),/قابل اصلاح/);
const cancelled=audit.cancel(saved2,{...ctx,reason:'درخواست مشتری',at:'2026-11-17T09:30:55.201Z'});
assert.strictEqual(cancelled.status,'باطل‌شده');
assert.strictEqual(cancelled.cancelledBy,ctx.user);
assert.strictEqual(cancelled.cancelReason,'درخواست مشتری');
assert.strictEqual(cancelled.cancelledAt,'2026-11-17T09:30:55.201Z');
assert.strictEqual(cancelled.auditTrail.length,3);
assert.strictEqual(cancelled.auditTrail[2].type,'cancel');
assert(cancelled.auditTrail[2].changes.some(x=>x.f==='وضعیت'&&x.to==='باطل‌شده'));
assert.strictEqual(saved2.status,'صادرشده');
assert.throws(()=>audit.cancel(cancelled,ctx),/قابل ابطال/);
assert.throws(()=>audit.cancel({...base,handedAt:'2026-11-17T09:00:00Z'},ctx),/قابل ابطال/);
assert.throws(()=>audit.cancel({...base,status:'ترخیص‌شده'},ctx),/قابل ابطال/);
assert.throws(()=>audit.cancel(base,{...ctx,reason:'  '}),/دلیل تغییر/);
const legacy=[{type:'edit',rid:'11',at:'2026-11-01T08:00:00Z',user:'قدیمی',changes:[]}];
const merged=audit.allEvents([cancelled],legacy);
assert.strictEqual(merged.length,4);
assert.strictEqual(merged[0].rid,'11');
assert.strictEqual(merged[3].rid,'12');
assert.strictEqual(audit.allEvents([cancelled],merged).length,4);
const html=fs.readFileSync('app/index.html','utf8');
for(const s of ['<script src="waybill-audit.js"></script>',
 'barresanWaybillAudit.amend(__old,rec',
 'barresanWaybillAudit.cancel(list[i]',
 "id='v25AmendBox'",'data-v28-amend','data-v28-cancel','data-v28-log',
 'auditDetail(x)'])assert(html.includes(s),'missing UI feature '+s);
assert(!html.includes('id="hidBuildMarker"'));
console.log('Waybill audit regression passed: actor, timestamp, 100↔10, packages, history, cancellation, status locks.');
