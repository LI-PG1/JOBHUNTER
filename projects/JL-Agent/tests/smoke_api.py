"""API 冒烟/回归测试（P2~P3）：CRUD + 校验错误 + 照片上传 + JD 分析/搜索/提交关卡。

运行：先启动服务（uvicorn app.main:app），再执行
    .venv\\Scripts\\python.exe tests\\smoke_api.py

LLM 依赖用例：本机配置 DEEPSEEK_API_KEY（.env）时跑通「生成→任务→取消」全链路；
未配置时验证优雅降级错误码（50002）。
"""
import io
import json
import os
import urllib.request

import httpx
from PIL import Image

from dotenv import load_dotenv

BASE = "http://127.0.0.1:8000"
load_dotenv()  # 加载工程根 .env（与服务器同源，用于判断是否具备 LLM 链路）
HAS_LLM = bool(os.getenv("DEEPSEEK_API_KEY"))
ok = 0
fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [PASS] {name}")
    else:
        fail += 1
        print(f"  [FAIL] {name} {detail}")


def post(path, payload):
    r = httpx.post(BASE + path, json=payload, timeout=10)
    return r.status_code, r.json()


def build_resume(**over):
    base = {
        "basicInfo": {"name": "张三", "age": 24, "email": "zhangsan@example.com", "phone": "13800138000"},
        "education": [
            {"school": "安徽大学", "major": "应用统计", "degree": "学士",
             "start_month": "2020.09", "end_month": "2024.06"}
        ],
        "skill": [
            {"category": "专业技能", "name": "Python", "level": "熟练"},
            {"category": "工具与框架", "name": "PyTorch"},
        ],
        "project": [
            {"name": "RAG 检索系统", "role": "开发", "start_month": "2024.07", "end_month": "2024.09",
             "tech_stack": ["FastAPI", "Chroma"], "items": [{"text": "构建检索增强生成系统"}]}
        ],
    }
    base.update(over)
    return base


print("== 1. 健康检查 ==")
r = httpx.get(BASE + "/api/health", timeout=10)
check("GET /api/health", r.status_code == 200 and r.json()["code"] == 0)

print("== 2. 创建简历 ==")
sc, j = post("/api/resume", build_resume())
rid = j.get("data", {}).get("resumeId") if sc == 200 else None
check("POST /api/resume 创建成功", sc == 200 and bool(rid), str(j))
if not rid:
    raise SystemExit("无法继续：创建失败")

print("== 3. 读取简历 ==")
r = httpx.get(f"{BASE}/api/resume/{rid}", timeout=10)
j = r.json()
check("GET /api/resume/{id}", j["code"] == 0 and j["data"]["basicInfo"]["name"] == "张三")
check("教育/技能/项目条数回读", len(j["data"]["education"]) == 1 and len(j["data"]["skill"]) == 2)

print("== 4. 校验错误（教育时间 end<=start → 40007） ==")
bad = build_resume(education=[{"school": "A", "major": "B", "degree": "学士",
                               "start_month": "2024.06", "end_month": "2023.09"}])
sc, j = post("/api/resume", bad)
check("40007 教育时间非法", sc == 400 and j["code"] == 40007, str(j))

print("== 5. 校验错误（教育 4 条 → 40011） ==")
four = [{"school": f"S{i}", "major": "M", "degree": "学士", "start_month": "2020.09", "end_month": "2024.06"} for i in range(4)]
sc, j = post("/api/resume", build_resume(education=four))
check("40011 教育数量超限", sc == 400 and j["code"] == 40011, str(j))

print("== 6. 校验错误（技能为空 → 40001） ==")
sc, j = post("/api/resume", build_resume(skill=[]))
check("40001 技能必填", sc == 400 and j["code"] == 40001, str(j))

print("== 7. 校验错误（邮箱非法 → 40001） ==")
sc, j = post("/api/resume", build_resume(basicInfo={"name": "张三", "age": 24, "email": "bad-email",
                                                    "phone": "13800138000"}))
check("40001 邮箱格式", sc == 400 and j["code"] == 40001, str(j))

print("== 8. 校验错误（实习 end<=start → 40007） ==")
sc, j = post("/api/resume", build_resume(
    internship=[{"company": "C", "position": "P", "start_month": "2024.05", "end_month": "2024.01"}]))
check("40007 实习时间非法", sc == 400 and j["code"] == 40007, str(j))

print("== 9. 更新简历 ==")
upd = build_resume()
upd["skill"] = [{"category": "专业技能", "name": "Python"}, {"category": "工具与框架", "name": "FastAPI"},
                {"category": "语言能力", "name": "英语", "level": "熟悉"}]
