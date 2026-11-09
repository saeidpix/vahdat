# -*- coding: utf-8 -*-
"""Apply v1.6.2 branch-local policy to the extracted and already patched source.

Run AFTER universal/prepare.py and universal/patch_sync_inventory.py.
All migrations are additive: no existing waybill or sync cursor is modified.
"""
from pathlib import Path

ROOT=Path("Vahdat-1.5.7")/"windows"

def one(src,old,new,why):
    n=src.count(old)
    if n!=1:raise RuntimeError("%s: expected exactly one anchor, got %d"%(why,n))
    return src.replace(old,new,1)

policy_module='''# -*- coding: utf-8 -*-
"""Locally versioned issuance policy for a single Vahdat branch.

Storage is one flat charge PER WAYBILL AT ISSUANCE in this beta.
A waybill retains its recorded amount when the rate changes later.
No daily billing, destination charge mutation, or repeated charge is attempted.
"""
import json
import re

KEY = "branch_issuance_policy_v1"
OPTIONAL_FIELDS = {
    "sender": "نام فرستنده",
    "receiver": "نام گیرنده",
    "sender_phone": "موبایل فرستنده",
    "phone": "موبایل گیرنده",
    "description": "شرح بار"
}
DEFAULT_REQUIRED = dict(sender=True, receiver=True, sender_phone=False,
                        phone=False, description=False)
MAX_FEE = 10**12
DEFAULT = dict(version=1, storage_flat_fee_toman=0,
               storage_mode="once_per_waybill_at_issue",
               required_fields=DEFAULT_REQUIRED.copy())


def load(conn):
    row=conn.execute("SELECT value FROM settings WHERE name=?",(KEY,)).fetchone()
    if row is None:return json.loads(json.dumps(DEFAULT))
    try:stored=json.loads(row["value"])
    except (ValueError, TypeError):raise RuntimeError("Stored issuance policy is invalid.")
    if not isinstance(stored,dict):raise RuntimeError("Stored issuance policy is invalid.")
    result=json.loads(json.dumps(DEFAULT))
    result["storage_flat_fee_toman"]=int(stored.get("storage_flat_fee_toman",0))
    required=stored.get("required_fields",{})
    if isinstance(required,dict):
        for field in OPTIONAL_FIELDS:
            if isinstance(required.get(field),bool):
                result["required_fields"][field]=required[field]
    return result


def set_policy(conn, incoming):
    if not isinstance(incoming,dict):
        raise ValueError("تنظیمات ارسالی معتبر نیست.")
    unknown=set(incoming)-{"storage_flat_fee_toman","required_fields","version","storage_mode"}
    if unknown:raise ValueError("پارامتر نامعتبر در تنظیمات.")
    mode=incoming.get("storage_mode","once_per_waybill_at_issue")
    if mode!="once_per_waybill_at_issue":
        raise ValueError("در نسخه فعلی فقط مبلغ ثابت برای هر بارنامه پشتیبانی می‌شود.")
    raw=incoming.get("storage_flat_fee_toman",0)
    if isinstance(raw,bool):
        raise ValueError("مبلغ انبارداری نامعتبر است.")
    if isinstance(raw,int):
        fee=raw
    elif isinstance(raw,str):
        normalized=raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
                                               "01234567890123456789"))
        if not re.fullmatch(r"[0-9,٬\\s]+",normalized):
            raise ValueError("مبلغ انبارداری باید عدد باشد.")
        fee=int(re.sub(r"[^0-9]","",normalized) or "0")
    else:raise ValueError("مبلغ انبارداری باید عدد باشد.")
    if not 0<=fee<=MAX_FEE:
        raise ValueError("مبلغ انبارداری خارج از محدوده مجاز است.")
    required=incoming.get("required_fields",{})
    if not isinstance(required,dict) or any(k not in OPTIONAL_FIELDS for k in required):
        raise ValueError("فهرست فیلدهای اجباری معتبر نیست.")
    if any(not isinstance(v,bool) for v in required.values()):
        raise ValueError("وضعیت اجباری بودن فیلد باید روشن یا خاموش باشد.")
    current=load(conn)
    current["required_fields"].update(required)
    current["storage_flat_fee_toman"]=fee
    conn.execute("INSERT INTO settings(name,value) VALUES(?,?) "
                 "ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                 (KEY,json.dumps(current,ensure_ascii=False)))
    return current


def validate_issue(data,policy):
    if not isinstance(data,dict):return "اطلاعات بارنامه معتبر نیست."
    for field,label in OPTIONAL_FIELDS.items():
        if not policy["required_fields"].get(field,False):
            continue
        val=str(data.get(field,"") or "").strip()
        if not val:return "فیلد «%s» اجباری است."%label
        if field in ("sender_phone","phone"):
            normalized=val.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
                                                   "01234567890123456789"))
            if not re.fullmatch(r"09\\d{9}",normalized):
                return "برای «%s» شماره موبایل ۱۱ رقمی وارد کنید."%label
    return None
'''
(ROOT/"branch_policy.py").write_text(policy_module,encoding="utf-8")

