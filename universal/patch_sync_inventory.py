# -*- coding: utf-8 -*-
"""Build-only patch: inventory by state + safe inbound conflict diagnostics and retry.

Preserves the user database; deliberately does NOT reset the hub pull cursor
or erase/confiscate any unprocessed event. Existing conflicts are retained
with their original payload until a successful authenticated re-application.
"""
from pathlib import Path

base=Path("Vahdat-1.5.7")/"windows"

def change_once(text, old, new, name):
    found=text.count(old)
    if found!=1:
        raise RuntimeError("{}: expected exactly 1 anchor, got {}".format(name, found))
    return text.replace(old,new,1)

sync_file=base/"sync_engine.py"
sync=sync_file.read_text(encoding="utf-8")
sync=change_once(sync,
    "    values.update(number=_new_number(c,'waybills'),source_number=b.get('number'),",
    "    values.update(sender_phone=b.get('sender_phone') or '',"
    "description=b.get('description') or '',number=_new_number(c,'waybills'),source_number=b.get('number'),",
    "nullable optional sender fields from old clients")
sync+="""

def conflict_report(connect, limit=50):
    # Never send tokens or full waybill/customer payloads to the UI.
    limit=max(1,min(int(limit),100))
    with connect() as c:
        rows=c.execute('''SELECT id,event_id,reason,payload,happened_at
                          FROM sync_conflicts ORDER BY happened_at,id LIMIT ?''',(limit,)).fetchall()
        count=c.execute('SELECT COUNT(*) FROM sync_conflicts').fetchone()[0]
    output=[]
    for r in rows:
        try:
            ev=json.loads(r['payload'])
            kind=str(ev.get('kind','unknown'))[:50]
            origin=str(ev.get('source_branch','unknown'))[:100]
        except Exception:
            kind='unknown';origin='unknown'
        output.append(dict(id=r['id'],event_id=r['event_id'],kind=kind,
                      source_branch=origin,reason=str(r['reason'])[:300],
                      happened_at=r['happened_at']))
    return dict(count=count,items=output)


def retry_conflicts(connect, branch_name, limit=100):
    # Repair cannot race the periodic background sync loop.
    if not _SYNC_LOCK.acquire(blocking=False):
        return dict(busy=True,repaired=0,remaining=conflict_report(connect,1)['count'])
    repaired=0
    errors=[]
    try:
        with connect() as c:
            rows=c.execute('SELECT id,event_id,payload FROM sync_conflicts ORDER BY happened_at,id LIMIT ?',
                           (max(1,min(int(limit),100)),)).fetchall()
        # Commit each reprocessed event independently, in original chronological order.
        # A malformed event never partially writes any business record.
        for row in rows:
            try:
                ev=json.loads(row['payload'])
                if str(ev.get('id',''))!=str(row['event_id']):
                    raise ValueError('Inconsistent conflict event ID')
                with connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    apply_event(c,ev,branch_name)
                    c.execute('DELETE FROM sync_conflicts WHERE id=?',(row['id'],))
                    c.commit()
                repaired+=1
            except Exception as exc:
                reason=str(exc)[:500]
                with connect() as c:
                    c.execute('UPDATE sync_conflicts SET reason=? WHERE id=?',(reason,row['id']))
                    c.commit()
                errors.append(dict(event_id=row['event_id'],reason=reason))
        return dict(ok=True,repaired=repaired,remaining=conflict_report(connect,1)['count'],
                    failed=len(errors),failures=errors[:8])
    finally:
        _SYNC_LOCK.release()
"""
sync_file.write_text(sync,encoding="utf-8")

