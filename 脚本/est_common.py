# -*- coding: utf-8 -*-
"""数智沙盘 est API 公共模块（被 游戏-派工.py / 游戏-发薪.py / 其他脚本复用）

能力：
1. 读 .tmp\\api\\ctx.json（gameId/round/teamId/ruleId/userId）与 .tmp\\api\\auid.txt（Authorization）
2. auId 过期（2 小时）自动续期：用平台登录页内置 RSA 公钥加密密码 → POST /login → 响应头 authorization
   （账号密码见 Agent.md：525营销 <ACCOUNT> / <PASSWORD>；其它岗位账号密码 <PASSWORD>）
3. GET（可重试、401 自动续期重试）与 POST（**只发一次、绝不重试**）封装
4. 代理固定 http://127.0.0.1:10808，只访问 http://sp4.chiper.top

为什么不再从 Edge 历史抓 auId：平台登录接口 /login 用账号密码即可换新 auId，
不用浏览器、不用验证码、不会顶掉平台会话。原 游戏-取auid.py 仍可用（需浏览器进实践）。

用法：
    import est_common as E
    E.ensure_auid()                 # 过期则自动重登
    j = E.js("/est/hrd/employeeList", {"page": 1, "size": 50}, post_id=3)
    r = E.post_once("/est/hrd/payday", {"creator": E.USER_ID, ...}, post_id=3)
"""
import base64
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request

def _find_root():
    """向上找包含 .tmp\\api\\ctx.json 的工作目录（脚本复制到 .tmp\\api\\脚本 也能用）"""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isfile(os.path.join(d, ".tmp", "api", "ctx.json")):
            return d
        d = os.path.dirname(d)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


ROOT = _find_root()
TMP = os.path.join(ROOT, ".tmp", "api")
CTX_PATH = os.path.join(TMP, "ctx.json")
AUID_PATH = os.path.join(TMP, "auid.txt")
PROXY = os.environ.get("GAME_PROXY", "http://127.0.0.1:10808")
BASE_URL = "http://sp4.chiper.top"
DEFAULT_CASE_ID = "141326524873703438"

# Agent.md 里的账号
DEFAULT_USER = "<ACCOUNT>"
DEFAULT_PWD = "<PASSWORD>"

# 平台登录页（/sworldweb/p__Login.44b8fab8.async.js）里的 RSA 公钥
_RSA_PUB_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAree/kbLiNvfnFqf9+0LvjkGeuQ04Qto8dQgasV9DO6WkasZP8NbNJUyibC5WX6"
    "JUxjKPTIGe3FwwEgnWcHu7CpJEFzLiqoO9Pi8eh7zyvzMpBUg8j/+BYzFOF3ao5Jl1ufYzHMnfLn4zBoNkR6jayP7/awQYoANRdrZ1KsYHIa"
    "5W/ardJaTgRh9r0Oxd+WottZkSNH7Tp7HGuc70QG1mAa/vZbaq44rMH4iXDaOkqqlPmyFl7dtBTvojfObeW2j+FX4L8xn46HA/MmpbIhd2j8"
    "QHlLUiCheVuJyDlTBP/hrtdnpLIumO0MI6LeOj7c+J+ft2NLiBXrKV/qpyjYCw5wIDAQAB"
)

_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}) if PROXY else urllib.request.ProxyHandler({})
)

try:
    CTX = json.load(open(CTX_PATH, encoding="utf-8"))
except Exception:
    CTX = {}

GAME_ID = str(CTX.get("gameId", "2110951798943174657"))
ROUND = str(CTX.get("round", "2"))
TEAM_ID = str(CTX.get("teamId", "7"))
RULE_ID = str(CTX.get("ruleId", "127423418293927983"))
USER_ID = str(CTX.get("userId", "<USER_ID>"))
USER_TYPE = str(CTX.get("userType", "3"))
CASE_ID = str(CTX.get("caseId", DEFAULT_CASE_ID))


# ---------------------------------------------------------------- RSA / 登录
def _read_len(b, i):
    l = b[i]
    i += 1
    if l & 0x80:
        n = l & 0x7F
        l = int.from_bytes(b[i:i + n], "big")
        i += n
    return l, i


def _parse_rsa_pub(der_b64):
    der = base64.b64decode(der_b64)
    _, i = _read_len(der, 1)          # outer SEQUENCE
    l2, j = _read_len(der, i + 1)     # AlgorithmIdentifier
    j += l2 + 1                       # + BIT STRING tag
    l3, k = _read_len(der, j)
    k += 1                            # unused bits
    inner = der[k:k + l3 - 1]
    _, m = _read_len(inner, 1)        # RSAPublicKey SEQUENCE
    ln, m = _read_len(inner, m + 1)   # modulus
    n = int.from_bytes(inner[m:m + ln], "big")
    m += ln
    le, m = _read_len(inner, m + 1)   # exponent
    e = int.from_bytes(inner[m:m + le], "big")
    return n, e


