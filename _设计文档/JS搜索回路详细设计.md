# JS 搜索回路详细设计（match_agent · 搜索循环）

> 定位：`4_大改造架构设计-v2.0.md §2`（JS-Agent → match_agent）的子设计文档，聚焦**搜索回路**（decide → execute → evaluate → brake_check）的 API 调用逻辑与错误处理机制。
> 配套：`JS-Agent_改造设计.md`（改造总览）｜`4_大改造架构设计-v2.0.md §2.2-2.4`（目标图/节点/State）。
> 状态：**设计草案**——基于现状代码（`app/agent/loop.py` 搜索段、`app/plugins/search.py`、`app/core/llm.py`、`app/plugins/fetch.py`）逆向设计，待讨论定稿。

---

## 1. 现状与改造动机

### 1.1 现状（写死 while，`loop.py` ③ 搜索段）

```
while rounds < max_rounds:
    pending = [q for q in queries if q not in executed]
    if not pending: break
    rounds += 1
    for q in pending[:2]:              # 每轮固定 2 条 query，顺序执行
        resp = search_plugin.search(q, num=8)
        # 全部后端失败 → 重试 2 次（sleep 6s）
        # 每条结果 → _structure_batch（LLM 结构化洗涤）→ 收录 entries
    # 收敛：连续 2 轮无新增 → break；达标提前 break
```

**问题**：
1. **策略固定**：query 按规划顺序机械执行，不根据本轮结果动态调整（某条 query 收获大 → 继续深挖；收获为零 → 换角度）
2. **渠道固定**：不感知"当前 query 适合哪个后端"（招聘平台类 query 用百度/360 命中率高，官网类用 Bing/DDG 更稳）
3. **收录判定一刀切**：`_structure_batch` 洗涤后直接收录，无"新不新/好不好"评估，垃圾结果也进池
4. **刹车机械**：只有"连续 2 轮无新增"与"达标提前停"两个粗糙闸门

### 1.2 改造目标（Agent 化）

```
decide（LLM 决策下一步）→ execute（执行搜索）→ evaluate（LLM 评估结果）→ brake_check（五闸门刹车）
```

LLM 只在 `decide` 与 `evaluate` 两个决策点介入；`execute`/`brake_check` 保持确定性代码——**决策交给 LLM，执行与刹车交给规则**。

---

## 2. 回路状态机

### 2.1 搜索子状态（挂载于 MatchState）

```python
class SearchLoopState(TypedDict, total=False):
    queries: list[dict]          # 种子 query（planner 产出）+ 回路新增
    executed: set[str]           # 已执行 query（去重）
    entries: list[dict]          # 已收录条目（摘要化）
    round_stats: list[dict]      # 每轮 {query, backend, found, new, kept}（decide 的输入）
    rounds: int
    budget_left: int             # 剩余预算（token/轮数折算）
    trace: list[dict]            # 全量行动日志（行动/结果/决策理由）
    decision: dict               # 决策器输出（当前轮）
    brake_reason: str            # 收敛原因（trace/报告用）
```

### 2.2 每轮流程

```
① decide   → 输出 {action, params, reason}
② execute  → 执行搜索（后端映射 + 回退链 + 重试）→ raw_items
③ evaluate → 评估 novelty/quality → keep/discard 过滤 → 收录 entries
④ brake_check → 五闸门 → continue / converge
```

### 2.3 动作空间（decide 输出）

| 动作 | 含义 | 参数 | 与现状对应 |
|---|---|---|---|
| `rewrite_query` | 改写/新增 query（换角度、扩缩小范围） | `query`（含城市注入） | pending[:2] 顺序执行 |
| `switch_channel` | 切渠道（招聘平台/官网/社区）或指定后端 | `channel` / `backend` | 无（现状固定链） |
| `deep_dive` | 对高价值 query 深挖（变体/翻页/更多结果） | `base_query`, `variant` | ⑥ 扩散 |
| `expand` | 基于 top 岗位扩散同类搜索 | `seed_entry` | ⑥ 扩散（模板 query） |
| `converge` | 认为已收敛，结束循环 | — | 现状收敛条件 |

> 决策约束（确定性护栏）：`converge` 必须同时满足 `rounds >= min_search_rounds` 且收录数达标，否则判为非法决策强制 `continue`。

---

## 3. 节点设计

### 3.1 decide —— LLM 搜索决策器