appfile=ROOT/"app.py"
src=appfile.read_text(encoding="utf-8")
src=one(src,"import sync_engine\n","import sync_engine\nimport branch_policy\n","import policy")
src=one(src,
    "        sync_engine.migrate(c)\n",
    "        sync_engine.migrate(c)\n        # Existing waybills are never rewritten by the new policy.\n"
    "        c.execute('INSERT OR IGNORE INTO settings(name,value) VALUES(?,?)',"
    " (branch_policy.KEY,json.dumps(branch_policy.DEFAULT,ensure_ascii=False)))\n"
    "        c.commit()\n",
    "initialize policy without touching bills")
src=one(src,
    "            central_managed=central is not None)",
    "            central_managed=central is not None,\n"
    "            branch_policy=branch_policy.load(c))",
    "publish read-only settings to authenticated issue UI")
src=one(src,
    "@app.post(\"/api/waybills\")",
    '''@app.post("/api/branch-policy")
def save_branch_policy():
    # Built-in authentication + CSRF validation run before the route.
    # A branch manager holding generic 'settings' permission is NOT enough.
    with connect() as c:
        user=c.execute("SELECT role,enabled FROM users WHERE id=?",
                       (session.get("uid"),)).fetchone()
        if not user or not user["enabled"] or user["role"]!="superadmin":
            return error("فقط سوپرمدیر می‌تواند تعرفه و فیلدهای اجباری را تغییر دهد.",403)
        try:
            c.execute("BEGIN IMMEDIATE")
            next_policy=branch_policy.set_policy(c,request.get_json(silent=True) or {})
            operations.audit(c,"BRANCH_POLICY_UPDATED",
                "issuance",next_policy)
            c.commit()
        except ValueError as exc:
            c.rollback()
            return error(str(exc),422)
    return jsonify(ok=True,branch_policy=next_policy)

@app.post("/api/waybills")''',
    "protected superadmin policy endpoint")
src=one(src,
    '    now=int(time.time()*1000)\n    try:pieces=max(1,min(number(d.get("pieces") or 1),1000000))',
    '    now=int(time.time()*1000)\n'
    '    if number(d.get("pieces"))<1 or number(d.get("pieces"))>1000000:\n'
    '        return error("تعداد بسته باید بین ۱ تا یک میلیون باشد.",422)\n'
    '    try:pieces=max(1,min(number(d.get("pieces") or 1),1000000))',
    "enforce nonzero package count server side")
src=one(src,
    "            c.execute('BEGIN IMMEDIATE')\n"
    "            r=c.execute(\"SELECT value FROM settings WHERE name='destinations'\").fetchone()",
    "            c.execute('BEGIN IMMEDIATE')\n"
    "            policy=branch_policy.load(c)\n"
    "            missing=branch_policy.validate_issue(d,policy)\n"
    "            if missing:return error(missing,422)\n"
    "            # Do not trust the fee supplied by an employee/browser: snapshot the\n"
    "            # current authorized policy in this NEW waybill exactly once.\n"
    "            b['storage_fee']=policy['storage_flat_fee_toman']\n"
    "            b['total']=b['prepaid']+b['post_fare']+b['storage_fee']+b['other_fee']\n"
    "            r=c.execute(\"SELECT value FROM settings WHERE name='destinations'\").fetchone()",
    "server-side policy + immutable per-waybill storage snapshot")
