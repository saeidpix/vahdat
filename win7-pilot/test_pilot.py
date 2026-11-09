# -*- coding: utf-8 -*-
"""Smoke tests for the isolated Windows 7 / 4GB RAM Qaemshahr pilot."""
import os
import pathlib
import sys
import tempfile

root = pathlib.Path(__file__).resolve().parent.parent / "Vahdat-1.5.7"
sys.path.insert(0, str(root / "windows"))
with tempfile.TemporaryDirectory(prefix="vahdat-win7-pilot-test-") as tmp:
    os.environ["PROGRAMDATA"] = tmp
    import app as v
    v.init()
    assert v.PORT == 8877, v.PORT
    assert v.DATA.name == "VahdatPilotQaemshahr", v.DATA
    assert v.DB.exists()
    client = v.app.test_client()
    health = client.get("/api/health")
    assert health.status_code == 200 and health.json["version"] == "1.5.7-win7-qaemshahr-pilot"
    bootstrap = client.post("/api/auth/bootstrap", json={
        "name": "مدیر آزمایشی", "mobile": "09120000000", "password": "SecurePass123!"
    })
    assert bootstrap.status_code == 200, bootstrap.json
    status = client.get("/api/auth/status")
    assert status.status_code == 200 and status.json["authenticated"], status.json
    csrf = {"X-CSRF-Token": status.json["csrf"]}
    prefs = client.get("/api/settings")
    assert prefs.status_code == 200, prefs.json
    assert prefs.json["branch_id"] == "qaemshahr" and prefs.json["origin"] == "قائم‌شهر"
    assert prefs.json["destinations"] == ["تهران"], prefs.json
    badprefs = client.post("/api/settings", json={"destinations": ["آمل"]}, headers=csrf)
    assert badprefs.status_code == 409, badprefs.json
    denied = client.post("/api/waybills", json={"destination": "ساری"}, headers=csrf)
    assert denied.status_code == 409, denied.json
    for n in range(1, 31):
        r = client.post("/api/waybills", json={"destination": "تهران", "sender": "TEST",
                 "receiver": "TEST", "pieces": 1, "prepaid": 1000}, headers=csrf)
        assert r.status_code == 201, (n, r.status_code, r.json)
        b = r.json["waybill"]
        assert b["number"] == n and b["id"].startswith("VH-PILOT-"), b
        assert b["origin"] == "قائم‌شهر" and b["destination"] == "تهران", b
    limit = client.post("/api/waybills", json={"destination": "تهران"}, headers=csrf)
    assert limit.status_code == 409, limit.json
    assert "۳۰" in limit.json["error"], limit.json
    sync = client.get("/api/sync/status")
    assert sync.status_code == 200 and not sync.json["enabled"], sync.json
    assert sync.json["branch_id"] == "qaemshahr", sync.json
    print("OK: isolated data, branch lock, 30-bill limit, numbering 1..30, auth and sync status.")