**API 调用**：`llm.chat_json(DECIDE_SYSTEM, user_context, provider_id, model, max_tokens=800)`

**输入（user_context）**：
```
- 画像卡摘要（城市/技能线/学历）
- 本轮 round_stats：已执行 query 清单 + 每条收获（found/new/kept）
- 当前收录数与缺口（对照 max_results × 2 目标）
- 预算剩余（budget_left）
```

**输出 schema**：
```json
{"action": "rewrite_query|switch_channel|deep_dive|expand|converge",
 "params": {"query": "...", "channel": "招聘平台|官网|社区", "backend": "百度|360|Bing|...",
            "base_query": "...", "variant": "...", "seed_entry": "..."},
 "reason": "决策理由（≤50字）"}
```

**错误处理**：
- `chat_json` 抛 `LLMError` / 解析失败 → **规则降级决策器**：按"未执行 query 顺序执行 → 全执行完 → 收敛"的机械策略决策（等价于现状），并记 `trace[].degraded=true`
- 决策 schema 非法（action 不在枚举 / converge 不满足护栏）→ 视为非法，本次按规则降级决策执行，不阻塞循环

### 3.2 execute —— 搜索执行

**输入**：`decision.params`（query/channel/backend 偏好）
**输出**：`raw_items`（含 backend 名）+ `used_backends`

**渠道→后端偏好映射**：

| 决策渠道 | 首选后端 | 理由 |
|---|---|---|
| 招聘平台 | 百度 → 360 → Playwright | 大陆可达、招聘页命中率高 |
| 官网 | Bing → DDGS → 百度 | 官网查询对垃圾结果敏感，优先干净源 |
| 社区 | 百度 → 360 → Bing | 覆盖知乎/CSDN 等技术社区 |

> `backend` 显式指定时：仅在该后端可用的前提下尝试它，失败立即回退链兜底（不跳过回退）。

**API 调用**：`search_plugin.search(query, num=8)` → `{"results", "backend"}`

**重试逻辑（保留现状 + 加固）**：
```
while not results and retry < 2 and resp.get("error"):
    retry += 1
    time.sleep(6)                    # 冷却限流窗口
    resp = search_plugin.search(query, num=8)
```
- 重试仅针对"全部后端失败"（`error` 存在）；单后端失败由回退链处理，不触发重试
- 每后端失败自动冷却 120s（`SearchPlugin.COOLDOWN_SECONDS`），冷却内跳过

### 3.3 evaluate —— LLM 结果评估器

**API 调用**：`llm.chat_json(EVALUATE_SYSTEM, batch_json, provider_id, model, max_tokens=2000)`

**输入**：本轮 `raw_items`（title/url/snippet/date 批量）
**输出**：
```json
{"items": [
  {"index": 0, "novelty": "new|seen|duplicate", "quality": "high|medium|low",
   "keep": true, "reason": "..."}
]}
```

**收录规则**：
- `keep=true` 且 `novelty != duplicate` → 收录（进 entries）
- `novelty=seen`（URL 已存在但信息更全）→ 合并更新（不新增）
- `quality=low` 且非招聘页 → discard

**错误处理（降级为规则评估）**：
- LLM 失败 / 解析失败 → 规则评估：`novelty` 用 URL 去重（`scrub.dedupe` 现有逻辑），`quality` 用 is_job 洗涤标记（`_structure_batch` 降级输出），`keep` = is_job=true
- **evaluate 降级不阻塞循环**（记 `trace[].eval_degraded=true`）

### 3.4 brake_check —— 五闸门刹车

| 闸门 | 条件 | 动作 |
|---|---|---|
| G1 轮数上限 | `rounds >= max_search_rounds`（strict=10） | converge |
| G2 连续无新增 | `no_new_rounds >= 2` 且 `rounds >= min_search_rounds`（strict=3） | converge |
| G3 预算上限 | `budget_left <= 0`（token 折算） | converge |
| G4 query 去重 | 全部 query 已执行且无新 action 产出 | converge |
| G5 LLM 降级计数 | `degraded_decide >= 3` 连续（决策器持续失败） | converge（防死循环） |

**G1-G5 全为确定性代码**（无 LLM），保证回路必有终点。

---

## 4. 具体 API 调用逻辑

### 4.1 LLM API（`core/llm.py::chat_json`）

