# Agent 工作台 · Agent Workbench

*A zero-dependency observability layer for parallel AI agents: state instead of logs, stall detection, per-agent intervention, pluggable runtimes. Python 3.9+ stdlib only.*

> 模型已经能编排几百个子 agent 了，但没有产品解决「人怎么看懂几百个 agent 在干什么」。
> 这不是模型问题，是产品问题。

并行跑十几个 agent 时，日志会互相刷屏，人看不出谁在做什么、谁卡住了、该看哪一个。
这个工作台不显示日志流，显示**状态**。

## 四个产品决定

| 决定 | 为什么 |
|---|---|
| **状态而非日志** | 每个 agent 一格，颜色即状态（排队／运行／卡住／完成／失败／已中止）。人扫一眼就知道该看哪个 |
| **卡住要被主动标记** | 超过 `STALL_SEC` 没有新输出即标为「卡住」，而不是等它超时。一个安静的 agent 和一个死掉的 agent，在日志里长得一样 |
| **干预必须是单点的** | 可以只中止或只重试某一个 agent，其余不受影响。全局 kill 是最差的补救方式 |
| **可观测层不该关心 agent 是什么** | 运行时可插拔：`shell` 跑任意命令，`claude` 跑真实 Claude Code agent。契约只有一条——给我一个吐行的进程 |

## 跑起来

```bash
python3 server.py          # → http://127.0.0.1:8777
```

界面上点「开始一次运行」。**没有本地行情库也能跑**——`job_factor_scan.py` 检测不到数据时会切到合成随机游走序列，保证任何机器 clone 下来都能看到工作台运行。

我本机的工作负载是**真实的**：对本地 3,100 只 A 股
× 7 年日线做并行因子扫描 + 全历史 MA5/20 交叉回测（成本 0.25% 双边），
分片并行，保留真实失败模式（历史不足、停牌、解析失败）。

单分片实测输出示例：

```
[shard 0/24] 认领 130 只标的
  ✗ 001339.SZ 历史不足 0 根，剔除
    MA5/20 全历史回测：6197 笔 ｜ 胜率 33.3% ｜ 均值 +0.57%
[shard 0] 完成 1.2s ｜ 合格 129 ｜ 剔除 1 ｜ 高波(年化>85%) 6
```

## 文件

```
server.py            零依赖 HTTP 服务（标准库 http.server）
orchestrator.py      并行编排 + 状态机 + 卡住检测 + 单点干预
runners.py           可插拔运行时（shell / claude），含开跑前可用性探测
store.py             SQLite 事件存储 —— 单一事实来源，编排器崩了历史仍在
job_factor_scan.py   真实工作负载：因子扫描 + MA 交叉回测
ui.html              工作台界面
```

## 已知边界

- `claude` runner 需要 CLI 已登录；未登录时 `runners.probe()` 会**在开跑前**明说，
  而不是跑到一半才失败。
- 卡住阈值是产品参数，取决于任务的正常输出节奏，没有普适值。
- 当前工作负载是 CPU 密集型且很快（秒级）；工作台真正的目标场景是
  30–120 秒级的 LLM agent。

无第三方依赖，Python 3.9+ 即可运行。


## 相关

作者作品集（含本项目运行截图与另外五个系统的验证记录）：https://shujun0410.github.io
