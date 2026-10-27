from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
import migrate


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name); self.db=self.path/'test.db'; self.folder=self.path/'migrations'; self.folder.mkdir()
        with closing(sqlite3.connect(self.db)): pass

    def file(self,name,sql): (self.folder/name).write_text(sql,encoding='utf-8')

    def test_order_and_no_reapply(self):
        self.file('0001_create.sql','CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT);')
        self.file('0002_insert.sql',"INSERT INTO items(name) VALUES ('one');")
        self.assertEqual(migrate.apply(self.db,self.folder),['0001_create.sql','0002_insert.sql'])
        self.assertEqual(migrate.apply(self.db,self.folder),[])
        with closing(sqlite3.connect(self.db)) as c: self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],1)

    def test_failing_migration_rolls_back_its_changes(self):
        self.file('0001_fail.sql','CREATE TABLE doomed(id INTEGER); INSERT INTO missing VALUES (1);')
        with self.assertRaises(sqlite3.Error): migrate.apply(self.db,self.folder)
        with closing(sqlite3.connect(self.db)) as c:
            self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='doomed'").fetchone())
            self.assertEqual(c.execute(f'SELECT count(*) FROM {migrate.TABLE}').fetchone()[0],0)

    def test_checksum_changed_blocks_further_work(self):
        self.file('0001_a.sql','CREATE TABLE items(id);'); migrate.apply(self.db,self.folder)
        self.file('0001_a.sql','CREATE TABLE items(id, changed);')
        self.file('0002_b.sql','CREATE TABLE later(id);')
        with self.assertRaises(ValueError): migrate.apply(self.db,self.folder)
        with closing(sqlite3.connect(self.db)) as c: self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='later'").fetchone())

    def test_missing_applied_file_refused(self):
        self.file('0001_a.sql','CREATE TABLE a(id);'); migrate.apply(self.db,self.folder)
        (self.folder/'0001_a.sql').unlink(); self.file('0002_b.sql','CREATE TABLE b(id);')
        with self.assertRaises(ValueError): migrate.apply(self.db,self.folder)

    def test_transaction_control_refused_and_rolled_back(self):
        self.file('0001_bad.sql','CREATE TABLE first(id); COMMIT; CREATE TABLE second(id);')
        with self.assertRaises(sqlite3.DatabaseError): migrate.apply(self.db,self.folder)
        with closing(sqlite3.connect(self.db)) as c: self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='first'").fetchone())

    def test_duplicate_versions_and_bad_filename(self):
        self.file('0001_a.sql','SELECT 1;'); self.file('0001_b.sql','SELECT 2;')
        with self.assertRaises(ValueError): migrate.read_migrations(self.folder)

    def test_statements_handles_semicolon_in_string(self):
        self.file('0001_a.sql',"CREATE TABLE t(x); INSERT INTO t VALUES('a;b');")
        migrate.apply(self.db,self.folder)
        with closing(sqlite3.connect(self.db)) as c: self.assertEqual(c.execute('SELECT x FROM t').fetchone()[0],'a;b')

    def test_missing_database_does_not_create_it(self):
        self.file('0001_a.sql','SELECT 1;'); p=self.path/'missing.db'
        with self.assertRaises(ValueError): migrate.apply(p,self.folder)
        self.assertFalse(p.exists())


if __name__=='__main__': unittest.main()