_N, _E = _parse_rsa_pub(_RSA_PUB_B64)


def rsa_encrypt(text: str) -> str:
    """PKCS#1 v1.5 加密（等价前端 JSEncrypt），返回 base64"""
    msg = text.encode("utf-8")
    k = (_N.bit_length() + 7) // 8
    ps = bytes(secrets.choice(range(1, 256)) for _ in range(k - len(msg) - 3))
    em = b"\x00\x02" + ps + b"\x00" + msg
    return base64.b64encode(pow(int.from_bytes(em, "big"), _E, _N).to_bytes(k, "big")).decode()


def platform_login(login_name: str = DEFAULT_USER, password: str = DEFAULT_PWD):
    """平台登录，返回 (auId, 响应JSON)；失败返回 (None, 响应JSON)"""
    boundary = "----DSHFormBoundary" + secrets.token_hex(8)
    fields = [("loginName", login_name), ("password", rsa_encrypt(password))]
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields]
    body = ("".join(parts) + f"--{boundary}--\r\n").encode()
    r = urllib.request.Request(BASE_URL + "/login", data=body, method="POST")
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    r.add_header("User-Agent", "Mozilla/5.0")
    r.add_header("Accept", "application/json, text/plain, */*")
    r.add_header("Origin", "https://sp4.chiper.top")
    r.add_header("Referer", "https://sp4.chiper.top/sworldweb/login")
    try:
        resp = _OPENER.open(r, timeout=40)
        raw = resp.read().decode("utf-8", "replace")
        return resp.headers.get("authorization"), (json.loads(raw) if raw.strip() else {})
    except Exception as e:
        return None, {"err": repr(e)[:160]}


# ---------------------------------------------------------------- token
def _jwt_payload(tok):
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return {}


def token_exp(tok):
    return _jwt_payload(tok).get("exp") or 0


def auid_from_history():
    """从 Edge 历史里的最新 estweb/home?qs=... 提取浏览器会话 auId（不登录、不顶号）
    平台是单会话：禁止用 /login 顶掉浏览器，否则浏览器一重登又顶掉脚本，来回互踢触发风控。"""
    try:
        import shutil
        import sqlite3
        hist = os.path.join(os.environ.get('LOCALAPPDATA', ''),
                            r'Microsoft\Edge\User Data\Default\History')
        copy = os.path.join(TMP, 'EdgeHistory.db')
        shutil.copyfile(hist, copy)
        c = sqlite3.connect(copy)
        row = c.execute("select url from urls where url like '%estweb/home%' "
                        "order by last_visit_time desc limit 1").fetchone()
        c.close()
        if not row:
            return None
        qs = row[0].split('qs=', 1)[1]
        d = json.loads(urllib.parse.unquote(base64.b64decode(urllib.parse.unquote(qs)).decode('utf-8', 'replace')))
        return d.get('auId')
    except Exception:
        return None


def auid(force_refresh=False):
    """读取 auid.txt；过期/失效时**优先从浏览器历史提取**；默认绝不自动密码登录。"""
    tok = ""
    try:
        tok = open(AUID_PATH, encoding="utf-8").read().strip()
    except Exception:
        tok = ""
    if not force_refresh and tok and token_exp(tok) - time.time() > 120:
        return tok
    new = auid_from_history()
    if new and token_exp(new) - time.time() > 120:
        if new != tok:
            open(AUID_PATH, "w", encoding="utf-8").write(new)
            print(f"[auid] 已从浏览器历史提取 token exp="
                  f"{time.strftime('%H:%M:%S', time.localtime(token_exp(new)))}", file=sys.stderr)
        return new
    if not force_refresh and tok and token_exp(tok) - time.time() > 120:
        return tok
    if os.environ.get("EST_ALLOW_PWD_LOGIN") == "1":
        new2, resp = platform_login()
        if not new2:
            raise RuntimeError(f"auId 续期失败：{resp}")
        open(AUID_PATH, "w", encoding="utf-8").write(new2)
        print(f"[auid] 已用密码登录续期（会顶掉浏览器会话！）", file=sys.stderr)
        return new2
    raise RuntimeError("auId 失效且浏览器历史里也没有新 token：请在浏览器重新进入实践游戏页后重试"
                       "（禁止自动密码登录，避免与浏览器互踢触发风控；确需密码登录请设 EST_ALLOW_PWD_LOGIN=1）")


