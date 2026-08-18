"""resume_agent 共享状态：ResumeState（§3.4 组件独立 State）。

P0 链：direction → prepare(factsheet) → generate(blocks) → review(review_results) → build(resume+html)
输出契约（大脑 N3/N8 进程内调用）：
    {resume, blocks, html, config, factsheet, review_results, errors}
"""
from typing import Any, TypedDict


class ResumeState(TypedDict, total=False):
    task_id: str
    direction: str                    # 本次生成方向（单次单方向，§3.3）
    resume: dict[str, Any]            # 用户简历数据（camelCase）
    source_materials: dict[str, Any]  # 用户素材锚点（P4 审核基准）
    jobs: list[dict[str, Any]]        # JD（1~5 套同一方向）
    factsheet: dict[str, Any]         # JD 分析事实表（prepare 产出）
    search_results: dict[str, Any]    # 联网检索结果（P1 接入）
    blocks: dict[str, Any]            # block → 板块输出
    review_results: dict[str, Any]    # block → ReviewResult（P3 已填充）
    rounds: dict[str, int]            # block → 重写轮数（P3 使用）
    content_plan: dict[str, Any]
    page_option: str
    config: dict[str, Any]
    errors: list[str]

    # 内部运行时（不进契约输出）
    html: str
    assembly_config: dict[str, Any]
    _ctx: Any                        # GenContext 运行时对象（P0 进程内传递）
