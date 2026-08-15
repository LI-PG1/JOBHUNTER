# 参与贡献

感谢你愿意帮助改进 JS-Agent。请阅读以下约定后再提交。

## 开发环境

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt pytest
```

## 提交规范

- 分支命名：`feature/<简述>` / `fix/<简述>`
- Commit Message 用中文描述**为什么**改（而非改了啥），控制在 1-2 句
- PR 标题格式：`<类型>: <摘要>`（类型：feat / fix / docs / test / refactor）

## 测试要求

- 任何代码改动必须通过全部测试：`pytest tests -q`
- 新增逻辑必须配套单元测试（三层网关、企业分类、LLM 客户端、API 冒烟均为独立测试模块）
- LLM 相关测试一律 mock 网络层（参考 `tests/test_llm.py`），禁止真实调用 API

## 规则库扩展

- 技能/岗位/行业本体位于 `rules/`，遵循对应 JSON Schema
- 新增技能需标注技能线：`application`（应用）/ `inference`（推理）/ `both`（双线）/ `core`（基础）
- 别名字段用英文小写 + 中文原词，方便词边界匹配

## 安全红线

- **绝不**在代码、提交、文档中写入任何 API Key / 密钥
- `storage/keys.json`、`config.json` 已 git 忽略，勿用 `git add -A` 强制提交
- 搜索通道涉及非官方源：新增后端需在插件面板标注灰区（`gray: true`）并附免责说明

## 许可证

本项目采用 MIT License，贡献即代表同意以该协议授权你的贡献。
