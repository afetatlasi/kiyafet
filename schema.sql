PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS provinces(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS units(id INTEGER PRIMARY KEY, province_id INTEGER NOT NULL REFERENCES provinces(id), name TEXT NOT NULL, UNIQUE(province_id,name));
CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL,
 full_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('PERSONNEL','MATERIAL','DIRECTOR','HQ','ADMIN')),
 province_id INTEGER REFERENCES provinces(id), unit_id INTEGER REFERENCES units(id), registry TEXT NOT NULL UNIQUE,
 title TEXT NOT NULL DEFAULT '', specialty TEXT NOT NULL DEFAULT '', start_date TEXT NOT NULL DEFAULT '',
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), sizes TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL, CHECK(role IN ('HQ','ADMIN') OR province_id IS NOT NULL));
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts(attempt_key TEXT PRIMARY KEY, failures INTEGER NOT NULL, first_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS catalog(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, category TEXT NOT NULL, unit TEXT NOT NULL DEFAULT 'Adet', minimum INTEGER NOT NULL DEFAULT 10 CHECK(minimum>=0), active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), supply_type TEXT NOT NULL DEFAULT 'SPECIAL' CHECK(supply_type IN ('SUMMER','WINTER','SPECIAL')), annual_limit INTEGER NOT NULL DEFAULT 1 CHECK(annual_limit BETWEEN 1 AND 100), size_key TEXT NOT NULL DEFAULT 'Standart');
CREATE TABLE IF NOT EXISTS stock(location INTEGER NOT NULL CHECK(location BETWEEN 0 AND 81), item_id INTEGER NOT NULL REFERENCES catalog(id), size TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0), PRIMARY KEY(location,item_id,size));
CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY, province_id INTEGER NOT NULL REFERENCES provinces(id), created_by INTEGER NOT NULL REFERENCES users(id), note TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requests(
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), province_id INTEGER NOT NULL REFERENCES provinces(id), item_id INTEGER NOT NULL REFERENCES catalog(id), size TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity>0), request_kind TEXT NOT NULL CHECK(request_kind IN ('ANNUAL','SPECIAL','REPLACEMENT')), entitlement_year INTEGER NOT NULL, replacement_assignment_id INTEGER REFERENCES assignments(id), priority TEXT NOT NULL CHECK(priority IN ('NORMAL','URGENT')), reason TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('SUBMITTED','PROVINCE_REVIEW','HQ_REVIEW','APPROVED','SHIPPED','RECEIVED','FULFILLED','PARTIAL_COMPLETED','REJECTED')),
 approved INTEGER NOT NULL DEFAULT 0 CHECK(approved>=0), issued INTEGER NOT NULL DEFAULT 0 CHECK(issued>=0 AND issued<=quantity), batch_id INTEGER REFERENCES batches(id),
 rejection_reason TEXT NOT NULL DEFAULT '', shipment_ref TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assignments(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), request_id INTEGER NOT NULL REFERENCES requests(id), item_id INTEGER NOT NULL REFERENCES catalog(id), size TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), serial TEXT NOT NULL DEFAULT '', issue_location INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('PENDING','CONFIRMED','RETURNED')), issued_at TEXT NOT NULL, confirmed_at TEXT, returned_at TEXT);
CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY, assignment_id INTEGER NOT NULL REFERENCES assignments(id), user_id INTEGER NOT NULL REFERENCES users(id), type TEXT NOT NULL CHECK(type IN ('DAMAGED','WORN','LOST')), description TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY, location INTEGER NOT NULL, item_id INTEGER NOT NULL REFERENCES catalog(id), size TEXT NOT NULL, delta INTEGER NOT NULL, kind TEXT NOT NULL, reference TEXT NOT NULL, actor_id INTEGER REFERENCES users(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), province_id INTEGER, action TEXT NOT NULL, entity TEXT NOT NULL, entity_id INTEGER, detail TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'audit is append only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'audit is append only'); END;
CREATE INDEX IF NOT EXISTS requests_scope ON requests(province_id,status,user_id);
CREATE INDEX IF NOT EXISTS assignments_user ON assignments(user_id,status);
CREATE INDEX IF NOT EXISTS movements_scope ON movements(location,created_at);
CREATE INDEX IF NOT EXISTS audit_scope ON audit(province_id,created_at);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS workflow(key TEXT PRIMARY KEY, value INTEGER NOT NULL CHECK(value IN (0,1)));
INSERT OR IGNORE INTO workflow VALUES('allow_local_issue',1),('allow_partial_allocation',1),('require_serial',0);
CREATE INDEX IF NOT EXISTS annual_entitlement_scope ON requests(user_id,item_id,entitlement_year,request_kind);
