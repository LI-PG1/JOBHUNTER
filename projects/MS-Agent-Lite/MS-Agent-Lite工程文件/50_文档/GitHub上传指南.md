# GitHub 上传指南（纯小白版）

> 目标：把 面试准备助手（纯文本版）从你的电脑传到 GitHub，让其他人（或你自己换电脑时）能下载使用。
> 全程英文网页界面，本文把每个按钮的英文和中文意思都标出来。
> 预计 20~30 分钟。**前提**：已在本地跑通一次——拿到 API Key、能双击「启动面试准备助手.bat」打开面板（见《新手安装使用指南》第 1~4 步）。

---

## 第 1 步 注册 GitHub 账号

1. 浏览器打开 https://github.com
2. 点右上角 **Sign up**（注册）
3. 按提示填：邮箱（Email address）、密码（Create a password）、用户名（Username）
4. 完成人机验证 → 去邮箱收验证邮件，点里面的链接激活

> 英文界面导航速查：
> - **Sign up** = 注册　|　**Sign in** = 登录　|　**Username** = 用户名（会出现在你的仓库地址里）
> - **Email** = 邮箱　|　**Password** = 密码　|　**Verify** = 验证

---

## 第 2 步 确认本地电脑上装了 Git

在终端（Win + R → cmd）输入：
```
git --version
```
出现类似 `git version 2.4x.x` → 已装好，跳到第 3 步。
如果提示「不是内部或外部命令」→ 去 https://git-scm.com 下载安装（一路 Next 默认），装完重新打开终端再验证。

---

## 第 3 步 先检查：哪些文件绝不能传

上传前先在文件夹里检查一遍，这是**最重要的一步**。

### 3.1 仓库结构说明（每个文件夹是干嘛的）

```
MS-Agent-Lite\（上传后别人会看到这些）
├── README.md                  # 项目说明书（首页展示的文字）
├── .gitignore                 # Git 黑名单：config.json / 简历 / 生成材料 / node_modules / 解压产物 自动不上传
├── 启动面试准备助手.bat      # 双击启动软件（免装 Node，首次自动解压运行环境）
├── runtime\                   # ✅ 内置便携版 Node.js（node.zip）与依赖包切片（node_modules.zip.part1~3）
└── MS-Agent-Lite工程文件\
    ├── 新手安装使用指南.md      # 新手教程
    ├── 00_规范\                # 设计文档与生成规范
    ├── 10_知识库/简历基准\      # ⚠ 你的个人简历 + 参与边界卡（涉及个人数据！）
    ├── 10_知识库/岗位画像\      # 各公司岗位画像模板
    ├── 10_知识库/面经实证\      # 面经记录（可能含个人信息）
    ├── 30_产出/面试材料\       # ⚠ 生成结果（含你的简历信息衍生内容）
    ├── 40_界面\                # 网页界面（使用指南.html / 用户界面.html）
    └── 20_执行\
        ├── config.json             # ⚠⚠ 含你的 API Key（真金白银，绝不能传）
        ├── config.example.json     # ✅ 脱敏模板（Key 为空，可传，已为你准备好）
        ├── node_modules\           # ⚠ 解压生成的工具（首次启动由 runtime 自动解压，本地若已存在也绝不传）
        ├── server.js / pipeline.js / ...  # ✅ 程序代码（可传）
        └── web\                    # ✅ 网页界面代码（可传）
```

### 3.2 上传规则（背下来）

