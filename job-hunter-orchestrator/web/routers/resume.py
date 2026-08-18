"""/api/resume —— 简历文件处理（PDF 解析）。

- POST /api/resume/parse_pdf  上传 PDF → pypdf 提取文本（供简历版本管理使用）
  扫描件/图片型 PDF 无文本层时返回 422 提示。
"""
import io
from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter()

MAX_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/parse_pdf")
async def parse_pdf(file: UploadFile = File(...)) -> Dict[str, Any]:
    name = (file.filename or "").lower()
    if not name.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")
    raw = await file.read()
    if len(raw) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="PDF 超过 10MB，请压缩后重试")
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        pages: list[str] = []
        for p in reader.pages:
            try:
                pages.append(p.extract_text() or "")
            except Exception:
                pages.append("")
        text = "\n".join(pages).strip()
        if not text:
            raise HTTPException(
                status_code=422,
                detail="未能从该 PDF 提取到文本——可能为扫描件/图片型 PDF，请改用 txt/md 或粘贴文本",
            )
        return {"ok": True, "name": file.filename, "pages": len(pages), "text": text, "chars": len(text)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 解析失败：{e}")
