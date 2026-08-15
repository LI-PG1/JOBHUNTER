"""企业类型判定（方案 v0.5 §9）：央企 / 国企 / 大型 / 中型 / 小型。

判定优先级：央企 → 国企 → 大型 → 中型 → 小型（先判性质，再判规模）。
数据来源优先级：企业官网/财报 > 国资委名录 > 企查查/天眼查 > 招聘页公司介绍 > 媒体。
独角兽（估值>10 亿美元）统一归入中型。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 国资委监管央企名录（常用子集，可扩展；完整名录以国资委官网为准）
CENTRAL_SOE_NAMES = [
    "国家电网", "南方电网", "中国石化", "中国石油", "中国海油", "中国电子", "中国电信", "中国移动",
    "中国联通", "中国建筑", "中国中铁", "中国铁建", "中交集团", "中国中车", "国家能源集团", "中国华能",
    "中国大唐", "中国华电", "国家电投", "华润集团", "招商局", "中广核", "中国核工业", "中国航天科技",
    "中国航天科工", "中国航空工业", "中国船舶", "中国兵器", "中国宝武", "中粮集团", "中国五矿",
    "国投集团", "中国诚通", "中国国新", "中国邮政", "中国远洋海运", "东航集团", "南航集团", "中航集团",
    "中国一汽", "东风公司", "中国旅游集团", "中国有色矿业", "中国黄金", "华侨城", "中国建材", "中国电建",
    "中国能建", "中国安能", "中盐集团", "中国国际工程", "中国化学", "中国物流", "中国铁物",
]
# 国企特征词（地方国资控股），结合名称判断
SOE_KEYWORDS = ["国资委", "国资控股", "国有控股", "国有企业", "集团(省|市)属", "地方国企"]

# 独角兽特征词（招聘页/媒体常标注）
UNICORN_KEYWORDS = ["独角兽", "估值 10 亿美元", "估值超 10 亿", "全球独角兽", "胡润独角兽"]


class EnterpriseClassifier:
    def __init__(self) -> None:
        self.names: list[str] = list(CENTRAL_SOE_NAMES)
        self._load_central_list()

    def _load_central_list(self) -> None:
        """从 rules/enterprise.json 扩展央企名录（若存在）。"""
        path = Path(__file__).resolve().parent.parent.parent / "rules" / "enterprise.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            extra = data.get("central_soe", [])
            for n in extra:
                if n not in self.names:
                    self.names.append(n)
        except (json.JSONDecodeError, OSError):
            pass

    # ---------- 判定 ----------

    @staticmethod
    def _contains(text: str, terms: list[str]) -> bool:
        for t in terms:
            if t and t in text:
                return True
        return False

    def classify(
        self,
        company: str,
        employees: int | None = None,
        revenue_yi: float | None = None,
        stage: str | None = None,
        listed: bool = False,
        market_cap_yi: float | None = None,
        extra_text: str = "",
    ) -> str:
        """返回：央企 / 国企 / 大型 / 中型 / 小型 / 未知。"""
        text = f"{company} {extra_text}"

        # ① 央企（国资委名录）
        for name in self.names:
            if name and name in company:
                return "央企"

        # ② 国企（国资控股特征）
        if self._contains(text, ["国资委", "国有控股", "国资控股"]) or "集团" in company and any(
            k in extra_text for k in ["市国资委", "省国资委", "地方国资"]
        ):
            return "国企"

        # ③ 大型
        if (employees and employees > 5000) or (revenue_yi and revenue_yi > 500) or (
            listed and market_cap_yi and market_cap_yi > 500
        ) or self._contains(text, ["世界 500 强", "中国 500 强", "500 强"]):
            return "大型"

        # ④ 中型（含独角兽统一归中型）
        if (employees and 500 <= employees <= 5000) or (revenue_yi and 10 <= revenue_yi <= 500) or (
            stage and stage.lower() >= "c"
        ) or self._contains(text, UNICORN_KEYWORDS):
            return "中型"

        # ⑤ 小型
        if (employees is not None and employees < 500) or (revenue_yi is not None and revenue_yi < 10):
            return "小型"

        return "未知"


classifier = EnterpriseClassifier()