| 文件夹 / 文件 | 能传吗 | 原因 |
|---------------|--------|------|
| 所有 `.js` / `.html` / `.md` / `.json`（除下两行） | ✅ 传 | 程序代码和文档 |
| `MS-Agent-Lite工程文件/20_执行/config.json` | ❌ 绝不传 | 里面有你的 API Key |
| `MS-Agent-Lite工程文件/20_执行/config.example.json` | ✅ 传 | 脱敏模板，别人照着填 |
| `MS-Agent-Lite工程文件/20_执行/node_modules` | ❌ 绝不传 | 首次启动由 runtime 自动解压，无需上传 |
| `MS-Agent-Lite工程文件/10_知识库/简历基准`（简历 PDF） | ❌ 建议不传 | 个人简历 = 个人隐私 |
| `MS-Agent-Lite工程文件/30_产出/面试材料` | ❌ 建议不传 | 生成内容基于你的简历 |
| `MS-Agent-Lite工程文件/10_知识库/面经实证` | ❌ 建议不传 | 含个人面试记录 |
| `runtime\`（node.zip + node_modules.zip.part1~3） | ✅ 传 | 内置便携版 Node.js 与依赖包（各 <100MB，GitHub 限制内） |
| `runtime\node\`、`runtime\node_modules.zip` | ❌ 绝不传 | 首次启动解压生成的产物与临时合并文件，已列入 .gitignore |

> 判断口诀：**带 key 的、带个人简历的、node_modules、解压产物，一律不传。**

---

## 第 4 步 在 GitHub 网站创建空仓库（约 3 分钟）

1. 登录后点右上角 **+** 号 → 选 **New repository**（新建仓库）

```
┌───────────────────────────────────────┐
│  +  ← 点这里（右上角）                  │
│    ├ New repository     新建仓库        │
│    └ New gist           新建代码片段    │
└───────────────────────────────────────┘
```

2. 填写仓库信息（全英文页面，对照下表）：

| 英文 | 中文意思 | 怎么填 |
|------|----------|--------|
| Repository name | 仓库名 | `MS-Agent-Lite` |
| Description (optional) | 描述（可跳过） | 面试材料生成 Agent |
| Public / Private | 公开 / 私有 | 想让大家下载选 **Public**；只想自己用选 **Private** |
| Add a README file | 顺便建一个说明文件 | **不要勾选**（我们自带 README） |

3. 点底部绿色按钮 **Create repository**（创建仓库）
4. 创建成功后，浏览器地址栏会显示 `https://github.com/你的用户名/MS-Agent-Lite` —— **把这个地址复制保存**，一会儿要用

---

## 第 5 步 用 Git 把本地项目推上去（约 5 分钟）

### 5.1 打开终端，进入项目文件夹

```
cd /d D:\MS-Agent-Lite
```
> 注意：这次进的是 **MS-Agent-Lite**（项目根目录），不是 `MS-Agent-Lite工程文件\20_执行`。

### 5.2 检查"保护文件"（项目已自带，确认即可）

在**文件资源管理器**里确认两件事：

1. `D:\MS-Agent-Lite` 根目录**已有 `.gitignore`**（项目自带，无需手动创建）。它是 Git 的"黑名单"：列在里面的文件/文件夹——你的 `MS-Agent-Lite工程文件\20_执行\config.json`（含 Key）、简历、生成材料、node_modules——在 `git add` 时会被自动跳过，**不用手动记**。
   > 万一你的版本里没有（比如是很早下载的），就手动新建一个文本文件改名为 `.gitignore`（注意：文件名就是 `.gitignore`，前面是点，没有其他名字；如果保存后变成了 `.gitignore.txt`，把最后的 `.txt` 删掉），用记事本打开粘贴下面内容后保存：
   >
   > ```
   > # 密钥与本地配置（绝不外传）
   > MS-Agent-Lite工程文件/20_执行/config.json
   > 
   > # 个人数据
   > MS-Agent-Lite工程文件/10_知识库/简历基准/
   > MS-Agent-Lite工程文件/30_产出/面试材料/
   > MS-Agent-Lite工程文件/10_知识库/面经实证/
   > 
   > # 依赖与系统文件
   > node_modules/
   > runtime/node/                    # 内置 Node 解压产物（首次启动自动解压生成）
   > runtime/node_modules.zip         # 依赖合并临时文件（首次启动自动合并后删除）
   > .DS_Store
   > Thumbs.db
   > ```

2. `MS-Agent-Lite工程文件\20_执行\config.json`（含你 Key 的那个）**留在本地不要动**；上传的是脱敏模板 `MS-Agent-Lite工程文件\20_执行\config.example.json`（Key 为空，它本来就传）。**不要**把 `config.example.json` 改名覆盖 `config.json`。

### 5.3 逐条执行命令

在终端 `D:\MS-Agent-Lite>` 下，**一条一条**输入下面的命令，每输入一条按一次回车：

```
git init
```
> 看到 `Initialized empty Git repository` = 成功（这步把文件夹变成"仓库"）。

```
git add .
```
> 没有输出 = 成功（这步把要传的文件全部"选中"，已按 .gitignore 跳过黑名单）。

```
git commit -m "first commit"
```
> 看到 `1 file changed` 或 `N files changed` = 成功（这步打一个"存档点"）。

```
git branch -M main
```
> 没有输出 = 成功（把主分支名改成 main，GitHub 的默认叫法）。

