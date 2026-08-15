# 简历生成助手 变更记录（R 系列）

> 变更留痕表：每轮迭代一行，含范围 / 关键改动 / 验收 / 提交。依据《通用规范》§六 决策留痕与需求基线。
> 验收基准：`docs/contract.md` §7 E1-E13；体验目标：产品体检 55 → ≥110/130。

## 约定
- 范围：feature（新功能）/ refine（体验优化）/ fix（缺陷修复）/ docs（文档）
- 验收：logic_check（133 项）/ smoke_api（52 项）/ 浏览器专项 / 构建验证

## R17 起迭代记录

| 版本 | 范围 | 关键改动 | 验收 | 提交 |
|---|---|---|---|---|
| R30 | fix | 品牌与模型校正：产品显示名统一「简历生成助手」（仅显示名，路径/仓库/产物名不动）；DeepSeek 改用真实 API 名 deepseek-v4-flash / deepseek-v4-pro（下拉显示常见名、发送官方名，兼容 deepseek-chat/reasoner 历史别名存量回显）；分页布局修复（板块标题 page-break-after:avoid 不孤悬页尾、密度估算补真实间距 liMargin/itemMargin/rowMargin/overviewMargin 防空白防溢出、一段实习至少匹配 2 项目、技能分类收敛 3~5 类且无单技能碎分类行）；新增技术文档 | logic 36 项回归 + node/py_compile 全量 PASS | 待提交 |
| R29 | fix | 版本验收（TSE）闭环：导出前新增 AI 内容确认清单（强制勾选 + 水印模式必选展示 + Esc 关闭）；保存失败提示红色醒目；README 更新（简介文案、共创欢迎语、作者邮箱） | logic 133 + smoke 52 + 浏览器 7/7 PASS | 884da86 / f57d42e |
| R28 | feature | 主页底部新增致谢页脚：感谢使用 简历生成助手 + 作者邮箱 mailto 链接（居中弱化排版，宽度与内容区对齐） | HTTP 渲染验证 PASS | 44a622c |
| R27 | refine | 美术风格（VIS）审核落地：对比度修复 12 处（--ok-ink 深档等，AA 达标）+ 字阶 6 tokens 收敛（11/11.5→12px）+ 间距 4px 网格 tokens；品牌调性→视觉元素映射文档；顶栏版本号（去品牌重复）；emoji→统一线性 SVG 图标 | 浏览器 12/12 PASS | dd127d7 |
| R26 | refine | UI/UX 审核落地：P0 键盘焦点指示与对比度升级、AI 交互态清单文档；P1 设计规范文档与语义色 tokens 收编、首启 onboarding 引导；P2 预览 clamp 自适应与完成进度脉冲 | 浏览器 10/10 PASS | 2d0562b |
| R25b | refine | 导出格式下拉与提醒栏去除 (打印)/(Word)/(数据) 括号提示 | 浏览器 PASS | 302792f |
| R25a | feature | 导出支持 Markdown / HTML（标准 GFM + HTML5 打印样式）；操作说明覆盖全部输入控件（动态行 data-help + section 区分同名 class）；文案修订（学校示例改企鹅大学、时间字段去歧义） | node + HTTP 链路 + 浏览器 22 项 PASS | 4805faa / 1b93f17 |
| R25 | feature | 三栏布局：左栏常驻流程栏（4 步高亮 + 动态引导行）+ 右栏常驻提醒栏（聚焦/点击显示说明，HELP 字典三段式 + 兜底欢迎态） | 浏览器 17 项 PASS | 53a719f |
| R24 | feature | 配置界面改纯下拉：厂商/模型选择自动填充 name/baseurl 并隐藏；Key 占位符随厂商+模型动态化；存量自定义配置 __custom 回显 | logic 133 + smoke 52 + 浏览器 8 项 PASS | 5345b62 |
| R23 | feature | 厂商两级联动；生成前必填缺失滚动红框定位；4 步引导条随流程切换高亮 | logic + smoke PASS | c988e54 |
| R22 | feature | 仓库版版本机制 0.6.0 + 部署文档 + 独立 EXE 分发方案 | 构建验证 PASS | 60eca97 |
| R21 | feature | 便携式自包含分发：嵌入式 Python 打包 ZIP + 跨解释器启动器四层回退 + 双击 bat | ZIP 构建/启动验证 PASS | ea9514b |
| R20 | feature | 插件双层机制增强：配置与启用分离、失败排查指引、集成 OpenCLI/MediaCrawler/Agent-Reach（扫码提示）、Tavily 教程、水印选项说明；修复 git 空目录误判与安装超时挂起 | 浏览器验证 PASS | 7bc22fc |
| R19 | feature | 可集成插件双层启动机制（一键配置 + 功能模块精细控制，状态联动同步） | 插件状态联动验证 PASS | b01bc5e |
| R18 | fix | 修复插件勾选失败回滚；高级设置改为顶部常驻按钮 + 右侧抽屉（仿 MS-Agent） | 回滚复测 PASS | 3a3ceb2 |
| R17 | feature | 时间选择统一限定 2015.01~2030.12（开始与结束一致） | 前后端校验 PASS | 3930bf7 |

## R17 之前（归档摘要）

R1-R16 为早期产品迭代（PRD/P1-P8 工程契约阶段，见 `docs/contract.md`），关键里程碑：P2 数据层与校验（e995662）、P3 JD 分析/提交关卡（b48464e）、P4 生成引擎 DAG + SSE（0df01eb）、P5 适配闭环（48d85ad）、P6 前端预览编辑（c14bdf3）、R15 多 Provider 设置控制台（333b69f）、R16 插件注册表（db3959d / 9743514）。
