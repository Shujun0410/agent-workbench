"""并行 agent 编排器。
每个 agent 是一个真实的 `claude -p` 子进程。
三个产品决定：
  1) 状态模型 —— pending / running / stalled / done / failed / killed，不是日志刷屏
  2) 卡住检测 —— 超过 STALL_SEC 没有新输出即标记 stalled，而不是等它超时
  3) 单点干预 —— 可以 kill 或 retry 单个 agent，不打断其余
"""
import subprocess, threading, queue, time, uuid, os, sys, json, signal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store
from runners import RUNNERS

STALL_SEC = 8           # 多久没有新输出算“卡住”（产品参数：这些任务每 25 项打一次日志）
MAX_PARALLEL = 4

_procs = {}             # (run_id, agent_id) -> Popen
_control = {}           # (run_id, agent_id) -> "kill" | "retry"
_clock = threading.Lock()

def request(run_id, agent_id, action):
    with _clock:
        _control[(run_id, agent_id)] = action

def _take(run_id, agent_id):
    with _clock:
        return _control.pop((run_id, agent_id), None)

def _run_agent(run_id, agent_id, label, spec, attempt=1):
    store.upsert_agent(run_id, agent_id, label, "running", f"第 {attempt} 次尝试")
    store.event(run_id, agent_id, "start", {"spec": str(spec)[:600], "attempt": attempt})
    try:
        p = RUNNERS[spec.get("runner", "shell")](spec)
    except FileNotFoundError:
        store.upsert_agent(run_id, agent_id, label, "failed", "运行时不可用", exit_code=-1)
        return
    _procs[(run_id, agent_id)] = p

    last = time.time(); buf = []; stalled = False
    q = queue.Queue()
    def pump():
        for line in iter(p.stdout.readline, ''):
            q.put(line)
        q.put(None)
    threading.Thread(target=pump, daemon=True).start()

    while True:
        act = _take(run_id, agent_id)
        if act == "kill":
            try: os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception: pass
            store.upsert_agent(run_id, agent_id, label, "killed", "被用户中止", exit_code=-2)
            store.event(run_id, agent_id, "killed", {"by": "user"})
            return
        if act == "retry":
            try: os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception: pass
            store.event(run_id, agent_id, "retry", {"attempt": attempt + 1})
            return _run_agent(run_id, agent_id, label, spec, attempt + 1)
        try:
            line = q.get(timeout=1.0)
        except queue.Empty:
            line = ""
        if line is None:
            break
        if line:
            buf.append(line); last = time.time()
            if stalled:
                stalled = False
                store.upsert_agent(run_id, agent_id, label, "running", "已恢复输出")
            store.event(run_id, agent_id, "out", {"line": line.rstrip()[:500]})
            store.upsert_agent(run_id, agent_id, label, "running", line.strip()[:120])
        elif not stalled and time.time() - last > STALL_SEC:
            stalled = True
            store.upsert_agent(run_id, agent_id, label, "stalled",
                               f"已 {int(time.time()-last)} 秒无输出")
            store.event(run_id, agent_id, "stalled", {"silent_sec": int(time.time() - last)})

    code = p.wait()
    out = "".join(buf)
    state = "done" if code == 0 else "failed"
    store.upsert_agent(run_id, agent_id, label, state, out.strip()[-300:] or f"退出码 {code}", exit_code=code)
    store.event(run_id, agent_id, "end", {"exit": code, "chars": len(out)})

def run(task_name, subtasks, run_id=None):
    """subtasks: [{'id':..,'label':..,'prompt':..}, ...]"""
    store.init()
    run_id = run_id or f"run_{int(time.time())}_{uuid.uuid4().hex[:4]}"
    store.start_run(run_id, task_name, len(subtasks))
    for st in subtasks:
        store.upsert_agent(run_id, st["id"], st["label"], "pending", "排队中")
    sem = threading.Semaphore(MAX_PARALLEL)
    threads = []
    def worker(st):
        with sem:
            _run_agent(run_id, st["id"], st["label"], st)
    for st in subtasks:
        t = threading.Thread(target=worker, args=(st,), daemon=True)
        t.start(); threads.append(t)
    for t in threads: t.join()
    store.end_run(run_id)
    return run_id

if __name__ == "__main__":
    subs = [{"id": f"a{i}", "label": f"探针 {i}",
             "prompt": f"只回答一个数字：{i}*7 等于多少？不要解释。"} for i in range(1, 4)]
    print("run_id =", run(" 冒烟测试", subs))