src=one(src,
    "version=\"1.6.1-desktop-stock-recovery-beta\"",
    "version=\"1.6.2-desktop-policy-beta\"",
    "version bump")
appfile.write_text(src,encoding="utf-8")

issue=ROOT/"assets"/"operations-ui.js"
js=issue.read_text(encoding="utf-8")
js=one(js,
    "moneyInput('storage_fee','انبارداری')",
    "moneyInput('storage_fee','انبارداری (تعرفه ثابت)',(state.settings.branch_policy||{}).storage_flat_fee_toman||0)",
    "prefill flat rate from current policy")
js=one(js,
    "d.pieces=num(d.pieces)||1;",
    "d.pieces=num(d.pieces);",
    "do not silently coerce missing package count to one")
js=one(js,
    " if(!d.destination||!d.sender.trim()||!d.receiver.trim())throw Error('مقصد، نام فرستنده و نام گیرنده را وارد کنید.');",
    """ if(!d.destination||d.pieces<1)throw Error('مقصد معتبر و تعداد صحیح بسته‌ها اجباری است.');
 const required=((state.settings||{}).branch_policy||{}).required_fields||{sender:true,receiver:true};
 for(const [key,label] of Object.entries({sender:'نام فرستنده',sender_phone:'موبایل فرستنده',receiver:'نام گیرنده',phone:'موبایل گیرنده',description:'شرح بار'})){
   if(required[key]&&!String(d[key]||'').trim())throw Error('فیلد «'+label+'» اجباری است.');
 }""",
    "dynamic client side mandatory fields")
js+='''
// Branch policy is always obtained from GET /api/settings. The server is authoritative.
const beforeBranchPolicyIssue=newForm;
newForm=function(){
 beforeBranchPolicyIssue();
 const cfg=((state.settings||{}).branch_policy)||{};
 const rules=cfg.required_fields||{sender:true,receiver:true};
 const inputIds={sender:'sender',receiver:'receiver',sender_phone:'senderPhone',phone:'phone',description:'description'};
 Object.entries(inputIds).forEach(function(pair){
   const el=$$(pair[1]);if(!el)return;
   const yes=!!rules[pair[0]];
   el.required=yes;
   const label=document.querySelector('label[for="'+pair[1]+'"]');
   if(label&&yes&&!label.textContent.includes('*'))label.textContent+=' *';
 });
 const fee=$$('storage_fee');
 if(fee){
   fee.value=fmt(cfg.storage_flat_fee_toman||0);
   fee.readOnly=true;
   fee.title='این مبلغ طبق تعرفه مصوب سوپرمدیر تعیین می‌شود.';
   fee.style.background='#f1f5f9';
 }
 const pieces=$$('pieces');
 if(pieces){pieces.required=true;pieces.setAttribute('min','1')}
 updateIssueTotal();
};
'''
issue.write_text(js,encoding="utf-8")

