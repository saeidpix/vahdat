# -*- coding: utf-8 -*-
"""Regression tests for configurable mandatory fields and immutable fee snapshots."""
import os
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"Vahdat-1.5.7"/"windows"),str(ROOT/"universal")]

class BranchPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="vahdat-branch-policy-")
        self.addCleanup(self.temp.cleanup)
        os.environ["PROGRAMDATA"]=self.temp.name
        import app
        import secret_store
        app.DATA=pathlib.Path(self.temp.name)/"VahdatUniversal"
        app.DATA.mkdir(parents=True,exist_ok=True)
        app.DB=app.DATA/"vahdat.sqlite3"
        app.sync_engine.load_config=secret_store.load_config
        app.init()
        self.app=app
        self.client=app.app.test_client()
        result=self.client.post("/api/auth/bootstrap",json={
            "name":"سوپرمدیر","mobile":"09120000000","password":"SuperAdminPassword123"
        })
        self.assertEqual(result.status_code,200,result.get_json())
        st=self.client.get("/api/auth/status").get_json()
        self.assertEqual(st["user"]["role"],"superadmin")
        self.headers={"X-CSRF-Token":st["csrf"]}
        secret_store.save_config(app.DATA,"qaemshahr","CI-ONLY-DUMMY-TOKEN-012345678900000000000000000",enabled=True)
        with app.connect() as c:
            c.execute("UPDATE sync_meta SET value='1' WHERE key='catalog_ready'")
            c.execute("INSERT INTO sync_branch_catalog VALUES(?,?,?,?)",
                      ("tehran","تهران",1,1))
            c.commit()

    def policy(self,amount,fields):
        result=self.client.post("/api/branch-policy",headers=self.headers,json={
            "storage_flat_fee_toman":amount,
            "storage_mode":"once_per_waybill_at_issue",
            "required_fields":fields
        })
        self.assertEqual(result.status_code,200,result.get_json())
        return result.get_json()["branch_policy"]

    def bill(self,**overrides):
        data={"destination":"تهران","pieces":5,"sender":"فرستنده تست",
              "receiver":"گیرنده تست","prepaid":10000,"post_fare":20000,
              "storage_fee":9999999,"other_fee":400,
              "phone":"","sender_phone":"","description":""}
        data.update(overrides)
        return self.client.post("/api/waybills",headers=self.headers,json=data)

    def test_price_is_server_owned_and_existing_bills_unchanged(self):
        saved=self.policy(5000,{"sender":True,"receiver":True})
        self.assertEqual(saved["storage_flat_fee_toman"],5000)
        first=self.bill()
        self.assertEqual(first.status_code,201,first.get_json())
        first_id=first.get_json()["waybill"]["id"]
        self.assertEqual(first.get_json()["waybill"]["storage_fee"],5000)
        self.assertEqual(first.get_json()["waybill"]["total"],35400)
        self.policy(7000,{"sender":True,"receiver":True})
        second=self.bill()
        self.assertEqual(second.status_code,201,second.get_json())
        self.assertEqual(second.get_json()["waybill"]["storage_fee"],7000)
        details=self.client.get("/api/waybills/"+first_id).get_json()
        self.assertEqual(details["waybill"]["storage_fee"],5000)
        self.assertEqual(details["waybill"]["total"],35400)
        with self.app.connect() as c:
            r=c.execute("SELECT COUNT(*) FROM events WHERE waybill_id=? AND kind='ISSUED'",
                        (first_id,)).fetchone()
            self.assertEqual(r[0],1)

    def test_missing_required_mobile_rejected_and_toggleable(self):
        self.policy(0,{"sender":True,"receiver":True,
                       "sender_phone":True,"phone":True,"description":True})
        missing=self.bill()
        self.assertEqual(missing.status_code,422,missing.get_json())
        bad=self.bill(sender_phone="123",phone="09121234567",description="کارتن")
        self.assertEqual(bad.status_code,422,bad.get_json())
        okay=self.bill(sender_phone="09121234567",phone="09121234568",description="کارتن")
        self.assertEqual(okay.status_code,201,okay.get_json())
        self.policy(0,{"sender":False,"receiver":False,
                       "sender_phone":False,"phone":False,"description":False})
        optional=self.bill(sender="",receiver="",sender_phone="",phone="",description="")
        self.assertEqual(optional.status_code,201,optional.get_json())

    def test_system_fields_always_mandatory_and_strict_server_validation(self):
        self.policy(1000,{"sender":False,"receiver":False})
        self.assertEqual(self.bill(pieces=0).status_code,422)
        self.assertEqual(self.bill(pieces=-2).status_code,422)
        self.assertEqual(self.bill(destination="").status_code,409)
        self.assertEqual(self.bill(destination="آمل").status_code,409)
        self.assertEqual(self.bill(pieces=1,destination="تهران").status_code,201)

    def test_branch_admin_cannot_update_superadmin_policy(self):
        r=self.client.post("/api/users",headers=self.headers,json={
           "name":"مدیر شعبه","mobile":"09120000021","password":"BranchManagerPassword123",
           "role":"admin"
        })
        self.assertEqual(r.status_code,201,r.get_json())
        self.client.post("/api/auth/logout",headers=self.headers)
        login=self.client.post("/api/auth/login",json={"mobile":"09120000021",
                                                       "password":"BranchManagerPassword123"})
        self.assertEqual(login.status_code,200,login.get_json())
        st=self.client.get("/api/auth/status").get_json()
        self.assertEqual(st["user"]["role"],"admin")
        r=self.client.post("/api/branch-policy",
            headers={"X-CSRF-Token":st["csrf"]},
            json={"storage_flat_fee_toman":99999,"required_fields":{}})
        self.assertEqual(r.status_code,403,r.get_json())
        listing=self.client.get("/api/settings")
        self.assertEqual(listing.status_code,200,listing.get_json())
        self.assertEqual(listing.get_json()["branch_policy"]["storage_flat_fee_toman"],0)

    def test_reject_invalid_rate_without_mangling_previous_policy(self):
        self.policy(500,{"sender":True})
        for x in ("-500","100x","123.50",True,10**13):
            with self.subTest(rate=x):
                r=self.client.post("/api/branch-policy",headers=self.headers,
                    json={"storage_flat_fee_toman":x,"required_fields":{}})
                self.assertEqual(r.status_code,422,r.get_json())
        self.assertEqual(self.client.get("/api/settings").get_json()
                         ["branch_policy"]["storage_flat_fee_toman"],500)

if __name__=="__main__":
    unittest.main(verbosity=2)
