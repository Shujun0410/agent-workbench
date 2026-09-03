"""零依赖 HTTP 服务：托管工作台界面 + 状态接口 + 单点干预接口。
用标准库 http.server —— 不引入任何框架，一个 python3 server.py 就能跑。
"""
import os, sys, json, threading, http.server, socketserver, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import store, orchestrator, runners

PORT = 8777
_current = {"run_id": None}

LLM_TASKS = [
    "用三句话解释什么是 walk-forward 验证，以及它防的是哪种自欺。",
    "一个回测年化 20% 但胜率只有 32%，这在说明什么？给两个可能。",
    "解释「生存者偏差」在股票回测里的具体表现，一个例子。",
    "什么是前视偏差？举一个候选池构建时容易犯的例子。",
    "为什么并行 agent 系统需要「卡住检测」而不是只靠超时？",
    "用一句话区分「显示状态」和「显示日志」对人的意义。",
]
def launch(n_shards=24, parallel=6, runner="shell"):
    orchestrator.MAX_PARALLEL = parallel
    if runner == "minimax":
        subs = [{"id": f"m{i:02d}", "label": f"LLM {i:02d}", "runner": "minimax", "prompt": t}
                for i, t in enumerate(LLM_TASKS)]
        name = "MiniMax M2 · 6 个真实 LLM agent 并行"
    else:
        subs = [{"id": f"s{i:02d}", "label": f"分片 {i:02d}", "runner": "shell",
                 "cmd": f'cd "{HERE}" && python3 -u job_factor_scan.py {i} {n_shards}'}
                for i in range(n_shards)]
        name = "全市场因子扫描 · 3,100 只 × 7 年"
    def go():
        _current["run_id"] = orchestrator.run(name, subs)
    t = threading.Thread(target=go, daemon=True); t.start()

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=HERE, **k)
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path == "/api/state":   return self._json(store.snapshot(q.get("run",[None])[0]))
        if u.path == "/api/timeline":
            return self._json(store.timeline(q["run"][0], q["agent"][0]))
        if u.path == "/api/runtimes": return self._json(runners.probe())
        if u.path == "/api/launch":
            launch(int(q.get("n",[24])[0]), int(q.get("p",[6])[0]), q.get("runner",["shell"])[0]); return self._json({"ok":True})
        if u.path == "/api/act":
            orchestrator.request(q["run"][0], q["agent"][0], q["do"][0]); return self._json({"ok":True})
        if u.path == "/": self.path = "/ui.html"
        return super().do_GET()

if __name__ == "__main__":
    store.init()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H) as s:
        print(f"Agent 工作台: http://127.0.0.1:{PORT}")
        s.serve_forever()
