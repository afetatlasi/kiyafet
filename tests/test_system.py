import concurrent.futures
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import server

PASSWORD='Test-password-123!'
class Fixture:
    @classmethod
    def setUpClass(cls): cls.password_hash=server.hash_password(PASSWORD)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=server.Store(Path(self.temp.name)/'test.sqlite3');self.store.initialize()
        with self.store.db(True) as db:
            for name,role,pid in [('admin','ADMIN',None),('hq','HQ',None),('person','PERSONNEL',6),('person2','PERSONNEL',34),('material','MATERIAL',6),('material2','MATERIAL',34),('director','DIRECTOR',6),('director2','DIRECTOR',34)]:
                db.execute('INSERT INTO users(username,password_hash,full_name,role,province_id,registry,created_at,sizes) VALUES(?,?,?,?,?,?,?,?)',(name,self.password_hash,name,role,pid,name,server.now(),json.dumps({'Üst':'L','Alt':'L','Mont':'XL','Ayakkabı':'43','Eldiven':'9'})))
        with self.store.db() as db:
            self.actors={r['username']:dict(r) for r in db.execute('SELECT * FROM users')}
            self.special=db.execute("SELECT id FROM catalog WHERE name='KBRN Koruyucu Tulum'").fetchone()[0]
            self.summer=db.execute("SELECT id FROM catalog WHERE name='Yazlık Görev Ayakkabısı'").fetchone()[0]
    def tearDown(self): self.temp.cleanup()
    def call(self,who,path,**data): return self.store.mutate(self.actors[who],'/api/'+path,data)
    def request(self,who='person',item=None,qty=3,**extra):
        self.call(who,'requests',item_id=item or self.special,size='L',quantity=qty,priority='NORMAL',reason='Operasyon ihtiyacı',**extra)
        with self.store.db() as db:return db.execute('SELECT MAX(id) FROM requests').fetchone()[0]
    def action(self,who,rid,action,**extra):return self.call(who,'request-action',id=rid,action=action,**extra)
    def to_hq(self,rid):self.action('material',rid,'review');self.action('director',rid,'forward')
    def stock(self,loc,quantity=10,item=None,size='L'):
        self.call('admin','stock',location=loc,item_id=item or self.special,size=size,delta=quantity,note='Test stok girişi')
    def qty(self,loc,item=None,size='L'):
        with self.store.db() as db:
            row=db.execute('SELECT quantity FROM stock WHERE location=? AND item_id=? AND size=?',(loc,item or self.special,size)).fetchone()
            return row[0] if row else 0
    def row(self,table,rid):
        with self.store.db() as db:return dict(self.store.get(db,table,rid))
    def assignment(self):
        self.stock(6);rid=self.request(qty=1);self.action('material',rid,'issue',quantity=1)
        with self.store.db() as db:return db.execute('SELECT MAX(id) FROM assignments').fetchone()[0]
    def user_data(self,who,**changes):
        u=dict(self.actors[who]);keys=['id','username','full_name','role','province_id','unit_id','registry','title','specialty','start_date','active']
        return {**{k:u.get(k) for k in keys},**changes}
