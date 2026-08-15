"""照片上传（契约 §4.2）：格式/尺寸/大小校验（Pillow），更新简历 photo 字段。"""
from fastapi import APIRouter, File, Form, Request, UploadFile

from ..core.validation import check_photo
from ..storage import Storage

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("/photo", response_model=dict)
async def upload_photo(
    request: Request,
    resume_id: str = Form(...),
    file: UploadFile = File(...),
):
    """校验并保存照片；返回照片元数据（dataUrl 供预览）。"""
    app = request.app
    storage: Storage = app.state.storage
    limits = app.state.config.limits

    # 简历必须存在
    storage.load_resume(resume_id)

    data = await file.read()
    meta = check_photo(data, file.filename or "", limits)

    photo_id = storage.new_photo_id()
    file_path = storage.save_photo(photo_id, data, meta["format"])
    data_url = storage.photo_to_data_url(file_path)

    # 回写简历 photo 字段（持久化 filePath 等，不落 base64）
    resume = storage.load_resume(resume_id)
    resume["photo"] = {
        "filePath": file_path,
        "width": meta["width"],
        "height": meta["height"],
        "ratio": meta["ratio"],
        "format": meta["format"],
    }
    resume["updated_at"] = app.state.now()
    storage.save_resume(resume)

    return {
        "code": 0,
        "message": "ok",
        "data": {"dataUrl": data_url, **meta},
    }