app_file=base/"app.py"
app=app_file.read_text(encoding="utf-8")
anchor="""@app.post('/api/sync/now')
def sync_now():
    return jsonify(sync_engine.sync_once(connect,DATA))
"""
addition="""
@app.get('/api/inventory')
def inventory():
    # A received-but-not-delivered inbound waybill is physically in stock.
    # Issued/in-transit and delivered are shown separately for reconciliation.
    with connect() as c:
        incoming=c.execute('''SELECT * FROM waybills WHERE origin_here=0
                               ORDER BY created_at DESC,number DESC LIMIT 300''').fetchall()
    waiting=[bill(r) for r in incoming if r['received_at'] is None]
    in_stock=[bill(r) for r in incoming if r['received_at'] is not None and r['delivered_at'] is None]
    delivered=[bill(r) for r in incoming if r['delivered_at'] is not None]
    summary=sync_engine.get_status(connect,DATA)
    return jsonify(waiting=waiting,in_stock=in_stock,delivered=delivered,
        counts=dict(waiting=len(waiting),in_stock=len(in_stock),delivered=len(delivered)),
        conflicts=summary['conflicts'],preview_limit=300)


def _require_local_superadmin():
    # The original auth middleware still validates login and CSRF on POST.
    with connect() as c:
        row=c.execute('SELECT role,enabled FROM users WHERE id=?',(session.get('uid'),)).fetchone()
        return bool(row and row['enabled'] and row['role']=='superadmin')


@app.get('/api/sync/conflicts')
def sync_conflicts_for_admin():
    if not _require_local_superadmin():
        return error('جزئیات مغایرت فقط برای سوپرمدیر مجاز است.',403)
    return jsonify(sync_engine.conflict_report(connect))


@app.post('/api/sync/conflicts/retry')
def sync_retry_conflicts_for_admin():
    if not _require_local_superadmin():
        return error('ترمیم مغایرت فقط برای سوپرمدیر مجاز است.',403)
    cfg=sync_engine.load_config(DATA)
    if not cfg.get('enabled') or not cfg.get('branch_id'):
        return error('تنظیمات شعبه هنوز فعال نیست.',409)
    return jsonify(sync_engine.retry_conflicts(connect,cfg['branch_name']))

"""
app=change_once(app,anchor,anchor+addition,"insert protected inventory/diagnostics routes")
app=change_once(app,'version="1.6.0-universal-desktop-beta"','version="1.6.1-desktop-stock-recovery-beta"',"health version")
app_file.write_text(app,encoding="utf-8")

sync=sync_file.read_text(encoding="utf-8")
sync=change_once(sync,"version='1.6.0-universal-desktop-beta'",
                 "version='1.6.1-desktop-stock-recovery-beta'","heartbeat version")
sync_file.write_text(sync,encoding="utf-8")

operations_file=base/"assets"/"operations-ui.js"
ui=operations_file.read_text(encoding="utf-8")
ui=change_once(ui,
    "const PERM_NAV={new:'issue',",
    "const PERM_NAV={stock:'list',new:'issue',",
    "warehouse navigation RBAC")
ui=change_once(ui,
    "else if(p==='scan')pageScan();",
    "else if(p==='stock')await pageWarehouseStock();\n else if(p==='scan')pageScan();",
    "warehouse route")