**端点**：按厂商 `PROVIDERS[provider_id].base_url`（15 家预设，OpenAI 兼容协议，如 DeepSeek `https://api.deepseek.com/v1/chat/completions`）

**请求体**：
```json
{
  "model": "<resolved_model>",
  "messages": [
    {"role": "system", "content": "<SYSTEM>"},
    {"role": "user", "content": "<user_context>"}
  ],
  "temperature": 0.2,
  "max_tokens": 800,
  "response_format": {"type": "json_object"},   // json_mode 厂商自动附加
  "thinking": {"type": "disabled"}               // disable_thinking 厂商自动附加（防推理占 token 截断）
}
```

**响应解析**：`choices[0].message.content` → 剥离 ``` 代码围栏 → `json.loads` → 返回 `(obj, resp_meta)`（含 provider/model/usage/elapsed_s）

**错误分类与处理**：

| 错误 | 触发点 | 处理 |
|---|---|---|
| `ProviderNotConfiguredError` | 无可用 Key | 致命（前置 `test_provider` 自检可避免） |
| `LLMError`（HTTPError） | HTTP 4xx/5xx | 上层（decide/evaluate）降级规则策略 |
| `LLMError`（URLError） | 网络不可达 | 上层降级；连续 3 次 → 记 degraded 计数 |
| `LLMError`（解析失败） | JSON 不合法/为空 | 上层降级 |
| 输出为空 | 推理思考占满 max_tokens | 上层降级（disable_thinking 已尽量规避） |

### 4.2 搜索后端 API（`plugins/search.py`）

| 后端 | 端点 | 关键参数 | 超时 | 解析要点 | 主要失败模式 |
|---|---|---|---|---|---|
| 智谱 web_search | `https://open.bigmodel.cn/api/paas/v4/tools/web_search_pro` | `search_engine=search_std` / `search_query` / `max_result≤10` / `tools[].web_search` | 45s | `choices[].message.tool_calls[].search_result[]` → title/link/content/date | 无 GLM Key |
| Tavily | `https://api.tavily.com/search` | `api_key` / `query` / `max_results≤10` / `search_depth=advanced` | 45s | `results[]` → title/url/content/published_date | 无 Tavily Key |
| 百度 | `https://www.baidu.com/s?wd=<q>&ie=utf-8` | GET + Chrome TLS 指纹（curl_cffi，未装降级 urllib） | 30s | 按 `result c-container` 块切分；真实链接优先取 `mu` 属性（绕过跳转）；摘要取 `summaryData.generalLines[].text` | **安全验证页**（`len<20000` 或含"安全验证"）→ RuntimeError → 冷却 120s |
| 360 | `https://m.so.com/s?q=<q>`（移动端优先） | GET | 30s | 移动端 `a.alink > h3.res-title + p.g-main.summary`；`m.so.com/jump?u=` 解真实链接 | 移动端被拦 → 桌面端 `www.so.com/s` 兜底；"访问异常" → RuntimeError → 冷却 |
| DDGS | `https://html.duckduckgo.com/html/?q=<q>` | GET | 8s | `a.result__a` 正则；`uddg=` 解真实链接 | 国内不可达（连接超时）→ 冷却 |
| Bing | `https://cn.bing.com/search?q=<q>` | GET + UA/Accept-Language | 30s | `li.b_algo` → h2>a + p 摘要 | 反爬降级（结果质量差，仅官网类兜底） |
| Playwright | 真实 Chrome 依次访问 百度→360→Bing | 浏览器无头 | 20s/引擎 | `h3 a` / `li.b_algo h2 a` 选择器；反爬页按 title 快速跳过 | 未安装 chromium（~150MB）→ 不可用 |

**统一返回**：`SearchPlugin.search(query, num)` → `{"results": [{title,url,snippet,date}], "backend": "百度"}`；全失败 → `{"results": [], "backend": "全部失败", "error": "<last_err>"}`

### 4.3 正文抓取 API（deep_judge 深判 / `plugins/fetch.py`）

| 通道 | 实现 | 优先级 | 失败处理 |
|---|---|---|---|
| Jina Reader | `GET https://r.jina.ai/<url>` | ① | 超时/空 → ② |
| Trafilatura | 本地 `fetch_url` + `extract` | ② | 异常 → ③ |
| urllib 直连 | HTML → `_html_to_text`（去 script/style + 剥离标签） | ③ | 异常 → 返回 failed |
| Playwright | 浏览器渲染（备注，深判暂不启用） | ④ | — |

