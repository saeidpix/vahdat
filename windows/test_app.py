# -*- coding: utf-8 -*-
import base64, gzip, json, os, pathlib, sys, tempfile, unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).parent
sys.path.insert(0,str(ROOT))
TMP=tempfile.TemporaryDirectory()
os.environ["PROGRAMDATA"]=TMP.name
import app as v

class VahdatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        v.init()
        cls.client=v.app.test_client()

    def test_jalali_and_seconds(self):
        import datetime
        millis=int(datetime.datetime(2026,11,8,8,9,10,
                   tzinfo=v.TZ).timestamp()*1000)
        result=v.shamsi(millis)
        self.assertIn("۱۴۰۵/۰۸/۱۷",result)
        self.assertIn("۰۸:۰۹:۱۰",result)

    def test_settings_and_zero_restrictions(self):
        r=self.client.get("/api/settings")
        self.assertEqual(r.json["destinations"],["قائم‌شهر"])
        self.assertEqual(r.json["origin"],"تهران")
        r=self.client.post("/api/settings",json={"destinations":["قائم‌شهر","ساری"]})
        self.assertEqual(r.status_code,200)

    def test_issue_qr_import_and_payment(self):
        r=self.client.post("/api/waybills",json={
            "destination":"قائم‌شهر","sender":"علی","receiver":"محمد",
            "phone":"123","pieces":3,"prepaid":300000,"post_fare":500000,
            "storage_fee":120000,"other_fee":80000
        })
        self.assertEqual(r.status_code,201)
        bill=r.json["waybill"]
        self.assertEqual(bill["total"],1000000)
        self.assertEqual(bill["due"],700000)
        raw=v.encode_qr(bill)
        self.assertTrue(raw.startswith("VHD1:"))
        # Android decodes GZIP Base64Url JSON; verify identical keys.
        payload=json.loads(gzip.decompress(base64.urlsafe_b64decode(raw[5:])))
        self.assertEqual(payload["v"],2)
        self.assertEqual(payload["k"],500000)
        self.assertEqual(payload["w"],120000)
        self.assertEqual(payload["x"],80000)
        self.assertEqual(v.decode_qr(raw)["id"],bill["id"])
        # Same ID cannot be imported twice: no duplicate stored.
        r=self.client.post("/api/import",json={"qr":raw})
        self.assertFalse(r.json["fresh"])
        number=bill["id"]
        r=self.client.post("/api/waybills/"+number+"/receive",json={})
        self.assertTrue(r.json["changed"])
        r=self.client.post("/api/waybills/"+number+"/receive",json={})
        self.assertFalse(r.json["changed"])
        r=self.client.post("/api/waybills/"+number+"/deliver",
                           json={"person":"محمد","collected":700000})
        self.assertTrue(r.json["changed"])
        self.assertEqual(r.json["waybill"]["status"],"تحویل‌شده")
        self.assertEqual(r.json["waybill"]["post_collected"],700000)
        self.assertTrue(r.json["waybill"]["delivered_at_fa"])
        self.assertEqual(self.client.get("/api/qr/"+number).status_code,200)

    def test_old_android_qr_v1(self):
        old={"v":1,"id":"VH-1700000-LEGACY","o":"تهران","d":"قائم‌شهر",
             "s":"","r":"","p":"","n":1,"t":900,"a":200,"c":1750000000000}
        raw="VHD1:"+base64.urlsafe_b64encode(
            gzip.compress(json.dumps(old).encode("utf-8"))).decode()
        d=v.decode_qr(raw)
        self.assertEqual(d["post_fare"],700)
        self.assertEqual(d["storage_fee"],0)

if __name__=="__main__":unittest.main()
