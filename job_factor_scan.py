"""一个真实的 agent 工作单元：对一批标的做因子计算 + 数据质量校验。
故意保留真实失败模式（历史不足、停牌、全零成交），因为工作台要展示的
正是"谁失败了、为什么"，而不是一路绿灯。
用法: python3 job_factor_scan.py <shard_index> <shard_total>
"""
import sys, os, glob, csv, math, time, random

DATA = os.environ.get("DATA_DIR", os.path.expanduser("~/.claude/backtest-data/data7y"))
MIN_BARS = 250          # 少于一年数据 → 判定为不合格样本

def load(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((r["date"], float(r["close"]), float(r["vol"])))
            except (ValueError, KeyError, TypeError):
                continue
    return rows

def analyse(rows):
    """全历史滚动计算 —— 不是只看尾部，因为尾部会骗人。"""
    closes = [c for _, c, _ in rows]
    vols   = [v for _, _, v in rows]
    n = len(closes)
    rets = [closes[i]/closes[i-1] - 1 if closes[i-1] > 0 else 0.0 for i in range(1, n)]

    # 滚动 20 日年化波动（全历史）
    W = 20; roll = []
    for i in range(W, len(rets)):
        w = rets[i-W:i]
        mu = sum(w)/W
        roll.append(math.sqrt(sum((r-mu)**2 for r in w)/(W-1)) * math.sqrt(252))
    # 最大回撤（全历史）
    peak = closes[0]; mdd = 0.0
    for c in closes:
        if c > peak: peak = c
        if peak > 0: mdd = max(mdd, 1 - c/peak)
    # 趋势持续性：收盘价在 MA60 之上的天数占比
    above = 0; cnt = 0
    for i in range(60, n):
        ma60 = sum(closes[i-60:i]) / 60
        cnt += 1
        if closes[i] > ma60: above += 1
    return {"bars": n,
            "ann_vol": roll[-1] if roll else 0.0,
            "vol_p90": sorted(roll)[int(len(roll)*0.9)] if roll else 0.0,
            "max_dd": mdd,
            "above_ma60": above/cnt if cnt else 0.0,
            "halt_days": sum(1 for v in vols[-60:] if v <= 0),
            "ma_cross": _ma_cross_bt(closes)}

def _ma_cross_bt(closes, fast=5, slow=20, cost=0.0025):
    """全历史 MA 交叉回测 —— 真活，不是为了拖时间。
    单边成本 0.25%，与主回测口径一致。"""
    n = len(closes); pos = 0; entry = 0.0; trades = []
    for i in range(slow, n):
        f = sum(closes[i-fast:i]) / fast
        sl = sum(closes[i-slow:i]) / slow
        if pos == 0 and f > sl:
            pos = 1; entry = closes[i]
        elif pos == 1 and f < sl:
            trades.append(closes[i]/entry - 1 - 2*cost); pos = 0
    if pos == 1 and entry > 0:
        trades.append(closes[-1]/entry - 1 - 2*cost)
    if not trades: return {"n": 0, "win": 0.0, "avg": 0.0}
    wins = [t for t in trades if t > 0]
    return {"n": len(trades), "win": len(wins)/len(trades),
            "avg": sum(trades)/len(trades)}

def synthetic_rows(seed, n=1700):
    """本机没有行情库时的回退：生成随机游走日线，保证工作台在任何机器上都能演示。"""
    rnd = random.Random(seed); px = 10.0; rows = []
    for i in range(n):
        px = max(0.5, px * (1 + rnd.gauss(0, 0.02)))
        vol = 0.0 if rnd.random() < 0.01 else rnd.uniform(1e6, 5e7)   # 1% 概率模拟停牌
        rows.append((f"d{i}", px, vol))
    return rows

def main():
    idx, total = int(sys.argv[1]), int(sys.argv[2])
    files = sorted(glob.glob(os.path.join(DATA, "*.csv")))
    if not files:
        n = 3100 // total
        print(f"[shard {idx}/{total}] 未找到本地行情库 {DATA}，改用合成数据演示（{n} 只）", flush=True)
        files = [f"SYN{idx*n+i:05d}" for i in range(n)]
    mine = files[idx::total] if files and files[0].endswith(".csv") else files
    print(f"[shard {idx}/{total}] 认领 {len(mine)} 只标的", flush=True)

    ok = bad = 0; halted = []; hi_vol = []
    bt_n = bt_win = 0; bt_sum = 0.0
    t0 = time.time()
    for i, path in enumerate(mine):
        code = os.path.basename(path).replace(".csv", "")
        try:
            rows = load(path) if path.endswith(".csv") else synthetic_rows(hash(path) & 0xffff, n=random.Random(path).choice([120, 900, 1700]))
            if len(rows) < MIN_BARS:
                bad += 1
                print(f"  ✗ {code} 历史不足 {len(rows)} 根，剔除", flush=True)
                continue
            m = analyse(rows)
            ok += 1
            if m["halt_days"] >= 10:
                halted.append((code, m["halt_days"]))
            if m["ann_vol"] > 0.85:
                hi_vol.append((code, round(m["ann_vol"], 3)))
            b = m["ma_cross"]
            if b["n"]:
                bt_n += b["n"]; bt_win += b["win"] * b["n"]; bt_sum += b["avg"] * b["n"]
        except Exception as e:
            bad += 1
            print(f"  ✗ {code} 解析失败 {type(e).__name__}", flush=True)
        if (i + 1) % 25 == 0:
            print(f"  … 已处理 {i+1}/{len(mine)}，合格 {ok}，剔除 {bad}", flush=True)

    if bt_n:
        print(f"    MA5/20 全历史回测：{bt_n} 笔 ｜ 胜率 {bt_win/bt_n*100:.1f}% ｜ 均值 {bt_sum/bt_n*100:+.2f}%", flush=True)
    print(f"[shard {idx}] 完成 {time.time()-t0:.1f}s ｜ 合格 {ok} ｜ 剔除 {bad} "
          f"｜ 长期停牌 {len(halted)} ｜ 高波(年化>85%) {len(hi_vol)}", flush=True)
    for c, v in sorted(hi_vol, key=lambda x: -x[1])[:5]:
        print(f"    高波: {c} 年化波动 {v}", flush=True)
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
