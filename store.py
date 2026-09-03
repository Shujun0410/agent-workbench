"""事件存储：所有 agent 状态变化写入 SQLite，UI 只读这里。
单一事实来源 —— 编排器崩了，历史还在；UI 刷新，状态不丢。"""
import sqlite3, json, time, threading, os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs.db")
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, task TEXT, started REAL, finished REAL, n_agents INTEGER
);
CREATE TABLE IF NOT EXISTS agents(
  run_id TEXT, agent_id TEXT, label TEXT, state TEXT, detail TEXT,
  started REAL, updated REAL, finished REAL, exit_code INTEGER,
  PRIMARY KEY(run_id, agent_id)
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, agent_id TEXT,
  ts REAL, kind TEXT, payload TEXT
);
CREATE INDEX IF NOT EXISTS ix_ev ON events(run_id, id);
"""

def conn():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    return c

def init():
    with _lock, conn() as c:
        c.executescript(SCHEMA)

def start_run(run_id, task, n):
    with _lock, conn() as c:
        c.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?)", (run_id, task, time.time(), None, n))

def end_run(run_id):
    with _lock, conn() as c:
        c.execute("UPDATE runs SET finished=? WHERE run_id=?", (time.time(), run_id))

def upsert_agent(run_id, agent_id, label, state, detail="", exit_code=None):
    now = time.time()
    with _lock, conn() as c:
        row = c.execute("SELECT started FROM agents WHERE run_id=? AND agent_id=?", (run_id, agent_id)).fetchone()
        started = row[0] if row and row[0] else (now if state == "running" else None)
        fin = now if state in ("done", "failed", "killed") else None
        c.execute("""INSERT INTO agents(run_id,agent_id,label,state,detail,started,updated,finished,exit_code)
                     VALUES(?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(run_id,agent_id) DO UPDATE SET
                       state=excluded.state, detail=excluded.detail, updated=excluded.updated,
                       started=COALESCE(agents.started, excluded.started),
                       finished=COALESCE(excluded.finished, agents.finished),
                       exit_code=COALESCE(excluded.exit_code, agents.exit_code)""",
                  (run_id, agent_id, label, state, detail, started, now, fin, exit_code))

def event(run_id, agent_id, kind, payload):
    with _lock, conn() as c:
        c.execute("INSERT INTO events(run_id,agent_id,ts,kind,payload) VALUES(?,?,?,?,?)",
                  (run_id, agent_id, time.time(), kind, json.dumps(payload, ensure_ascii=False)[:8000]))

def snapshot(run_id=None):
    with _lock, conn() as c:
        c.row_factory = sqlite3.Row
        if not run_id:
            r = c.execute("SELECT run_id FROM runs ORDER BY started DESC LIMIT 1").fetchone()
            if not r: return {"run": None, "agents": []}
            run_id = r["run_id"]
        run = dict(c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone())
        ags = [dict(x) for x in c.execute(
            "SELECT * FROM agents WHERE run_id=? ORDER BY agent_id", (run_id,)).fetchall()]
        return {"run": run, "agents": ags, "now": time.time()}

def timeline(run_id, agent_id, limit=200):
    with _lock, conn() as c:
        c.row_factory = sqlite3.Row
        return [dict(x) for x in c.execute(
            "SELECT * FROM events WHERE run_id=? AND agent_id=? ORDER BY id DESC LIMIT ?",
            (run_id, agent_id, limit)).fetchall()]
