"""prep_agent 状态契约（面试材料生成 + 质量回路）。

对齐大脑节点（N6 prep_materials）与架构 §3.5：
    输入 {resume, company, job, jd_text?, resume_ver?, quality?, llm?}
    输出 {materials, quality_summary, errors}

进程内内存态：无 storage/持久化（与大脑集成形态一致，Q9 同款）。
"""
from __future__ import annotations

from typing import Any, TypedDict


class PrepState(TypedDict, total=False):
    # ---- 输入 ----
    resume: dict[str, Any]          # 用户简历（结构化）
    resume_text: str                # 简历文本（可选，质量回路 D1 基准之一）
    company: str                    # 公司名
    job: dict[str, Any]             # 岗位信息（name/direction 等）
    jd_text: str                    # JD 文本（可选，D3 审核用）
    resume_ver: str                 # "A" | "B" | ""（参与边界卡版本）
    card: str                       # 参与边界卡文本（可选，D1/D2 权威基准）
    quality: dict[str, Any]         # 质量回路配置覆盖 {mode?, maxRounds?, reviewFiles?}
    llm: dict[str, Any]             # LLM 配置 {backend?, api_key?, model?, base_url?}

    # ---- 中间态 ----
    files: list[dict[str, Any]]     # 待生成文件定义（name/hint）
    materials: list[dict[str, Any]] # [{name, content}] 生成结果
    rounds: int                     # 已执行回炉轮次

    # ---- 输出 ----
    quality_summary: list[dict[str, Any]]  # [{file, round, verdict, issues[]}]
    errors: list[str]