r = httpx.put(f"{BASE}/api/resume/{rid}", json=upd, timeout=10)
check("PUT /api/resume/{id}", r.status_code == 200 and r.json()["code"] == 0, str(r.json()))
r = httpx.get(f"{BASE}/api/resume/{rid}", timeout=10)
check("更新后技能 3 条", len(r.json()["data"]["skill"]) == 3)

print("== 10. 照片上传（有效 PNG 600x800） ==")
buf = io.BytesIO()
Image.new("RGB", (600, 800), (200, 200, 220)).save(buf, format="PNG")
png_bytes = buf.getvalue()
r = httpx.post(f"{BASE}/api/upload/photo", data={"resume_id": rid},
               files={"file": ("photo.png", png_bytes, "image/png")}, timeout=10)
j = r.json()
check("上传成功并返回元数据", r.status_code == 200 and j["code"] == 0 and j["data"]["ratio"] == "3:4",
      str(j))
r = httpx.get(f"{BASE}/api/resume/{rid}", timeout=10)
photo = r.json()["data"].get("photo") or {}
check("简历 photo 字段已回写", photo.get("filePath") and photo.get("format") == "png", str(photo))

print("== 11. 照片上传（非法格式 txt → 40004） ==")
r = httpx.post(f"{BASE}/api/upload/photo", data={"resume_id": rid},
               files={"file": ("a.txt", b"not an image", "text/plain")}, timeout=10)
check("40004 格式不支持", r.status_code == 400 and r.json()["code"] == 40004, str(r.json()))

print("== 12. 照片上传（超大 → 40006） ==")
big = b"\x00" * (5 * 1024 * 1024 + 10)
r = httpx.post(f"{BASE}/api/upload/photo", data={"resume_id": rid},
               files={"file": ("big.png", big, "image/png")}, timeout=10)
check("40006 大小超限", r.status_code == 400 and r.json()["code"] == 40006, str(r.json()))

print("== 13. 列表 + 删除 ==")
r = httpx.get(f"{BASE}/api/resume", timeout=10)
check("列表包含新建简历", r.status_code == 200 and any(i["id"] == rid for i in r.json()["data"]["items"]))
r = httpx.delete(f"{BASE}/api/resume/{rid}", timeout=10)
check("DELETE 成功", r.status_code == 200 and r.json()["data"]["deleted"] is True)
r = httpx.get(f"{BASE}/api/resume/{rid}", timeout=10)
check("删除后 404（40008）", r.status_code == 400 and r.json()["code"] == 40008, str(r.json()))

print("\n== 14. P3 搜索模式检测 ==")
r = httpx.get(f"{BASE}/api/search/mode", timeout=10)
j = r.json()
d = j.get("data") or {}
check("GET /api/search/mode 结构", j["code"] == 0 and isinstance(d.get("apiReady"), bool)
      and d.get("deepAvailable") is False and isinstance(d.get("missing"), list), str(j))

print("== 15. P3 技能校验参数（空列表 → 422） ==")
sc, j = post("/api/skills/validate", {"skills": [], "jobs": []})
check("skills/jobs 为空 → 422", sc == 422, str(j))

print("== 16. P3 生成关卡：无 JD → 40001 ==")
sc, j = post("/api/generate", {"resumeId": "res_not_exist", "pageOption": "one-page"})
check("简历不存在 → 40008", sc == 400 and j["code"] == 40008, str(j))

# 新建带 JD 的简历用于关卡测试
jobs1 = [{"title": "大模型应用开发实习生", "jdText": "负责 LLM Agent 与 RAG 系统开发，熟悉 Python、PyTorch、Docker"}]
r3 = post("/api/resume", build_resume(jobs=jobs1))
rid3 = r3[1]["data"]["resumeId"]
check("创建带 JD 的简历", r3[0] == 200 and bool(rid3), str(r3[1]))

rid_no_job = post("/api/resume", build_resume())[1]["data"]["resumeId"]
sc, j = post("/api/generate", {"resumeId": rid_no_job, "pageOption": "one-page"})
check("有简历无 JD → 40001", sc == 400 and j["code"] == 40001, str(j))

print("== 17. P3 JD 数量上限（6 套 → 40011） ==")
six_jobs = [{"title": f"岗位{i}", "jdText": "文本内容"} for i in range(6)]
sc, j = post("/api/resume", build_resume(jobs=six_jobs))
check("JD 超 5 套 → 40011", sc == 400 and j["code"] == 40011, str(j))

