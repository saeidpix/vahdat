"""Exercise actual HTML/JS against a real HTTP server and isolated SQLite database."""
import os, pathlib, tempfile, threading, json, urllib.request
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

tmp=tempfile.TemporaryDirectory()
os.environ['PROGRAMDATA']=tmp.name
import app as v

v.init()
server=make_server('127.0.0.1',0,v.app,threaded=True)
thread=threading.Thread(target=server.serve_forever,daemon=True)
thread.start()
base=f'http://127.0.0.1:{server.server_port}'
shots=pathlib.Path(os.environ.get('VAHDAT_SCREENSHOTS','browser-results'))
shots.mkdir(parents=True,exist_ok=True)
try:
    with sync_playwright() as p:
        kwargs={'headless':True}
        if os.environ.get('VAHDAT_BROWSER'):
            kwargs['executable_path']=os.environ['VAHDAT_BROWSER']
        browser=p.chromium.launch(**kwargs)
        page=browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1,reduced_motion='reduce')
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('dialog',lambda d:d.accept())
        page.goto(base)
        expect(page.locator('h2')).to_have_text('خانه')
        expect(page.locator('.tile')).to_have_count(4)
        assert page.locator('.tile small').count()==0
        for image in ['.taxi','.logo']:
            expect(page.locator(image)).to_have_js_property('complete',True)
            assert page.locator(image).evaluate('(e)=>e.naturalWidth>0')
        page.screenshot(path=str(shots/'home.png'),full_page=True)
        page.locator('#nav-reports').click()
        expect(page.locator('h2')).to_have_text('گزارش مالی')
        assert all('۰ تومان' in x for x in page.locator('.stat strong').all_text_contents())
        page.locator('#nav-settings').click()
        expect(page.locator('#newdest')).to_be_visible()
        page.locator('#newdest').fill('ساری')
        page.get_by_role('button',name='افزودن مقصد',exact=True).click()
        with page.expect_response(lambda r:r.url.endswith('/api/settings') and r.request.method=='POST'):
            page.get_by_role('button',name='ذخیره مقصدها',exact=True).click()
        page.reload()
        page.locator('#nav-new').click()
        expect(page.locator('#destination')).to_have_value('قائم‌شهر')
        expect(page.locator('#destination option')).to_have_count(2)
        for key,value in [('sender','فرستنده'),('receiver','گیرنده'),('phone','۰۹۱۲۱۲۳۴۵۶۷'),('pieces','۲'),('prepaid','۳۰۰۰۰۰'),('post_fare','500000'),('storage_fee','۱۲۰۰۰۰'),('other_fee','80000')]:
            page.locator('#'+key).fill(value)
        expect(page.locator('#prepaid')).to_have_value('۳۰۰٬۰۰۰')
        expect(page.locator('#fareTotal')).to_have_text('۱٬۰۰۰٬۰۰۰ تومان')
        page.screenshot(path=str(shots/'issuance.png'),full_page=True)
        page.locator('#issueButton').click()
        expect(page.locator('h2')).to_have_text('جزئیات بارنامه')
        expect(page.locator('.keyrow').first).to_contain_text('۱')
        assert 'VH-' not in page.locator('#page').inner_text()
        with urllib.request.urlopen(base+'/api/waybills') as r:
            bill=json.load(r)['items'][0]
        assert bill['number']==1 and bill['total']==1000000
        raw=v.encode_qr(bill)
        page.locator('#nav-scan').click()
        page.locator('#qrInput').fill(raw)
        page.locator('#qrInput').press('Enter')
        expect(page.locator('h2')).to_have_text('جزئیات بارنامه')
        page.get_by_role('button',name='ثبت دریافت بار',exact=True).click()
        expect(page.locator('#person')).to_be_visible()
        page.get_by_role('button',name='ثبت تحویل',exact=True).click()
        expect(page.get_by_text('بار تحویل شده است',exact=True)).to_be_visible()
        page.locator('#nav-list').click()
        page.locator('#search').fill('۱')
        expect(page.locator('tbody tr')).to_have_count(1)
        expect(page.locator('tbody td').first).to_have_text('۱')
        page.locator('#nav-reports').click()
        expect(page.locator('.stat strong').first).to_have_text('۱٬۰۰۰٬۰۰۰ تومان')
        page.screenshot(path=str(shots/'reports.png'),full_page=True)
        page.locator('#nav-settings').click()
        with page.expect_download() as download:
            page.get_by_role('link',name='دریافت پشتیبان').click()
        assert download.value.suggested_filename.endswith('.sqlite3')
        for width in [1440,1024,768,390]:
            page.set_viewport_size({'width':width,'height':900})
            for name in ['home','new','scan','list','reports','settings']:
                page.locator('#nav-'+name).click()
                expect(page.locator('h2')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,name)
        assert not errors,errors
        browser.close()
        print('PASS: six pages, real API, money, numbering, QR, receive/deliver, reports, settings, backup, responsive layouts')
finally:
    server.shutdown()
    thread.join()
    tmp.cleanup()
