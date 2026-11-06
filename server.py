"""AFAD clothing/inventory application. Python 3.12+, standard library only."""
from __future__ import annotations
import argparse, csv, getpass, hashlib, hmac, io, json, logging, os, re, secrets, sqlite3, sys, time
from contextlib import contextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
ROLES = ('PERSONNEL', 'MATERIAL', 'DIRECTOR', 'HQ', 'ADMIN')
CITIES = 'Adana,Adıyaman,Afyonkarahisar,Ağrı,Amasya,Ankara,Antalya,Artvin,Aydın,Balıkesir,Bilecik,Bingöl,Bitlis,Bolu,Burdur,Bursa,Çanakkale,Çankırı,Çorum,Denizli,Diyarbakır,Edirne,Elazığ,Erzincan,Erzurum,Eskişehir,Gaziantep,Giresun,Gümüşhane,Hakkari,Hatay,Isparta,Mersin,İstanbul,İzmir,Kars,Kastamonu,Kayseri,Kırklareli,Kırşehir,Kocaeli,Konya,Kütahya,Malatya,Manisa,Kahramanmaraş,Mardin,Muğla,Muş,Nevşehir,Niğde,Ordu,Rize,Sakarya,Samsun,Siirt,Sinop,Sivas,Tekirdağ,Tokat,Trabzon,Tunceli,Şanlıurfa,Uşak,Van,Yozgat,Zonguldak,Aksaray,Bayburt,Karaman,Kırıkkale,Batman,Şırnak,Bartın,Ardahan,Iğdır,Yalova,Karabük,Kilis,Osmaniye,Düzce'.split(',')

def current_year(): return datetime.now(ZoneInfo('Europe/Istanbul')).year

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
class Problem(Exception):
    def __init__(self, message, status=400): self.message, self.status = message, status

def text(data, key, minimum=1, maximum=300):
    value = data.get(key, '')
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise Problem(f'{key}: {minimum}–{maximum} karakter gerekli.')
    return value.strip()

def integer(data, key, minimum=1, maximum=1000000):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise Problem(f'{key}: {minimum}–{maximum} aralığında tam sayı gerekli.')
    return value

def hash_password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise Problem('Parola 12–256 karakter olmalıdır.')
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return salt + ':' + key.hex()

def verify_password(password, encoded):
    try:
        salt, expected = encoded.split(':')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, AttributeError, UnicodeError): return False

def public_user(row):
    result = dict(row)
    result.pop('password_hash', None)
    result['sizes'] = json.loads(result['sizes'])
    return result

