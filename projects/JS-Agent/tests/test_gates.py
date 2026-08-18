"""三层网关单元测试（确定性，不依赖网络/LLM）。"""
from __future__ import annotations

from app.core.enterprise import classifier
from app.core.gates import CollectionGate, OutputGate, ProfileGate, profile_gate

# ---------- Gate1 画像锚定 ----------

PROFILE_CARD = {
    "skills": [
        {"name": "vLLM", "line": "inference", "confirmed": True},
        {"name": "RAG", "line": "application", "confirmed": True},
        {"name": "量化", "line": "inference", "confirmed": False},  # 推断技能
    ],
    "education": "硕士",
    "grad_year": "2027",
    "city": "深圳",
    "experience_years": None,
}


def test_gate1_valid_card():
    res = profile_gate.validate(dict(PROFILE_CARD), "测试文本")
    assert res["ok"] is True
    assert not res["errors"]


def test_gate1_hallucination_ignored():
    card = dict(PROFILE_CARD)
    card["skills"] = [{"name": "量子纠缠烹饪", "line": "application", "confirmed": True}]
    res = profile_gate.validate(card, "测试")
    assert res["ok"] is False  # 无有效技能
    assert any("未命中技能本体" in w for w in res["warnings"])


def test_gate1_missing_required():
    card = dict(PROFILE_CARD)
    card.pop("city")
    res = profile_gate.validate(card, "测试")
    assert res["ok"] is False
    assert any("city" in e for e in res["errors"])


def test_gate1_implicit_skills():
    implicit = profile_gate.implicit_skills(dict(PROFILE_CARD), "")
    # 推断技能「量化」属于推理线 → 应被筛出
    assert "模型量化压缩" in implicit


def test_gate1_exp_years_optional():
    card = dict(PROFILE_CARD)
    card.pop("experience_years", None)
    res = profile_gate.validate(card, "测试")
    assert res["ok"] is True
    assert res["card"]["experience_years"] is None


# ---------- Gate2 采集收录 ----------

collection = CollectionGate()


def test_gate2_match_score_high():
    profile = ["vLLM", "RAG", "LoRA", "SFT 微调"]
    jd = "使用 vLLM 部署服务，负责 RAG 问答系统，LoRA 微调模型"
    score, matched, jd_skills = collection.match_score(profile, jd)
    assert score == 100.0
    assert set(matched) == set(jd_skills)


def test_gate2_match_score_partial():
    profile = ["vLLM"]
    jd = "使用 vLLM 部署，并用 TensorRT-LLM 优化推理"
    score, matched, _ = collection.match_score(profile, jd)
    assert 0 < score < 100
    assert "vLLM 推理服务" in matched


def test_gate2_match_score_with_implicit():
    """隐含（推断）技能参与匹配打分，且口径与 missing 计算一致。"""
    profile = ["vLLM"]
    implicit = ["模型量化压缩"]
    jd = "vLLM 推理服务部署，模型量化（GPTQ AWQ）"
    score_no, _, _ = collection.match_score(profile, jd)                 # 不含隐含
    score_yes, matched, _ = collection.match_score(profile, jd, implicit)  # 含隐含
    assert score_yes > score_no
    assert "模型量化压缩" in matched
    assert score_no < 100.0  # 无量化技能时打不满
    # judge 路径：隐含技能计入打分后，missing 不应再包含已补足的技能
    entry = {"jd_text": jd, "updated_at": "2026-08-01", "enterprise_type": "中型"}
    r = collection.judge(entry, profile, implicit, ["央企", "国企", "大型", "中型", "小型"])
    assert r["match_score"] == 100.0
    assert "模型量化压缩" not in r.get("missing_skills", [])


def test_gate2_judge_accepted():
    entry = {"jd_text": "负责 vLLM 部署、RAG 系统、LoRA 微调，Docker 容器化", "updated_at": "2026-08-01",
             "enterprise_type": "中型", "company": "测试公司"}
    r = collection.judge(entry, ["vLLM", "RAG", "LoRA", "Docker"], [], ["央企", "国企", "大型", "中型", "小型"])
    assert r["status"] == "accepted"
    assert r["match_score"] >= 80


def test_gate2_judge_gap():
    entry = {"jd_text": "TensorRT 部署 SGLang 服务，K8s 集群，CUDA 编程", "updated_at": "2026-08-01",
             "enterprise_type": "中型"}
    r = collection.judge(entry, ["TensorRT", "SGLang", "K8s"], [], ["央企", "国企", "大型", "中型", "小型"])
    assert r["status"] == "gap"
    assert r["match_score"] < 80
    assert "补足" in r.get("gap_tips", "")