```
git remote add origin https://github.com/你的用户名/MS-Agent-Lite.git
```
> 没有输出 = 成功（把本地仓库和 GitHub 那个空仓库"连上线"）。**把地址换成你第 4 步复制的那个。**

```
git push -u origin main
```
> 这步会弹出登录窗口（或要求输入用户名密码）→ 见下方 **5.4 首次推送登录**。

### 5.4 首次推送登录（重点，很多人卡在这）

GitHub 从 2021 年起**不允许用账号密码**推送，要用一个叫 **Token（令牌）** 的东西：

1. 浏览器打开：`https://github.com/settings/tokens`（GitHub 右上角头像 → **Settings** 设置 → 左侧最底部 **Developer settings** 开发者设置 → **Personal access tokens** 个人访问令牌 → **Tokens (classic)**）
2. 点 **Generate new token (classic)**（生成新令牌）
3. 在 **Note**（备注）里随便写个名字，如 `my-pc`
4. 在 **Expiration**（有效期）选 `90 days`（90 天，到期后再生成一个即可）
5. 勾选第一组 **repo**（读写仓库，一个勾就够）
6. 滑到最底下点绿色 **Generate token**（生成令牌）
7. **立刻复制**那串 `ghp_xxxxxx` 开头的字符（只显示这一次！）
8. 回到终端，在弹出窗口的 **Password / Token** 输入框里**粘贴这个令牌**（用户名填你的 GitHub 用户名），点登录

> 推送成功后看到：
> ```
> Branch 'main' set up to track remote branch 'main' from 'origin'.
> To https://github.com/你的用户名/MS-Agent-Lite.git
>    * [new branch]      main -> main
> ```
> = 大功告成！

---

## 第 6 步 验证上传成功

1. 浏览器打开 `https://github.com/你的用户名/MS-Agent-Lite`
2. 确认能看到：`README.md`、`runtime` 文件夹、`MS-Agent-Lite工程文件` 文件夹、`启动面试准备助手.bat` 等
3. 点进 `runtime`，确认能看到 `node.zip` 和 `node_modules.zip.part1/2/3`（GitHub 单文件限制 100MB，已拆 3 片）
4. 点进 `MS-Agent-Lite工程文件\20_执行`，确认能看到 `config.example.json`、**看不到** `config.json` 和 `node_modules`
5. 都对了 → 别人就能按《新手安装使用指南》从你的仓库下载使用了 🎉

---

## 第 7 步 以后更新了代码怎么再传

每次改完代码，在终端 `D:\MS-Agent-Lite>` 下执行三连：

```
git add .
git commit -m "更新说明，例如：修复 xx"
git push
```

---

## 常见问题（英文报错对照）

| 报错（英文） | 意思 | 解决 |
|--------------|------|------|
| `fatal: not a git repository` | 当前不在仓库里 | 确认终端路径是 `D:\MS-Agent-Lite>`，再执行 `git init` |
| `remote origin already exists` | 已经连接过远程 | 跳过 `git remote add origin ...`，直接 `git push -u origin main` |
| `fatal: Authentication failed` | 登录没通过 | Token 过期或粘贴不全。重新生成 Token（见 5.4），再 push 一次 |
| `error: src refspec main does not match any` | 没有提交记录 | 先执行 `git add .` 和 `git commit -m "first commit"` |
| `warning: LF will be replaced by CRLF` | 换行符提示 | 正常现象，忽略即可 |
| `Remote Repository Not Found` | 仓库地址不对 | 检查 `git remote add origin` 那行地址是否和浏览器地址一致 |
| `[rejected] ... (fetch first)` | 远程已有内容 | 你之前 push 过。执行 `git pull --rebase` 再 `git push` |

---

## 最后检查清单

- [ ] 浏览器打开仓库，能看到代码
- [ ] MS-Agent-Lite工程文件\20_执行 里**没有** config.json、node_modules
- [ ] 根目录 `runtime` 里有 node.zip 和 node_modules.zip.part1/2/3；`runtime\node` / `runtime\node_modules.zip` 没被上传
- [ ] MS-Agent-Lite工程文件/10_知识库/简历基准 / MS-Agent-Lite工程文件/30_产出/面试材料 / MS-Agent-Lite工程文件/10_知识库/面经实证 没有上传
- [ ] 本地 `MS-Agent-Lite工程文件/20_执行/config.json` 还是原来的（Key 没被清掉）
- [ ] 用仓库的 ZIP 在另一台电脑按《新手安装使用指南》走通了一遍