ui+="""

// Clear inventory state is derived from local SQLite, never a UI deletion.
async function pageWarehouseStock(){
 const d=await apiCall('/api/inventory');
 const rowHtml=(items)=>items.map(b=>
  '<tr><td>'+esc(fmt(b.display_number||b.number))+'</td><td>'+esc(b.origin)+' ← '+esc(b.destination)+'</td>'+
  '<td>'+esc(b.receiver)+'</td><td>'+esc(fmt(b.pieces))+'</td>'+
  '<td>'+esc(b.status)+'</td><td><button class="btn secondary" data-id="'+esc(b.id)+
  '" onclick="showBill(this.dataset.id)">جزئیات</button></td></tr>').join('');
 const block=(name,items)=>card(section('box',name)+
  (items.length?'<div class="tablewrap"><table><thead><tr><th>شماره</th><th>مسیر</th><th>گیرنده</th><th>بسته‌ها</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>'+
   rowHtml(items)+'</tbody></table></div>':'<div class="muted">در این وضعیت بارنامه‌ای ثبت نشده است.</div>'));
 const c=d.counts;
 let intro='<div class="message">موجودی انبار فقط شامل بارهایی است که دریافت آن‌ها ثبت شده و هنوز به صاحب کالا تحویل نشده‌اند. بارنامه پس از تحویل در سوابق باقی می‌ماند.</div>';
 if(d.conflicts)intro+='<div class="message err">توجه: '+fmt(d.conflicts)+' مغایرت همگام‌سازی وجود دارد؛ ممکن است بارنامه‌های مرکزی هنوز به این فهرست منتقل نشده باشند. سوپرمدیر باید مغایرت‌ها را بررسی کند.</div>';
 const stats='<div class="grid4">'+[['در مسیر / در انتظار دریافت',c.waiting],['موجودی فعلی انبار',c.in_stock],['تحویل نهایی',c.delivered]].map(x=>'<div class="stat"><small>'+esc(x[0])+'</small><strong>'+fmt(x[1])+'</strong></div>').join('')+'</div>';
 set(title('موجودی انبار')+intro+stats+block('بارهای موجود در انبار',d.in_stock)+
 block('در مسیر یا در انتظار دریافت',d.waiting)+block('تحویل‌شده به گیرنده (خارج از موجودی)',d.delivered));
}


async function inspectSyncConflicts(){
 const host=document.getElementById('syncConflictDetails');
 if(!host)return;
 try{
  const r=await apiCall('/api/sync/conflicts');
  if(!r.count){host.innerHTML='<div class="message">مغایرت ثبت‌شده‌ای وجود ندارد.</div>';return;}
  host.innerHTML='<p class="message err">'+fmt(r.count)+' مغایرت موجود است. دلیل‌های زیر از دیتابیس همین شعبه خوانده شده‌اند، نه از اطلاعات محرمانه سرور.</p>'+
  r.items.map(x=>'<div class="keyrow"><strong>'+esc(x.kind)+'</strong><span>'+
     esc(x.reason)+'</span></div>').join('')+
  '<p class="settings-helper">ترمیم صرفاً رویدادهای خطادار محفوظ در این کامپیوتر را دوباره بررسی می‌کند؛ اطلاعات را حذف نمی‌کند. اگر دلیل همچنان برقرار باشد، مغایرت باقی می‌ماند.</p>'+
  '<button class="btn secondary" type="button" onclick="retrySyncConflicts()">تلاش امن برای بازیابی مغایرت‌ها</button>';
 }catch(e){host.textContent=e.message||String(e)}
}
async function retrySyncConflicts(){
 if(!confirm('رویدادهای مغایرت‌دار دوباره بررسی شوند؟ هیچ بارنامه‌ای پاک نخواهد شد.'))return;
 try{
  const r=await post('/api/sync/conflicts/retry',{});
  if(r.busy){alert('همگام‌سازی دیگری در حال اجراست؛ دوباره تلاش کنید.');return;}
  alert('بازیابی‌شده: '+fmt(r.repaired)+' | باقی‌مانده: '+fmt(r.remaining));
  await inspectSyncConflicts();
 }catch(e){fail(e)}
}
"""
operations_file.write_text(ui,encoding="utf-8")

htmlfile=base/"ui.html"
html=htmlfile.read_text(encoding="utf-8")
nav='<button type="button" class="nav" id="nav-list" onclick="go(\'list\')">'
stock='<button type="button" class="nav" id="nav-stock" onclick="go(\'stock\')"><span class="sym"><svg class="icon" viewBox="0 0 64 64" aria-hidden="true"><use href="/assets/icons.svg#box"></use></svg></span><span class="text">موجودی انبار</span></button>\n'
html=change_once(html,nav,stock+nav,"inventory navigation placement")
htmlfile.write_text(html,encoding="utf-8")

settings=base/"assets"/"settings-ui.js"
s=settings.read_text(encoding="utf-8")
s=change_once(s,"  set(html);\n  renderDest();",
"""  set(html);
  if(typeof currentUser!=='undefined' && currentUser && currentUser.role==='superadmin'){
    const parent=document.querySelector('.settings-aside');
    if(parent)parent.insertAdjacentHTML('beforeend','<section class="card settings-card"><div class="settings-card-heading"><h3>عیب‌یابی همگام‌سازی</h3></div><p class="settings-helper">علت مغایرت‌های محفوظ در این شعبه را بررسی کنید.</p><button class="btn secondary" type="button" onclick="inspectSyncConflicts()">نمایش علت مغایرت‌ها</button><div id="syncConflictDetails"></div></section>');
  }
  renderDest();""","superadmin-only diagnostics entry")
settings.write_text(s,encoding="utf-8")

iss=base/"install.iss"
install=iss.read_text(encoding="utf-8")
install=change_once(install,'#define MyAppVersion "1.6.0-beta"',
                   '#define MyAppVersion "1.6.1-beta"',"installer version")
install=change_once(install,'OutputBaseFilename=Vahdat-Desktop-Setup-Win7-to-Win11-v1.6.0-beta',
                   'OutputBaseFilename=Vahdat-Desktop-Setup-Win7-to-Win11-v1.6.1-beta',"installer filename")
iss.write_text(install,encoding="utf-8")

print("Applied warehouse + conflict-recovery patch without resetting data/cursors.")
