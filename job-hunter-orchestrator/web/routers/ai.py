"""/api/ai —— 面试追踪智能识别（对齐 interview-tracker 子项目契约）。

- POST /api/ai/test   探测 API Key 是否已配置（在线模式判定）
- POST /api/ai/parse  识别粘贴文本 → 结构化投递信息
  走 OpenAI 兼容接口 LLM 结构化抽取（需 .env 配置 LLM_API_KEY/LLM_MODEL/LLM_BASE_URL）
"""
import json
import re
import urllib.request
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from web.routers.console import _read_env

router = APIRouter()

class ParseRequest(BaseModel):
    text: str


def _llm_parse(text: str) -> Dict[str, Any]:
    """OpenAI 兼容接口结构化抽取（real 模式）。"""
    env = _read_env()
    key = env.get("LLM_API_KEY", "")
    model = env.get("LLM_MODEL", "deepseek-v4-flash")
    base = env.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
    prompt = (
        "从下面的投递/面试信息中抽取结构化字段，输出严格 JSON（不要多余文字）。\n"
        '字段：{"company":"公司名","title":"岗位名","workType":"autumn|convert|nonconvert|unknown",'
        '"city":"城市","url":"链接","appliedDate":"YYYY-MM-DD","interviewAt":"YYYY-MM-DD HH:mm 或空",'
        '"note":"备注","offerDeadline":"YYYY-MM-DD 或空","todo":{"text":"待办","due":"YYYY-MM-DD"}或null,'
        '"stages":{"resume":{"date":"","state":null},"written":{"date":"","state":null,"deadline":null},'
        '"interviews":[],"hr":null},"uncertain":["需人工核对项"]}\n'
        "信息如下：\n" + text
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise HTTPException(status_code=502, detail=f"LLM 网络错误: {e.reason}") from e
    content = data["choices"][0]["message"]["content"]
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
    return json.loads(content)


@router.post("/ai/test")
def ai_test() -> Dict[str, Any]:
    env = _read_env()
    return {"ok": bool(env.get("LLM_API_KEY"))}


@router.post("/ai/parse")
def ai_parse(req: ParseRequest) -> Dict[str, Any]:
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="请先粘贴需要识别的信息")
    env = _read_env()
    if not env.get("LLM_API_KEY"):
        raise HTTPException(status_code=400, detail="未配置 API Key，请先在控制台配置并测试连接")
    try:
        data = _llm_parse(text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="AI 识别返回格式异常，请重试")
    return {"data": data}
