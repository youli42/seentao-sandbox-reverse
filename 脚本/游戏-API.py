# -*- coding: utf-8 -*-
"""数智沙盘 API 工具（只读状态 + 预算 + 开产）
用法：
  python 游戏-API.py status          # 打印赛局全状态
  python 游戏-API.py budget 70000 500000 0   # 营销/生产/人力 预算
  python 游戏-API.py startprod       # 两条产线开产（智能生产）
前提：.tmp\api\auid.txt 内有有效 auId（游戏页 qs 解码得到，2 小时过期）
"""
import sys, io, json, urllib.request, urllib.parse, time, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = r'D:\SSDWP\学校\05-创业模拟课程'
CTX = os.path.join(ROOT, r'.tmp\api\ctx.json')
AU = open(os.path.join(ROOT, r'.tmp\api\auid.txt'), encoding='utf-8').read().strip()
PROXY = os.environ.get("GAME_PROXY", "http://127.0.0.1:10808")   # 直连常超时，走本地代理
try:
    _ctx = json.load(open(CTX, encoding='utf-8'))
except Exception:
    _ctx = {}
# 所有标识都从 ctx.json 读，缺省用 261 学期第 7 组已知值
BASE = {"gameId": str(_ctx.get("gameId", "2110951798943174657")),
        "round": str(_ctx.get("round", "1")),
        "teamId": str(_ctx.get("teamId", "7")),
        "userType": "3",
        "ruleId": str(_ctx.get("ruleId", "127423418293927983")),
        "userId": str(_ctx.get("userId", "<USER_ID>")),
        "caseId": str(_ctx.get("caseId", "141326524873703438")),
        "postId": str(_ctx.get("postId", "2"))}
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}) if PROXY else urllib.request.ProxyHandler({}))


def req(method, path, query=None, body=None, retries=None):
    # POST 默认只发一次：超时可能已在服务端生效，重试会重复下单/重复借款
    if retries is None:
        retries = 4 if method == "GET" else 1
    urls = "http://sp4.chiper.top" + path + "?" + urllib.parse.urlencode({**BASE, **(query or {})}, doseq=True)
    for _ in range(retries):
        try:
            r = urllib.request.Request(urls, data=body, method=method)
            for k, v in (("Authorization", AU), ("accept-language", "zh-CN"),
                         ("locale", "zh-CN"), ("User-Agent", "Mozilla/5.0")):
                r.add_header(k, v)
            if body is not None:
                r.add_header("Content-Type", "application/x-www-form-urlencoded")
            resp = _OPENER.open(r, timeout=45)
            d = resp.read().decode("utf-8", "replace")
            if d.strip():
                return d
        except Exception:
            pass
        time.sleep(2)
    return ""


def js(path, params=None):
    try:
        return json.loads(req("GET", path, params))
    except Exception:
        return {}


def status():
    b = js("/est/dataBanlanceSheet/getDataBanlanceSheet").get("data") or {}
    print(f"现金 {b.get('cash')} 权益 {b.get('ownerEquityTotal')} 材料 {b.get('material')} 产成品 {b.get('finishedProduct')} 负债 {b.get('liabilitiesTotal')}")
    for r in (js("/est/cfo/budgetList").get("data") or []):
        print(f"预算 dept{r.get('deptType')} 本季={r.get('thisRoundBudget')} 使用={r.get('currentRoundUse')}")
    for e in ((js("/est/cto/equipment/list", {"currentPage": 1, "pageSize": 10}).get("data") or {}).get("records") or []):
        print(f"产线{e.get('index')} {e.get('lineName')} 产品={e.get('productName')} 特性={e.get('productFeatureCode')} 普工={e.get('employeeConfigRegular')} state={e.get('state')} 产出={e.get('actualOutput')}")
    for s in (js("/est/md/stockList", {"currentPage": 1, "pageSize": 20}).get("data", {}).get("records") or []):
        print(f"库存 {s.get('materialName')} x{s.get('quantity')}")
    for c in (js("/est/md/dataProductStateList").get("data", {}).get("records") or []):
        print(f"资质 {c.get('productName')} state={c.get('state')} 完成轮={c.get('performingPeriod')}")
    for c in (js("/est/md/dataIsolList").get("data", {}).get("records") or []):
        print(f"ISO {c.get('isoName')} state={c.get('state')} 完成轮={c.get('performingPeriod')}")
    for c in (js("/est/md/saleChannelList").get("data", {}).get("records") or []):
        print(f"渠道 {c.get('channelName')} state={c.get('state')} 完成轮={c.get('performingPeriod')}")
    for d in (js("/est/dataDeductionGoodwill/getList").get("data") or []):
        print(f"扣分 r{d.get('round')} {d.get('event')} -{d.get('deductionCount')}")


