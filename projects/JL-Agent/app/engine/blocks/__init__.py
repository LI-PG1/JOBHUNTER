"""块注册表（契约 §5.1 分层）：第一层并行（无 JD 依赖）/ 第二层依赖共享事实表。"""
from .base import GenContext, llm_with_degrade
from .internship import gen_internship
from .projects import gen_projects
from .rules import gen_education, gen_honor, gen_skills
from .skill_extend import gen_skill_extend
from .summary import gen_summary

BLOCK_GENERATORS = {
    "summary": gen_summary,
    "education": gen_education,
    "internship": gen_internship,
    "skills": gen_skills,
    "honor": gen_honor,
    "projects": gen_projects,
    "skill_extend": gen_skill_extend,
}

# 第一层（无 JD 依赖，并行）；honor 为规则块不计进度权重
LAYER1 = ["summary", "education", "internship", "skills", "honor"]
# 第二层（依赖共享事实表）
LAYER2 = ["projects", "skill_extend"]
