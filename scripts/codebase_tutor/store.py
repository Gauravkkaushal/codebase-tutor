"""SQLite knowledge store."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from . import SCHEMA_VERSION

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files(
  path TEXT PRIMARY KEY, lang TEXT, role TEXT, size INTEGER, mtime_ns INTEGER, lines INTEGER,
  hash TEXT, status TEXT, parser TEXT, error TEXT, analyzed_at REAL, entry TEXT);
CREATE TABLE IF NOT EXISTS symbols(
  id INTEGER PRIMARY KEY, file TEXT, name TEXT, qualname TEXT, kind TEXT, start_line INTEGER,
  end_line INTEGER, signature TEXT, exported INTEGER, parent TEXT, body_hash TEXT);
CREATE INDEX IF NOT EXISTS ix_sym_file ON symbols(file);
CREATE INDEX IF NOT EXISTS ix_sym_name ON symbols(name);
CREATE INDEX IF NOT EXISTS ix_sym_qual ON symbols(qualname);
CREATE TABLE IF NOT EXISTS imports(
  id INTEGER PRIMARY KEY, file TEXT, line INTEGER, module TEXT, names TEXT, kind TEXT,
  reexport INTEGER, resolved TEXT, external INTEGER);
CREATE INDEX IF NOT EXISTS ix_imp_file ON imports(file);
CREATE INDEX IF NOT EXISTS ix_imp_res ON imports(resolved);
CREATE TABLE IF NOT EXISTS exports(file TEXT, name TEXT, local TEXT);
CREATE INDEX IF NOT EXISTS ix_exp_file ON exports(file);
CREATE TABLE IF NOT EXISTS calls(
  id INTEGER PRIMARY KEY, file TEXT, line INTEGER, caller TEXT, expr TEXT, name TEXT, receiver TEXT,
  resolved_id INTEGER, resolution TEXT, external TEXT);
CREATE INDEX IF NOT EXISTS ix_call_file ON calls(file);
CREATE INDEX IF NOT EXISTS ix_call_res ON calls(resolved_id);
CREATE INDEX IF NOT EXISTS ix_call_caller ON calls(file, caller);
CREATE TABLE IF NOT EXISTS routes(
  id INTEGER PRIMARY KEY, file TEXT, line INTEGER, framework TEXT, method TEXT, path TEXT,
  handlers TEXT, router TEXT, kind TEXT, full_path TEXT, handler_ids TEXT, mount_target TEXT);
CREATE TABLE IF NOT EXISTS control(
  id INTEGER PRIMARY KEY, file TEXT, symbol TEXT, line INTEGER, kind TEXT, text TEXT, outcome TEXT);
CREATE INDEX IF NOT EXISTS ix_ctl ON control(file, symbol);
CREATE TABLE IF NOT EXISTS env_vars(file TEXT, line INTEGER, name TEXT);
CREATE INDEX IF NOT EXISTS ix_env_file ON env_vars(file);
CREATE INDEX IF NOT EXISTS ix_routes_file ON routes(file);
CREATE INDEX IF NOT EXISTS ix_call_name ON calls(name);
CREATE TABLE IF NOT EXISTS test_links(test_file TEXT, target_file TEXT, via TEXT, confidence TEXT);
CREATE INDEX IF NOT EXISTS ix_tl_target ON test_links(target_file);
CREATE INDEX IF NOT EXISTS ix_tl_test ON test_links(test_file);
CREATE TABLE IF NOT EXISTS evidence(
  id TEXT PRIMARY KEY, file TEXT, start_line INTEGER, end_line INTEGER, text_hash TEXT,
  file_hash TEXT, created_at REAL, status TEXT);
CREATE TABLE IF NOT EXISTS snapshots(
  id TEXT PRIMARY KEY, created_at REAL, git_commit TEXT, branch TEXT, dirty INTEGER, files INTEGER,
  manifest TEXT, note TEXT);
"""

PER_FILE_TABLES = ("symbols", "imports", "exports", "calls", "routes", "control", "env_vars")


class Store:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        if self.get_meta("schema_version") is None:
            self.set_meta("schema_version", str(SCHEMA_VERSION))
        self.db.commit()

    # ---------------------------------------------------------------- meta
    def get_meta(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value))

    def get_json(self, key, default=None):
        v = self.get_meta(key)
        return json.loads(v) if v else default

    def set_json(self, key, value):
        self.set_meta(key, json.dumps(value))

    # ---------------------------------------------------------------- files
    def file_index(self) -> dict:
        return {r["path"]: (r["size"], r["mtime_ns"], r["hash"], r["status"])
                for r in self.db.execute("SELECT path,size,mtime_ns,hash,status FROM files")}

    def delete_file_facts(self, path: str):
        for t in PER_FILE_TABLES:
            self.db.execute(f"DELETE FROM {t} WHERE file=?", (path,))
        self.db.execute("DELETE FROM test_links WHERE test_file=? OR target_file=?", (path, path))

    def delete_file(self, path: str):
        self.delete_file_facts(path)
        self.db.execute("DELETE FROM files WHERE path=?", (path,))

    def upsert_file(self, entry, lines: int, status: str, parser: str, error: str, entry_reasons: list):
        self.db.execute(
            "INSERT OR REPLACE INTO files(path,lang,role,size,mtime_ns,lines,hash,status,parser,error,analyzed_at,entry)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (entry.path, entry.lang, entry.role, entry.size, entry.mtime_ns, lines, entry.hash, status, parser,
             error, time.time(), json.dumps(entry_reasons) if entry_reasons else None))

    def insert_facts(self, path: str, facts: dict):
        db = self.db
        db.executemany(
            "INSERT INTO symbols(file,name,qualname,kind,start_line,end_line,signature,exported,parent,body_hash)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            [(path, s["name"], s["qualname"], s["kind"], s["start"], s["end"], s["signature"], int(s["exported"]),
              s["parent"], s["body_hash"]) for s in facts["symbols"]])
        db.executemany(
            "INSERT INTO imports(file,line,module,names,kind,reexport) VALUES(?,?,?,?,?,?)",
            [(path, i["line"], i["module"], json.dumps(i["names"]), i["kind"], int(i["reexport"])) for i in facts["imports"]])
        db.executemany("INSERT INTO exports(file,name,local) VALUES(?,?,?)",
                       [(path, e[0], e[1]) for e in facts["exports"]])
        db.executemany(
            "INSERT INTO calls(file,line,caller,expr,name,receiver) VALUES(?,?,?,?,?,?)",
            [(path, c["line"], c["caller"], c["expr"], c["name"], c["receiver"]) for c in facts["calls"]])
        db.executemany(
            "INSERT INTO routes(file,line,framework,method,path,handlers,router,kind) VALUES(?,?,?,?,?,?,?,?)",
            [(path, r["line"], r["framework"], r["method"], r["path"], json.dumps(r["handlers"]), r["router"], r["kind"])
             for r in facts["routes"]])
        db.executemany(
            "INSERT INTO control(file,symbol,line,kind,text,outcome) VALUES(?,?,?,?,?,?)",
            [(path, c["symbol"], c["line"], c["kind"], c["text"], c["outcome"]) for c in facts["controls"]])
        db.executemany("INSERT INTO env_vars(file,line,name) VALUES(?,?,?)",
                       [(path, e[0], e[1]) for e in facts["env_vars"]])

    def commit(self):
        self.db.commit()

    def q(self, sql, args=()):
        return self.db.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        return self.db.execute(sql, args).fetchone()

    def close(self):
        self.db.commit()
        self.db.close()


def row_dict(row) -> dict:
    return {k: row[k] for k in row.keys()} if row is not None else None