def budget(m, p, h):
    cur = js("/est/cfo/budgetList").get("data") or []
    plan = {1: int(m), 2: int(p), 3: int(h)}
    for r in cur:
        r["thisRoundBudget"] = plan.get(r.get("deptType"), 0)
        r.pop("editable", None)
    body = urllib.parse.urlencode({"budgetList": json.dumps(cur, ensure_ascii=False)}).encode()
    print("预算写入:", req("POST", "/est/cfo/inputBudget", None, body)[:120])
    time.sleep(1)
    for r in (js("/est/cfo/budgetList").get("data") or []):
        print(f"  回读 dept{r.get('deptType')} 本季={r.get('thisRoundBudget')}")


def startprod():
    recs = ((js("/est/cto/equipment/list", {"currentPage": 1, "pageSize": 10}).get("data") or {}).get("records") or [])
    cols = js("/est/cto/employee/column/list").get("data") or {}
    rota = (cols.get("ruleRotaList") or [{}])[0].get("id", "")
    prods = [{"equipmentId": ln.get("equipmentCode"), "productId": ln.get("ruleProductId")} for ln in recs]
    body = urllib.parse.urlencode({"rotaId": rota, "equipmentProducts": json.dumps(prods),
                                   "dateTime": int(time.time() * 1000)}).encode()
    print("开产:", req("POST", "/est/cto/equipment/smart/openSmartProduction", None, body)[:300])


LOAN_LOG = os.path.join(ROOT, r'.tmp\api\last_borrow.json')


def loans_snapshot(retries=6):
    """读贷款（服务端慢，多试几次）"""
    for _ in range(retries):
        d = (js("/est/cfoLoan/getLoanList").get("data") or {})
        lst = d.get("list")
        if lst is not None:
            return lst
        time.sleep(3)
    return []


def print_loans():
    lst = loans_snapshot()
    tot = sum((l.get("loanCash") or 0) for l in lst)
    ti = sum((l.get("loanInterest") or 0) for l in lst)
    for l in lst:
        print(f"  贷款 {l.get('loanName')} 本金{l.get('loanCash')} 息{l.get('loanInterest')} "
              f"{l.get('loanStartTime')}->{l.get('loanEndTime')}")
    print(f"  合计本金 {tot}｜合计利息 {ti}")


def borrow(code, amount):
    """借款：本轮已有同 code 就跳过；POST 只发一次；空响应要等 40s 再回读确认（防重复借款）"""
    lst = loans_snapshot()
    same = [l for l in lst if l.get("loanStartTime") == int(BASE["round"]) and l.get("loanName", "").startswith(
        {"DK1": "直接融资", "DK2": "短期银行", "DK3": "长期银行"}.get(code, code))]
    if same:
        print(f"本轮已有 {code} 贷款 {[l.get('loanCash') for l in same]}，跳过借款")
        return
    # 冷却：上次借款尝试 180s 内不再发（服务端可能延迟生效）
    try:
        last = json.load(open(LOAN_LOG, encoding='utf-8'))
        if time.time() - last.get("ts", 0) < 180 and last.get("round") == BASE["round"]:
            print(f"⚠️ 上次借款尝试在 {int(time.time()-last['ts'])}s 前（{last.get('code')} {last.get('amount')}），"
                  f"服务端可能已生效。先手动跑 loans 确认，不要重复借款。")
            return
    except Exception:
        pass
    open(LOAN_LOG, 'w', encoding='utf-8').write(json.dumps(
        {"ts": int(time.time()), "round": BASE["round"], "code": code, "amount": amount}))
    body = urllib.parse.urlencode({"loanCode": code, "loanCash": amount, "creator": BASE["userId"]}).encode()
    resp = req("POST", "/est/cfoLoan/saveLoan", None, body)
    print(f"借款 {code} {amount} 返回: {resp[:120] if resp else '(空响应=可能超时，勿立即重发)'}")
    # 空响应 → 最多等 40s 确认是否已落库
    for i in range(8):
        lst = loans_snapshot(retries=1)
        hit = [l for l in lst if l.get("loanStartTime") == int(BASE["round"])]
        if hit:
            print(f"  回读确认({(i+1)*5}s): " + ", ".join(f"{l.get('loanName')} {l.get('loanCash')} 息{l.get('loanInterest')} "
                                                    f"{l.get('loanStartTime')}->{l.get('loanEndTime')}" for l in hit))
            return
        time.sleep(5)
    print("  40s 内未回读到贷款：把 loans 结果再确认一次再决定是否重试")


def setctx(round_no=None, post=None):
    """更新 ctx.json（换季后必须改 round，否则接口全错）"""
    c = dict(_ctx)
    if round_no:
        c["round"] = str(round_no)
    if post:
        c["postId"] = str(post)
    open(CTX, 'w', encoding='utf-8').write(json.dumps(c, ensure_ascii=False))
    print("ctx ->", c, "（重新运行脚本生效）")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        status()
    elif cmd == "budget":
        budget(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "startprod":
        startprod()
    elif cmd == "borrow":
        borrow(sys.argv[2], int(sys.argv[3]))
    elif cmd == "loans":
        print_loans()
    elif cmd == "ctx":
        setctx(sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3] if len(sys.argv) > 3 else None)
    else:
        print("用法: status | budget <营销> <生产> <人力> | startprod | borrow <DK1|DK2|DK3> <金额> | ctx <round> [postId]")
