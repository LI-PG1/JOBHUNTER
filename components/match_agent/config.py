"""match_agent 阈值与配置（P0 对齐 JS-Agent strict 档语义）。

注意：judge 混合判定（H1-H6 硬约束 + LLM 软性维度）在 P1 接入；
P0 仅纯规则判定（技能分 + 企业档 + 时效 + 阈值），行为≈原 Gate2。
"""
from __future__ import annotations

# ---- 判定阈值（原 config.CONSTRAINT_PRESETS strict 档）----
MATCH_ACCEPT = 80            # final ≥ 80 → accepted
MATCH_GAP = 60               # 60 ≤ final < 80 → gap
MATCH_EXPAND = 90            # ≥90 触发扩散（P1 由决策器接管）

# ---- 搜索（P0 线性执行种子 query；回路 P1 接入）----
MAX_SEARCH_ROUNDS = 10
MIN_SEARCH_ROUNDS = 3
BUDGET = 12                  # 决策+评估 LLM 调用预算（G3）
MAX_QUERIES_PER_ROUND = 2
DEFAULT_NUM = 8              # 每 query 拉取条数

# ---- 时效（P0 简化：无日期字段不判）----
FRESH_DAYS = 60

# ---- 输出 ----
MAX_RESULTS = 20             # 最终清单上限

# ---- 企业档过滤（selected_types 为空=不限制）----
COMPANY_TYPES: list[str] = ["央企", "国企", "大型", "中型"]
