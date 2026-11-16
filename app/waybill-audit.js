(function (root) {
  'use strict';
  var fieldLabels = [
    ['origin','مبدأ'], ['senderName','نام فرستنده'], ['senderMobile','موبایل فرستنده'],
    ['senderPhone','تلفن فرستنده'], ['senderAddress','آدرس فرستنده'],
    ['recipientName','نام گیرنده'], ['recipientMobile','موبایل گیرنده'],
    ['recipientPhone','تلفن گیرنده'], ['recipientAddress','آدرس گیرنده'],
    ['destination','مقصد'], ['preFare','پیش‌کرایه'], ['postFare','پس‌کرایه'],
    ['storageFee','انبارداری'], ['otherFee','سایر هزینه‌ها'], ['total','جمع کل'],
    ['waybillNotes','توضیحات']
  ];
  var money = new Set(['preFare','postFare','storageFee','otherFee','total']);
  function fmtMoney(n) { return new Intl.NumberFormat('fa-IR').format(Number(n)||0) + ' تومان'; }
  function fmtText(v) { var t = String(v == null ? '' : v).trim(); return t || '—'; }
  function packages(r) {
    return (Array.isArray(r.packages) ? r.packages : []).map(function (p) {
      return fmtText(p.title)+(p.kind ? ' ('+p.kind+')' : '')+' × '+String(Number(p.qty)||0)+
        (p.weight ? ' · '+p.weight+' کیلو' : '');
    }).join(' | ') || '—';
  }
  function changes(oldR, nextR) {
    var out = [];
    fieldLabels.forEach(function (item) {
      var k=item[0], label=item[1];
      var oldValue=money.has(k)?(Number(oldR[k])||0):String(oldR[k] == null ? '' : oldR[k]).trim();
      var newValue=money.has(k)?(Number(nextR[k])||0):String(nextR[k] == null ? '' : nextR[k]).trim();
      if (oldValue !== newValue)
        out.push({f:label,from:money.has(k)?fmtMoney(oldValue):fmtText(oldValue),
          to:money.has(k)?fmtMoney(newValue):fmtText(newValue)});
    });
    var op=packages(oldR),np=packages(nextR);
    if (op!==np) out.push({f:'مشخصات بسته',from:op,to:np});
    return out;
  }
  function canChange(r) {
    return !!r && String(r.status||'صادرشده')==='صادرشده' &&
      !r.handedAt && !r.receivedAt && !r.releasedAt && !r.cancelledAt;
  }
  function priorTrail(r) { return Array.isArray(r.auditTrail) ? r.auditTrail : []; }
  function context(ctx) {
    var reason=fmtText(ctx && ctx.reason);
    if (reason==='—') throw new Error('ثبت دلیل تغییر الزامی است.');
    var user=fmtText(ctx && ctx.user);
    var userId=String((ctx && ctx.userId)||'');
    var at=String((ctx && ctx.at)||new Date().toISOString());
    if (!Number.isFinite(Date.parse(at))) throw new Error('زمان ثبت تغییر معتبر نیست.');
    return {reason:reason,user:user,userId:userId,at:at};
  }
  function event(type, oldR, ctx, diff) {
    var info=context(ctx);
    return {
      id:'audit-'+type+'-'+info.at+'-'+String(oldR.id),
      type:type,rid:String(oldR.id),at:info.at,user:info.user,userId:info.userId,
      reason:info.reason,changes:diff
    };
  }
  function amend(oldR, nextR, ctx) {
    if (!canChange(oldR)) throw new Error('بارنامه پس از تحویل به راننده یا تغییر وضعیت، قابل اصلاح نیست.');
    if (String(oldR.id)!==String(nextR.id)) throw new Error('شماره بارنامه قابل تغییر نیست.');
    var diff=changes(oldR,nextR);
    if (!diff.length) throw new Error('هیچ تغییری در بارنامه انجام نشده است.');
    var e=event('edit',oldR,ctx,diff);
    return Object.assign({},nextR,{auditTrail:priorTrail(oldR).concat([e]),
      amendedAt:e.at,amendedBy:e.user,amendCount:(Number(oldR.amendCount)||0)+1});
  }
  function cancel(oldR, ctx) {
    if (!canChange(oldR)) throw new Error('فقط بارنامه صادرشده و تحویل‌نداده‌شده قابل ابطال است.');
    var e=event('cancel',oldR,ctx,[{f:'وضعیت',from:fmtText(oldR.status||'صادرشده'),to:'باطل‌شده'}]);
    return Object.assign({},oldR,{
      status:'باطل‌شده',cancelledAt:e.at,cancelledBy:e.user,cancelReason:e.reason,
      statusBeforeCancel:fmtText(oldR.status||'صادرشده'),auditTrail:priorTrail(oldR).concat([e])
    });
  }
  function allEvents(records, legacy) {
    var old=Array.isArray(legacy)?legacy:[];
    var now=(Array.isArray(records)?records:[]).flatMap(function (r) {
      return priorTrail(r).map(function (e) {
        return Object.assign({},e,{rid:String(r.id)});
      });
    });
    var seen=new Set();
    return old.concat(now).filter(function (e) {
      var id=e && e.id || [e.rid,e.type,e.at,e.user].join('|');
      if (seen.has(id)) return false;
      seen.add(id);return true;
    });
  }
  var api={changes:changes,canChange:canChange,amend:amend,cancel:cancel,
    allEvents:allEvents,packages:packages};
  if (typeof module!=='undefined' && module.exports) module.exports=api;
  if (root) root.barresanWaybillAudit=api;
})(typeof window==='undefined'?null:window);
