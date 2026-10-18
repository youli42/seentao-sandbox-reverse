# 数智沙盘平台接口文档（sp4.chiper.top）

> 2026-10-18 整理｜来源：平台 OpenAPI（`.tmp/api/openapi.json`，347 路径/368 操作）＋ 第 7 组正式局实测。
> 目的：给后续同学/接手者一份**可直接照抄**的接口清单与踩坑记录。

## 目录
| 文件 | 内容 |
|---|---|
| `01-接口总览.md` | 全部 368 个操作，按模块（tag）分组的表格，含"实测"状态 |
| `02-核心接口详解.md` | 常用接口的**准确报文**、字段、响应与注意事项 |
| `03-错误码与坑.md` | 错误码对照表、`200 假成功`、空响应、单会话风控、窗口类操作 SOP |
| `openapi-paths.csv` | 机器可读清单（method/path/tags/summary/verified/params） |
| `附-openapi.json` | 平台原始 OpenAPI 规格（可用于生成 SDK/客户端） |

## 快速开始（三步）
```python
import sys, os
sys.path.insert(0, r'<工作区>\脚本')
import est_common as E            # 已封装：代理/公共参数/auId/GET 重试

E.ROUND = '5'                     # 当前季（必须与游戏一致，见页面 qs 的 round）
d = E.js('/est/dataBanlanceSheet/getDataBanlanceSheet', post_id=4)   # 读：资产负债表
print(d['data']['cash'])
```

## 必备约定
1. **代理**：所有请求必须走 `http://127.0.0.1:10808`（xray/v2rayN），直连超时。
2. **鉴权**：Header `Authorization: <auId>`（**不加 Bearer**），2 小时过期。
   - ⚠️ 平台是**单会话**：禁止用密码 `/login` 续期（会顶掉浏览器，互踢触发风控）；请用 `脚本\游戏-取auid.py` 从 Edge 历史最新 `estweb/home?qs=` 提取浏览器 auId。
3. **公共参数**（query，几乎所有 `/est/*` 都要）：`gameId / round / teamId / userType=3 / ruleId / userId / caseId / postId`
   - `postId`＝岗位：1 营销｜2 生产｜3 人力｜4 财务
4. **读写**：只读用 `GET`（参数放 query）；写用 `POST`（`application/x-www-form-urlencoded`）。
   - 多数写接口参数放 **query**（如预算、报表、竞单）；放 body 可能"200 假成功"。
5. **POST 永不自动重试**：超时/空响应可能是服务端仍在处理，等 30–60s 回读后再决定。
6. **按 round 过滤**：只读接口带当前 `round`，否则读到历史快照。

## 常用入口
| 用途 | 接口 |
|---|---|
| 赛局轮次/状态 | `GET /sworld/training/getById?id=<gameId>` |
| 资产负债/现金 | `GET /est/dataBanlanceSheet/getDataBanlanceSheet` |
| 产线/派工 | `GET /est/cto/equipment/list`、`GET /est/cto/employee/output/list` |
| 预算 | `GET /est/cfo/budgetList`、`POST /est/cfo/inputBudget?budgetList=<JSON>` |
| 发薪 | `GET /est/hrd/employeeList` → `GET /est/hrd/paydayCash` → `POST /est/hrd/payday` |
| 竞单 | `GET /est/board/temp/market/ruleOrder/list` → `POST /est/cooDealerOrderStorage/saveOrder` |
| 评分 | `GET /est/score/getTeamScoreList` |
| 年报 | `GET/POST /est/cfoReport/*`（仅年末轮可交，见 02） |

## 免责
- 接口来自平台前端逆向与实测，**平台版本升级后可能失效**；写操作前先"读前置"，操作后必须"回读校验"。
- 教师端（GM）接口（`/est/gm*`）学生账号可用性/权限未经完整验证，请勿在正式局随意调用。