print("== 18. P3 任务不存在 → 40008 ==")
r = httpx.get(f"{BASE}/api/task/no_such_task", timeout=10)
check("GET 任务不存在 → 40008", r.status_code == 400 and r.json()["code"] == 40008)
r = httpx.post(f"{BASE}/api/task/no_such_task/cancel", timeout=10)
check("取消不存在任务 → 40008", r.status_code == 400 and r.json()["code"] == 40008)
r = httpx.get(f"{BASE}/api/task/no_such_task/events", timeout=10)
check("SSE 任务不存在 → 40008", r.status_code == 400 and r.json()["code"] == 40008)

if not HAS_LLM:
    print("== 19. P3 无 LLM Key：技能校验/生成关卡优雅降级 ==")
    sc, j = post("/api/skills/validate", {"skills": [{"category": "专业技能", "name": "Python"}], "jobs": jobs1})
    check("技能校验 → 50002（LLM 未配置）", sc == 500 and j["code"] == 50002, str(j))
    sc, j = post("/api/generate", {"resumeId": rid3, "pageOption": "one-page"})
    check("生成关卡 → 50002（JD 分析失败）", sc == 500 and j["code"] == 50002, str(j))
else:
    print("== 19. P3 LLM 链路：技能校验三档 + 生成→任务→取消 ==")
    sc, j = post("/api/skills/validate", {"skills": [{"category": "专业技能", "name": "Python"}], "jobs": jobs1})
    check("技能校验通过（pass）", sc == 200 and j["code"] == 0 and j["data"]["verdict"] == "pass", str(j))
    sc, j = post("/api/generate", {"resumeId": rid3, "pageOption": "one-page"})
    task_id = j.get("data", {}).get("taskId") if sc == 200 else None
    check("提交关卡通过并创建任务", sc == 200 and bool(task_id), str(j))
    if task_id:
        r = httpx.get(f"{BASE}/api/task/{task_id}", timeout=10)
        state = r.json()["data"]["state"]
        check("任务已启动（非终态）", r.status_code == 200 and state in ("pending", "analyzing", "generating"),
              str(r.json()))
        r = httpx.post(f"{BASE}/api/task/{task_id}/cancel", timeout=10)
        check("取消任务", r.status_code == 200 and r.json()["data"]["canceled"] is True, str(r.json()))
        r = httpx.post(f"{BASE}/api/task/{task_id}/cancel", timeout=10)
        check("重复取消 → 40009", r.status_code == 400 and r.json()["code"] == 40009, str(r.json()))
        r = httpx.get(f"{BASE}/api/task/{task_id}/events", timeout=10)
        check("SSE 回放含 task.canceled", r.status_code == 200 and "task.canceled" in r.text, r.text[:120])

print("== 20. P6 编辑锁定 / 解锁 / 重装配（§5.5 / §6） ==")
upd3 = build_resume(jobs=jobs1)
upd3["summary"] = [{"text": "初始自我评价句。", "criticality": "low", "estimatedLines": 1}]
r = httpx.put(f"{BASE}/api/resume/{rid3}", json=upd3, timeout=10)
check("整存补 summary", r.status_code == 200 and r.json()["code"] == 0, str(r.json()))

r = httpx.put(f"{BASE}/api/resume/{rid3}/item",
              json={"block": "summary", "index": 0, "text": "编辑后的自我评价"}, timeout=10)
j = r.json()
check("item 编辑 200", r.status_code == 200 and j["code"] == 0, str(j))
d = j["data"]
check("edited 锁定生效（critical）", d["resume"]["summary"][0]["edited"] is True
      and d["resume"]["summary"][0]["criticality"] == "critical", str(d["resume"]["summary"][0]))
check("重装配 html 含编辑标记", 'data-block="summary" data-index="0"' in d["html"])

r = httpx.put(f"{BASE}/api/resume/{rid3}/item",
              json={"block": "project", "index": 0, "subIndex": 0, "text": "改过的项目要点"}, timeout=10)
j = r.json()
check("项目叶子编辑 200", r.status_code == 200 and j["code"] == 0, str(j))
check("项目叶子锁定", j["data"]["resume"]["project"][0]["items"][0]["edited"] is True,
      str(j["data"]["resume"]["project"][0]["items"][0]))

r = httpx.put(f"{BASE}/api/resume/{rid3}/item",
              json={"block": "education", "index": 0, "text": "x"}, timeout=10)
check("不可编辑板块 → 40001", r.status_code == 400 and r.json()["code"] == 40001, str(r.json()))

