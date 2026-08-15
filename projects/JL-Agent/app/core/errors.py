"""统一错误与错误码（契约 §4.1）。"""
from typing import Optional


class AppError(Exception):
    """业务错误：携带错误码与中文可读提示，由全局异常处理器转 envelope。"""

    def __init__(self, code: int, message: str, detail: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}


# 客户端错误（4xxxx）
E_PARAM = 40001
E_SKILL_BLOCK = 40002
E_THEME_BLOCK = 40003
E_PHOTO_FORMAT = 40004
E_PHOTO_SIZE = 40005
E_PHOTO_BYTES = 40006
E_EDU_TIME = 40007
E_TASK_NOT_FOUND = 40008
E_TASK_STATE = 40009
E_EXPORT_UNCONFIRMED = 40010
E_LIMIT = 40011
E_EDITED_LOCK = 40012

# 服务端错误（5xxxx）
E_RULES_MISSING = 50001
E_LLM = 50002
E_SEARCH = 50003
E_BLOCK_FAIL = 50004
E_TEMPLATE = 50005
E_EXPORT = 50006
