# -*- coding: utf-8 -*-
"""数智沙盘 · 发薪（payday）——报文已逆出，但**当前回合服务端不开窗口**

从 est.js（模块 nchs / 模型 salary）与 chunks（/SbR 工资页）逆出的真实调用链：
    ① GET  /est/hrd/employeeList?page=1&size=50        → data.employeeCodes[]、data.flag
    ② GET  /est/hrd/paydayCash?employeeCodes=<逗号拼接>  → data.totalCash（本季应发合计）
    ③ POST /est/hrd/payday  form body:
         creator=<userId>&employeeCodes=<逗号拼接>&gameId&round&teamId
       （单人分支用 employeeId=<employeeCode>，同一接口）
    ④ 成功后重拉 employeeList；现金减少 = 发薪成功

【实测结论（2026-10-18 round=2，gameId 2110951798943174657）】
- ② 在 round=2 报 500「员工信息不存在」；**round=3 返回 totalCash=14400**（=6人月薪合计4800×3，季度工资）
- ③ round=2/round=1 报 500「不能解聘在产员工」；round=3 报 500「系统错误」
- 关键：③ 的「不能解聘在产员工」与传入 employeeCodes **无关**——传无效码 999999、短账号 27、
  hrd id、6 个有效码、单人、query-only、body-only、把两条产线工人清空后，全部同样报错。
  说明它不是员工级校验，而是**当前回合的服务端全局闸门**（发薪窗口未开；员工列表 flag=false，
  界面「统一发薪」按钮此时也是 disabled）。
- 因此本回合（round=2）无论界面还是接口都发不了薪；金额已经可以算出（14400）。
  预计下一回合（round 3，系统 clone 员工/开放工资单）用同一报文即可；届时本脚本 pay 即成功。

用法：
    python 脚本\\游戏-发薪.py            # 只读：员工/发薪状态/应发金额/现金
    python 脚本\\游戏-发薪.py show
    python 脚本\\游戏-发薪.py paycash    # 试算 round=2、3、4… 的应发金额（定位发薪窗口）
    python 脚本\\游戏-发薪.py pay        # 真正发薪（flag=false 时拒绝执行；--force 强试）
    python 脚本\\游戏-发薪.py pay --force

安全约定：POST 只发一次、绝不自动重试（超时可能已在服务端生效，重试会重复发薪）。
参数来源：.tmp\\api\\ctx.json；auid：.tmp\\api\\auid.txt（过期自动重登，见 est_common.py）
"""
import argparse
import json
import os
import sys
import time

sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import est_common as E  # noqa: E402


def show():
    recs, flag, codes = E.employees()
    print(f"round={E.ROUND} employees={len(recs)} employeeList.flag={flag}")
    for e in recs:
        print(f"  {e.get('employeeName')} {e.get('levelCode')} 月薪={e.get('monthlySalary')} "
              f"paydayState={e.get('paydayState')} workState={e.get('workState')} code={e.get('employeeCode')}")
    print("employeeCodes =", ",".join(codes))
    for rnd in (E.ROUND, str(int(E.ROUND) + 1)):
        j = E.js("/est/hrd/paydayCash", {"employeeCodes": ",".join(codes), "round": rnd}, post_id=3)
        print(f"paydayCash(round={rnd}) -> {json.dumps(j, ensure_ascii=False)[:220]}")
    print("现金 =", E.cash())
    if not flag:
        print("\n⚠️ employeeList.flag=false：服务端判定本回合不可发薪（界面“统一发薪”按钮此时是禁用的）。")


def paycash():
    recs, flag, codes = E.employees()
    print(f"employees={len(recs)} flag={flag}")
    for rnd in range(1, int(E.ROUND) + 5):
        j = E.js("/est/hrd/paydayCash", {"employeeCodes": ",".join(codes), "round": str(rnd)}, post_id=3)
        print(f"round={rnd} -> {json.dumps(j, ensure_ascii=False)[:180]}")


def pay(force=False):
    recs, flag, codes = E.employees()
    print(f"before: cash={E.cash()} employees={len(recs)} flag={flag} round={E.ROUND}")
    if not codes:
        print("没有员工（employeeList.employeeCodes 为空），无法发薪")
        return
    jc = E.js("/est/hrd/paydayCash", {"employeeCodes": ",".join(codes)}, post_id=3)
    print("paydayCash(round=%s) -> %s" % (E.ROUND, json.dumps(jc, ensure_ascii=False)[:220]))
    if jc.get("code") != 200:
        print("⚠️ paydayCash 未返回可发金额；按 UI 流程此时不应继续 POST payday。")
        if not force:
            print("   若仍要强试：加 --force（只发一次，失败无副作用）")
            return
    if not flag and not force:
        print("⚠️ flag=false（本回合服务端未开放发薪窗口），已跳过 POST。要强试加 --force。")
        return
    fields = {"creator": E.USER_ID, "employeeCodes": ",".join(codes),
              "gameId": E.GAME_ID, "round": E.ROUND, "teamId": E.TEAM_ID}
    print("POST /est/hrd/payday  body=", json.dumps(fields, ensure_ascii=False))
    res = E.post_once("/est/hrd/payday", fields, post_id=3, timeout=120)
    print("  <-", res[:400] if res else "(空响应：可能仍在处理，等 30-60s 回读，不要重发)")
    # 回读：等 30s（服务端常 30-60s）
    for i in range(7):
        time.sleep(10)
        recs2, flag2, _ = E.employees()
        c = E.cash()
        states = [(x.get("employeeName"), x.get("paydayState")) for x in recs2]
        print(f"  回读 {10 * (i + 1)}s: cash={c} flag={flag2} paydayState={states}")
        if c is not None:
            break
    print("提示：成功标准 = 现金减少 且 paydayState 变化；若报「不能解聘在产员工」见脚本头部说明。")


def main():
    ap = argparse.ArgumentParser(description="数智沙盘发薪（payday）")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("show")
    sub.add_parser("paycash")
    p = sub.add_parser("pay")
    p.add_argument("--force", action="store_true", help="flag=false / paydayCash 失败时仍强试一次 POST")
    a = ap.parse_args()
    cmd = a.cmd or "show"
    if cmd == "show":
        show()
    elif cmd == "paycash":
        paycash()
    elif cmd == "pay":
        pay(force=getattr(a, "force", False))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
