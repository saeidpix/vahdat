# -*- coding: utf-8 -*-
"""Vahdat desktop using the ORIGINAL web UI inside a native Qt window.

Keeps the original HTML/CSS/JS (rounded controls, photo illustrations,
RTL forms and print view), but launches NO external browser. A local-only
Waitress instance serves the existing Flask routes. Company sync remains
outgoing HTTPS. Windows 7 SP1+ x86 and x64 use Qt 5.15/Python 3.8 x86.

Connection credentials can only be provisioned via a separate native
dialog after authenticating as a superadmin. Credentials remain DPAPI encrypted.
"""
import os
import sys
import socket
import threading
import traceback

# Qt Chromium is old for Windows 7; never allow it to browse the Internet.
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
from PyQt5.QtCore import Qt, QUrl, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QDialog, QFormLayout, QComboBox, QLineEdit,
    QCheckBox, QDialogButtonBox, QMessageBox, QFrame, QInputDialog,
)
from PyQt5.QtWebEngineWidgets import (
    QWebEngineView, QWebEnginePage, QWebEngineProfile,
    QWebEngineUrlRequestInterceptor
)
from waitress import create_server

import app as backend
import secret_store

backend.sync_engine.load_config = secret_store.load_config

NAVY = "#132d50"
BLUE = "#2565d8"
YELLOW = "#f3c43b"
CSS = """
QMainWindow, QDialog { background:#f1f5fb; }
QLabel { color:#233a56; font-family:Tahoma; font-size:11pt; }
QPushButton { font: bold 10pt Tahoma; color:white; background:#2565d8;
    border:1px solid #1c55ba; border-radius:10px; padding:12px 17px; }
QPushButton:hover { background:#1853ba; }
QPushButton:pressed { background:#103f91; }
QPushButton:disabled { background:#a3bad8; }
QLineEdit, QComboBox { color:#233a56; font:10pt Tahoma;
    background:#fff; border:1px solid #cad7e7; border-radius:9px;
    padding:9px; min-height:22px; selection-background-color:#2565d8; }
QLineEdit:focus, QComboBox:focus { border:2px solid #2565d8; }
QCheckBox { font:10pt Tahoma; spacing:10px; color:#233a56; }
QFrame#toolbar { background:#132d50; border-bottom:3px solid #f3c43b; }
QFrame#toolbar QLabel { color:white; }
QFrame#toolbar QPushButton { background:#f3c43b; color:#132d50;
    border:0; padding:9px 14px; font:bold 10pt Tahoma; }
QFrame#toolbar QPushButton:hover { background:#ffe17a; }
QDialog QLabel#heading { color:#132d50; font:bold 14pt Tahoma; }
"""


class LocalOnly(QWebEngineUrlRequestInterceptor):
    def __init__(self, port, parent=None):
        super().__init__(parent)
        self.port = port

    def interceptRequest(self, info):
        url = info.requestUrl()
        scheme = url.scheme().lower()
        if scheme in ("data", "blob", "about"):
            return
        if scheme == "http" and url.host() in ("127.0.0.1", "localhost") and url.port() == self.port:
            return
        # Loading arbitrary external content in Win7's legacy Chromium is unsafe.
        info.block(True)


class RestrictedPage(QWebEnginePage):
    def __init__(self, profile, port, parent=None):
        super().__init__(profile, parent)
        self.port = port

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme().lower() in ("data", "blob", "about"):
            return True
        return url.scheme().lower() == "http" and url.host() in ("127.0.0.1", "localhost") and url.port() == self.port


