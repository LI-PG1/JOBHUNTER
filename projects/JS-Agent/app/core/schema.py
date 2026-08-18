"""JSON Schema：画像卡 / 岗位条目 / 匹配清单输出（网关与 LLM 输出校验共用）。"""
from __future__ import annotations

# 画像卡：LLM 解析用户画像的强约束输出
PROFILE_CARD_SCHEMA = {
    "type": "object",
    "required": ["skills", "education", "grad_year", "city", "experience_years", "company_types"],
    "properties": {
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "line", "confirmed"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "line": {"enum": ["application", "inference", "both", "core"]},
                    # confirmed=true 表示用户原文声明；false 表示 LLM 推断（待规则复核）
                    "confirmed": {"type": "boolean"},
                },
            },
        },
        "education": {"type": "string"},
        "grad_year": {"type": "string"},
        "city": {"type": "string"},
        # 可选字段（用户可不填）
        "experience_years": {"type": ["integer", "null"]},
        "company_types": {
            "type": "array",
            "items": {"enum": ["央企", "国企", "大型", "中型", "小型"]},
        },
        "raw_summary": {"type": "string"},
    },
}

# 岗位条目：采集/洗涤后进入候选池的结构
JOB_ENTRY_SCHEMA = {
    "type": "object",
    "required": ["title", "company", "city", "source_url", "updated_at", "enterprise_type"],
    "properties": {
        "title": {"type": "string"},
        "company": {"type": "string"},
        "city": {"type": "string"},
        "salary": {"type": "string"},
        "source_url": {"type": "string"},
        "source_type": {"type": "string"},  # 招聘平台/官网/社区
        "updated_at": {"type": "string"},
        "enterprise_type": {"enum": ["央企", "国企", "大型", "中型", "小型", "未知"]},
        "jd_skills": {"type": "array", "items": {"type": "string"}},
        "skill_line": {"enum": ["application", "inference", "both", "other"]},
    },
}

# 匹配清单输出（LLM 生成，网关复核）
MATCH_LIST_SCHEMA = {
    "type": "object",
    "required": ["summary", "jobs"],
    "properties": {
        "summary": {"type": "string"},
        "jobs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "company", "match_score", "skill_line", "missing_skills", "source_url"],
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "city": {"type": "string"},
                    "salary": {"type": "string"},
                    "match_score": {"type": "number"},
                    # 混合判定新增（改造设计 §2，可选字段兼容旧输出）
                    "final_score": {"type": "number"},
                    "llm_verdict": {"type": "object"},
                    "resume_tips": {"type": "array", "items": {"type": "string"}},
                    "skill_line": {"enum": ["application", "inference", "both", "other"]},
                    "matched_skills": {"type": "array", "items": {"type": "string"}},
                    "missing_skills": {"type": "array", "items": {"type": "string"}},
                    "gap_tips": {"type": "string"},
                    "source_url": {"type": "string"},
                    "updated_at": {"type": "string"},
                },
            },
        },
    },
}