> 灰区防护：招聘平台主机（`_is_grey`，如 zhipin/liepin/boss）不抓正文，避免违反站点规则——深判跳过。

---

## 5. 错误处理机制总览

### 5.1 错误分级

| 级别 | 定义 | 处置 | 实例 |
|---|---|---|---|
| **可重试** | 瞬时性、重试大概率成功 | 有限重试（≤2 次，间隔 6s） | 全部后端失败、网络抖动 |
| **可降级** | 该能力失效但可用规则/旧逻辑替代 | 降级到确定性逻辑，不阻塞回路 | LLM 决策/评估失败、洗涤失败 |
| **可冷却** | 反爬/限流，短期内不可用 | 冷却 120s 内跳过该后端 | 百度安全验证、360 访问异常 |
| **可跳过** | 单条目/单 query 失败不影响整体 | 跳过并记录 | 单 URL 非法、深判抓取失败 |
| **致命** | 无法继续，向上抛错 | 任务 failed | Key 未配置、画像网关不过、用户取消 |

### 5.2 分层处理策略

```
┌─ 全局：TaskRegistry.fail(error) 落 failed；TTL 30min 惰性清理
│   ├─ AgentAbortedError（用户取消）→ 立即抛，后台线程落 failed
│   └─ JSAgentError（致命）→ 任务 failed
├─ 循环层（brake_check）：G1-G5 确定性收敛，回路必终止
├─ 决策层（decide/evaluate）：
│   ├─ chat_json 失败 → 规则降级决策/评估（等价现状行为）
│   ├─ 连续降级 3 次 → G5 刹车
│   └─ 非法决策（action 越界/converge 不满足护栏）→ 本次按规则执行
├─ 执行层（execute）：
│   ├─ 后端回退链：优先级逐个尝试，失败进冷却 120s
│   ├─ 空结果：全部失败 → 重试 2 次（sleep 6s）
│   └─ 解析异常（_http_json/正则）：视为该后端失败 → 回退
└─ 抓取层（fetch）：Jina → Trafilatura → urllib 多级回退
```

### 5.3 降级矩阵

| 失败点 | 降级为 | 效果 | 记录 |
|---|---|---|---|
| decide LLM 失败 | 顺序执行未执行 query → 全执行完收敛 | ≈ 现状 | `trace[].degraded` |
| evaluate LLM 失败 | URL 去重 + is_job 规则收录 | 收录略宽（不丢数据） | `trace[].eval_degraded` |
| `_structure_batch` 洗涤失败 | 字段留空，is_job=true 保守收录 | 广收不丢 | 已有 |
| 某后端失败 | 下一后端 | 结果可能略差 | `used_backends` |
| 深判抓取失败/灰区 | 跳过深判，用 snippet | match_score 精度略降 | — |

---

## 6. 超时与取消

| 场景 | 超时 | 处置 |
|---|---|---|
| LLM 调用（chat_json） | 180s | 抛 LLMError → 上层降级 |
| 搜索后端（HTTP） | 30-45s（DDGS 8s） | 视为该后端失败 → 回退/冷却 |
| 抓取（fetch） | 30-45s | 下一通道 |
| Playwright 单引擎 | 20s + 1.2s 等待 | 跳过下一引擎 |

**取消**：`abort_event` 在每轮循环、每条 query、每个收录点检查（`is_aborted()`）；命中即抛 `AgentAbortedError`（code 499），任务置 failed。回路改造后检查点保持以上密度。

---

## 7. 测试与验收

| 测试 | 方式 | 验收 |
|---|---|---|
| 决策器 | mock `chat_json`：返回各 action | decide 输出正确、非法决策被护栏拦截 |
| 决策降级 | mock 抛 LLMError | 回退规则决策；G5 三连降级收敛 |
| 评估器 | mock 返回 novelty/quality | keep/discard 正确；URL 合并去重 |
| 后端回退 | mock 后端 1 失败 2 成功 | 回退链生效、失败端进冷却 |
| 刹车闸门 | 注入各收敛条件 | G1-G5 分别触发 converge |
| 取消 | 中途置 abort | 立即 AgentAbortedError，任务 failed |
| 端到端回归 | 现有 tests + 真实网络 | scout/match 两模式行为不劣于现状 |