ui=ROOT/"assets"/"settings-ui.js"
settings=ui.read_text(encoding="utf-8")
settings+='''
// Business policy is branch-local. Only SUPERADMIN can edit; everyone else sees a
// read-only summary. This does not modify central routing or secret credentials.
const beforePolicySettings=settingsForm;
settingsForm=async function(){
 await beforePolicySettings();
 const cfg=(state.settings||{}).branch_policy||{};
 const r=cfg.required_fields||{};
 const admin=(typeof currentUser!=='undefined' && currentUser&&currentUser.role==='superadmin');
 const descriptors=[
  ['sender','نام فرستنده'],['receiver','نام گیرنده'],
  ['sender_phone','موبایل فرستنده'],['phone','موبایل گیرنده'],
  ['description','شرح بار']
 ];
 const fee='<section class="card settings-card"><div class="settings-card-heading"><span class="settings-card-symbol is-gold">'+icon('money')+'</span><div><h3>تعرفه ثابت انبارداری</h3><p>مبلغ یک‌بار برای هر بارنامه جدید در زمان صدور ثبت می‌شود؛ بارنامه‌های قبلی تغییر نمی‌کنند.</p></div></div>'+
  '<div class="field"><label for="branchStorageFlatFee">مبلغ انبارداری هر بارنامه (تومان)</label><input type="text" inputmode="numeric" data-money-input id="branchStorageFlatFee" value="'+esc(fmt(cfg.storage_flat_fee_toman||0))+'" '+(admin?'':'readonly')+'></div>'+
  '<p class="settings-helper">در این نسخه محاسبه روزانه وجود ندارد؛ مبلغ حتی در صورت تأخیر در دریافت دوباره اضافه نخواهد شد.</p></section>';
 const flags='<section class="card settings-card"><div class="settings-card-heading"><span class="settings-card-symbol is-blue">'+icon('settings')+'</span><div><h3>فیلدهای اجباری صدور بارنامه</h3><p>برای فیلدهای موجود در فرم انتخاب کنید کدام مشخصات حتماً تکمیل شوند.</p></div></div>'+
  '<div class="settings-print-options">'+descriptors.map(function(f){
   return '<label class="settings-print-choice" for="req-'+f[0]+'"><span class="settings-choice-copy"><strong>'+esc(f[1])+'</strong></span><input id="req-'+f[0]+'" type="checkbox" '+(r[f[0]]?'checked':'')+' '+(admin?'':'disabled')+'><span class="settings-switch" aria-hidden="true"></span></label>';
  }).join('')+'</div>'+
  '<p class="settings-helper">مقصد مجاز و تعداد بسته‌ها همیشه اجباری‌اند و امکان غیرفعال کردن آن‌ها وجود ندارد.</p>'+
  (admin?'<div class="settings-actions"><button class="btn" type="button" onclick="saveBranchPolicy()">'+icon('save')+'ذخیره تعرفه و فیلدهای اجباری</button></div>':
         '<p class="settings-helper">فقط سوپرمدیر می‌تواند این تنظیمات را تغییر دهد.</p>')+
  '</section>';
 const main=document.querySelector('.settings-main');
 if(main)main.insertAdjacentHTML('beforeend',fee+flags);
 if(admin)numericInputs();
};
async function saveBranchPolicy(){
 if(!currentUser||currentUser.role!=='superadmin')return fail(Error('فقط سوپرمدیر مجاز است.'));
 const fields={};
 ['sender','receiver','sender_phone','phone','description'].forEach(k=>{
   fields[k]=!!$$('req-'+k)?.checked;
 });
 try{
  const updated=await post('/api/branch-policy',{
   storage_flat_fee_toman:amount('branchStorageFlatFee'),
   required_fields:fields,
   storage_mode:'once_per_waybill_at_issue'
  });
  state.settings.branch_policy=updated.branch_policy;
  alert('تعرفه انبارداری و شرایط ثبت بارنامه ذخیره شدند.');
  await settingsForm();
 }catch(err){fail(err)}
}
'''
ui.write_text(settings,encoding="utf-8")
iss=ROOT/"install.iss"
installer=iss.read_text(encoding="utf-8")
installer=one(installer,'#define MyAppVersion "1.6.1-beta"',
              '#define MyAppVersion "1.6.2-beta"',"version in installer")
installer=one(installer,'OutputBaseFilename=Vahdat-Desktop-Setup-Win7-to-Win11-v1.6.1-beta',
              'OutputBaseFilename=Vahdat-Desktop-Setup-Win7-to-Win11-v1.6.2-beta',
              "installer output")
iss.write_text(installer,encoding="utf-8")
print("Branch policy patch 1.6.2 applied; SQLite data untouched.")
