# -*- coding: utf-8 -*-
"""Smoke tests for warehouse lifecycle and recoverable inbound conflict queue."""
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"Vahdat-1.5.7"/"windows"))
sys.path.insert(0,str(ROOT/"universal"))
import app
import sync_engine
import secret_store


class InventoryAndRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="vahdat-stock-ci-")
        os.environ["PROGRAMDATA"]=cls.temp.name
        app.DATA=pathlib.Path(cls.temp.name)/"VahdatUniversal"
        app.DATA.mkdir(parents=True,exist_ok=True)
        app.DB=app.DATA/"vahdat.sqlite3"
        app.sync_engine.load_config=secret_store.load_config
        app.init()
        cls.client=app.app.test_client()
        r=cls.client.post("/api/auth/bootstrap",json={
            "name":"سوپرمدیر تست","mobile":"09120000000","password":"TestStrongPassword100"
        })
        assert r.status_code==200,r.get_json()
        status=cls.client.get("/api/auth/status").get_json()
        assert status["user"]["role"]=="superadmin",status
        cls.headers={"X-CSRF-Token":status["csrf"]}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_inventory_reconciles_warehouse_and_excludes_delivered(self):
        t=int(time.time()*1000)
        with app.connect() as c:
            for suffix,received,delivered in [('1',None,None),('2',t,None),('3',t,t+1)]:
                c.execute("""INSERT INTO waybills(
                  id,origin,destination,sender,receiver,phone,pieces,prepaid,post_fare,
                  storage_fee,other_fee,total,created_at,received_at,delivered_at,origin_here,number)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  ("VH-1760000000000-STOCK"+suffix,"تهران","قائم‌شهر","فرستنده","گیرنده",
                   "09120000000",2,10000,30000,0,0,40000,t,received,delivered,0,int(suffix)))
        r=self.client.get("/api/inventory")
        self.assertEqual(r.status_code,200,r.get_json())
        d=r.get_json()
        self.assertEqual(d["counts"],dict(waiting=1,in_stock=1,delivered=1))
        self.assertEqual(d["in_stock"][0]["id"],"VH-1760000000000-STOCK2")
        self.assertEqual(d["delivered"][0]["id"],"VH-1760000000000-STOCK3")
        self.assertNotEqual(d["in_stock"][0]["status"],"تحویل‌شده")

    def test_conflict_replay_repairs_valid_and_preserves_bad(self):
        secret_store.save_config(app.DATA,"qaemshahr","TEST-ONLY-CI-KEY-0123456789012345678901234567",enabled=True)
        t=int(time.time()*1000)
        key="VH-1760000000000-RECOV1"
        b=dict(id=key,origin="تهران",destination="قائم‌شهر",
               sender="فرستنده تست",receiver="گیرنده تست",phone="09120000000",
               pieces=1,prepaid=10000,post_fare=0,storage_fee=0,other_fee=0,
               total=10000,created_at=t,number=301,sender_phone=None,description=None)
        good=dict(id="E-"+"a"*32,kind="waybill_issued",
                  source_branch="تهران",payload={"waybill":b})
        bad=dict(id="E-"+"b"*32,kind="waybill_issued",
                 source_branch="شعبه نامعتبر",payload={"waybill":dict(b,id="VH-1760000000000-BADONE")})
        with app.connect() as c:
            for n,ev in enumerate((good,bad),1):
                c.execute("INSERT INTO sync_conflicts(id,event_id,reason,payload,happened_at) VALUES(?,?,?,?,?)",
                          ("C-ci-"+str(n),ev["id"],"legacy import error",
                           json.dumps(ev,ensure_ascii=False),t+n))
            c.execute("UPDATE sync_meta SET value='200' WHERE key='cursor'")
        result=self.client.get("/api/sync/conflicts")
        self.assertEqual(result.status_code,200,result.get_json())
        self.assertEqual(result.get_json()["count"],2)
        self.assertNotIn("فرستنده تست",str(result.get_json()))
        r=self.client.post("/api/sync/conflicts/retry",headers=self.headers)
        self.assertEqual(r.status_code,200,r.get_json())
        out=r.get_json()
        self.assertEqual(out["repaired"],1,out)
        self.assertEqual(out["remaining"],1,out)
        with app.connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM waybills WHERE id=?",(key,)).fetchone()[0],1)
            self.assertEqual(c.execute("SELECT value FROM sync_meta WHERE key='cursor'").fetchone()[0],"200")
            self.assertEqual(c.execute("SELECT COUNT(*) FROM sync_conflicts").fetchone()[0],1)
        repeat=self.client.post("/api/sync/conflicts/retry",headers=self.headers).get_json()
        self.assertEqual(repeat["repaired"],0,repeat)

    def test_non_superadmin_cannot_repair_conflicts(self):
        add=self.client.post("/api/users",headers=self.headers,json={
            "name":"مدیر شعبه","mobile":"09120000011","password":"AnotherStrongPass123","role":"admin"
        })
        self.assertEqual(add.status_code,201,add.get_json())
        self.client.post("/api/auth/logout",headers=self.headers)
        r=self.client.post("/api/auth/login",json={
            "mobile":"09120000011","password":"AnotherStrongPass123"
        })
        self.assertEqual(r.status_code,200,r.get_json())
        st=self.client.get("/api/auth/status").get_json()
        self.assertEqual(st["user"]["role"],"admin")
        self.assertEqual(self.client.get("/api/sync/conflicts").status_code,403)
        self.assertEqual(self.client.post("/api/sync/conflicts/retry",
                         headers={"X-CSRF-Token":st["csrf"]}).status_code,403)


if __name__=="__main__":
    unittest.main(verbosity=2)
