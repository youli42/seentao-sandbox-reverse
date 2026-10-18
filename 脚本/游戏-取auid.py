# -*- coding: utf-8 -*-
"""取 auId：从 Edge 历史里抓最新 estweb/home 游戏页 URL → 解 qs → 写 auid.txt / 更新 ctx.json
用法：
  python 脚本\游戏-取auid.py            # 只刷新 auId（+ 标记过期时间）
  python 脚本\游戏-取auid.py --round 1  # 同时把 ctx.json 的 round 改成 1
前提：浏览器已进入实践游戏页（estweb/home?qs=...），Edge 历史已落盘（通常几秒内）。
"""
import sys, io, os, re, json, time, base64, shutil, sqlite3, urllib.parse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ROOT = r'D:\SSDWP\学校\05-创业模拟课程'
TMP = os.path.join(ROOT, r'.tmp\api')
HIST = os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Microsoft\Edge\User Data\Default\History')
COPY = os.path.join(TMP, 'EdgeHistory.db')
AUID = os.path.join(TMP, 'auid.txt')
CTX = os.path.join(TMP, 'ctx.json')


def latest_game_url():
    for _ in range(3):
        try:
            shutil.copyfile(HIST, COPY)
        except Exception:
            pass
        try:
            c = sqlite3.connect(COPY)
            row = c.execute("select url,last_visit_time from urls where url like '%estweb/home%' "
                            "order by last_visit_time desc limit 1").fetchone()
            c.close()
            if row:
                return row[0], row[1]
        except Exception as e:
            print('读取历史失败:', e)
        time.sleep(2)
    return None, 0


def decode_qs(url):
    qs = url.split('qs=', 1)[1]
    raw = base64.b64decode(urllib.parse.unquote(qs)).decode('utf-8', 'replace')
    return json.loads(urllib.parse.unquote(raw))


def main():
    want_round = None
    if '--round' in sys.argv:
        want_round = sys.argv[sys.argv.index('--round') + 1]
    url, visit = latest_game_url()
    if not url:
        print('未找到 estweb/home 历史记录：先在浏览器里进入实践游戏页')
        return 1
    d = decode_qs(url)
    au = d.get('auId') or ''
    if not au:
        print('qs 里没有 auId:', list(d.keys()))
        return 1
    open(AUID, 'w', encoding='utf-8').write(au)
    try:
        ctx = json.load(open(CTX, encoding='utf-8'))
    except Exception:
        ctx = {}
    ids = {'gameId': 'trainId', 'ruleId': 'ruleId', 'userType': 'userType',
           'teamId': 'groupId', 'userId': 'userId'}
    for k, qk in ids.items():
        if d.get(qk) is not None:
            ctx[k] = str(d.get(qk))
    if want_round:
        ctx['round'] = str(want_round)
    open(CTX, 'w', encoding='utf-8').write(json.dumps(ctx, ensure_ascii=False))
    # 解析 JWT 过期时间
    exp = None
    try:
        payload = au.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload)).get('exp')
    except Exception:
        pass
    exp_s = time.strftime('%m-%d %H:%M:%S', time.localtime(exp)) if exp else '?'
    left = int(exp - time.time()) if exp else 0
    print(f"已写 auid.txt len={len(au)} 过期={exp_s} 剩余={left//60}分{left%60}秒")
    print(f"qs: round={d.get('round')} role={d.get('currentRoleType')} postIds={d.get('postIds')} "
          f"gameId={d.get('trainId')} ruleId={d.get('ruleId')} classId={d.get('classId')} userId={d.get('userId')}")
    print("ctx.json ->", json.dumps(ctx, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
