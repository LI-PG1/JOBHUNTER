"""高精度预算（契约 §5.3 预算前置）：模型自估行数协议 + 校准表。

P4 落地：收集各描述性板块输出的 estimatedLines，提供校准表读写。
P5（适配闭环）测量实际渲染行数后调用 record_actual 追加校准行，
校正系数 = 历史 actual/estimated 中位数（暂无数据时 = 1.0）。
"""
import json
import statistics
from pathlib import Path
from typing import List, Optional

ESTIMATED_KEYS = {"summary": "sentences", "internship": "items", "projects": "projects"}
DEFAULT_FACTOR = 1.0


class BudgetTracker:
    """预算校准表（data/calibration.json）读写与收集。"""

    def __init__(self, data_dir: str):
        self.path = Path(data_dir) / "calibration.json"
        self.rows: List[dict] = []
        self._last: dict = {}          # {block: {detailLevel, estimatedLines}}（P5 多块校准）
        if self.path.exists():
            try:
                self.rows = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.rows = []

    # ------------------------------------------------------------ 收集（P4）

    @staticmethod
    def collect_estimated(block: str, output: dict) -> List[dict]:
        """从块输出中抽取 {text, estimatedLines} 列表（自估协议 §5.3）。"""
        key = ESTIMATED_KEYS.get(block)
        if not key:
            return []
        items = output.get(key) or []
        if block == "internship":
            items = [d for it in items for d in (it.get("duties") or [])]
        if block == "projects":
            items = [d for p in items for d in (p.get("items") or [])]
        return [
            {"text": str(x.get("text", ""))[:120], "estimatedLines": int(x.get("estimatedLines") or 0)}
            for x in items if isinstance(x, dict)
        ]

    def record_estimated(self, block: str, output: dict, detail_level: str = "标准") -> int:
        """记录本次自估（不落校准表，actual 未知）；返回该块总估计行数。"""
        entries = self.collect_estimated(block, output)
        total = sum(e["estimatedLines"] for e in entries)
        self._last[block] = {"detailLevel": detail_level, "estimatedLines": total}
        return total

    # ------------------------------------------------------------ 校准（P5 实测）

    def record_actual(self, block: str, actual_lines: int, detail_level: str = "标准",
                      page_width: int = 794, estimated_lines: Optional[int] = None) -> float:
        """P5 适配闭环实测后追加校准行，返回累计校正系数。

        estimated_lines 由前端从 task.done config.blocks 基线回传（§5.3）；
        缺省时回退本次运行记录（record_estimated 写入的 _last）。
        """
        est = estimated_lines if estimated_lines is not None \
            else ((self._last.get(block) or {}).get("estimatedLines", 0) or 0)
        ratio = round(actual_lines / est, 3) if est else 0.0
        self.rows.append({
            "blockType": block, "detailLevel": detail_level, "pageWidth": page_width,
            "estimatedLines": est, "actualLines": actual_lines, "ratio": ratio,
        })
        self._save()
        return self.factor(block)

    def factor(self, block: str) -> float:
        """该板块历史 actual/estimated 中位数；无数据返回 1.0。"""
        ratios = [r["ratio"] for r in self.rows if r.get("blockType") == block and r.get("ratio")]
        if not ratios:
            return DEFAULT_FACTOR
        return round(statistics.median(ratios), 3)

    def _save(self) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.rows, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