class Store:
    def __init__(self, path): self.path = str(path)
    @contextmanager
    def db(self, write=False):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=15000')
        try:
            if write: db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally: db.close()
    def initialize(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript((ROOT / 'schema.sql').read_text())
            db.executemany('INSERT OR IGNORE INTO provinces(id,name) VALUES(?,?)', enumerate(CITIES, 1))
            db.executemany('INSERT OR IGNORE INTO units(province_id,name) VALUES(?,?)', [(i, 'Arama Kurtarma Birlik Müdürlüğü') for i in range(1,82)])
            initial = [
                ('Yazlık Görev Üstü','Kıyafet',50,'SUMMER','Üst'),
                ('Yazlık Görev Pantolonu','Kıyafet',50,'SUMMER','Alt'),
                ('Yazlık Görev Ayakkabısı','Ayakkabı',40,'SUMMER','Ayakkabı'),
                ('Kışlık Görev Montu','Kıyafet',50,'WINTER','Mont'),
                ('Kışlık Görev Üstü','Kıyafet',50,'WINTER','Üst'),
                ('Kışlık Görev Pantolonu','Kıyafet',50,'WINTER','Alt'),
                ('Kışlık Görev Botu','Ayakkabı',40,'WINTER','Ayakkabı'),
                ('Koruyucu Kask','KKD',60,'SPECIAL','Standart'),
                ('İş Eldiveni','KKD',100,'SPECIAL','Eldiven'),
                ('Kafa Lambası','Operasyonel Ekipman',30,'SPECIAL','Standart'),
                ('KBRN Koruyucu Tulum','KBRN',10,'SPECIAL','Üst'),
                ('KBRN Tam Yüz Maskesi','KBRN',10,'SPECIAL','Standart'),
                ('Dağcı Emniyet Kemeri','Dağcılık',10,'SPECIAL','Alt'),
                ('Dağcı Kaskı','Dağcılık',10,'SPECIAL','Standart'),
                ('Tırmanış İpi','Dağcılık',10,'SPECIAL','Standart')]
            for name,category,minimum,supply,size_key in initial:
                db.execute('INSERT OR IGNORE INTO catalog(name,category,minimum,supply_type,size_key) VALUES(?,?,?,?,?)',(name,category,minimum,supply,size_key))
        try: os.chmod(self.path, 0o600)
        except OSError: pass
    @staticmethod
    def audit(db, actor, action, entity, entity_id=None, detail='', province=None):
        db.execute('INSERT INTO audit(actor_id,province_id,action,entity,entity_id,detail,created_at) VALUES(?,?,?,?,?,?,?)', (actor['id'] if actor else None, province if province is not None else (actor['province_id'] if actor else None), action,entity,entity_id,detail,now()))
    @staticmethod
    def require(actor, *roles):
        if actor['role'] not in roles: raise Problem('Bu işlem için yetkiniz yok.',403)
    @staticmethod
    def scope(actor, province):
        if actor['role'] not in ('HQ','ADMIN') and actor['province_id'] != province:
            raise Problem('Başka bir ilin kayıtlarına erişemezsiniz.',403)
    @staticmethod
    def get(db, table, ident):
        # Table names are internal literals, never request input.
        row = db.execute(f'SELECT * FROM {table} WHERE id=?',(ident,)).fetchone()
        if row is None: raise Problem('Kayıt bulunamadı.',404)
        return row
    @staticmethod
    def move(db, location, item, size, delta, kind, ref, actor):
        db.execute('INSERT OR IGNORE INTO stock(location,item_id,size,quantity) VALUES(?,?,?,0)',(location,item,size))
        result = db.execute('UPDATE stock SET quantity=quantity+? WHERE location=? AND item_id=? AND size=? AND quantity+?>=0',(delta,location,item,size,delta))
        if result.rowcount != 1: raise Problem('Bu beden için yeterli stok yok.',409)
        db.execute('INSERT INTO movements(location,item_id,size,delta,kind,reference,actor_id,created_at) VALUES(?,?,?,?,?,?,?,?)',(location,item,size,delta,kind,str(ref),actor['id'] if actor else None,now()))
    def login(self, username, password, client):
        if not isinstance(username,str) or not isinstance(password,str) or len(username)>100 or len(password)>256:
            raise Problem('Geçersiz giriş bilgileri.',401)
        key = hashlib.sha256((client+'|'+username.lower()).encode()).hexdigest()
        with self.db(True) as db:
            stamp = int(time.time())
            db.execute('DELETE FROM login_attempts WHERE first_at<?',(stamp-900,))
            attempt = db.execute('SELECT * FROM login_attempts WHERE attempt_key=?',(key,)).fetchone()
            if attempt and attempt['failures'] >= 10: raise Problem('Çok fazla deneme. 15 dakika sonra tekrar deneyin.',429)
            actor = db.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE AND active=1',(username,)).fetchone()
            valid = verify_password(password,actor['password_hash'] if actor else '00'*16+':'+'00'*64)
            if not actor or not valid:
                db.execute('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(attempt_key) DO UPDATE SET failures=failures+1',(key,stamp))
                failure = True
            else:
                failure = False
                db.execute('DELETE FROM login_attempts WHERE attempt_key=?',(key,))
                db.execute('DELETE FROM sessions WHERE expires_at<?',(stamp,))
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),actor['id'],csrf,stamp+28800))
                self.audit(db,actor,'LOGIN','user',actor['id'])
        if failure: raise Problem('Kullanıcı adı veya parola hatalı.',401)
        return token, csrf, public_user(actor)
    def session(self, token):
        with self.db() as db:
            row = db.execute('SELECT user_id,csrf FROM sessions WHERE token_hash=? AND expires_at>?',(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
            if not row: raise Problem('Oturum açmanız gerekiyor.',401)
            actor = db.execute('SELECT * FROM users WHERE id=? AND active=1',(row['user_id'],)).fetchone()
            if not actor: raise Problem('Hesap etkin değil.',401)
            return actor, row['csrf']
    def logout(self, token):
        with self.db(True) as db: db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
    def bootstrap(self, actor, report=False):
        with self.db() as db:
            role, pid = actor['role'], actor['province_id']
            global_access = role in ('HQ','ADMIN')
            clauses, args = ('1=1',[]) if global_access else ('r.user_id=?',[actor['id']]) if role=='PERSONNEL' else ('r.province_id=?',[pid])
            requests = [dict(r) for r in db.execute(f'''SELECT r.*,u.full_name,p.name province,c.name item,c.category FROM requests r JOIN users u ON u.id=r.user_id JOIN provinces p ON p.id=r.province_id JOIN catalog c ON c.id=r.item_id WHERE {clauses} ORDER BY r.id DESC''', args)]
            uwhere, uargs = ('1=1',[]) if global_access else ('u.id=?',[actor['id']]) if role=='PERSONNEL' else ('u.province_id=?',[pid])
            users = [public_user(u) for u in db.execute(f'SELECT u.* FROM users u WHERE {uwhere} ORDER BY u.full_name',uargs)]
            assignments = [dict(r) for r in db.execute(f'''SELECT a.*,u.full_name,u.province_id,p.name province,c.name item FROM assignments a JOIN users u ON u.id=a.user_id JOIN provinces p ON p.id=u.province_id JOIN catalog c ON c.id=a.item_id WHERE {uwhere} ORDER BY a.id DESC''',uargs)]
            stock = [] if role=='PERSONNEL' else [dict(r) for r in db.execute('''SELECT s.*,c.name item,c.minimum,c.category,c.unit,COALESCE(p.name,'Merkez Depo') location_name FROM stock s JOIN catalog c ON c.id=s.item_id LEFT JOIN provinces p ON p.id=s.location WHERE (?=1 OR s.location=?) ORDER BY s.location,c.name,s.size''',(int(global_access),pid))]
            audits = [dict(r) for r in db.execute('''SELECT a.*,COALESCE(u.full_name,'Sistem') actor FROM audit a LEFT JOIN users u ON u.id=a.actor_id WHERE (?=1 OR a.province_id=?) AND (?!= 'PERSONNEL' OR a.actor_id=?) ORDER BY a.id DESC''' + ('' if report else ' LIMIT 200'),(int(global_access),pid,role,actor['id']))]
            movements = [] if role=='PERSONNEL' else [dict(r) for r in db.execute('''SELECT m.*,c.name item,COALESCE(p.name,'Merkez Depo') location_name FROM movements m JOIN catalog c ON c.id=m.item_id LEFT JOIN provinces p ON p.id=m.location WHERE (?=1 OR m.location=?) ORDER BY m.id DESC''' + ('' if report else ' LIMIT 200'),(int(global_access),pid))]
            incidents = [dict(r) for r in db.execute(f'''SELECT i.*,u.full_name,c.name item FROM incidents i JOIN assignments a ON a.id=i.assignment_id JOIN users u ON u.id=a.user_id JOIN catalog c ON c.id=a.item_id WHERE {uwhere} ORDER BY i.id DESC''',uargs)]
            return dict(entitlement_year=current_year(),entitlements=self.entitlements(db,users),workflow={r['key']:bool(r['value']) for r in db.execute('SELECT * FROM workflow')},user=public_user(actor),provinces=[dict(r) for r in db.execute('SELECT * FROM provinces')],units=[dict(r) for r in db.execute('SELECT * FROM units')],catalog=[dict(r) for r in db.execute('SELECT * FROM catalog ORDER BY name')],users=users,requests=requests,assignments=assignments,stock=stock,audit=audits,movements=movements,incidents=incidents)
    @staticmethod
    def annual_used(db,uid,item,year):
        return db.execute("""SELECT COALESCE(SUM(CASE WHEN status IN ('FULFILLED','PARTIAL_COMPLETED') THEN issued ELSE quantity END),0) FROM requests WHERE user_id=? AND item_id=? AND entitlement_year=? AND request_kind='ANNUAL' AND status!='REJECTED'""",(uid,item,year)).fetchone()[0]
    def entitlements(self,db,users):
        result=[]
        items=db.execute("SELECT * FROM catalog WHERE active=1 AND supply_type IN ('SUMMER','WINTER')").fetchall()
        for user in users:
            if user['province_id'] is None: continue
            for item in items:
                used=self.annual_used(db,user['id'],item['id'],current_year())
                result.append(dict(user_id=user['id'],item_id=item['id'],season=item['supply_type'],year=current_year(),limit=item['annual_limit'],used_or_pending=used,remaining=max(0,item['annual_limit']-used)))
        return result
    def create_request(self,db,actor,user,data):
        item=self.get(db,'catalog',integer(data,'item_id'))
        if not item['active']: raise Problem('Malzeme kullanıma kapalı.')
        priority=text(data,'priority')
        if priority not in ('NORMAL','URGENT'): raise Problem('Geçersiz öncelik.')
        qty=integer(data,'quantity',1,10000);size=text(data,'size',1,30)
        reason=text(data,'reason',5,2000);year=current_year()
        kind=data.get('request_kind','AUTO')
        if kind=='AUTO': kind='SPECIAL' if item['supply_type']=='SPECIAL' else 'ANNUAL'
        if kind not in ('ANNUAL','SPECIAL','REPLACEMENT'): raise Problem('Geçersiz talep türü.')
        replacement=None
        if kind=='ANNUAL':
            if item['supply_type']=='SPECIAL': raise Problem('Bu malzeme ihtiyaç halinde talep edilir.')
            used=self.annual_used(db,user['id'],item['id'],year)
            if used+qty>item['annual_limit']: raise Problem(f'{year} yıllık hakkı aşılıyor. Kalan: {max(0,item["annual_limit"]-used)}. Erken yıpranma için zimmetten yenileme talebi açın.',409)
        elif kind=='SPECIAL':
            if item['supply_type']!='SPECIAL': raise Problem('Yıllık kıyafetler normal hak ediş veya zimmete bağlı yenileme olarak talep edilir.')
        else:
            replacement=self.get(db,'assignments',integer(data,'replacement_assignment_id'))
            if replacement['user_id']!=user['id'] or replacement['item_id']!=item['id']:
                raise Problem('Yenileme zimmeti personel ve malzemeyle eşleşmiyor.',403)
            if replacement['status']!='CONFIRMED': raise Problem('Yenileme için teslim onaylı ve iade edilmemiş zimmet seçin.',409)
            if qty>replacement['quantity']: raise Problem('Yenileme miktarı mevcut zimmeti aşamaz.')
            existing=db.execute("SELECT 1 FROM requests WHERE replacement_assignment_id=? AND status NOT IN ('FULFILLED','PARTIAL_COMPLETED','REJECTED')",(replacement['id'],)).fetchone()
            if existing: raise Problem('Bu zimmete bağlı açık yenileme talebi zaten var.',409)
        rid=db.execute("""INSERT INTO requests(user_id,province_id,item_id,size,quantity,request_kind,entitlement_year,replacement_assignment_id,priority,reason,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,'SUBMITTED',?,?)""",(user['id'],user['province_id'],item['id'],size,qty,kind,year,replacement['id'] if replacement else None,priority,reason,now(),now())).lastrowid
        if replacement:
            iid=db.execute("INSERT INTO incidents(assignment_id,user_id,type,description,created_at) VALUES(?,?,'WORN',?,?)",(replacement['id'],user['id'],reason,now())).lastrowid
            self.audit(db,actor,'CREATE_INCIDENT','incident',iid,f'Erken yıpranma; talep #{rid}',province=user['province_id'])
        self.audit(db,actor,'CREATE_REQUEST','request',rid,f'{kind}; hak ediş yılı {year}',province=user['province_id'])
        return rid
    def mutate(self, actor, route, data):
        with self.db(True) as db:
            # Reload inside the write lock: deactivation/role changes apply immediately.
            actor = self.get(db,'users',actor['id'])
            if not actor['active']: raise Problem('Hesap etkin değil.',403)
            if route=='/api/sizes':
                sizes = data.get('sizes')
                if not isinstance(sizes,dict) or set(sizes)-{'Üst','Alt','Mont','Ayakkabı','Eldiven'}: raise Problem('Geçersiz beden alanları.')
                clean = {k:text(sizes,k,1,15) for k in sizes}
                db.execute('UPDATE users SET sizes=? WHERE id=?',(json.dumps(clean,ensure_ascii=False),actor['id']))
                self.audit(db,actor,'UPDATE_SIZES','user',actor['id'])
            elif route=='/api/requests':
                uid = data.get('user_id',actor['id'])
                if type(uid) is not int: raise Problem('Geçersiz personel.')
                user = self.get(db,'users',uid)
                if actor['role']=='PERSONNEL' and uid!=actor['id']: raise Problem('Yalnız kendi adınıza talep oluşturabilirsiniz.',403)
                if actor['role']!='PERSONNEL': self.require(actor,'MATERIAL','DIRECTOR','HQ','ADMIN')
                self.scope(actor,user['province_id'])
                if not user['active'] or user['province_id'] is None: raise Problem('Etkin il personeli seçin.')
                self.create_request(db,actor,user,data)
            elif route=='/api/annual-kit':
                uid=data.get('user_id',actor['id'])
                if type(uid) is not int: raise Problem('Geçersiz personel.')
                user=self.get(db,'users',uid)
                if actor['role']=='PERSONNEL' and uid!=actor['id']: raise Problem('Yalnız kendi hakkınızı talep edebilirsiniz.',403)
                self.scope(actor,user['province_id'])
                if not user['active'] or user['province_id'] is None: raise Problem('Etkin il personeli seçin.')
                season=text(data,'season')
                if season not in ('SUMMER','WINTER'): raise Problem('Yazlık veya kışlık takım seçin.')
                items=db.execute('SELECT * FROM catalog WHERE active=1 AND supply_type=?',(season,)).fetchall()
                if not items: raise Problem('Bu mevsim için aktif takım tanımı yok.')
                sizes=json.loads(user['sizes']);created=0
                for item in items:
                    remaining=item['annual_limit']-self.annual_used(db,uid,item['id'],current_year())
                    if remaining<=0: continue
                    size='Standart' if item['size_key']=='Standart' else sizes.get(item['size_key'],'')
                    if not size: raise Problem(f'{item["size_key"]} beden bilgisi eksik. Personel önce bedenlerini kaydetmeli.')
                    self.create_request(db,actor,user,dict(item_id=item['id'],size=size,quantity=remaining,priority='NORMAL',reason=f'{current_year()} yılı '+('yazlık' if season=='SUMMER' else 'kışlık')+' takım hak edişi; ayakkabı dahil.',request_kind='ANNUAL'))
                    created+=1
                if not created: raise Problem('Bu yılın takım hakkı için talepler zaten oluşturulmuş veya hak kullanılmış.',409)
            elif route=='/api/request-action': self.request_action(db,actor,data)
            elif route=='/api/batches':
                self.require(actor,'DIRECTOR')
                ids=data.get('request_ids')
                if not isinstance(ids,list) or not ids or len(ids)>200 or any(type(x) is not int for x in ids) or len(set(ids))!=len(ids): raise Problem('1–200 farklı talep seçin.')
                records=[self.get(db,'requests',i) for i in ids]
                for r in records:
                    self.scope(actor,r['province_id'])
                    if r['status']!='PROVINCE_REVIEW': raise Problem('Yalnız il onayındaki talepler toplu iletilebilir.',409)
                bid=db.execute('INSERT INTO batches(province_id,created_by,note,created_at) VALUES(?,?,?,?)',(actor['province_id'],actor['id'],text(data,'note',5,1000),now())).lastrowid
                for r in records:
                    db.execute("UPDATE requests SET status='HQ_REVIEW',batch_id=?,updated_at=? WHERE id=?",(bid,now(),r['id']))
                    self.audit(db,actor,'BATCH_FORWARD','request',r['id'],f'Toplu talep #{bid}')
            elif route=='/api/stock':
                self.require(actor,'MATERIAL','HQ','ADMIN')
                loc=integer(data,'location',0,81)
                if actor['role']=='MATERIAL' and loc!=actor['province_id']: raise Problem('Yalnız kendi il deponuzu yönetebilirsiniz.',403)
                if actor['role']=='HQ' and loc!=0: raise Problem('Başkanlık yalnız merkez depoya giriş yapabilir.',403)
                item=self.get(db,'catalog',integer(data,'item_id'))
                size=text(data,'size',1,30);delta=integer(data,'delta',-100000,100000)
                if delta==0: raise Problem('Miktar sıfır olamaz.')
                note=text(data,'note',5,1000)
                self.move(db,loc,item['id'],size,delta,'ADJUSTMENT',note,actor)
                self.audit(db,actor,'STOCK_ADJUSTMENT','stock',item['id'],f'{size}: {delta}; {note}',province=loc)
            elif route=='/api/assignment-action':
                a=self.get(db,'assignments',integer(data,'id')); action=text(data,'action')
                user=self.get(db,'users',a['user_id'])
                if action=='confirm':
                    if actor['id']!=a['user_id']: raise Problem('Teslimi yalnız ilgili personel onaylayabilir.',403)
                    if a['status']!='PENDING': raise Problem('Bu teslim zaten işlendi.',409)
                    db.execute("UPDATE assignments SET status='CONFIRMED',confirmed_at=? WHERE id=?",(now(),a['id']))
                elif action=='return':
                    self.require(actor,'MATERIAL');self.scope(actor,user['province_id'])
                    if a['status']=='RETURNED': raise Problem('Malzeme zaten iade edilmiş.',409)
                    note=text(data,'note',5,1000)
                    self.move(db,actor['province_id'],a['item_id'],a['size'],a['quantity'],'RETURN',a['id'],actor)
                    db.execute("UPDATE assignments SET status='RETURNED',returned_at=? WHERE id=?",(now(),a['id']))
                    self.audit(db,actor,'RETURN_NOTE','assignment',a['id'],note)
                else: raise Problem('Geçersiz zimmet işlemi.')
                self.audit(db,actor,'ASSIGNMENT_'+action.upper(),'assignment',a['id'],province=user['province_id'])
            elif route=='/api/incidents':
                a=self.get(db,'assignments',integer(data,'assignment_id'))
                if a['user_id']!=actor['id']: raise Problem('Yalnız kendi zimmetiniz için bildirim yapabilirsiniz.',403)
                if a['status']=='RETURNED': raise Problem('İade edilen malzemeye bildirim yapılamaz.',409)
                kind=text(data,'type')
                if kind not in ('DAMAGED','WORN','LOST'): raise Problem('Geçersiz bildirim türü.')
                iid=db.execute('INSERT INTO incidents(assignment_id,user_id,type,description,created_at) VALUES(?,?,?,?,?)',(a['id'],actor['id'],kind,text(data,'description',5,2000),now())).lastrowid
                self.audit(db,actor,'CREATE_INCIDENT','incident',iid,kind)
            elif route=='/api/users': self.user_edit(db,actor,data)
            elif route=='/api/catalog':
                self.require(actor,'ADMIN')
                values=(text(data,'name',2,150),text(data,'category',2,80),text(data,'unit',1,30),integer(data,'minimum',0,100000),integer(data,'active',0,1),text(data,'supply_type'),integer(data,'annual_limit',1,100),text(data,'size_key'))
                if values[5] not in ('SUMMER','WINTER','SPECIAL') or values[7] not in ('Üst','Alt','Mont','Ayakkabı','Eldiven','Standart'): raise Problem('Geçersiz tedarik türü / beden alanı.')
                if data.get('id'):
                    ident=integer(data,'id');self.get(db,'catalog',ident)
                    db.execute('UPDATE catalog SET name=?,category=?,unit=?,minimum=?,active=?,supply_type=?,annual_limit=?,size_key=? WHERE id=?',(*values,ident))
                else: ident=db.execute('INSERT INTO catalog(name,category,unit,minimum,active,supply_type,annual_limit,size_key) VALUES(?,?,?,?,?,?,?,?)',values).lastrowid
                self.audit(db,actor,'UPSERT_CATALOG','catalog',ident)
            elif route=='/api/units':
                self.require(actor,'ADMIN');pid=integer(data,'province_id',1,81)
                ident=db.execute('INSERT INTO units(province_id,name) VALUES(?,?)',(pid,text(data,'name',2,150))).lastrowid
                self.audit(db,actor,'CREATE_UNIT','unit',ident,province=pid)
            elif route=='/api/workflow':
                self.require(actor,'ADMIN')
                if set(data)!={'allow_local_issue','allow_partial_allocation','require_serial'} or any(type(v) is not bool for v in data.values()):
                    raise Problem('Geçersiz iş akışı ayarları.')
                for key,value in data.items(): db.execute('UPDATE workflow SET value=? WHERE key=?',(int(value),key))
                self.audit(db,actor,'UPDATE_WORKFLOW','workflow',detail=json.dumps(data))
            elif route=='/api/password':
                if not isinstance(data.get('current'),str) or len(data['current'])>256 or not verify_password(data['current'],actor['password_hash']): raise Problem('Mevcut parola hatalı.',403)
                db.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(data.get('password')),actor['id']))
                db.execute('DELETE FROM sessions WHERE user_id=?',(actor['id'],))
                self.audit(db,actor,'CHANGE_PASSWORD','user',actor['id'])
                return {'ok':True,'reauthenticate':True}
            else: raise Problem('İşlem bulunamadı.',404)
        return {'ok':True}
    def request_action(self,db,actor,data):
        r=self.get(db,'requests',integer(data,'id'));action=text(data,'action')
        self.scope(actor,r['province_id'])
        status=r['status'];new_status=status;detail=''
        rules={w['key']:bool(w['value']) for w in db.execute('SELECT * FROM workflow')}
        if action=='review':
            self.require(actor,'MATERIAL')
            if status!='SUBMITTED': raise Problem('Talep il incelemesinde değil.',409)
            new_status='PROVINCE_REVIEW'
        elif action=='forward':
            self.require(actor,'DIRECTOR')
            if status!='PROVINCE_REVIEW': raise Problem('Talep il onayında değil.',409)
            new_status='HQ_REVIEW'
        elif action=='reject':
            self.require(actor,'DIRECTOR','HQ')
            expected='HQ_REVIEW' if actor['role']=='HQ' else 'PROVINCE_REVIEW'
            if status!=expected: raise Problem('Bu aşamada ret verilemez.',409)
            detail=text(data,'note',5,1000)
            db.execute('UPDATE requests SET rejection_reason=? WHERE id=?',(detail,r['id']))
            new_status='REJECTED'
        elif action=='approve':
            self.require(actor,'HQ')
            if status!='HQ_REVIEW': raise Problem('Talep Başkanlık incelemesinde değil.',409)
            qty=integer(data,'quantity',1,r['quantity'])
            if qty<r['quantity'] and not rules['allow_partial_allocation']: raise Problem('Kısmi tahsis yönetici tarafından kapatıldı.',409)
            self.move(db,0,r['item_id'],r['size'],-qty,'RESERVE',r['id'],actor)
            db.execute('UPDATE requests SET approved=? WHERE id=?',(qty,r['id']))
            detail=f'{qty}/{r["quantity"]} adet tahsis edildi'
            new_status='APPROVED'
        elif action=='cancel-allocation':
            self.require(actor,'HQ')
            if status!='APPROVED': raise Problem('Yalnız sevk edilmemiş tahsis iptal edilebilir.',409)
            detail=text(data,'note',5,1000)
            self.move(db,0,r['item_id'],r['size'],r['approved'],'RESERVATION_RELEASE',r['id'],actor)
            db.execute('UPDATE requests SET approved=0,rejection_reason=? WHERE id=?',(detail,r['id']))
            new_status='REJECTED'
        elif action=='close':
            self.require(actor,'MATERIAL')
            if status not in ('SUBMITTED','RECEIVED'): raise Problem('Bu aşamada talep kapatılamaz.',409)
            detail=text(data,'note',5,1000)
            # Received material stays in province stock; no physical shipment is reversed.
            db.execute('UPDATE requests SET rejection_reason=? WHERE id=?',(detail,r['id']))
            new_status='REJECTED'
        elif action=='ship':
            self.require(actor,'HQ')
            if status!='APPROVED': raise Problem('Talep tahsis edilmiş değil.',409)
            detail=text(data,'shipment_ref',3,100)
            db.execute('UPDATE requests SET shipment_ref=? WHERE id=?',(detail,r['id']))
            new_status='SHIPPED'
        elif action=='receive':
            self.require(actor,'MATERIAL')
            if status!='SHIPPED': raise Problem('Talep sevkiyatta değil.',409)
            self.move(db,r['province_id'],r['item_id'],r['size'],r['approved'],'SHIPMENT_RECEIPT',r['id'],actor)
            new_status='RECEIVED'
        elif action=='issue':
            self.require(actor,'MATERIAL')
            if status not in ('SUBMITTED','RECEIVED'): raise Problem('Talep teslim için uygun aşamada değil.',409)
            if status=='SUBMITTED' and not rules['allow_local_issue']: raise Problem('Doğrudan il stoktan teslim kapalı.',409)
            # A transferred employee's historical request stays with its originating province.
            user=self.get(db,'users',r['user_id'])
            if user['province_id']!=r['province_id'] or not user['active']:
                raise Problem('Personelin ili/durumu değişmiş. Güncel ilinde yeni talep oluşturulmalıdır.',409)
            qty=integer(data,'quantity',1,r['quantity'] if status=='SUBMITTED' else r['approved'])
            self.move(db,r['province_id'],r['item_id'],r['size'],-qty,'ISSUE',r['id'],actor)
            serial=text(data,'serial',1 if rules['require_serial'] else 0,100)
            db.execute("INSERT INTO assignments(user_id,request_id,item_id,size,quantity,serial,issue_location,status,issued_at) VALUES(?,?,?,?,?,?,?,'PENDING',?)",(r['user_id'],r['id'],r['item_id'],r['size'],qty,serial,r['province_id'],now()))
            db.execute('UPDATE requests SET issued=? WHERE id=?',(qty,r['id']))
            new_status='FULFILLED' if qty==r['quantity'] else 'PARTIAL_COMPLETED'
            detail=f'{qty} adet teslim; eksik {r["quantity"]-qty} adet için yeni talep açılabilir'
        else: raise Problem('Geçersiz talep işlemi.')
        db.execute('UPDATE requests SET status=?,updated_at=? WHERE id=?',(new_status,now(),r['id']))
        self.audit(db,actor,'REQUEST_'+action.upper(),'request',r['id'],detail,province=r['province_id'])
    def user_edit(self,db,actor,data):
        self.require(actor,'ADMIN')
        role=text(data,'role')
        if role not in ROLES: raise Problem('Geçersiz rol.')
        pid=data.get('province_id')
        if pid is not None:
            pid=integer(data,'province_id',1,81);self.get(db,'provinces',pid)
        if role not in ('HQ','ADMIN') and pid is None: raise Problem('İl zorunludur.')
        unit=data.get('unit_id')
        if unit is not None:
            unit=integer(data,'unit_id')
            if self.get(db,'units',unit)['province_id']!=pid: raise Problem('Birim seçilen ile ait değil.')
        username=text(data,'username',3,80)
        if not re.fullmatch(r'[A-Za-z0-9_.@-]+',username): raise Problem('Kullanıcı adı yalnız Latin harfleri, rakam ve _.@- içerebilir.')
        start=text(data,'start_date',0,10)
        if start:
            try: datetime.strptime(start,'%Y-%m-%d')
            except ValueError: raise Problem('İşe başlama tarihi YYYY-AA-GG biçiminde olmalı.')
        active=integer(data,'active',0,1)
        values=(username,text(data,'full_name',2,120),role,pid,unit,text(data,'registry',1,80),text(data,'title',0,120),text(data,'specialty',0,150),start,active)
        if data.get('id'):
            uid=integer(data,'id');old=self.get(db,'users',uid)
            # Maintain one active administrator; self role/deactivation is deliberately blocked.
            if uid==actor['id'] and (not active or role!='ADMIN'): raise Problem('Kendi yönetici yetkinizi kaldıramazsınız.')
            db.execute('UPDATE users SET username=?,full_name=?,role=?,province_id=?,unit_id=?,registry=?,title=?,specialty=?,start_date=?,active=? WHERE id=?',(*values,uid))
            if data.get('password'): db.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(data['password']),uid))
            db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            if old['province_id']!=pid:
                self.audit(db,actor,'TRANSFER','user',uid,f'{old["province_id"]} → {pid}; zimmet ve geçmiş korundu',province=pid)
        else:
            uid=db.execute('INSERT INTO users(username,full_name,role,province_id,unit_id,registry,title,specialty,start_date,active,password_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(*values,hash_password(data.get('password')),now())).lastrowid
        self.audit(db,actor,'UPSERT_USER','user',uid,role,province=pid)

class Handler(BaseHTTPRequestHandler):
    server_version='AFAD/1.0'
    def log_message(self, fmt, *args):
        # Do not log request bodies, cookies, credentials or query strings.
        logging.info('%s %s %s',self.command,urlsplit(self.path).path,args[1] if len(args)>1 else '')
    def send(self,status,body,content_type='application/json; charset=utf-8',cookie=None):
        if not isinstance(body,bytes): body=json.dumps(body,ensure_ascii=False).encode()
        self.send_response(status)
        for k,v in {'Content-Type':content_type,'Content-Length':str(len(body)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'same-origin','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items(): self.send_header(k,v)
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(body)
    def cookie(self,token,delete=False):
        return f'afad_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if delete else 28800}'+('; Secure' if self.server.secure else '')
    def token(self):
        try:
            c=SimpleCookie();c.load(self.headers.get('Cookie',''));return c['afad_session'].value if 'afad_session' in c else ''
        except CookieError: return ''
    def body(self):
        if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise Problem('JSON gövdesi gerekli.',415)
        try: length=int(self.headers.get('Content-Length','0'))
        except ValueError: raise Problem('Geçersiz gövde uzunluğu.')
        if not 0<length<=65536: raise Problem('İstek gövdesi 1–65536 bayt olmalı.',413)
        try: data=json.loads(self.rfile.read(length))
        except (ValueError,UnicodeError): raise Problem('Geçersiz JSON.')
        if not isinstance(data,dict): raise Problem('JSON nesnesi gerekli.')
        return data
    def dispatch(self):
        path=urlsplit(self.path).path;store=self.server.store
        if self.command=='GET' and path in ('/','/app.js','/style.css'):
            f=ROOT/'static'/({'/':'index.html'}.get(path,path.lstrip('/')))
            types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}
            return self.send(200,f.read_bytes(),types[f.suffix])
        if self.command=='GET' and path=='/health': return self.send(200,{'ok':True})
        if self.command not in ('GET','POST'): raise Problem('Yöntem desteklenmiyor.',405)
        if self.command=='POST':
            # Login also requires same origin. Never trust arbitrary forwarded host values.
            origin=self.headers.get('Origin')
            if origin and origin!=self.server.origin: raise Problem('İstek kaynağı geçersiz.',403)
            data=self.body()
            if path=='/api/login':
                token,csrf,user=store.login(data.get('username'),data.get('password'),self.client_address[0])
                return self.send(200,{'user':user,'csrf':csrf},cookie=self.cookie(token))
        actor,csrf=store.session(self.token())
        if self.command=='GET':
            if path=='/api/bootstrap':
                result=store.bootstrap(actor);result['csrf']=csrf
                return self.send(200,result)
            if path=='/api/report.csv':
                data=store.bootstrap(actor,report=True);kind=urlsplit(self.path).query
                # Allow only named report choices, never arbitrary table/column selection.
                kind={'requests':'requests','stock':'stock','assignments':'assignments','movements':'movements','incidents':'incidents','users':'users','audit':'audit'}.get(kind,'requests')
                rows=data[kind]
                fields={'audit':['id','actor','province_id','action','entity','entity_id','detail','created_at'],'requests':['id','province','full_name','item','size','quantity','request_kind','entitlement_year','replacement_assignment_id','approved','issued','status','batch_id','shipment_ref'], 'stock':['location_name','item','size','quantity','minimum'], 'assignments':['id','full_name','province','item','size','quantity','status','issued_at','confirmed_at','returned_at'], 'movements':['id','location_name','item','size','delta','kind','reference','created_at'], 'incidents':['id','full_name','item','type','description','created_at'],'users':['id','full_name','registry','province_id','unit_id','title','specialty','start_date','active']}[kind]
                buf=io.StringIO();w=csv.writer(buf,delimiter=';');w.writerow(fields)
                for row in rows:
                    # Prevent spreadsheet formula injection in all string columns.
                    w.writerow([("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')) else v) for v in (row.get(f,'') for f in fields)])
                return self.send(200,('\ufeff'+buf.getvalue()).encode(),'text/csv; charset=utf-8')
            raise Problem('Sayfa bulunamadı.',404)
        if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),csrf): raise Problem('Oturum doğrulaması geçersiz. Sayfayı yenileyin.',403)
        if path=='/api/logout':
            store.logout(self.token());return self.send(200,{'ok':True},cookie=self.cookie('',True))
        result=store.mutate(actor,path,data)
        return self.send(200,result)
    def handle_request(self):
        try: self.dispatch()
        except Problem as e: self.send(e.status,{'error':e.message})
        except sqlite3.IntegrityError: self.send(409,{'error':'Kayıt mevcut veya ilişkili veri kuralına aykırı.'})
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception:
            logging.exception('Request failed')
            self.send(500,{'error':'Sunucu hatası. İşlem kaydedilmedi.'})
    do_GET=do_POST=do_PUT=do_DELETE=handle_request

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,store,origin,secure):
        super().__init__(address,Handler);self.store=store;self.origin=origin;self.secure=secure
    def get_request(self):
        sock,address=super().get_request();sock.settimeout(15);return sock,address

def create_admin(store):
    with store.db() as db:
        if db.execute("SELECT 1 FROM users WHERE role='ADMIN' AND active=1").fetchone(): raise Problem('Etkin yönetici zaten var. Yeni kullanıcıları yönetim ekranından ekleyin.')
    username=input('Yönetici kullanıcı adı: ').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.@-]{3,80}',username): raise Problem('Geçersiz kullanıcı adı.')
    password=getpass.getpass('Parola (en az 12 karakter): ')
    if password!=getpass.getpass('Parola tekrarı: '): raise Problem('Parolalar eşleşmiyor.')
    with store.db(True) as db:
        uid=db.execute("INSERT INTO users(username,password_hash,full_name,role,registry,created_at) VALUES(?,?,?,'ADMIN',?,?)",(username,hash_password(password),'Sistem Yöneticisi','ADMIN-'+secrets.token_hex(4),now())).lastrowid
        store.audit(db,None,'CREATE_INITIAL_ADMIN','user',uid)
    print('Yönetici oluşturuldu. Kullanıcıları Sistem Ayarları ekranından tanımlayabilirsiniz.')

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=os.environ.get('AFAD_DB',str(ROOT/'data'/'afad.sqlite3')))
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--origin',default=os.environ.get('AFAD_ORIGIN'))
    parser.add_argument('--init-admin',action='store_true')
    args=parser.parse_args();store=Store(args.db);store.initialize()
    if args.init_admin: create_admin(store);return
    origin=args.origin or f'http://127.0.0.1:{args.port}'
    parsed=urlsplit(origin)
    if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise Problem('--origin yalnız http(s) kök adresi olmalıdır.')
    origin=origin.rstrip('/')
    if args.host not in ('127.0.0.1','localhost','::1') and parsed.scheme!='https':
        raise Problem('Dış ağda çalıştırmak için --origin https://alan-adiniz gerekli; TLS ters vekili kullanın.')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    print(f'AFAD sunucusu {args.host}:{args.port} üzerinde. Origin: {origin}',flush=True)
    with Server((args.host,args.port),store,origin,parsed.scheme=='https') as server:
        try: server.serve_forever()
        except KeyboardInterrupt: pass

if __name__=='__main__':
    try: main()
    except Problem as error: sys.exit(error.message)