r = httpx.post(f"{BASE}/api/resume/{rid3}/item/unlock", json={"block": "summary", "index": 0}, timeout=10)
check("解锁 edited=false", r.status_code == 200
      and r.json()["data"]["resume"]["summary"][0]["edited"] is False, str(r.json()))

r = httpx.post(f"{BASE}/api/resume/{rid3}/render", json={"density": "compact"}, timeout=10)
check("render density=compact", r.status_code == 200
      and 'data-density="compact"' in r.json()["data"]["html"], str(r.json()))
r = httpx.get(f"{BASE}/api/resume/{rid3}", timeout=10)
check("density 已持久化", r.json()["data"]["density"] == "compact", str(r.json()))

print("== 21. 设置控制台 / 导出 / 列表字段 ==")
r = httpx.get(f"{BASE}/api/settings", timeout=10)
d = r.json()["data"]
check("设置默认值（深度搜索开/水印无）", r.status_code == 200 and d["deepSearchDefault"] is True
      and d["watermarkDefault"] == "formal", str(d))
r = httpx.put(f"{BASE}/api/settings", json={"apiKey": "sk-smoke-abcdef123456", "deepSearchDefault": True,
                                            "watermarkDefault": "formal"}, timeout=10)
d = r.json()["data"]
check("设置保存 + Key 脱敏", r.status_code == 200 and d["hasKey"] is True
      and "sk-s" in d["apiKeyMasked"] and "****" in d["apiKeyMasked"], str(d))
r = httpx.put(f"{BASE}/api/settings", json={"apiKey": ""}, timeout=10)
check("清空 Key", r.json()["data"]["hasKey"] is False)

# 多 Provider：新增 → 激活 → 回读脱敏 → 自检结构 → 删除
r = httpx.put(f"{BASE}/api/settings/providers", json={
    "name": "GLM", "baseUrl": "https://open.bigmodel.cn/api/paas/v4",
    "model": "glm-4-flash", "apiKey": "sk-glm-abcdef", "capabilities": "text", "enabled": True}, timeout=10)
d = r.json()["data"]
pid = next((p for p in d["providers"] if p.get("name") == "GLM"), {}).get("id")
check("新增 provider 并自动激活", r.status_code == 200 and pid and d["activeProviderId"] == pid, str(d))
r = httpx.post(f"{BASE}/api/settings/providers/{pid}/activate", timeout=10)
check("显式激活 provider", r.status_code == 200 and r.json()["data"]["activeProviderId"] == pid, str(r.json()))
r = httpx.get(f"{BASE}/api/settings", timeout=10)
d = r.json()["data"]
check("设置回读含 providers/activeProviderId",
      isinstance(d.get("providers"), list) and d["activeProviderId"] == pid, str(d))
row = next((p for p in d["providers"] if p.get("id") == pid), {})
check("provider Key 脱敏", row.get("apiKey") is None
      and "sk-g" in row.get("apiKeyMasked", ""), str(d["providers"]))
r = httpx.post(f"{BASE}/api/settings/providers/test", json={
    "baseUrl": "https://invalid.example.invalid/v1", "model": "x", "apiKey": "sk-bad"}, timeout=10)
d = r.json()["data"]
check("配置自检返回结构", r.status_code == 200 and d["ok"] is False and "error" in d, str(d))
r = httpx.delete(f"{BASE}/api/settings/providers/{pid}", timeout=10)
d = r.json()["data"]
check("删除 provider 生效", r.status_code == 200
      and all(p.get("id") != pid for p in d["providers"]), str(d["providers"]))

r = httpx.get(f"{BASE}/api/resume/{rid3}/export?format=json", timeout=10)
check("导出 JSON", r.status_code == 200 and "application/json" in r.headers.get("content-type", ""), str(r.status_code))
r = httpx.get(f"{BASE}/api/resume/{rid3}/export?format=docx", timeout=10)
check("导出 DOCX", r.status_code == 200 and "wordprocessingml" in r.headers.get("content-type", "")
      and len(r.content) > 100, str(r.status_code))
r = httpx.get(f"{BASE}/api/resume/{rid3}/export?format=html", timeout=10)
check("导出非法格式 → 40001", r.status_code == 400 and r.json()["code"] == 40001, str(r.json()))

r = httpx.get(f"{BASE}/api/resume", timeout=10)
item = next((x for x in r.json()["data"]["items"] if x["id"] == rid3), None)
check("列表含方向+本地位置", item is not None and item["file"] == f"data/resumes/{rid3}.json", str(item))

print(f"\n结果: {ok} 通过, {fail} 失败")
raise SystemExit(1 if fail else 0)
