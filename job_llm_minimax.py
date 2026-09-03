"""一个真实的 LLM agent 工作单元：通过 MiniMax 开放平台跑一个任务，流式逐行输出。
契约与其它 job 一样——吐行、退出码。这样工作台的"卡住检测"对 LLM 也有意义：
模型 20 秒没吐 token，和一个卡死的子进程，在状态板上是同一种颜色。

环境变量：
  MINIMAX_API_KEY   必填。缺失即 fail-closed 退出（退出码 2），不伪造输出。
  MINIMAX_BASE_URL  默认 https://api.minimaxi.com/v1（国际站用 https://api.minimax.io/v1）
  MINIMAX_MODEL     默认 MiniMax-M2
用法：python3 job_llm_minimax.py "<task prompt>"
"""
import os, sys, json, time, urllib.request, urllib.error

def main():
    key = os.environ.get("MINIMAX_API_KEY")
    if not key:
        print("[minimax] MINIMAX_API_KEY 未设置 —— 拒绝伪造输出，退出", flush=True); return 2
    base = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1").rstrip("/")
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2")
    prompt = sys.argv[1] if len(sys.argv) > 1 else "用三句话说明什么是 walk-forward 验证。"
    body = json.dumps({"model": model, "stream": True,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body, method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    print(f"[minimax] model={model} 请求已发出", flush=True)
    t0 = time.time(); chars = 0; buf = ""
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            for raw in r:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"): continue
                data = line[5:].strip()
                if data == "[DONE]": break
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {}).get("content", "")
                except (KeyError, IndexError, json.JSONDecodeError):
                    continue
                if not delta: continue
                buf += delta; chars += len(delta)
                # 按句/行吐出，而不是每个 token 一行，让状态板可读
                while any(p in buf for p in ("\n", "。", "！", "？")):
                    cut = max(buf.find(p) for p in ("\n", "。", "！", "？") if p in buf) + 1
                    print("  " + buf[:cut].strip(), flush=True); buf = buf[cut:]
    except urllib.error.HTTPError as e:
        print(f"[minimax] HTTP {e.code}: {e.read()[:200].decode('utf-8','ignore')}", flush=True); return 1
    except Exception as e:
        print(f"[minimax] 失败 {type(e).__name__}: {e}", flush=True); return 1
    if buf.strip(): print("  " + buf.strip(), flush=True)
    print(f"[minimax] 完成 {time.time()-t0:.1f}s ｜ {chars} 字符", flush=True)
    return 0 if chars else 1

if __name__ == "__main__":
    sys.exit(main())
