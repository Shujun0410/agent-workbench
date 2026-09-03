"""可插拔的 agent 运行时。
产品判断：可观测层不该关心 agent 是什么 —— 它只需要一个吐行的进程。
所以 runner 的契约极简：给我命令，我给你逐行输出与退出码。
"""
import subprocess, os, sys

def shell_runner(spec):
    """任意 shell 命令作为 agent。零依赖，立即可用。"""
    return subprocess.Popen(
        spec["cmd"], shell=True, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, start_new_session=True)

def claude_runner(spec):
    """真实的 Claude Code agent。需要 `claude` 已登录。"""
    return subprocess.Popen(
        ["claude", "-p", spec["prompt"]], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, start_new_session=True)

def minimax_runner(spec):
    """真实 LLM agent：MiniMax 开放平台（OpenAI 兼容、流式）。需要 MINIMAX_API_KEY。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return subprocess.Popen(
        [sys.executable, "-u", os.path.join(here, "job_llm_minimax.py"), spec["prompt"]],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, start_new_session=True)

RUNNERS = {"shell": shell_runner, "claude": claude_runner, "minimax": minimax_runner}

def probe():
    """开跑前先探测哪些运行时可用 —— 不可用就明说，不要跑到一半才失败。"""
    out = {}
    try:
        r = subprocess.run(["claude", "-p", "ping"], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=40)
        txt = (r.stdout + r.stderr).lower()
        out["claude"] = "未登录（运行 claude /login 后可用）" if "not logged in" in txt else "可用"
    except FileNotFoundError:
        out["claude"] = "未安装"
    except Exception as e:
        out["claude"] = f"探测失败：{type(e).__name__}"
    out["minimax"] = "可用（已配置 MINIMAX_API_KEY）" if os.environ.get("MINIMAX_API_KEY") else "未配置 MINIMAX_API_KEY"
    out["shell"] = "可用"
    return out