def test_gate2_judge_excluded_low():
    entry = {"jd_text": "React 前端开发，TypeScript，Vue", "updated_at": "2026-08-01", "enterprise_type": "中型"}
    r = collection.judge(entry, ["vLLM", "RAG", "LoRA"], [], ["央企", "国企", "大型", "中型", "小型"])
    assert r["status"] == "excluded"


def test_gate2_enterprise_filter():
    entry = {"jd_text": "vLLM 推理优化，K8s 部署", "updated_at": "2026-08-01", "enterprise_type": "大型"}
    r = collection.judge(entry, ["vLLM", "K8s", "RAG"], [], ["中型", "小型"])
    assert r["status"] == "excluded"
    assert "企业类型" in r.get("exclude_reason", "")


def test_gate2_unknown_type_filtered():
    """「未知」类型不再豁免：用户明确勾选类型时，无法归类的岗位按不在所选范围排除。"""
    entry = {"jd_text": "vLLM 推理优化", "updated_at": "2026-08-01", "enterprise_type": "未知"}
    r = collection.judge(entry, ["vLLM", "K8s"], [], ["央企"])
    assert r["status"] == "excluded"
    assert "企业类型" in r.get("exclude_reason", "")


def test_gate2_empty_selected_types_unlimited():
    """selected_types 为空（前端全不勾 + 画像未声明）= 不限，企业类型不过滤（含「未知」）。"""
    entry = {"jd_text": "负责 vLLM 部署、RAG 系统、LoRA 微调，Docker 容器化", "updated_at": "2026-08-01",
             "enterprise_type": "未知"}
    r = collection.judge(entry, ["vLLM", "RAG", "LoRA", "Docker"], [], [])
    assert r["status"] == "accepted"  # 匹配度满分，未被企业类型过滤


def test_gate2_merged_types_respects_frontend_and_profile():
    """合并集合（前端 ∪ 画像）中任一端命中即可收录：画像声明「国企」不被前端只勾「央企」忽略。"""
    entry = {"jd_text": "负责 vLLM 部署、RAG 系统、LoRA 微调，Docker 容器化", "updated_at": "2026-08-01",
             "enterprise_type": "国企"}
    merged = ["央企", "国企"]  # 前端勾「央企」∪ 画像推断「国企」
    r = collection.judge(entry, ["vLLM", "RAG", "LoRA", "Docker"], [], merged)
    assert r["status"] == "accepted"


def test_gate2_stale_filter():
    entry = {"jd_text": "vLLM 推理优化", "updated_at": "2025-01-01", "enterprise_type": "中型"}
    r = collection.judge(entry, ["vLLM", "RAG", "LoRA"], [], ["央企", "国企", "大型", "中型", "小型"])
    assert r["status"] == "excluded"
    assert "时效" in r.get("exclude_reason", "")


# ---------- 企业类型五档判定 ----------

def test_enterprise_central_soe():
    assert classifier.classify("中国电子科技集团") == "央企"
    assert classifier.classify("中广核集团") == "央企"


def test_enterprise_local_soe():
    assert classifier.classify("深圳能源集团", extra_text="市国资委控股") == "国企"


def test_enterprise_large():
    assert classifier.classify("某知名大厂", employees=10000) == "大型"


def test_enterprise_medium_unicorn():
    assert classifier.classify("某独角兽公司", extra_text="全球独角兽") == "中型"
    assert classifier.classify("某公司", employees=2000) == "中型"


def test_enterprise_small():
    assert classifier.classify("某创业公司", employees=80) == "小型"


def test_enterprise_unknown():
    assert classifier.classify("未知公司") == "未知"


# ---------- Gate3 输出质检 ----------

output = OutputGate()


def test_gate3_required_fields():
    job = {"title": "A", "company": "B", "match_score": 80, "skill_line": "application", "missing_skills": [], "source_url": ""}
    errors = output.validate_job(job)
    assert errors  # source_url 缺失/非法
    assert any("source_url" in e for e in errors)


def test_gate3_valid_job():
    job = {"title": "A", "company": "B", "match_score": 80, "skill_line": "application",
           "missing_skills": ["量化"], "source_url": "https://example.com/job/1"}
    assert not output.validate_job(job)


def test_gate3_empty_missing_skills_valid():
    """完全匹配岗位 missing_skills=[] 是合法状态，不被判为缺字段。"""
    job = {"title": "A", "company": "B", "match_score": 100, "skill_line": "inference",
           "missing_skills": [], "source_url": "https://example.com/job/100"}
    assert not output.validate_job(job)


def test_gate3_cross_check():
    job = {"title": "A", "company": "B", "match_score": 50, "skill_line": "inference",
           "missing_skills": [], "source_url": "https://example.com"}
    errors = output.cross_check(job, 85.0)
    assert errors  # 偏差 35 > 15
    assert not output.cross_check(job, 55.0)
