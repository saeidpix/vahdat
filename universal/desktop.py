# -*- coding: utf-8 -*-
"""Native Tkinter desktop client for ALL five Vahdat branches (Windows 7-11).

Flask's verified business logic runs in-process with test_client. There is no
HTTP listener, browser, webview, firewall modification or SQL Server access.
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import urllib.parse

import secret_store
import app as backend

backend.sync_engine.load_config = secret_store.load_config

BRANCHES = secret_store.BRANCHES
FONT = ("Tahoma", 10)
TITLE_FONT = ("Tahoma", 15, "bold")
NAV_BG = "#102653"
BG = "#f2f5fa"
YELLOW = "#f4c632"


class Desktop:
    def __init__(self):
        backend.init()
        backend.sync_engine.start_worker(backend.connect, backend.DATA)
        self.client = backend.app.test_client()
        self.root = tk.Tk()
        self.root.title("اتوبنز وحدت | برنامه دسکتاپ شعب")
        self.root.geometry("1100x735")
        self.root.minsize(870, 595)
        self.root.configure(bg=BG)
        self.user = None
        self.perms = []
        self.csrf = ""
        self.sync_result = None
        self.configure_style()
        self.refresh_session()

    def configure_style(self):
        theme = ttk.Style()
        theme.theme_use("clam")
        theme.configure(".", font=FONT)
        theme.configure("TFrame", background=BG)
        theme.configure("TLabel", background=BG, foreground="#12233d")
        theme.configure("TButton", padding=(12, 8))
        theme.configure("TEntry", padding=5)
        theme.configure("Treeview", rowheight=29, font=FONT)
        theme.configure("Treeview.Heading", font=("Tahoma", 9, "bold"))
        theme.configure("TCombobox", padding=4)
        theme.configure("Title.TLabel", font=TITLE_FONT)
        theme.configure("Small.TLabel", foreground="#63738a", font=("Tahoma", 9))

    def request(self, method, path, payload=None):
        headers = {"X-CSRF-Token": self.csrf} if method != "GET" and self.csrf else {}
        r = self.client.open(path, method=method, json=payload, headers=headers)
        data = r.get_json(silent=True)
        if r.status_code >= 400:
            raise ValueError((data or {}).get("error") or "خطای برنامه: {}".format(r.status_code))
        return data or {}

    def reset(self):
        for child in self.root.winfo_children():
            child.destroy()

    def text(self, parent, value, title=False, muted=False):
        style = "Title.TLabel" if title else "Small.TLabel" if muted else "TLabel"
        label = ttk.Label(parent, text=value, style=style, justify="right", anchor="e")
        label.pack(fill="x", pady=(3, 6))
        return label

    def entry(self, frame, caption, secret=False, preset=""):
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text=caption, width=23, anchor="e").pack(side="right", padx=8)
        var = tk.StringVar(value=preset)
        widget = ttk.Entry(row, textvariable=var, show="*" if secret else "", justify="right", width=40)
        widget.pack(side="right", fill="x", expand=True)
        return var

    def button(self, parent, caption, command):
        return ttk.Button(parent, text=caption, command=command)

    def action(self, func):
        try:
            func()
        except Exception as exc:
            messagebox.showerror("خطای برنامه", str(exc), parent=self.root)

    def refresh_session(self):
        status = self.request("GET", "/api/auth/status")
        self.user = status.get("user")
        self.perms = status.get("permissions", [])
        self.csrf = status.get("csrf") or ""
        if status.get("needs_setup"):
            self.login(setup=True)
        elif not status.get("authenticated"):
            self.login(setup=False)
        else:
            self.main("خانه")

    def login(self, setup=False):
        self.reset()
        holder = ttk.Frame(self.root, padding=40)
        holder.place(relx=0.5, rely=0.5, anchor="center", width=530)
        self.text(holder, "اتوبنز وحدت", title=True)
        self.text(holder, "ایجاد سوپرمدیر اولیه" if setup else "ورود به برنامه دسکتاپ شعب")
        if setup:
            name = self.entry(holder, "نام سوپرمدیر")
        phone = self.entry(holder, "شماره موبایل")
        password = self.entry(holder, "رمز عبور (حداقل ۱۰ حرف)", secret=True)

        def submit():
            payload = {"mobile": phone.get(), "password": password.get()}
            if setup:
                payload["name"] = name.get()
            path = "/api/auth/bootstrap" if setup else "/api/auth/login"
            self.request("POST", path, payload)
            self.refresh_session()
        b = self.button(holder, "ایجاد حساب مدیر" if setup else "ورود", lambda:self.action(submit))
        b.pack(fill="x", pady=16)
        self.text(holder, "برنامه به‌صورت محلی اجرا می‌شود و برای ثبت بارنامه به اینترنت دائمی نیاز ندارد.", muted=True)

    def main(self, section):
        self.reset()
        overall = tk.Frame(self.root, bg=BG)
        overall.pack(fill="both", expand=True)
        sidebar = tk.Frame(overall, bg=NAV_BG, width=220)
        sidebar.pack(side="right", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="اتوبنز وحدت", fg="white", bg=NAV_BG,
                 font=("Tahoma", 15, "bold"), pady=22).pack(fill="x")
        cfg = self.safe_cfg()
        tk.Label(sidebar, text=cfg.get("branch_name") or "شعبه تنظیم نشده", bg=NAV_BG,
                 fg="#f6d65a", font=("Tahoma", 10), pady=8).pack(fill="x")
        nav = [("خانه", "list"), ("صدور بارنامه", "issue"), ("بارنامه‌ها", "list"),
               ("تحویل به راننده", "handover"), ("دریافت و اسکن", "receive"),
               ("گزارش مالی", "reports"), ("کاربران", "users"),
               ("تنظیمات مرکزی", "superadmin")]
        for label, perm in nav:
            if perm == "superadmin" and (not self.user or self.user.get("role") != "superadmin"):
                continue
            if perm != "superadmin" and perm not in self.perms:
                continue
            selected = label == section
            tk.Button(sidebar, text=label, bg=YELLOW if selected else NAV_BG,
                      fg="#14223b" if selected else "white", bd=0, relief="flat",
                      activebackground="#ffe180", anchor="e", padx=16, pady=9,
                      font=FONT, command=lambda s=label:self.main(s)).pack(fill="x", padx=8, pady=2)
        tk.Button(sidebar, text="خروج از حساب", bg=NAV_BG, fg="white", bd=0, pady=12,
                  command=lambda:self.action(self.logout)).pack(side="bottom", fill="x")
        self.content = ttk.Frame(overall, padding=24)
        self.content.pack(side="left", fill="both", expand=True)
        self.text(self.content, section, title=True)
        handlers = {"خانه": self.dashboard, "صدور بارنامه": self.issue,
                    "بارنامه‌ها": self.bills, "تحویل به راننده": self.handover,
                    "دریافت و اسکن": self.receive, "گزارش مالی": self.reports,
                    "کاربران": self.users, "تنظیمات مرکزی": self.settings}
        self.action(handlers.get(section, self.dashboard))

    def logout(self):
        self.request("POST", "/api/auth/logout")
        self.csrf = ""
        self.refresh_session()

    def safe_cfg(self):
        try:
            return secret_store.load_config(backend.DATA)
        except Exception:
            return dict(enabled=False, branch_id="", branch_name="")

    def dashboard(self):
        report = self.request("GET", "/api/reports?period=today")
        status = self.request("GET", "/api/sync/status")
        cfg = self.safe_cfg()
        self.text(self.content, "شعبه: " + (cfg.get("branch_name") or "هنوز تنظیم نشده"))
        self.text(self.content, "شماره‌گذاری هر شعبه از ۱ در دیتابیس مستقل خودش شروع می‌شود.", muted=True)
        for title, value in [
            ("بارنامه‌های صادرشده امروز", report.get("issued", 0)),
            ("بارهای دریافت‌شده امروز", report.get("received", 0)),
            ("تحویل‌شده امروز", report.get("delivered", 0)),
            ("صف انتظار ارسال", status.get("pending", 0)),
            ("مغایرت‌های ارتباط", status.get("conflicts", 0))
        ]:
            line = ttk.Frame(self.content, padding=8)
            line.pack(fill="x", pady=3)
            ttk.Label(line, text=str(value), font=("Tahoma", 12, "bold")).pack(side="left")
            ttk.Label(line, text=title, anchor="e").pack(side="right")
        if not cfg.get("enabled"):
            self.text(self.content, "اتصال مرکزی غیرفعال است؛ سوپرمدیر باید تنظیمات شعبه را تکمیل کند.")
        elif not status.get("catalog_updated_at"):
            self.text(self.content, "پیش از صدور بارنامه، یک بار فهرست مسیرهای مجاز را از مرکز دریافت کنید.")
        self.button(self.content, "همگام‌سازی با مرکز", lambda:self.action(self.sync)).pack(anchor="e", pady=16)

    def issue(self):
        cfg = self.safe_cfg()
        pref = self.request("GET", "/api/settings")
        allowed = pref.get("destinations") or []
        if not cfg.get("enabled") or not pref.get("central_managed"):
            self.text(self.content, "صدور غیرفعال: اتصال امن و فهرست مسیرهای مرکز باید توسط سوپرمدیر تأیید شوند.")
            return
        fields = ttk.Frame(self.content)
        fields.pack(fill="x", anchor="n")
        self.text(fields, "مبدأ: " + cfg.get("branch_name", ""))
        line = ttk.Frame(fields)
        line.pack(fill="x", pady=7)
        ttk.Label(line, text="مقصد", width=23, anchor="e").pack(side="right")
        destination = tk.StringVar(value=allowed[0] if allowed else "")
        ttk.Combobox(line, textvariable=destination, values=allowed, state="readonly",
                     justify="right", width=40).pack(side="right", fill="x", expand=True)
        form = {}
        for key, caption, init in [
            ("sender", "فرستنده", ""), ("sender_phone", "موبایل فرستنده", ""),
            ("receiver", "گیرنده", ""), ("phone", "موبایل گیرنده", ""),
            ("pieces", "تعداد بسته", "1"),
            ("prepaid", "پیش‌کرایه (تومان)", "0"),
            ("post_fare", "پس‌کرایه (تومان)", "0"),
            ("storage_fee", "انبارداری (تومان)", "0"),
            ("other_fee", "سایر هزینه‌ها (تومان)", "0"),
            ("description", "توضیحات", "")]:
            form[key] = self.entry(fields, caption, preset=init)
        def submit():
            payload = {k: var.get() for k, var in form.items()}
            payload["destination"] = destination.get()
            if not payload["sender"].strip() or not payload["receiver"].strip():
                raise ValueError("نام فرستنده و گیرنده لازم است.")
            r = self.request("POST", "/api/waybills", payload)
            b = r["waybill"]
            messagebox.showinfo("بارنامه ثبت شد", "شماره بارنامه: {}".format(b["number"]), parent=self.root)
            self.main("بارنامه‌ها")
        self.button(fields, "ثبت بارنامه", lambda:self.action(submit)).pack(anchor="e", pady=12)

    def bills(self):
        search = ttk.Frame(self.content)
        search.pack(fill="x", pady=8)
        ttk.Label(search, text="جستجوی بارنامه").pack(side="right")
        query = tk.StringVar()
        ttk.Entry(search, textvariable=query, width=28, justify="right").pack(side="right", padx=8)
        cols = ("number", "origin", "destination", "receiver", "status", "created")
        tree = ttk.Treeview(self.content, columns=cols, show="headings", height=13)
        for key, caption, width in [
            ("number", "شماره", 65), ("origin", "مبدأ", 95), ("destination", "مقصد", 95),
            ("receiver", "گیرنده", 150), ("status", "وضعیت", 130), ("created", "تاریخ", 155)]:
            tree.heading(key, text=caption)
            tree.column(key, width=width, anchor="center")
        tree.pack(fill="both", expand=True)
        ids = {}
        def reload():
            ids.clear()
            for item in tree.get_children(): tree.delete(item)
            path = "/api/waybills?q=" + urllib.parse.quote(query.get())
            for b in self.request("GET", path).get("items", []):
                iid = tree.insert("", "end", values=(b.get("display_number") or b.get("number"),
                    b.get("origin"), b.get("destination"), b.get("receiver"),
                    b.get("status"), b.get("created_at_fa")))
                ids[iid] = b["id"]
        self.button(search, "جستجو", lambda:self.action(reload)).pack(side="right")
        def selected():
            marked = tree.selection()
            if not marked:raise ValueError("ابتدا یک بارنامه را انتخاب کنید.")
            b = self.request("GET", "/api/waybills/" + ids[marked[0]])["waybill"]
            messagebox.showinfo("مشخصات بارنامه", "شماره: {}\nشناسه: {}\nمبدأ: {}\nمقصد: {}\nفرستنده: {}\nگیرنده: {}\nتعداد: {}\nجمع (تومان): {:,}\nوضعیت: {}".format(
                b.get("display_number"), b["id"], b["origin"], b["destination"],
                b["sender"], b["receiver"], b["pieces"], b["total"], b["status"]), parent=self.root)
        self.button(self.content, "نمایش جزئیات بارنامه", lambda:self.action(selected)).pack(anchor="e", pady=10)
        reload()

    def receive(self):
        self.text(self.content, "کد QR یا بارکد را با اسکنر وارد کنید.")
        code = self.entry(self.content, "کد یا شماره بارنامه")
        def lookup():
            res = self.request("POST", "/api/scan/lookup", {"code": code.get()})
            b = res["waybill"]
            messagebox.showinfo("بارنامه", "{} — {} → {}\n{}".format(
                b["id"], b["origin"], b["destination"], b["status"]), parent=self.root)
        def receive():
            res = self.request("POST", "/api/scan/receive", {"code": code.get()})
            messagebox.showinfo("دریافت ثبت شد",
                "دریافت موقت - در انتظار تطبیق" if res.get("provisional") else "دریافت ثبت و در صف همگام‌سازی قرار گرفت.",
                parent=self.root)
        self.button(self.content, "استعلام بارنامه", lambda:self.action(lookup)).pack(anchor="e", pady=8)
        self.button(self.content, "ثبت دریافت بار", lambda:self.action(receive)).pack(anchor="e", pady=8)
        ttk.Separator(self.content).pack(fill="x", pady=20)
        deliver_code = self.entry(self.content, "شناسه بارنامه برای تحویل")
        person = self.entry(self.content, "نام تحویل‌گیرنده")
        collected = self.entry(self.content, "مبلغ دریافت‌شده", preset="0")
        def deliver():
            details = self.request("POST", "/api/scan/lookup", {"code": deliver_code.get()})["waybill"]
            self.request("POST", "/api/waybills/"+details["id"]+"/deliver",
                         {"person":person.get(),"collected":collected.get()})
            messagebox.showinfo("تحویل", "تحویل نهایی ثبت شد.", parent=self.root)
        self.button(self.content, "ثبت تحویل نهایی", lambda:self.action(deliver)).pack(anchor="e", pady=8)

    def handover(self):
        self.text(self.content, "ثبت راننده و تحویل گروهی بارنامه‌ها به راننده")
        first = self.entry(self.content, "نام راننده")
        last = self.entry(self.content, "نام خانوادگی")
        mobile = self.entry(self.content, "موبایل راننده")
        def add_driver():
            self.request("POST", "/api/drivers", {"first_name":first.get(),
                          "last_name":last.get(),"mobile":mobile.get()})
            messagebox.showinfo("راننده", "راننده ثبت شد.", parent=self.root)
            self.main("تحویل به راننده")
        self.button(self.content, "ثبت راننده", lambda:self.action(add_driver)).pack(anchor="e", pady=6)
        ttk.Separator(self.content).pack(fill="x", pady=15)
        drivers = self.request("GET", "/api/drivers").get("items", [])
        choices = {d["first_name"] + " " + d["last_name"] + " — " + d["mobile"]:d["id"] for d in drivers if d["enabled"]}
        self.text(self.content, "راننده فعال را انتخاب و شماره بارنامه‌های هم‌مقصد را وارد کنید.")
        dvar = tk.StringVar()
        selector = ttk.Combobox(self.content, values=list(choices), textvariable=dvar, state="readonly", justify="right")
        selector.pack(fill="x", pady=8)
        dest = self.entry(self.content, "مقصد")
        nums = self.entry(self.content, "شماره‌ها (با ویرگول جدا)")
        def manifest():
            if not dvar.get() in choices:raise ValueError("راننده را انتخاب کنید.")
            allb = self.request("GET", "/api/waybills").get("items", [])
            wanted = {int(n.strip()) for n in nums.get().replace("،", ",").split(",") if n.strip().isdigit()}
            found = [b["id"] for b in allb if b.get("origin_here") and b.get("number") in wanted]
            if not found or len(found)!=len(wanted):raise ValueError("شماره‌های بارنامه پیدا نشدند.")
            r = self.request("POST", "/api/manifests", {"driver_id":choices[dvar.get()],
                "destination":dest.get(),"waybill_ids":found})
            messagebox.showinfo("تحویل به راننده", "شماره حواله: {}".format(r["manifest"]["number"]), parent=self.root)
        self.button(self.content, "تحویل بارنامه‌ها به راننده", lambda:self.action(manifest)).pack(anchor="e", pady=10)

    def reports(self):
        report = self.request("GET", "/api/reports?period=all")
        for label, key in [("تعداد صادرشده", "issued"), ("دریافت مقصد", "received"),
                           ("تحویل‌شده", "delivered"), ("جمع مبلغ بارنامه‌ها", "total"),
                           ("پیش‌کرایه", "prepaid"), ("پس‌کرایه", "post_fare"),
                           ("انبارداری", "storage_fee"), ("سایر هزینه‌ها", "other_fee")]:
            self.text(self.content, "{}: {:,}".format(label, report.get(key,0)))
        self.text(self.content, "گزارش تفصیلی و چاپ سه‌برگی در نسخه عملیاتی بررسی می‌شوند.", muted=True)

    def users(self):
        result = self.request("GET", "/api/users")
        self.text(self.content, "کاربران تعریف‌شده: {}".format(len(result.get("items", []))))
        for item in result.get("items", []):
            self.text(self.content, "{} — {} — {}".format(item["name"], item["mobile"], item["role"]))
        ttk.Separator(self.content).pack(fill="x", pady=10)
        name = self.entry(self.content, "نام کارمند")
        mobile = self.entry(self.content, "شماره موبایل")
        password = self.entry(self.content, "رمز کارمند", secret=True)
        options = [x for x in result.get("roles", []) if x != "superadmin"]
        role = tk.StringVar(value=options[0] if options else "issuance")
        ttk.Combobox(self.content, values=options, textvariable=role,
                     state="readonly", justify="right").pack(fill="x", pady=8)
        def submit():
            self.request("POST", "/api/users", {"name":name.get(),"mobile":mobile.get(),
                         "password":password.get(),"role":role.get()})
            self.main("کاربران")
        self.button(self.content, "ثبت کارمند", lambda:self.action(submit)).pack(anchor="e", pady=8)

    def settings(self):
        if not self.user or self.user.get("role") != "superadmin":
            raise ValueError("تنظیمات ارتباط فقط برای سوپرمدیر مجاز است.")
        cfg = self.safe_cfg()
        self.text(self.content, "تنظیمات محرمانه اتصال مرکزی — فقط سوپرمدیر", title=False)
        self.text(self.content, "کلید ذخیره‌شده نمایش داده نمی‌شود. ذخیره‌سازی با Windows DPAPI انجام می‌شود.", muted=True)
        branch_names = {name:key for key,name in BRANCHES.items()}
        chosen = tk.StringVar(value=cfg.get("branch_name","") or "تهران")
        row = ttk.Frame(self.content)
        row.pack(fill="x", pady=10)
        ttk.Label(row, text="شعبه", width=23, anchor="e").pack(side="right")
        ttk.Combobox(row, textvariable=chosen, state="readonly", values=list(BRANCHES.values()),
                     justify="right").pack(side="right", fill="x", expand=True)
        self.text(self.content, "سرور مرکزی: " + secret_store.HUB)
        self.text(self.content, "کلید: " + ("ثبت شده (مخفی)" if cfg.get("token") else "هنوز ثبت نشده"))
        key = self.entry(self.content, "کلید جدید (در صورت نیاز)", secret=True)
        enabled = tk.BooleanVar(value=bool(cfg.get("enabled")))
        ttk.Checkbutton(self.content, text="ارتباط با مرکز فعال باشد", variable=enabled).pack(anchor="e", pady=12)
        def save():
            if self.user.get("role") != "superadmin":
                raise ValueError("فقط سوپرمدیر.")
            branch_id = branch_names[chosen.get()]
            current = secret_store.load_config(backend.DATA)
            with backend.connect() as db:
                count = db.execute("SELECT COUNT(*) FROM waybills").fetchone()[0]
            if current.get("branch_id") and branch_id != current["branch_id"] and count:
                raise ValueError("پس از ثبت بارنامه، تغییر هویت شعبه مجاز نیست. به نصب مستقل نیاز است.")
            token = key.get().strip()
            if not token and current.get("branch_id") == branch_id:
                token = current.get("token", "")
            secret_store.save_config(backend.DATA,branch_id,token,enabled.get())
            with backend.connect() as db:
                backend.operations.audit(db,"BRANCH_CONFIG_UPDATED",branch_id,{"enabled":bool(enabled.get())})
                db.commit()
            key.set("")
            messagebox.showinfo("ذخیره شد", "تنظیمات اتصال به‌صورت رمزگذاری‌شده ذخیره شد.",parent=self.root)
            self.main("تنظیمات مرکزی")
        self.button(self.content, "ذخیره تنظیمات امن", lambda:self.action(save)).pack(anchor="e", pady=12)
        self.button(self.content, "آزمایش اتصال", lambda:self.action(self.sync)).pack(anchor="e", pady=6)
        self.text(self.content, "توجه: با حساب کاربری متفاوت ویندوز ممکن است DPAPI نتواند کلید را باز کند.", muted=True)

    def sync(self):
        if self.sync_result == "pending":
            return
        self.sync_result = "pending"
        def worker():
            self.sync_result = backend.sync_engine.sync_once(backend.connect, backend.DATA)
        threading.Thread(target=worker, daemon=True).start()
        def check():
            if self.sync_result == "pending":
                self.root.after(300, check)
            else:
                result = self.sync_result
                self.sync_result = None
                if result.get("ok"):
                    messagebox.showinfo("اتصال برقرار شد", "ارسال: {} | دریافت: {}".format(
                        result.get("sent",0),result.get("received",0)),parent=self.root)
                elif result.get("busy"):
                    messagebox.showinfo("اتصال", "همگام‌سازی دیگری در حال اجراست.",parent=self.root)
                else:
                    messagebox.showwarning("وضعیت اتصال", str(result.get("error") or result),parent=self.root)
        self.root.after(400, check)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        Desktop().run()
    except Exception as exc:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("اتوبنز وحدت — خطا", str(exc), parent=root)
            root.destroy()
        except Exception:
            raise
        sys.exit(1)
