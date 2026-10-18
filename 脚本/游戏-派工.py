# -*- coding: utf-8 -*-
"""数智沙盘 · 派工（给产线配工人）——已实测可用

原理（从 est.js / chunks 逆出的真实报文，与画布「拖人上线」完全一致）：
    POST /est/cto/employee/output/save      (form body, 无 query)
      levelIds      = JSON字符串 {"GR1":[{"id":"<employeeCode>","name":"杨王"}],"GR2":[...]}
      baseOutput    = 产线基础产量（output/list 的 baseOutput，传统线=40）
      dataEquipmentId = 产线 equipmentCode（不是记录 id！）
      ruleRotaId    = 班次 id（/est/cto/employee/column/list 的 ruleRotaList[0].id，8时制 …089）
      index         = 产线序号（output/list 的 index）
      userId / gameId / round / teamId / ruleId / applyBudgetPost=2
    → {"code":200}，回读 /est/cto/employee/output/list 的 GR1/GR2 立即变化，
      actualOutput 按配置重算（配置不完整时为 0，employeeConfigRegular=0）。

前置：产线 state 必须是 2（停产）才能保存派工（界面同样只在 state=2 显示“保存”）。
注意：工人必须已入册（/est/hrd/employeeList 有记录），临时画布员工派工无效。

用法：
    python 脚本\\游戏-派工.py                       # 显示产线/派工/可用工人（只读）
    python 脚本\\游戏-派工.py show
    python 脚本\\游戏-派工.py restore                 # 按现有配置原样重存（幂等自检）
    python 脚本\\游戏-派工.py save --line 1 --gr1 151113493523730447,151113493523730448 --gr2 151113493523730452
    python 脚本\\游戏-派工.py auto                   # 按产线规则（传统线2普1高/自动线0普1高）自动补满

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

ROTA_DEFAULT = "127423418321195089"   # 8时制


def brief(recs):
    out = []
    for r in recs:
        out.append({
            "index": r.get("index"), "line": r.get("lineName"), "state": r.get("state"),
            "equipmentCode": r.get("equipmentCode"), "ruleRotaId": r.get("ruleRotaId"),
            "baseOutput": r.get("baseOutput"), "actualOutput": r.get("actualOutput"),
            "config": r.get("employeeConfigRegular"),
            "GR1": [(x.get("name"), x.get("id")) for x in (r.get("GR1") or [])],
            "GR2": [(x.get("name"), x.get("id")) for x in (r.get("GR2") or [])],
        })
    return out


def print_lines():
    recs, sel = E.lines()
    for r in brief(recs):
        print(f"产线{r['index']} {r['line']} state={r['state']} equipmentCode={r['equipmentCode']} "
              f"班次={r['ruleRotaId']} 基础产量={r['baseOutput']} 当前产量={r['actualOutput']} 配置={r['config']}")
        print(f"   普工GR1: {', '.join(f'{n}({i})' for n, i in r['GR1']) or '无'}")
        print(f"   高级GR2: {', '.join(f'{n}({i})' for n, i in r['GR2']) or '无'}")
    print(f"已被派工员工: {len(sel)} 人")
    return recs, sel


def workers():
    """可用工人（普通/高级）-> {GR1:[{id,name}], GR2:[...]}；employeeId 即 employeeCode"""
    j = E.js("/est/cto/employee/type/list", post_id=2)
    d = j.get("data") or {}
    out = {"GR1": [], "GR2": []}
    for lv in out:
        for w in d.get(lv) or []:
            out[lv].append({"id": str(w.get("employeeId")), "name": w.get("employeeName")})
    return out


def name_map():
    w = workers()
    return {x["id"]: x["name"] for lv in w.values() for x in lv}


def save_line(line_index, gr1_ids, gr2_ids, timeout=120):
    recs, _ = E.lines()
    line = next((r for r in recs if str(r.get("index")) == str(line_index)), None)
    if not line:
        print(f"找不到产线 index={line_index}（现有 {[r.get('index') for r in recs]}）")
        return False
    if str(line.get("state")) != "2":
        print(f"⚠️ 产线{line_index} state={line.get('state')}，不是 2（停产），界面不会允许保存派工；仍尝试发送…")
    names = name_map()
    def mk(ids):
        return [{"id": str(i), "name": names.get(str(i), "")} for i in (ids or [])]
    level_ids = json.dumps({"GR1": mk(gr1_ids), "GR2": mk(gr2_ids)}, ensure_ascii=False)
    fields = {
        "levelIds": level_ids,
        "baseOutput": str(line.get("baseOutput")),
        "dataEquipmentId": line.get("equipmentCode"),        # 关键：equipmentCode
        "ruleRotaId": line.get("ruleRotaId") or ROTA_DEFAULT,
        "userId": E.USER_ID,
        "index": str(line.get("index")),
        "applyBudgetPost": "2",
        "gameId": E.GAME_ID,
        "round": E.ROUND,
        "teamId": E.TEAM_ID,
        "ruleId": E.RULE_ID,
    }
    print(f"POST /est/cto/employee/output/save 产线{line_index}: GR1={gr1_ids} GR2={gr2_ids}")
    res = E.post_once("/est/cto/employee/output/save", fields, post_id=2, timeout=timeout)
    print("  <-", res[:300])
    ok = '"code":200' in res.replace(" ", "")
    # 回读校验（服务端可能 30-60s 才落库，最长等 30s）
    for i in range(6):
        time.sleep(5)
        recs2, _ = E.lines()
        line2 = next((r for r in recs2 if str(r.get("index")) == str(line_index)), None)
        if line2:
            got1 = [x.get("id") for x in (line2.get("GR1") or [])]
            got2 = [x.get("id") for x in (line2.get("GR2") or [])]
            if got1 == [str(x) for x in gr1_ids] and got2 == [str(x) for x in gr2_ids]:
                print(f"  ✅ 回读一致（{(i + 1) * 5}s）：GR1={[x.get('name') for x in line2.get('GR1') or []]} "
                      f"GR2={[x.get('name') for x in line2.get('GR2') or []]} "
                      f"actualOutput={line2.get('actualOutput')} config={line2.get('employeeConfigRegular')}")
                return True
    print("  ⚠️ 30s 内回读未与请求一致，请再跑 show 确认（POST 不要重复发）")
    return ok


def restore():
    """按当前 output/list 的 GR1/GR2 原样重存 —— 幂等自检，不改游戏状态"""
    recs, _ = E.lines()
    ok = True
    for r in recs:
        g1 = [str(x.get("id")) for x in (r.get("GR1") or [])]
        g2 = [str(x.get("id")) for x in (r.get("GR2") or [])]
        ok = save_line(r.get("index"), g1, g2) and ok
        time.sleep(2)
    return ok


def auto():
    """按产线规则自动补满：传统线 普2/高1，全自动线、全智能线 普0/高1"""
    rule_j = E.js("/est/cto/equipment/rule/list", {"currentPage": 1, "pageSize": 50}, post_id=2)
    rules = {}
    for r in ((rule_j.get("data") or {}).get("records") or []):
        rules[str(r.get("id"))] = {"GR1": int(r.get("GR1") or 0), "GR2": int(r.get("GR2") or 0),
                                   "name": r.get("productionLineName")}
    recs, sel = E.lines()
    avail = workers()
    used = set(sel)
    for r in recs:
        need = rules.get(str(r.get("ruleLineId")))
        if not need:
            print(f"产线{r.get('index')} 找不到规则（ruleLineId={r.get('ruleLineId')}），跳过")
            continue
        g1 = [str(x.get("id")) for x in (r.get("GR1") or [])]
        g2 = [str(x.get("id")) for x in (r.get("GR2") or [])]
        for lv, cur in (("GR1", g1), ("GR2", g2)):
            for w in avail[lv]:
                if len(cur) >= need[lv]:
                    break
                if w["id"] not in used:
                    cur.append(w["id"])
                    used.add(w["id"])
        if len(g1) < need["GR1"] or len(g2) < need["GR2"]:
            print(f"⚠️ 产线{r.get('index')} 人手不足：需要 {need['GR1']}普{need['GR2']}高，"
                  f"现有可用 {len(g1)}普{len(g2)}高")
        save_line(r.get("index"), g1, g2)
        time.sleep(2)


def main():
    ap = argparse.ArgumentParser(description="数智沙盘派工（output/save），已实测可用")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("show")
    sub.add_parser("restore")
    sub.add_parser("auto")
    p = sub.add_parser("save")
    p.add_argument("--line", required=True, help="产线 index")
    p.add_argument("--gr1", default="", help="普通工人 employeeCode，逗号分隔")
    p.add_argument("--gr2", default="", help="高级工人 employeeCode，逗号分隔")
    a = ap.parse_args()
    cmd = a.cmd or "show"
    if cmd == "show":
        print_lines()
        w = workers()
        print("\n可用工人（未考虑是否已派）:")
        for lv, lst in w.items():
            print(f"  {lv}: " + ", ".join(f"{x['name']}({x['id']})" for x in lst))
    elif cmd == "restore":
        restore()
    elif cmd == "auto":
        auto()
    elif cmd == "save":
        g1 = [x.strip() for x in a.gr1.split(",") if x.strip()]
        g2 = [x.strip() for x in a.gr2.split(",") if x.strip()]
        save_line(a.line, g1, g2)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
