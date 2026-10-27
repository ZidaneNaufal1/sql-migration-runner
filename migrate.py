"""Apply ordered, trusted SQLite migrations one transaction at a time."""
import argparse
import hashlib
from pathlib import Path
import re
import sqlite3
import sys

TABLE = '__migration_runner_history'
NAME = re.compile(r'([0-9]{4})_([a-z0-9_]+)\.sql\Z')
LIMIT = 65536


def read_migrations(folder):
    folder=Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('Migration directory must be a regular directory.')
    paths=sorted(folder.glob('*.sql'))
    if not paths or len(paths)>1000: raise ValueError('Provide 1–1000 migration files.')
    result=[]; seen=set()
    for path in paths:
        match=NAME.fullmatch(path.name)
        if not match or path.is_symlink() or not path.is_file(): raise ValueError('Invalid migration filename or symlink.')
        version=int(match.group(1))
        if version in seen or version == 0: raise ValueError('Migration versions must be unique and positive.')
        seen.add(version)
        with path.open('rb') as f: raw=f.read(LIMIT+1)
        if len(raw)>LIMIT: raise ValueError('Migration exceeds 64 KiB.')
        try: sql=raw.decode('utf-8')
        except UnicodeError: raise ValueError('Migration must be UTF-8.') from None
        result.append((version,path.name,hashlib.sha256(raw).hexdigest(),sql))
    return result


def statements(sql):
    buffer=''
    for char in sql:
        buffer+=char
        if char==';' and sqlite3.complete_statement(buffer):
            yield buffer
            buffer=''
    if buffer.strip():
        # SQLite accepts a final statement without a semicolon. Test completeness
        # by adding one, and let the database reject invalid SQL.
        if not sqlite3.complete_statement(buffer+';'): raise ValueError('Incomplete SQL statement.')
        yield buffer


def authorizer(action, arg1, arg2, dbname, source):
    forbidden={sqlite3.SQLITE_ATTACH,sqlite3.SQLITE_DETACH,sqlite3.SQLITE_PRAGMA,sqlite3.SQLITE_TRANSACTION,sqlite3.SQLITE_SAVEPOINT}
    if action in forbidden: return sqlite3.SQLITE_DENY
    if (arg1 and arg1.lower()==TABLE) or (arg2 and arg2.lower()==TABLE): return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def apply(db, folder):
    migrations=read_migrations(folder)
    db=Path(db).absolute()
    if not db.is_file() or db.is_symlink(): raise ValueError('Use an existing regular SQLite database, not a symlink.')
    c=sqlite3.connect(db,timeout=5)
    try:
        c.execute('PRAGMA foreign_keys=ON')
        c.execute(f'CREATE TABLE IF NOT EXISTS {TABLE} (version INTEGER PRIMARY KEY, filename TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        c.commit()
        # Check the complete recorded history before applying any new migrations.
        actual={v:(n,h) for v,n,h in c.execute(f'SELECT version,filename,checksum FROM {TABLE}')}
        available={v:(n,h) for v,n,h,_ in migrations}
        for version, info in actual.items():
            if available.get(version)!=info: raise ValueError(f'Applied migration {version:04d} is missing, renamed, or changed.')
        if actual and any(v < max(actual) and v not in actual for v,_,_,_ in migrations):
            raise ValueError('Cannot insert a migration before an applied version.')
        completed=[]
        for version,name,digest,sql in migrations:
            if version in actual: continue
            try:
                c.execute('BEGIN IMMEDIATE')
                # Recheck after the write lock: another runner may have applied it.
                current=c.execute(f'SELECT filename,checksum FROM {TABLE} WHERE version=?',(version,)).fetchone()
                if current:
                    if current!=(name,digest): raise ValueError('Concurrent migration checksum mismatch.')
                    c.rollback(); continue
                c.set_authorizer(authorizer)
                for statement in statements(sql): c.execute(statement)
                # Python 3.10 can retain a denying callback when passed None.
                # Replace it explicitly before recording history or committing.
                c.set_authorizer(lambda *_: sqlite3.SQLITE_OK)
                c.execute(f'INSERT INTO {TABLE}(version,filename,checksum) VALUES(?,?,?)',(version,name,digest))
                c.commit(); completed.append(name)
            except BaseException:
                c.set_authorizer(lambda *_: sqlite3.SQLITE_OK); c.rollback(); raise
        return completed
    finally: c.close()


def main(argv=None):
    p=argparse.ArgumentParser(description='Apply trusted SQLite migrations in order.')
    p.add_argument('--db',type=Path,required=True); p.add_argument('--migrations',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        done=apply(args.db,args.migrations)
        print('Applied:', ', '.join(done) if done else 'none')
        return 0
    except (OSError,ValueError,sqlite3.Error) as exc:
        print('Migration failed:',str(exc),file=sys.stderr); return 2


if __name__=='__main__': raise SystemExit(main())

