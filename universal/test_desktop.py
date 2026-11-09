# -*- coding: utf-8 -*-
"""Smoke tests for the shared Windows desktop edition."""
import os
import pathlib
import sys
import tempfile
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "Vahdat-1.5.7" / "windows"))
sys.path.insert(0, str(BASE / "universal"))

class UniversalTests(unittest.TestCase):
    def test_initial_setup_and_five_branch_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["PROGRAMDATA"] = tmp
            import app as core
            import secret_store
            core.DATA = pathlib.Path(tmp) / "VahdatUniversal"
            core.DATA.mkdir(exist_ok=True)
            core.DB = core.DATA / "vahdat.sqlite3"
            core.sync_engine.load_config = secret_store.load_config
            core.init()
            client = core.app.test_client()
            r = client.post("/api/auth/bootstrap", json={
                "name": "مدیر", "mobile": "09120000000", "password": "TestPassword1234"})
            self.assertEqual(r.status_code, 200, r.get_json())
            auth = client.get("/api/auth/status").get_json()
            self.assertEqual(auth["user"]["role"], "superadmin")
            headers = {"X-CSRF-Token": auth["csrf"]}
            r = client.post("/api/waybills", json={"destination": "تهران","pieces":1,"sender":"الف","receiver":"ب"}, headers=headers)
            self.assertEqual(r.status_code, 409)
            test_token = "0123456789" * 5
            for branch_id, name in secret_store.BRANCHES.items():
                secret_store.save_config(core.DATA, branch_id, test_token)
                cfg = secret_store.load_config(core.DATA)
                self.assertEqual(cfg["branch_id"], branch_id)
                self.assertEqual(cfg["branch_name"], name)
                self.assertNotIn(test_token.encode("ascii"),
                                 secret_store.location(core.DATA).read_bytes())
            secret_store.save_config(core.DATA, "qaemshahr", test_token)
            r = client.post("/api/waybills", json={"destination": "تهران","pieces":1,"sender":"الف","receiver":"ب"}, headers=headers)
            self.assertEqual(r.status_code, 409)
            with core.connect() as db:
                db.execute("UPDATE sync_meta SET value='1' WHERE key='catalog_ready'")
                db.execute("INSERT INTO sync_branch_catalog VALUES(?,?,?,?)",
                           ("tehran", "تهران", 1, 1))
                db.commit()
            r = client.post("/api/waybills", json={"destination":"بابل","pieces":1,"sender":"الف","receiver":"ب"}, headers=headers)
            self.assertEqual(r.status_code, 409)
            r = client.post("/api/waybills", json={
                "destination":"تهران", "sender":"آزمایشی", "receiver":"آزمایشی",
                "pieces":1, "prepaid":2000}, headers=headers)
            self.assertEqual(r.status_code, 201, r.get_json())
            self.assertEqual(r.get_json()["waybill"]["number"], 1)
            self.assertEqual(r.get_json()["waybill"]["origin"], "قائم‌شهر")
            self.assertFalse((core.DATA / "sync-config.json").exists())

if __name__ == "__main__":
    unittest.main(verbosity=2)
