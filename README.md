# SQLite Migration Runner

A small command-line tool for applying ordered, **trusted** SQLite migrations with SHA-256 history and per-migration transactions. Python 3.10+; standard library only; MIT.

Create a SQLite database and a migration directory such as:

```text
migrations/
  0001_create.sql
  0002_seed.sql
```

Each filename uses four digits, an underscore, a lowercase name, and `.sql`. Versions must be positive and unique. Files are applied in numeric order, up to 1000 files of 64 KiB each. The target database must already exist and must be a regular file; it is never created automatically.

```console
python migrate.py --db example.db --migrations migrations
python -m unittest -v
```

Applied version, filename and SHA-256 of original bytes are recorded in `__migration_runner_history`. Re-running skips identical migrations. A missing, renamed or modified applied file blocks further changes; adding a migration before an existing version is rejected. Each new migration is committed separately. If migration 2 fails, its changes roll back, while a successfully committed migration 1 remains. The history table itself is created before applying the first migration.

Transaction control, `ATTACH`, `DETACH`, `PRAGMA`, and changes to the history table are denied while migration SQL executes, to preserve transaction boundaries. SQL files can otherwise change application data: **review them, make a backup, and run only migrations from trusted authors**. This is not a SQL sandbox, migration rollback generator, or safe tool for untrusted SQL. There is no down migration, dry-run, target creation, automatic backup, distributed lock guarantee, or support for other database engines. File/path checks do not defend against adversarial filesystem races or hardlinks.

Tests cover ordering, no reapplication, checksums, rollback after failed SQL, transaction control, duplicate versions, strings containing semicolons, and missing databases. Test with `python -m unittest -v`; CI tests Windows/Linux and Python 3.10/3.12/3.14.

Owner/maintainer: Muhammad Zidane Naufal Azzam (ZidaneNaufal1). Implementation, tests and documentation were developed with Ciel/OpenAI Codex assistance. No external adoption, independent security audit or manual understanding is claimed.

## Ringkasan Bahasa Indonesia

Alat migrasi SQLite lokal dengan urutan, checksum dan transaksi per file. Jalankan hanya SQL tepercaya pada database yang sudah dicadangkan; jika migrasi gagal, perubahan pada file itu dibatalkan.