class ApplicationTests(Fixture, unittest.TestCase):
    def test_seed_has_81_provinces_and_two_shoe_types(self):
        data=self.store.bootstrap(self.actors['admin']);self.assertEqual(len(data['provinces']),81)
        self.assertEqual({c['supply_type'] for c in data['catalog'] if c['category']=='Ayakkabı'},{'SUMMER','WINTER'})
    def test_full_workflow_and_digital_receipt(self):
        self.stock(0);rid=self.request();self.to_hq(rid)
        self.action('hq',rid,'approve',quantity=3);self.assertEqual(self.qty(0),7)
        self.action('hq',rid,'ship',shipment_ref='KARGO-001');self.action('material',rid,'receive')
        self.assertEqual(self.qty(6),3);self.action('material',rid,'issue',quantity=3,serial='LOT-1');self.assertEqual(self.qty(6),0)
        a=self.store.bootstrap(self.actors['person'])['assignments'][0];self.call('person','assignment-action',id=a['id'],action='confirm')
        self.assertEqual(self.row('assignments',a['id'])['status'],'CONFIRMED')
        self.call('material','assignment-action',id=a['id'],action='return',note='Operasyon sonrası iade');self.assertEqual(self.qty(6),3)
    def test_other_province_and_person_are_blocked(self):
        rid=self.request();self.assertRaises(server.Problem,self.action,'material2',rid,'review')
        self.assertEqual(self.store.bootstrap(self.actors['person2'])['requests'],[])
        self.assertEqual(self.store.bootstrap(self.actors['material2'])['requests'],[])
        self.assertRaises(server.Problem,self.request,'person2',user_id=self.actors['person']['id'])
    def test_role_cannot_skip_approval(self):
        rid=self.request();self.assertRaises(server.Problem,self.action,'person',rid,'review')
        self.assertRaises(server.Problem,self.action,'hq',rid,'approve',quantity=3)
        self.assertRaises(server.Problem,self.call,'person','stock',location=6,item_id=self.special,size='L',delta=9,note='Yetkisiz giriş')
    def test_insufficient_stock_rolls_back(self):
        self.stock(0,2);rid=self.request();self.to_hq(rid)
        self.assertRaises(server.Problem,self.action,'hq',rid,'approve',quantity=3)
        self.assertEqual(self.qty(0),2);self.assertEqual(self.row('requests',rid)['status'],'HQ_REVIEW')
    def test_repeated_receipt_and_return_rejected(self):
        self.stock(0);rid=self.request();self.to_hq(rid);self.action('hq',rid,'approve',quantity=3);self.action('hq',rid,'ship',shipment_ref='REF-01');self.action('material',rid,'receive')
        self.assertRaises(server.Problem,self.action,'material',rid,'receive');self.assertEqual(self.qty(6),3)
        self.action('material',rid,'issue',quantity=3);a=self.store.bootstrap(self.actors['person'])['assignments'][0]
        self.call('material','assignment-action',id=a['id'],action='return',note='Test iade açıklaması')
        self.assertRaises(server.Problem,self.call,'material','assignment-action',id=a['id'],action='return',note='Tekrar iade');self.assertEqual(self.qty(6),3)
    def test_partial_allocation_is_visible(self):
        self.stock(0);rid=self.request(qty=5);self.to_hq(rid);self.action('hq',rid,'approve',quantity=2);self.action('hq',rid,'ship',shipment_ref='REF-02');self.action('material',rid,'receive');self.action('material',rid,'issue',quantity=2)
        self.assertEqual(self.row('requests',rid)['status'],'PARTIAL_COMPLETED');self.assertEqual(self.row('requests',rid)['issued'],2)
    def test_cancellation_releases_reserved_stock_once(self):
        self.stock(0);rid=self.request();self.to_hq(rid);self.action('hq',rid,'approve',quantity=3);self.action('hq',rid,'cancel-allocation',note='Tahsis iptal gerekçesi')
        self.assertEqual(self.qty(0),10);self.assertRaises(server.Problem,self.action,'hq',rid,'cancel-allocation',note='İkinci iptal')
    def test_rejection_requires_reason(self):
        rid=self.request();self.action('material',rid,'review');self.assertRaises(server.Problem,self.action,'director',rid,'reject',note='')
        self.action('director',rid,'reject',note='İhtiyaç uygun bulunmadı');self.assertEqual(self.row('requests',rid)['status'],'REJECTED')
    def test_batch_is_atomic_and_province_scoped(self):
        r1=self.request();r2=self.request('person2');self.action('material',r1,'review');self.action('material2',r2,'review')
        self.assertRaises(server.Problem,self.call,'director','batches',request_ids=[r1,r2],note='Toplu malzeme talebi')
        self.assertEqual(self.row('requests',r1)['status'],'PROVINCE_REVIEW')
        self.call('director','batches',request_ids=[r1],note='Toplu malzeme talebi');self.assertEqual(self.row('requests',r1)['status'],'HQ_REVIEW')
    def test_transfer_keeps_assignments_and_originating_requests(self):
        aid=self.assignment();rid=self.row('assignments',aid)['request_id']
        self.call('admin','users',**self.user_data('person',province_id=34))
        user=self.row('users',self.actors['person']['id']);self.assertEqual(user['province_id'],34)
        data=self.store.bootstrap(user);self.assertEqual(data['assignments'][0]['id'],aid);self.assertEqual(data['requests'][0]['province_id'],6)
        self.assertEqual(len(self.store.bootstrap(self.actors['material2'])['assignments']),1)
        self.assertEqual(self.row('requests',rid)['province_id'],6)
    def test_password_and_session_revocation(self):
        token,csrf,u=self.store.login('person',PASSWORD,'test');self.assertNotEqual(token,csrf)
        actor,_=self.store.session(token);self.assertEqual(actor['id'],u['id'])
        self.call('admin','users',**self.user_data('person',active=0));self.assertRaises(server.Problem,self.store.session,token)
    def test_failed_logins_are_throttled(self):
        for _ in range(10):
            with self.assertRaises(server.Problem) as ex:self.store.login('person','wrong','test')
            self.assertEqual(ex.exception.status,401)
        with self.assertRaises(server.Problem) as ex:self.store.login('person',PASSWORD,'test')
        self.assertEqual(ex.exception.status,429)
    def test_audit_cannot_be_changed(self):
        self.request()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.db(True) as db:db.execute("UPDATE audit SET detail='changed'")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.db(True) as db:db.execute('DELETE FROM audit')
    def test_concurrent_decrements_do_not_oversell(self):
        self.stock(6,1)
        def reduce():
            try:self.call('material','stock',location=6,item_id=self.special,size='L',delta=-1,note='Eşzamanlı çıkış');return True
            except server.Problem:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:reduce(),range(2)))
        self.assertEqual(sum(results),1);self.assertEqual(self.qty(6),0)
    def test_annual_kit_includes_shoes_and_prevents_duplicate(self):
        self.call('person','annual-kit',season='SUMMER');data=self.store.bootstrap(self.actors['person'])
        self.assertEqual(len(data['requests']),3);self.assertIn(self.summer,[r['item_id'] for r in data['requests']])
        self.assertRaises(server.Problem,self.call,'person','annual-kit',season='SUMMER')
        self.call('person','annual-kit',season='WINTER');self.assertEqual(len(self.store.bootstrap(self.actors['person'])['requests']),7)
    def test_missing_size_rolls_back_entire_kit(self):
        self.call('person','sizes',sizes={'Üst':'L','Alt':'L'})
        self.assertRaises(server.Problem,self.call,'person','annual-kit',season='SUMMER')
        self.assertEqual(len(self.store.bootstrap(self.actors['person'])['requests']),0)
    def test_annual_limit_cannot_be_bypassed_as_special(self):
        self.request(item=self.summer,qty=1)
        self.assertRaises(server.Problem,self.request,item=self.summer,qty=1)
        self.assertRaises(server.Problem,self.request,item=self.summer,qty=1,request_kind='SPECIAL')
        self.assertRaises(server.Problem,self.request,item=self.special,qty=1,request_kind='ANNUAL')
    def test_entitlement_resets_next_calendar_year(self):
        with patch('server.current_year',return_value=2026):self.request(item=self.summer,qty=1)
        with patch('server.current_year',return_value=2027):self.request(item=self.summer,qty=1)
        self.assertEqual(len(self.store.bootstrap(self.actors['person'])['requests']),2)
    def test_rejection_releases_annual_entitlement(self):
        rid=self.request(item=self.summer,qty=1);self.action('material',rid,'review');self.action('director',rid,'reject',note='Yanlış beden talebi')
        self.request(item=self.summer,qty=1)
    def test_early_wear_replacement_does_not_consume_annual_right(self):
        self.stock(6,item=self.summer);rid=self.request(item=self.summer,qty=1);self.action('material',rid,'issue',quantity=1)
        aid=self.store.bootstrap(self.actors['person'])['assignments'][0]['id'];self.call('person','assignment-action',id=aid,action='confirm')
        self.request(item=self.summer,qty=1,request_kind='REPLACEMENT',replacement_assignment_id=aid)
        data=self.store.bootstrap(self.actors['person']);e=next(e for e in data['entitlements'] if e['item_id']==self.summer)
        self.assertEqual(e['used_or_pending'],1);self.assertEqual(len(data['incidents']),1);self.assertEqual(data['requests'][0]['request_kind'],'REPLACEMENT')
        self.assertRaises(server.Problem,self.request,item=self.summer,qty=1,request_kind='REPLACEMENT',replacement_assignment_id=aid)
    def test_replacement_requires_own_confirmed_assignment(self):
        aid=self.assignment()
        self.assertRaises(server.Problem,self.request,qty=1,request_kind='REPLACEMENT',replacement_assignment_id=aid)
        self.call('person','assignment-action',id=aid,action='confirm')
        self.assertRaises(server.Problem,self.request,'person2',qty=1,request_kind='REPLACEMENT',replacement_assignment_id=aid)
    def test_special_equipment_is_available_on_demand(self):
        self.request(qty=10);self.request(qty=15)
        self.assertTrue(all(r['request_kind']=='SPECIAL' for r in self.store.bootstrap(self.actors['person'])['requests']))
    def test_workflow_settings_are_enforced(self):
        self.call('admin','workflow',allow_local_issue=False,allow_partial_allocation=False,require_serial=True)
        rid=self.request();self.stock(6)
        self.assertRaises(server.Problem,self.action,'material',rid,'issue',quantity=3)
        self.to_hq(rid);self.stock(0)
        self.assertRaises(server.Problem,self.action,'hq',rid,'approve',quantity=2)
        self.action('hq',rid,'approve',quantity=3);self.action('hq',rid,'ship',shipment_ref='REF-03');self.action('material',rid,'receive')
        before=self.qty(6);self.assertRaises(server.Problem,self.action,'material',rid,'issue',quantity=3)
        self.assertEqual(self.qty(6),before)
        self.action('material',rid,'issue',quantity=3,serial='LOT-123')
    def test_invalid_numbers_and_identifiers_rejected(self):
        for bad in [True,'3',0,-1,1.5]:self.assertRaises(server.Problem,self.request,qty=bad)
        self.assertRaises(server.Problem,self.call,'person','sizes',sizes={'role':'ADMIN'})
    def test_admin_user_catalog_and_unit_management(self):
        self.call('admin','units',province_id=6,name='KBRN Birimi')
        self.call('admin','catalog',name='KBRN Filtre',category='KBRN',unit='Adet',minimum=5,active=1,supply_type='SPECIAL',annual_limit=1,size_key='Standart')
        self.call('admin','users',username='new-person',full_name='Yeni Personel',role='PERSONNEL',province_id=6,unit_id=None,registry='NEW-1',title='',specialty='KBRN',start_date='2026-01-01',active=1,password=PASSWORD)
        self.assertRaises(server.Problem,self.call,'person','units',province_id=6,name='Yetkisiz birim')

    def test_transfer_does_not_reset_annual_entitlement(self):
        self.request(item=self.summer,qty=1)
        self.call('admin','users',**self.user_data('person',province_id=34))
        self.assertRaises(server.Problem,self.request,item=self.summer,qty=1)
    def test_return_does_not_reset_annual_entitlement(self):
        self.stock(6,item=self.summer);rid=self.request(item=self.summer,qty=1)
        self.action('material',rid,'issue',quantity=1)
        aid=self.store.bootstrap(self.actors['person'])['assignments'][0]['id']
        self.call('material','assignment-action',id=aid,action='return',note='Yıpranmış malzeme iade')
        self.assertRaises(server.Problem,self.request,item=self.summer,qty=1)
    def test_maintenance_backup_and_session_invalidation(self):
        import subprocess,sys
        source=self.store.path;backup=Path(self.temp.name)/'backup.sqlite3'
        command=[sys.executable,str(server.ROOT/'manage.py'),'--db',source]
        token,_,_=self.store.login('person',PASSWORD,'test')
        for args in [['backup','--output',str(backup)],['check'],['invalidate-sessions']]:
            result=subprocess.run(command+args,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        self.assertRaises(server.Problem,self.store.session,token)
        with sqlite3.connect(str(backup)) as db:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        result=subprocess.run(command+['backup','--output',str(backup)],capture_output=True)
        self.assertNotEqual(result.returncode,0)

class HttpTests(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp();self.http=server.Server(('127.0.0.1',0),self.store,'http://test.local',False)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.http.shutdown();self.http.server_close();self.thread.join();super().tearDown()
    def http_request(self,path,method='GET',body=None,cookie=None,csrf=None,origin='http://test.local'):
        c=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=5)
        headers={'Origin':origin}
        if cookie:headers['Cookie']=cookie
        if csrf:headers['X-CSRF-Token']=csrf
        if body is not None:headers['Content-Type']='application/json';body=json.dumps(body)
        c.request(method,path,body,headers);r=c.getresponse();result=(r.status,dict(r.getheaders()),r.read());c.close();return result
    def test_http_csrf_origin_and_cookie(self):
        status,headers,body=self.http_request('/api/login','POST',{'username':'person','password':PASSWORD});self.assertEqual(status,200)
        cookie=headers['Set-Cookie'].split(';')[0];csrf=json.loads(body)['csrf'];self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertEqual(self.http_request('/api/sizes','POST',{'sizes':{'Üst':'M'}},cookie)[0],403)
        self.assertEqual(self.http_request('/api/sizes','POST',{'sizes':{'Üst':'M'}},cookie,csrf,'https://evil.local')[0],403)
        self.assertEqual(self.http_request('/api/sizes','POST',{'sizes':{'Üst':'M'}},cookie,csrf)[0],200)
        self.assertEqual(self.http_request('/api/bootstrap')[0],401)
    def test_http_static_path_and_csv_scope(self):
        status,headers,body=self.http_request('/');self.assertEqual(status,200);self.assertIn('Content-Security-Policy',headers);self.assertIn(b'<html',body)
        self.assertEqual(self.http_request('/server.py')[0],401)
        self.request('person');self.request('person2')
        _,headers,body=self.http_request('/api/login','POST',{'username':'person','password':PASSWORD});cookie=headers['Set-Cookie'].split(';')[0]
        status,_,body=self.http_request('/api/report.csv?requests',cookie=cookie);self.assertEqual(status,200);self.assertNotIn('person2',body.decode());self.assertIn('person',body.decode())
        self.assertEqual(self.http_request('/schema.sql',cookie=cookie)[0],404)
    def test_http_csv_formula_escape_and_logout(self):
        aid=self.assignment();self.call('person','incidents',assignment_id=aid,type='WORN',description='=DANGEROUS-FORMULA()')
        _,headers,body=self.http_request('/api/login','POST',{'username':'person','password':PASSWORD});cookie=headers['Set-Cookie'].split(';')[0];csrf=json.loads(body)['csrf']
        _,_,body=self.http_request('/api/report.csv?incidents',cookie=cookie);self.assertIn("'=DANGEROUS",body.decode())
        self.assertEqual(self.http_request('/api/logout','POST',{},cookie,csrf)[0],200);self.assertEqual(self.http_request('/api/bootstrap',cookie=cookie)[0],401)
if __name__=='__main__':unittest.main()
