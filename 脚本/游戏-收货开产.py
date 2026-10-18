# -*- coding: utf-8 -*-
"""Q3 批处理：收货 → 开产 → 缴管理费（每步回读）"""
import sys, io, os, json, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import est_common as E

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
RND = int(E.ROUND)
LOG = []


def js(path, q=None, post=1):
    return E.js(path, q, post_id=post)


def post_once(path, fields, post=1):
    d = E.post_once(path, fields, post_id=post)
    LOG.append(f"  POST {path} -> {str(d)[:180]}")
    return d


def cash():
    return (js("/est/dataBanlanceSheet/getDataBanlanceSheet").get("data") or {}).get("cash")


LOG.append(f"round={RND} 起始现金 {cash()}")
# 1) 收货
orders = (js("/est/md/orderList", {"currentPage": 1, "pageSize": 50}).get("data") or {}).get("records") or []
due = [o for o in orders if (o.get("receiveData") or 99) <= RND and o.get("status") == 0]
LOG.append(f"待收货 {len(due)} 单: " + ", ".join(f"{o.get('orderNo')}/{o.get('materialName')}x{o.get('quantity')}" for o in due))
EXTRA = {"accountDate": 0, "creator": E.USER_ID, "price": 500, "unitPrice": 500, "materialPrice": 500,
         "round": RND, "postId": 2}
for o in due:
    form = {k: o.get(k) for k in ("id", "orderNo", "materialId", "materialName", "quantity", "totalPrice",
                                  "receiveData", "status", "creditName", "debitName", "createTime", "creator",
                                  "gameId", "teamId", "round", "accountDate", "materialCode", "price",
                                  "unitPrice", "deliveryDate") if o.get(k) is not None}
    form.update({k: v for k, v in EXTRA.items() if v is not None})
    for _ in range(6):
        d = post_once("/est/md/receiveGoods", form, post=2)
        m = re.search(r'"msg":"([A-Za-z_]+) 不能为', str(d))
        if m:
            f = m.group(1)
            guesses = {"creator": E.USER_ID, "accountDate": 0, "price": 500, "unitPrice": 500,
                       "materialPrice": 500, "round": RND, "postId": 2, "teamId": E.TEAM_ID,
                       "gameId": E.GAME_ID, "id": o.get("id")}
            if f in guesses:
                form[f] = guesses[f]
                continue
        break
    time.sleep(1)
stock = (js("/est/md/stockList", {"currentPage": 1, "pageSize": 20}).get("data") or {}).get("records") or []
LOG.append("库存: " + ", ".join(f"{s.get('materialName')}x{s.get('quantity')}" for s in stock) + f" 现金 {cash()}")

# 2) 开产（两线 8 时制）
lines = ((js("/est/cto/equipment/list", {"currentPage": 1, "pageSize": 20}).get("data") or {}).get("records") or [])
prods = [{"equipmentId": ln.get("equipmentCode"), "productId": ln.get("ruleProductId")} for ln in lines]
body = {"rotaId": "127423418321195089", "equipmentProducts": json.dumps(prods),
        "dateTime": int(time.time() * 1000)}
d = post_once("/est/cto/equipment/smart/openSmartProduction", body, post=2)
time.sleep(1.5)
lines2 = ((js("/est/cto/equipment/list", {"currentPage": 1, "pageSize": 20}).get("data") or {}).get("records") or [])
LOG.append("开产后产线: " + "; ".join(f"{x.get('lineName')} state={x.get('state')} 产出={x.get('actualOutput')}" for x in lines2))

# 3) 缴管理费
fee = js("/est/ruleFee/getFeeList").get("data") or []
fid = fee[0].get("id") if fee else "127423418321195068"
d = post_once("/est/cfoAccountsPayment/paymentCash",
              {"payCash": 1500, "feeCode": "1", "id": fid, "creator": E.USER_ID}, post=4)
time.sleep(1)

bs = js("/est/dataBanlanceSheet/getDataBanlanceSheet").get("data") or {}
LOG.append(f"末态 round={bs.get('round')} 现金={bs.get('cash')} 负债={bs.get('liabilitiesTotal')} "
           f"权益={bs.get('ownerEquityTotal')} 材料={bs.get('material')} 成品={bs.get('finishedProduct')}")
bu = js("/est/cfo/budgetList").get("data") or []
LOG.append("预算: " + json.dumps([(x.get('deptType'), x.get('thisRoundBudget'), x.get('currentRoundUse')) for x in bu], ensure_ascii=False))
open(os.path.join(E.TMP, 'q3_do.log'), 'w', encoding='utf-8').write("\n".join(LOG))
print("ok")
