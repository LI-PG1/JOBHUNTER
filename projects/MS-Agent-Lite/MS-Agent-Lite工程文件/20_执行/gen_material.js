// gen_material.js — 自动生成面试准备材料（CLI 入口，逻辑已迁移至 pipeline.js）
// 用法（保持原签名不变）:
//   node 20_执行\gen_material.js <公司名> <A|B> <JD文件路径>          # JD 存于 txt/md 文件
//   node 20_执行\gen_material.js <公司名> <A|B> --jd "JD文本"          # JD 直接传文本
//   node 20_执行\gen_material.js --dryrun                             # 只检查配置与输入就绪
//
// 机制：调用 20_执行\pipeline.js 的 runGenerate（多 provider fallback、逐文件生成、
//       build + verify 自动执行）；生成的是初稿，需人工复核。
const fs = require("fs");
const path = require("path");
const { runGenerate } = require("./pipeline.js");
const { listProviders } = require("./llm_gateway.js");

const ROOT = path.resolve(__dirname, "..");

// ---------- 输入读取 ----------
// 限定 JD 来源为 txt/md 且 ≤200KB：防任意本地文件被无意识读取并外发第三方 LLM（P1-8/P2-3）
function readJD(arg) {
  if (arg.startsWith("--jd=")) {
    const jd = arg.slice(5);
    if (jd.length > 20000) throw new Error("JD 文本过长（>20000 字符），请精简后重试");
    if (!jd) throw new Error("JD 文本为空");
    return jd;
  }
  if (fs.existsSync(arg)) {
    const ext = path.extname(arg).toLowerCase();
    if (![".txt", ".md", ".markdown"].includes(ext)) throw new Error("JD 文件仅支持 .txt / .md（收到 " + ext + "）");
    const st = fs.statSync(arg);
    if (st.size > 200 * 1024) throw new Error("JD 文件过大（>200KB），请精简或直接传文本");
    const jd = fs.readFileSync(arg, "utf8").trim();
    if (!jd) throw new Error("JD 文件内容为空");
    return jd;
  }
  throw new Error("JD 输入无效（非文件路径且非 --jd= 文本）: " + arg);
}

// ---------- 主流程 ----------
async function main() {
  // dryrun：只检查文本生成 provider 配置
  if (process.argv[2] === "--dryrun") {
    const info = listProviders("text");
    console.log("[dryrun] 文本生成可用 provider " + info.usable + "/" + info.total + " → " + (info.chain.join(" → ") || "(无)"));
    console.log("[dryrun] config OK");
    return;
  }

  const comp = process.argv[2];
  const ver = (process.argv[3] || "").toUpperCase();
  let jdArg = process.argv[4];
  // 兼容两种 JD 文本写法：--jd="JD文本" 与 --jd "JD文本"（空格分隔时文本在下一参数）
  if (jdArg === "--jd") jdArg = "--jd=" + (process.argv[5] || "");
  if (!comp || !/^[AB]$/.test(ver) || !jdArg) {
    console.error('用法: node 20_执行\\gen_material.js <公司名> <A|B> <JD文件路径 | --jd="JD文本">');
    console.error('      node 20_执行\\gen_material.js --dryrun');
    process.exit(1);
  }
  // 与 Web 入口同一白名单：防目录逃逸/非法字符（P1-8）
  if (!/^(?!\.{1,2}$)[^\\\/:*?"<>|\u0000-\u001f]{1,80}$/.test(comp)) {
    console.error('[gen] 公司名非法：不能包含 \\ / : * ? " < > | 或控制字符，也不能是 . / ..');
    process.exit(2);
  }

  const jd = readJD(jdArg);
  // M3：质量回路 CLI 开关 --quality=on|warn-only|off（非法值直接报错退出，不静默忽略）
  let quality;
  const qIdx = process.argv.findIndex(a => a.startsWith("--quality="));
  if (qIdx >= 0) {
    const v = process.argv[qIdx].slice(10).trim();
    if (["on", "warn-only", "off"].indexOf(v) >= 0) quality = { mode: v };
    else { console.error('[gen] --quality= 仅支持 on | warn-only | off（收到 "' + v + '"）'); process.exit(2); }
  }
  const outDir = path.join(ROOT, "30_产出", "面试材料", comp);
  fs.mkdirSync(outDir, { recursive: true });
  console.error("[gen] 输出目录: " + outDir);

  const result = await runGenerate({ company: comp, resumeVer: ver, jdText: jd, quality }, {
    onProgress: evt => {
      if (evt.type === "file") {
        if (evt.status === "done") console.error("[gen]   ✓ " + evt.name + ".md 写入 " + evt.bytes + " 字符");
        else if (evt.status === "running") console.error("[gen] 生成 " + evt.name + ".md ...");
        else if (evt.status === "failed") console.error("[gen]   ✗ " + evt.name + ".md 失败: " + (evt.error || ""));
      } else if (evt.type === "log") {
        console.error("[gen]   -> " + evt.text);
      } else if (evt.type === "build") {
        console.error("[gen] 运行 build.js ...");
      } else if (evt.type === "verify") {
        console.error("[gen] 运行 verify.js ...");
      }
    }
  });

  if (result.build && result.build.stdout) console.log(result.build.stdout);
  if (result.verify && result.verify.output) console.log(result.verify.output);
  console.error("[gen] 完成。产物: " + path.join(outDir, "面试准备.html"));
  console.error("[gen] 注意：生成的是初稿，需人工复核（重点：数字口径对照用户简历、项目边界、版本一致性）。");
  process.exit(result.ok ? 0 : 1);
}

main().catch(e => { console.error("[gen] FAILED:", e.message); process.exit(1); });