# ---------------------------------------------------------------- 请求
def _common(post_id):
    q = {"gameId": GAME_ID, "round": ROUND, "teamId": TEAM_ID, "userType": USER_TYPE,
         "ruleId": RULE_ID, "userId": USER_ID, "caseId": CASE_ID}
    if post_id is not None:
        q["postId"] = str(post_id)
    return q


def _open(method, path, query, body, timeout, tok):
    url = BASE_URL + path + "?" + urllib.parse.urlencode(query, doseq=True)
    r = urllib.request.Request(url, data=body, method=method)
    r.add_header("Authorization", tok)
    r.add_header("User-Agent", "Mozilla/5.0")
    r.add_header("locale", "zh-CN")
    r.add_header("accept-language", "zh-CN,zh;q=0.9")
    if body is not None:
        r.add_header("Content-Type", "application/x-www-form-urlencoded")
    return _OPENER.open(r, timeout=timeout).read().decode("utf-8", "replace")


def get(path, query=None, post_id=None, retries=4, timeout=40):
    """GET，可重试；401 自动续期后重试（含 HTTP 401 与 业务code=401 两种）"""
    q = {**_common(post_id), **(query or {})}
    last = ""
    for i in range(retries):
        try:
            d = _open("GET", path, q, None, timeout, auid())
            if d.strip():
                j = json.loads(d)
                # 平台常用 HTTP200 + {"code":401,"msg":"登陆已失效"}，必须识别
                if isinstance(j, dict) and j.get("code") == 401:
                    last = "code401"
                    try:
                        auid(force_refresh=True)
                    except Exception as e:
                        last = "401且无法续期:" + str(e)[:80]
                        break
                    time.sleep(1.0)
                    continue
                return j
            last = "(空响应)"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                try:
                    auid(force_refresh=True)
                except Exception as e2:
                    last = "401且无法续期:" + str(e2)[:80]
                    break
                continue
            last = f"HTTP{e.code}"
        except Exception as e:
            last = repr(e)[:120]
        time.sleep(1.5)
    return {"_err": last}


def js(path, query=None, post_id=None, retries=4):
    """GET 并返回 JSON（失败返回 {"_err": ...}）"""
    return get(path, query, post_id, retries)


def post_once(path, fields, post_id=None, query=None, timeout=120):
    """POST：**只发一次，绝不重试**（超时也可能已生效）。
    唯一例外：明确返回 code=401（登录失效，服务端未处理）→ 续期后安全重发一次。"""
    q = {**_common(post_id), **(query or {})}
    tok = auid()   # 发前确保 token 有效（不消耗请求）
    body = urllib.parse.urlencode(fields, doseq=True).encode()
    try:
        r = _open("POST", path, q, body, timeout, tok)
    except Exception as e:
        return "EXC:" + repr(e)[:200]
    if r and '"code":401' in r:
        try:
            auid(force_refresh=True)
        except Exception:
            return r
        try:
            return _open("POST", path, q, body, timeout, auid())
        except Exception as e:
            return "EXC:" + repr(e)[:200]
    return r


# ---------------------------------------------------------------- 常用读取
def lines():
    """产线（output/list）-> (records, selectedEmployeeIds)"""
    j = js("/est/cto/employee/output/list", post_id=2)
    d = j.get("data") or {}
    return (((d.get("pageData") or {}).get("records")) or []), (d.get("selectedEmployeeIds") or [])


def employees(round_no=None):
    """本回合在职员工列表（hrd/employeeList）-> (records, flag, employeeCodes)"""
    q = {"page": 1, "size": 50}
    if round_no:
        q["round"] = str(round_no)
    j = js("/est/hrd/employeeList", q, post_id=3)
    d = j.get("data") or {}
    recs = ((d.get("pages") or {}).get("records")) or []
    return recs, d.get("flag"), [str(x) for x in (d.get("employeeCodes") or [])]


def cash():
    d = (js("/est/dataBanlanceSheet/getDataBanlanceSheet", post_id=4).get("data") or {})
    return d.get("cash")


if __name__ == "__main__":
    tok = auid()
    p = _jwt_payload(tok)
    print("auid ok, exp", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.get("exp", 0))))
    print("ctx:", json.dumps(CTX, ensure_ascii=False))
    recs, flag, codes = employees()
    print(f"employees={len(recs)} flag={flag}")
    ls, sel = lines()
    print("lines:", [(x.get("index"), [w.get("name") for w in (x.get("GR1") or [])],
                     [w.get("name") for w in (x.get("GR2") or [])], x.get("actualOutput")) for x in ls])
    print("cash:", cash())
