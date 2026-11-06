"""SQLite maintenance. Backups never overwrite an existing path."""
import argparse
import os
import sqlite3
from pathlib import Path
from server import ROOT, Store

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=os.environ.get('AFAD_DB',str(ROOT/'data'/'afad.sqlite3')))
    commands=parser.add_subparsers(dest='command',required=True)
    backup=commands.add_parser('backup');backup.add_argument('--output',required=True)
    commands.add_parser('check');commands.add_parser('invalidate-sessions')
    args=parser.parse_args()
    source=Path(args.db).resolve()
    if not source.is_file():parser.error('Veritabanı bulunamadı.')
    if args.command=='backup':
        output=Path(args.output).resolve()
        output.parent.mkdir(parents=True,exist_ok=True)
        # O_EXCL protects an existing backup, including symbolic links.
        fd=os.open(str(output),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        try:
            with sqlite3.connect(str(source)) as db,sqlite3.connect(str(output)) as dest:
                db.backup(dest)
                if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Yedek doğrulaması başarısız.')
            print('Yedek oluşturuldu:',output)
        except Exception:
            output.unlink(missing_ok=True);raise
    elif args.command=='check':
        with sqlite3.connect(str(source)) as db:
            checks=[r[0] for r in db.execute('PRAGMA integrity_check')]
            foreign=list(db.execute('PRAGMA foreign_key_check'))
        if checks!=['ok'] or foreign:raise SystemExit('Veritabanı doğrulaması başarısız.')
        print('Veritabanı ve ilişkiler: OK')
    else:
        with Store(source).db(True) as db:
            db.execute('DELETE FROM sessions')
            Store.audit(db,None,'INVALIDATE_ALL_SESSIONS','session',detail='Bakım komutu')
        print('Tüm oturumlar sonlandırıldı.')
if __name__=='__main__':main()