class ProtectedSettings(QDialog):
    def __init__(self, parent, api):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("اتوبنز وحدت | تنظیمات محرمانه شعبه")
        self.setMinimumWidth(565)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet(CSS)
        outer = QVBoxLayout(self)
        outer.setSpacing(18)
        outer.setContentsMargins(25, 25, 25, 25)
        title = QLabel("اتصال امن شعبه به مرکز")
        title.setObjectName("heading")
        outer.addWidget(title)
        note = QLabel("فقط سوپرمدیر می‌تواند شناسه شعبه و کلید ارتباط را تغییر دهد.\nکلید ذخیره‌شده هیچ‌وقت نمایش داده نمی‌شود.")
        note.setWordWrap(True)
        outer.addWidget(note)
        form = QFormLayout()
        form.setSpacing(12)
        self.mobile = QLineEdit()
        self.mobile.setPlaceholderText("موبایل حساب سوپرمدیر همین برنامه")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("رمز عبور سوپرمدیر")
        form.addRow("ورود مجدد سوپرمدیر", self.mobile)
        form.addRow("رمز عبور", self.password)
        outer.addLayout(form)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#d6e0eb")
        outer.addWidget(line)
        opts = QFormLayout()
        opts.setSpacing(12)
        self.branch = QComboBox()
        for bid, name in secret_store.BRANCHES.items():
            self.branch.addItem(name, bid)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("کلید جدید (اگر کلید قبلاً ثبت شده، خالی بگذارید)")
        self.enabled = QCheckBox("فعال‌سازی همگام‌سازی با سرور مرکزی")
        self.hub = QLabel(secret_store.HUB)
        opts.addRow("شعبه", self.branch)
        opts.addRow("سرور مرکزی", self.hub)
        opts.addRow("کلید محرمانه", self.token)
        opts.addRow("", self.enabled)
        outer.addLayout(opts)
        existing = secret_store.load_config(backend.DATA)
        if existing.get("branch_id"):
            index = self.branch.findData(existing["branch_id"])
            if index >= 0:
                self.branch.setCurrentIndex(index)
        self.enabled.setChecked(bool(existing.get("enabled")))
        self.save = QPushButton("ذخیره تنظیمات امن")
        self.save.clicked.connect(self.provision)
        outer.addWidget(self.save)
        outer.addWidget(QLabel("حساب مدیر سایت اینترنتی با سوپرمدیر محلی متفاوت است."))

    def provision(self):
        mobile = self.mobile.text().strip()
        pwd = self.password.text()
        if not mobile or not pwd:
            QMessageBox.warning(self, "تأیید هویت", "موبایل و رمز سوپرمدیر را وارد کنید.")
            return
        # Independent in-memory client. Do not borrow the embedded WebEngine user's session.
        check = backend.app.test_client()
        result = check.post("/api/auth/login", json={"mobile":mobile, "password":pwd})
        if result.status_code != 200:
            QMessageBox.warning(self, "تأیید هویت", "نام کاربری یا رمز عبور معتبر نیست.")
            return
        identity = check.get("/api/auth/status").get_json(silent=True) or {}
        if (identity.get("user") or {}).get("role") != "superadmin":
            QMessageBox.warning(self, "عدم دسترسی", "فقط سوپرمدیر مجاز به تنظیم ارتباط است.")
            return
        branch_id = self.branch.currentData()
        current = secret_store.load_config(backend.DATA)
        if current.get("branch_id") and current["branch_id"] != branch_id:
            with backend.connect() as db:
                count = db.execute("SELECT COUNT(*) FROM waybills").fetchone()[0]
            if count:
                QMessageBox.warning(self, "شعبه ثبت‌شده",
                   "پس از صدور بارنامه، تغییر شناسه شعبه ممنوع است.")
                return
        key = self.token.text().strip()
        if not key and current.get("branch_id") == branch_id:
            key = current.get("token") or ""
        try:
            secret_store.save_config(backend.DATA, branch_id, key, enabled=self.enabled.isChecked())
        except Exception as exc:
            QMessageBox.critical(self, "ذخیره نشد", str(exc))
            return
        self.token.clear()
        self.password.clear()
        self.accept()


class DesktopWindow(QMainWindow):
    def __init__(self, server, port, api):
        super().__init__()
        self.server = server
        self.port = port
        self.api = api
        self.setWindowTitle("اتوبنز وحدت | مدیریت بارنامه شعب")
        self.resize(1320, 840)
        self.setMinimumSize(940, 610)
        self.setStyleSheet(CSS)
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        header = QFrame()
        header.setObjectName("toolbar")
        header.setFixedHeight(57)
        header.setLayoutDirection(Qt.RightToLeft)
        bar = QHBoxLayout(header)
        bar.setContentsMargins(20, 4, 20, 4)
        title = QLabel("اتوبنز وحدت  |  سامانه باربری شعب")
        title.setStyleSheet("font:bold 12pt Tahoma;color:white;")
        bar.addWidget(title)
        bar.addStretch()
        self.branch_name = QLabel()
        bar.addWidget(self.branch_name)
        self.settings_btn = QPushButton("تنظیمات امن سوپرمدیر  🔒")
        self.settings_btn.clicked.connect(self.provision)
        bar.addWidget(self.settings_btn)
        v.addWidget(header)
        self.profile = QWebEngineProfile("VahdatLocalOnly", self)
        self.profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        self.interceptor = LocalOnly(port, self)
        self.profile.setRequestInterceptor(self.interceptor)
        self.web = QWebEngineView()
        self.page = RestrictedPage(self.profile, port, self.web)
        self.web.setPage(self.page)
        v.addWidget(self.web, stretch=1)
        self.web.load(QUrl("http://127.0.0.1:{}/".format(port)))
        self.label_update()
        timer = QTimer(self)
        timer.timeout.connect(self.label_update)
        timer.start(18000)
        self.timer = timer

    def label_update(self):
        try:
            cfg = secret_store.load_config(backend.DATA)
            name = cfg.get("branch_name") or "شعبه هنوز تنظیم نشده"
        except Exception:
            name = "وضعیت تنظیمات نامشخص"
        self.branch_name.setText(name)

    def provision(self):
        try:
            dialog = ProtectedSettings(self, self.api)
            if dialog.exec_() == QDialog.Accepted:
                self.label_update()
                self.web.reload()
                QMessageBox.information(self, "تنظیمات ثبت شد", 
                    "اطلاعات شعبه رمزگذاری شد. اکنون وضعیت اتصال و مقصدها را بررسی کنید.")
        except Exception as exc:
            QMessageBox.critical(self, "تنظیمات", str(exc))

    def closeEvent(self, event):
        try:
            self.web.setPage(None)
            self.server.close()
        except Exception:
            pass
        event.accept()


def main():
    if os.name != "nt":
        raise RuntimeError("This desktop build is supported on Windows only.")
    backend.init()
    backend.sync_engine.start_worker(backend.connect, backend.DATA)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # The socket is explicitly confined to loopback; no branch LAN access.
    server = create_server(backend.app, host="127.0.0.1", port=port, threads=4)
    thread = threading.Thread(target=server.run, name="VahdatLocalRenderer", daemon=True)
    thread.start()
    app = QApplication(sys.argv)
    app.setFont(QFont("Tahoma", 10))
    window = DesktopWindow(server, port, backend.app)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "اتوبنز وحدت — خطا", str(exc))
        except Exception:
            traceback.print_exc()
        sys.exit(1)
