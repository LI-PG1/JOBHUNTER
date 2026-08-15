/* app.js：简历生成助手工作台控制器 —— 简历列表 / 表单 / 保存 / 生成（SSE）/ 预览联动 */
(function () {
  "use strict";

  var state = window.JL = window.JL || {};
  var es = null;
  // vis P2-3：统一线性图标（feather settings，stroke 跟随文字色），替代 emoji ⚙
  var ICO_GEAR = '<svg class="ico" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';

  function $id(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function monthToInput(v) { return (v || "").replace(".", "-"); }
  function inputToMonth(v) { return (v || "").replace("-", "."); }
  function list(v) { return String(v || "").split(/[,，、]/).map(function (s) { return s.trim(); }).filter(Boolean); }
  // r17：时间约束 —— 开始与结束均限 2015.01 ~ 2030.12
  var MIN_START = "2015.01";
  var MAX_END = "2030.12";
  // r3：自然描述 → 按「空行」分段（连续换行不拆分），每段作为一条待 AI 润色文本
  function paragraphs(v) {
    return String(v || "").split(/\n\s*\n/).map(function (s) { return s.trim(); }).filter(Boolean);
  }
  function errMsg(j) {
    if (j && j.message) return j.message;
    if (j && Array.isArray(j.detail)) {
      return j.detail.map(function (d) { return d.msg || JSON.stringify(d); }).join("；");
    }
    if (j && j.detail) return String(j.detail);
    return "未知错误";
  }

  /* ---------------- 健康检查 ---------------- */
  function health() {
    fetch("/api/health").then(function (r) { return r.json(); }).then(function (j) {
      var el = $id("health-status");
      if (j.code === 0) {
        el.textContent = "服务正常";
        el.className = "ok";
        var vt = $id("ver-tag");
        if (vt && j.data && j.data.version) vt.textContent = "v" + j.data.version;
      } else {
        el.textContent = "异常: " + j.message;
        el.className = "bad";
      }
    }).catch(function () {
      var el = $id("health-status");
      el.textContent = "无法连接后端";
      el.className = "bad";
    });
  }

  /* ---------------- 简历列表 ---------------- */
  function loadList() {
    return fetch("/api/resume").then(function (r) { return r.json(); }).then(function (j) {
      var ul = $id("resume-list");
      ul.innerHTML = "";
      (j.data.items || []).forEach(function (it) {
        var li = document.createElement("li");
        if (state.resumeId === it.id) li.className = "active";
        var main = document.createElement("div");
        main.className = "li-main";
        main.textContent = (it.name || "未命名") + (it.direction ? " · " + it.direction : "");
        var sub = document.createElement("div");
        sub.className = "li-sub";
        sub.textContent = "更新于 " + (it.updated_at || "").slice(0, 16).replace("T", " ") +
          " · " + (it.file || "");
        var del = document.createElement("span");
        del.className = "del";
        del.textContent = "删除";
        del.addEventListener("click", function (ev) {
          ev.stopPropagation();
          // 乐观删除（§r3）：立即移除条目，后台请求；失败回滚为真实列表
          ul.removeChild(li);
          fetch("/api/resume/" + it.id, { method: "DELETE" })
            .then(function (r) { return r.json(); })
            .then(function (jr) {
              if (jr.code !== 0) { loadList(); return; }
              if (state.resumeId === it.id) newResume();
            })
            .catch(function () { loadList(); });
        });
        li.appendChild(main);
        li.appendChild(sub);
        li.appendChild(del);
        li.addEventListener("click", function () { openResume(it.id); });
        ul.appendChild(li);
      });
      if (!(j.data.items || []).length) {
        // 阶段3：空状态指引 —— 告诉用户下一步做什么，而不是留白
        var emptyLi = document.createElement("li");
        emptyLi.className = "list-empty";
        emptyLi.innerHTML = "还没有简历——<b>填写上方「简历信息」并保存</b>后，简历会出现在这里；也可以先点「新建」立即开始。";
        ul.appendChild(emptyLi);
      }
      return j;
    }).catch(function (e) { console.warn("加载列表失败", e); });
  }

  function newResume() {
    state.resumeId = null;
    state.resume = null;
    clearForm();
    $id("cur-resume").textContent = "未保存（新建）";
    $id("btn-generate").disabled = true;
    loadList();
  }

  function openResume(id) {
    fetch("/api/resume/" + id).then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      state.resumeId = id;
      state.resume = j.data;
      state.config = null;
      state.html = null;
      fillForm(j.data);
      $id("cur-resume").textContent = ((j.data.basicInfo || {}).name || "未命名");
      $id("btn-generate").disabled = false;
      loadList();
    }).catch(function (e) {
      Adapt.showBanner("打开简历失败：" + e.message, true);
    });
  }

  /* ---------------- 表单行模板 ---------------- */
  // 枚举值与后端一致（§3.4）：degree/category 使用中文 value
  var DEGREES = [["专科", "专科"], ["学士", "学士"], ["硕士", "硕士"], ["博士", "博士"]];
  var CATS = [["专业技能", "专业技能"], ["工具与框架", "工具与框架"], ["语言能力", "语言能力"],
              ["算法与模型", "算法与模型"], ["数据与统计", "数据与统计"], ["工程实践", "工程实践"],
              ["证书资质", "证书资质"], ["兴趣爱好", "兴趣爱好"], ["其他能力", "其他能力"]];
  // r2/r3：职责/要点整行 + 高度 ×3；允许自然描述（每行一条 → 自然语言，AI 后续润色加工）
  var ROW_TMPL = {
    edu: '<div class="grid">' +
      '<label>学校<input class="in-school" maxlength="64"></label>' +
      '<label>专业<input class="in-major" maxlength="64"></label>' +
      '<label>学历<select class="in-degree"></select></label>' +
      '<label>开始<input class="in-start" type="month" required></label>' +
      '<label>结束<input class="in-end" type="month" required></label>' +
      '</div>',
    int: '<div class="grid">' +
      '<label>公司<input class="in-company" maxlength="64"></label>' +
      '<label>职位<input class="in-position" maxlength="64"></label>' +
      '<label>开始<input class="in-start" type="month" required></label>' +
      '<label>结束<input class="in-end" type="month" required></label>' +
      '<label class="full">职责（自然描述，AI 将自动润色整理）<textarea class="in-duties" rows="9" maxlength="800" data-limit="800"></textarea><span class="opt-hint cnt-hint" data-cnt="duties">0/800</span></label>' +
      '</div>',
    proj: '<div class="grid">' +
      '<label>项目名称<input class="in-name" maxlength="64"></label>' +
      '<label>角色<input class="in-role" maxlength="32"></label>' +
      '<label>开始<input class="in-start" type="month"></label>' +
      '<label>结束<input class="in-end" type="month"></label>' +
      '<label class="full">技术栈（逗号分隔）<input class="in-stack" maxlength="300"></label>' +
      '<label class="full">要点（自然描述，AI 将自动润色整理）<textarea class="in-items" rows="12" maxlength="800" data-limit="800"></textarea><span class="opt-hint cnt-hint" data-cnt="items">0/800</span></label>' +
      '</div>',
    skill: '<div class="grid">' +
      '<label>分类<select class="in-category"></select></label>' +
      '<label>技能<input class="in-name" maxlength="64"></label>' +
      '</div>',
    honor: '<div class="grid">' +
      '<label>奖项<input class="in-name" maxlength="128"></label>' +
      '<label>时间<input class="in-time" maxlength="32"></label>' +
      '</div>',
    job: '<div class="grid">' +
      '<label class="full">岗位名称<input class="in-title" maxlength="64"></label>' +
      '<label class="full">JD 原文<textarea class="in-jd" rows="5" maxlength="20000"></textarea></label>' +
      '</div>',
  };
  // r1：条目自动编号（按添加时间先后 = DOM 顺序）；实习/项目独立前缀
  var IDX_NUMS = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"];

  function reindex(sec) {
    var prefix = sec === "int" ? "实习" : (sec === "proj" ? "项目" : "");
    if (!prefix) return;
    var rows = $id(sec + "-rows").querySelectorAll(".row");
    rows.forEach(function (row, i) {
      var tag = row.querySelector(".idx");
      if (!tag) {
        tag = document.createElement("span");
        tag.className = "idx";
        row.insertBefore(tag, row.firstChild);
      }
      tag.textContent = prefix + (IDX_NUMS[i] || (i + 1));
    });
  }

  // r5：数量上限 → 添加按钮自动禁用（教育 3 / 实习 2 / JD 5）
  var SEC_MAX = { edu: 3, int: 2, job: 5 };

  function updateAddBtns() {
    Object.keys(SEC_MAX).forEach(function (sec) {
      var btn = document.querySelector('[data-add="' + sec + '"]');
      if (!btn) return;
      var n = $id(sec + "-rows").querySelectorAll(".row").length;
      btn.disabled = n >= SEC_MAX[sec];
    });
  }

  function addRow(sec, data) {
    var box = $id(sec + "-rows");
    var div = document.createElement("div");
    div.className = "row";
    div.innerHTML = ROW_TMPL[sec];
    var rm = document.createElement("span");
    rm.className = "rm";
    rm.textContent = "移除";
    rm.addEventListener("click", function () {
      box.removeChild(div);
      reindex(sec);
      updateAddBtns();
    });
    div.appendChild(rm);
    // r25 P9：动态行控件注入 data-help（sec-字段），右侧提醒栏按此匹配说明
    div.querySelectorAll("input, select, textarea").forEach(function (el) {
      if (el.className) el.setAttribute("data-help", sec + "-" + el.className);
    });
    // 输入限长计数：实习职责 / 项目要点 实时显示 已用/上限（上限 = data-limit = 800）
    div.querySelectorAll("textarea[data-limit]").forEach(function (ta) {
      var cnt = div.querySelector('[data-cnt="' + ta.getAttribute("data-cnt") + '"]');
      var limit = parseInt(ta.getAttribute("data-limit"), 10);
      var refresh = function () {
        var used = ta.value.length;
        if (cnt) {
          cnt.textContent = used + "/" + limit;
          cnt.classList.toggle("cnt-warn", used > limit * 0.9);
        }
      };
      ta.addEventListener("input", refresh);
      refresh();
    });
    // 下拉选项
    if (sec === "edu") {
      var sel = div.querySelector(".in-degree");
      DEGREES.forEach(function (d) {
        var o = document.createElement("option");
        o.value = d[1]; o.textContent = d[0];
        sel.appendChild(o);
      });
      if (data && data.degree) sel.value = data.degree;
    }
    if (sec === "skill") {
      var sel2 = div.querySelector(".in-category");
      CATS.forEach(function (c) {
        var o = document.createElement("option");
        o.value = c[1]; o.textContent = c[0];
        sel2.appendChild(o);
      });
      if (data && data.category) sel2.value = data.category;
    }
    // 回填
    if (data) {
      var fields = { school: "in-school", major: "in-major", company: "in-company", position: "in-position",
        name: "in-name", role: "in-role", time: "in-time", title: "in-title" };
      Object.keys(fields).forEach(function (f) {
        if (data[f] != null) div.querySelector("." + fields[f]).value = data[f];
      });
      var st = div.querySelector(".in-start"); if (st && data.startMonth) st.value = monthToInput(data.startMonth);
      var en = div.querySelector(".in-end"); if (en && data.endMonth) en.value = monthToInput(data.endMonth);
      var stack = div.querySelector(".in-stack"); if (stack && data.techStack) stack.value = (data.techStack || []).join("、");
      var duties = div.querySelector(".in-duties");
      if (duties && data.duties) duties.value = (data.duties || []).map(function (d) { return d.text; }).join("\n");
      var items = div.querySelector(".in-items");
      if (items && data.items) items.value = (data.items || []).map(function (i) { return i.text; }).join("\n");
      var jd = div.querySelector(".in-jd"); if (jd && data.jdText) jd.value = data.jdText;
    }
    // r17：时间输入范围 —— 开始与结束均限 2015-01 ~ 2030-12（月份选择器直接限制）
    if (sec === "edu" || sec === "int" || sec === "proj") {
      var st = div.querySelector(".in-start");
      var en = div.querySelector(".in-end");
      if (st) { st.min = "2015-01"; st.max = "2030-12"; }
      if (en) { en.min = "2015-01"; en.max = "2030-12"; }
    }
    box.appendChild(div);
    reindex(sec);
    updateAddBtns();
  }

  function collectRows(sec) {
    var box = $id(sec + "-rows");
    var out = [];
    box.querySelectorAll(".row").forEach(function (row) {
      var q = function (cls) { var el = row.querySelector("." + cls); return el ? el.value.trim() : ""; };
      var item = {};
      if (sec === "edu") {
        item = { school: q("in-school"), major: q("in-major"), degree: q("in-degree"),
                 startMonth: inputToMonth(q("in-start")), endMonth: inputToMonth(q("in-end")) };
        if (!item.school) return;
      } else if (sec === "int") {
        item = { company: q("in-company"), position: q("in-position"),
                 startMonth: inputToMonth(q("in-start")), endMonth: inputToMonth(q("in-end")),
                 duties: paragraphs(row.querySelector(".in-duties").value).map(function (t) { return { text: t }; }) };
        if (!item.company) return;
      } else if (sec === "proj") {
        item = { name: q("in-name"), role: q("in-role"),
                 startMonth: inputToMonth(q("in-start")), endMonth: inputToMonth(q("in-end")),
                 techStack: list(row.querySelector(".in-stack").value),
                 items: paragraphs(row.querySelector(".in-items").value).map(function (t) { return { text: t }; }) };
        if (!item.name) return;
      } else if (sec === "skill") {
        item = { category: q("in-category"), name: q("in-name") };
        if (!item.name) return;
      } else if (sec === "honor") {
        item = { name: q("in-name"), time: q("in-time") || null };
        if (!item.name) return;
      } else if (sec === "job") {
        item = { title: q("in-title"), jdText: row.querySelector(".in-jd").value.trim() };
        if (!item.title || !item.jdText) return;
      }
      out.push(item);
    });
    return out;
  }

  function fillForm(r) {
    clearForm();
    var b = r.basicInfo || {};
    $id("f-name").value = b.name || ""; $id("f-age").value = b.age || "";
    $id("f-email").value = b.email || ""; $id("f-phone").value = b.phone || "";
    $id("f-website").value = b.website || ""; $id("f-base").value = b.base || "";
    $id("f-duration").value = b.internshipDuration || ""; $id("f-start").value = b.startAvailable || "";
    (r.education || []).forEach(function (e) { addRow("edu", e); });
    (r.internship || []).forEach(function (i) { addRow("int", i); });
    (r.project || []).forEach(function (p) { addRow("proj", p); });
    (r.skill || []).forEach(function (s) { addRow("skill", s); });
    (r.honor || []).forEach(function (h) { addRow("honor", h); });
    (r.jobs || []).forEach(function (j) { addRow("job", j); });
  }

  function collectForm() {
    var r = {
      basicInfo: {
        name: $id("f-name").value.trim(), age: parseInt($id("f-age").value, 10) || null,
        email: $id("f-email").value.trim(), phone: $id("f-phone").value.trim(),
        website: $id("f-website").value.trim() || null, base: $id("f-base").value.trim() || null,
        internshipDuration: $id("f-duration").value.trim() || null,
        startAvailable: $id("f-start").value.trim() || null,
      },
      education: collectRows("edu"),
      internship: collectRows("int"),
      project: collectRows("proj"),
      skill: collectRows("skill"),
      honor: collectRows("honor"),
      jobs: collectRows("job"),
    };
    return r;
  }

  function clearForm() {
    ["f-name", "f-age", "f-email", "f-phone", "f-website", "f-base", "f-duration", "f-start"].forEach(function (id) {
      $id(id).value = "";
    });
    ["edu", "int", "proj", "skill", "honor", "job"].forEach(function (sec) {
      $id(sec + "-rows").innerHTML = "";
    });
    updateAddBtns();
  }

  /* ---------------- 保存 ---------------- */
  // r17：保存前时间校验 —— 开始与结束均须在 2015.01 ~ 2030.12 内
  function checkTimes(body) {
    [["education", "教育经历"], ["internship", "实习经历"], ["project", "项目经历"]].forEach(function (pair) {
      (body[pair[0]] || []).forEach(function (it) {
        if (it.startMonth && (it.startMonth < MIN_START || it.startMonth > MAX_END)) {
          throw new Error(pair[1] + "开始时间须在 2015 年 1 月至 2030 年 12 月之间");
        }
        if (it.endMonth && (it.endMonth < MIN_START || it.endMonth > MAX_END)) {
          throw new Error(pair[1] + "结束时间须在 2015 年 1 月至 2030 年 12 月之间");
        }
      });
    });
  }

  function saveResume() {
    var body = collectForm();
    var status = $id("save-status");
    try {
      checkTimes(body);
    } catch (e) {
      status.textContent = e.message;
      return;
    }
    var req;
    if (state.resumeId) {
      body.id = state.resumeId;
      // 保留表单未覆盖的生成态字段（页面密度/方向/内容计划/生成追溯/照片等）
      var old = state.resume || {};
      body.createdAt = old.createdAt || body.createdAt;
      body.pageOption = old.pageOption || "one-page";
      body.density = old.density || "normal";
      body.direction = old.direction || null;
      body.contentPlan = old.contentPlan || null;
      body.generation = old.generation || null;
      body.photo = old.photo || null;
      body.version = old.version || "intern-version";
      body.identity = old.identity || "intern";
      req = fetch("/api/resume/" + state.resumeId, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(function (r) { return r.json(); });
    } else {
      req = fetch("/api/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(function (r) { return r.json(); });
    }
    req.then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      if (!state.resumeId) {
        state.resumeId = j.data.resumeId;
      }
      $id("cur-resume").textContent = $id("f-name").value.trim() || "未命名";
      status.textContent = "已保存 " + new Date().toLocaleTimeString();
      status.classList.remove("err");
      status.classList.add("muted");
      $id("btn-generate").disabled = false;
      setFlow(3);   // r23 P2/P3：简历已保存 → 引导第 3 步生成
      loadList();
    }).catch(function (e) {
      status.textContent = "保存失败：" + e.message;
      status.classList.add("err");
      status.classList.remove("muted");
    });
  }

  /* ---------------- 设置控制台（多 Provider / 搜索 / 插件默认值） ---------------- */
  var editingProviderId = null;

  // r24：厂商预置表（仅下拉选择；配置参数/API 端点由选择自动生成，对用户隐藏）
  var PRESETS = {
    "deepseek": { label: "DeepSeek", baseUrl: "https://api.deepseek.com", keySample: "sk-...", models: [
      { id: "DeepSeek-V4-Flash", apiId: "deepseek-v4-flash", note: "快、便宜，日常够用" },
      { id: "DeepSeek-V4-Pro", apiId: "deepseek-v4-pro", note: "更强推理，成本更高" } ] },
    "siliconflow": { label: "硅基流动 SiliconFlow", baseUrl: "https://api.siliconflow.cn/v1", keySample: "sk-...", models: [
      { id: "Qwen/Qwen2.5-72B-Instruct", note: "国产开源，性价比高" },
      { id: "deepseek-ai/DeepSeek-V3", note: "推理强" },
      { id: "Qwen/Qwen2.5-7B-Instruct", note: "轻量快速" } ] },
    "openai": { label: "OpenAI", baseUrl: "https://api.openai.com/v1", keySample: "sk-...", models: [
      { id: "gpt-4o-mini", note: "低成本快速" },
      { id: "gpt-4o", note: "能力更强" } ] },
    "zhipu": { label: "智谱 GLM", baseUrl: "https://open.bigmodel.cn/api/paas/v4", keySample: "长串字母数字", models: [
      { id: "glm-4-flash", note: "免费快速" },
      { id: "glm-4-air", note: "轻量高性价比" },
      { id: "glm-4-plus", note: "更强" } ] },
    "qwen": { label: "阿里通义千问", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", keySample: "sk-...", models: [
      { id: "qwen-plus", note: "均衡" },
      { id: "qwen-turbo", note: "快" } ] },
    "moonshot": { label: "Moonshot Kimi", baseUrl: "https://api.moonshot.cn/v1", keySample: "sk-...", models: [
      { id: "kimi-k2.6", note: "现役通用" },
      { id: "kimi-k3", note: "旗舰，1M 上下文" } ] },
  };
  var VENDOR_IDS = ["deepseek", "siliconflow", "openai", "zhipu", "qwen", "moonshot"];

  // 模型名分离：apiId = 请求发送的官方 API 名；id = 用户可见常见名（DeepSeek 真实模型仅 v4-flash/v4-pro）
  function modelApiId(m) { return (m && m.apiId) || m.id; }
  // 历史兼容别名：deepseek-chat / deepseek-reasoner 均解析到 v4-flash
  var MODEL_ALIAS = { "deepseek-chat": "DeepSeek-V4-Flash", "deepseek-reasoner": "DeepSeek-V4-Flash" };
  function modelDisplayName(apiId) {
    for (var i = 0; i < VENDOR_IDS.length; i++) {
      var models = (PRESETS[VENDOR_IDS[i]] || {}).models || [];
      for (var j = 0; j < models.length; j++) {
        if (modelApiId(models[j]) === apiId) return models[j].id;
      }
    }
    return MODEL_ALIAS[apiId] || apiId;
  }

  function initVendors() {
    ["s-vendor", "p-vendor"].forEach(function (selId) {
      var sel = $id(selId);
      VENDOR_IDS.forEach(function (vid) {
        var o = document.createElement("option");
        o.value = vid;
        o.textContent = PRESETS[vid].label;
        sel.appendChild(o);
      });
      sel.addEventListener("change", function () { applyVendor(selId === "s-vendor" ? "quick" : "add"); });
    });
    // 模型下拉联动：换模型 → 更新配置名称（隐藏）+ Key placeholder
    $id("s-model").addEventListener("change", function () { onModelChange("quick"); });
    $id("p-model").addEventListener("change", function () { onModelChange("add"); });
    // 首屏默认态：快速配置组选中第一家厂商并联动填充（动态 placeholder 立即可见）
    $id("s-vendor").value = VENDOR_IDS[0];
    applyVendor("quick");
    $id("s-apikey").value = "";
  }

  // 选厂商 → 填充模型下拉（默认第一个）→ 自动生成 name/baseUrl（hidden）→ 动态化 Key placeholder
  function applyVendor(target) {
    var isQuick = target === "quick";
    var sel = $id(isQuick ? "s-vendor" : "p-vendor");
    var p = PRESETS[sel.value];
    var nameEl = $id(isQuick ? "s-name" : "p-name");
    var baseEl = $id(isQuick ? "s-baseurl" : "p-baseurl");
    var modelSel = $id(isQuick ? "s-model" : "p-model");
    var keyEl = $id(isQuick ? "s-apikey" : "p-apikey");
    if (!p) return;   // 存量自定义厂商项：name/baseUrl 已在回显时填入
    fillModelSelect(modelSel, sel.value, "");
    syncHidden(nameEl, baseEl, modelSel.value, sel.value);
    keyEl.placeholder = "粘贴 " + p.label + " API Key（" + p.keySample + "）· 模型 " + modelDisplayName(modelSel.value);
  }

  // 模型下拉填充：vendorId 的模型列表；selected 不在列表时追加（兼容存量自定义模型）
  function fillModelSelect(sel, vendorId, selected) {
    var p = PRESETS[vendorId] || { models: [] };
    sel.innerHTML = "";
    p.models.forEach(function (m) {
      var o = document.createElement("option");
      o.value = modelApiId(m);                       // value = 官方 API 名（保存/发送用）
      o.textContent = m.id + "（" + m.note + "）";   // 文本 = 常见名（用户可见）
      sel.appendChild(o);
    });
    if (selected) {
      var hit = p.models.some(function (m) { return modelApiId(m) === selected; });
      if (!hit) {
        var o = document.createElement("option");
        o.value = selected;
        o.textContent = modelDisplayName(selected) + "（存量配置）";
        sel.appendChild(o);
      }
      sel.value = selected;
    } else if (sel.options.length) {
      sel.value = sel.options[0].value;
    }
  }

  // 配置名称 / Base URL 由选择自动生成（用户不可见，防止误改）
  function syncHidden(nameEl, baseEl, model, vendorId) {
    var p = PRESETS[vendorId];
    if (!p) return;
    nameEl.value = p.label + " · " + modelDisplayName(model);
    baseEl.value = p.baseUrl;
  }

  // 模型变化：同步隐藏参数 + 更新 Key placeholder（R24 动态占位）
  function onModelChange(target) {
    var isQuick = target === "quick";
    var sel = $id(isQuick ? "s-vendor" : "p-vendor");
    var modelSel = $id(isQuick ? "s-model" : "p-model");
    var p = PRESETS[sel.value];
    if (!p || !modelSel.value) return;
    syncHidden($id(isQuick ? "s-name" : "p-name"),
               $id(isQuick ? "s-baseurl" : "p-baseurl"), modelSel.value, sel.value);
    $id(isQuick ? "s-apikey" : "p-apikey").placeholder =
      "粘贴 " + p.label + " API Key（" + p.keySample + "）· 模型 " + modelDisplayName(modelSel.value);
  }

  // 反向匹配：已有配置按 baseUrl 前缀回显厂商下拉
  function matchVendor(baseUrl, model) {
    for (var i = 0; i < VENDOR_IDS.length; i++) {
      var vid = VENDOR_IDS[i];
      var p = PRESETS[vid];
      if (p.baseUrl && baseUrl && baseUrl.indexOf(p.baseUrl) === 0) return vid;
    }
    return "";
  }

  // 存量自定义配置（baseUrl 不在预置表）：厂商下拉插入「自定义」标识项，保留原参数
  function ensureCustomVendor(act) {
    var sel = $id("s-vendor");
    // 先移除旧的自定义标识项，避免渲染残留
    for (var i = sel.options.length - 1; i >= 0; i--) {
      if (sel.options[i].value === "__custom") sel.remove(i);
    }
    var o = document.createElement("option");
    o.value = "__custom";
    o.textContent = "自定义 · " + (act.name || "手动配置");
    sel.appendChild(o);
    sel.value = "__custom";
  }

  // r25 P2/P3：左栏流程栏 —— 步骤高亮（active 当前 / done 已完成）+ railNote 动态引导行
  var RAIL_NOTES = {
    1: "开始：第 1 步 选择厂商与模型 → 粘贴 API Key → 保存并自检",
    2: "下一步：第 2 步 填写基本信息 / 教育 / 技能 / JD → 保存简历",
    3: "下一步：第 3 步 选择页数与水印 → 点「生成简历」",
    4: "完成：结果已生成，可在预览确认 / 编辑 / 打印导出",
  };
  function setFlow(step) {
    document.querySelectorAll("#progress-steps .pstep").forEach(function (el, i) {
      el.classList.toggle("active", i === step - 1);
      el.classList.toggle("done", i < step - 1);
    });
    var note = $id("railNote");
    if (note && RAIL_NOTES[step]) note.textContent = RAIL_NOTES[step];
  }

  // r25 P9：右栏常驻提醒栏 —— 字段说明字典（t = 一句话标题，h = 正文，f = 底部一行补充）
  // 与 MS-Agent §3.6 同款：聚焦 / 点击任意输入项即切换内容；未登记字段回退欢迎态
  var HELP = {
    "s-vendor": { t: "① 选择 AI 厂商", h:
      "<p>按你持有的 API Key 选择对应平台：<b>DeepSeek / 硅基流动 / OpenAI / 智谱 / 通义 / Kimi</b>。</p>" +
      "<p>选好后模型列表会自动更新，无需手动填写地址。</p>", f: "不确定选哪个？先看你申请 Key 的平台即可。" },
    "s-model": { t: "选择模型", h:
      "<p>厂商下会列出常用模型（括号里是特点与成本提示）。日常生成简历选<b>低成本</b>档即可，效果不好再换强档。</p>", f: "换模型不会丢已填简历内容，可随时切换重试。" },
    "s-apikey": { t: "🔑 API Key 是什么？", h:
      "<p>Key 相当于平台的<b>身份凭证</b>，在平台控制台「API Keys」页面创建，通常以 <code>sk-</code> 开头。</p>" +
      "<p>将整串 Key <b>完整粘贴</b>（前后不留空格），点「保存并自检」验证是否可用。</p>", f: "Key 只保存在本机，不会上传到任何第三方。" },
    "p-vendor": { t: "新增配置 · 选择厂商", h: "<p>高级设置里可维护多套模型配置，列表顺序即调用优先级，激活项排最前。</p>", f: "快速配置组会同步显示当前激活项。" },
    "p-model": { t: "新增配置 · 选择模型", h: "<p>选择该厂商下的具体模型，参数自动生成。</p>", f: "不同配置可对应不同厂商 / 模型，按需切换。" },
    "p-apikey": { t: "新增配置 · API Key", h: "<p>粘贴该配置对应的 API Key（格式同快速配置组）。</p>", f: "保存时会自动自检一次，失败会给出具体原因。" },
    "s-searchkey": { t: "🔎 Tavily 联网搜索 Key", h:
      "<p>配置后生成简历前会自动搜索权威来源，减少「待联网核实」标注。不配置也不影响生成。</p>" +
      "<ul><li>官方平台：<code>app.tavily.com</code> → 注册登录</li><li>左侧「API Keys」→「Create API Key」</li><li>粘贴 <code>tvly-</code> 开头的密钥保存</li></ul>", f: "留空保存 = 关闭联网搜索。" },
    "f-name": { t: "姓名", h: "<p>填写求职者姓名，将显示在简历顶部。</p>", f: "必填。" },
    "f-age": { t: "年龄", h: "<p>填写当前年龄（数字），留空亦可。</p>", f: "可选。" },
    "f-email": { t: "邮箱", h: "<p>填写常用邮箱，建议与投递渠道一致，如 <code>name@mail.com</code>。</p>", f: "必填，格式需包含 @。" },
    "f-phone": { t: "电话", h: "<p>填写手机号，招聘方主要通过电话联系。</p>", f: "必填。" },
    "g-page": { t: "页数选择", h: "<p>一页：精炼紧凑，适合应届 / 实习投递；两页：更从容，适合经历较多的场景。</p>", f: "AI 会按所选页数自动裁剪内容密度。" },
    "g-watermark": { t: "水印选择", h:
      "<p><b>无（正式无水印）</b>：版面干净，适合最终投递。</p>" +
      "<p><b>练习（有水印）</b>：底部叠加「本简历部分内容由 AI 生成，请确认真实性后再投递」提示，防止未经确认的内容被误投递。</p>", f: "正式投递前建议用「无」水印版本。" },
    "g-deep": { t: "深度搜索", h: "<p>开启后生成前自动联网核实关键信息（需在高级设置配置搜索 Key）。关闭则完全依赖模型能力，速度更快。</p>", f: "未配置搜索 Key 时该项不影响生成。" },
    "btn-save-settings": { t: "保存并自检", h: "<p>保存当前厂商 / 模型 / Key 配置，并立即向模型平台发起一次最小请求验证 Key 是否可用。</p>", f: "自检通过后即可开始生成简历。" },
    "btn-generate": { t: "简历生成", h: "<p>基于已保存的简历信息与右侧选项生成简历，过程实时显示进度。</p>", f: "需先保存简历（必填项完整）才能生成。" },
    "p-export-fmt": { t: "导出格式", h:
      "<p><b>PDF</b>：浏览器打印另存为 PDF，最通用；</p>" +
      "<p><b>DOCX</b>：导出可编辑 Word 文档；</p>" +
      "<p><b>Markdown</b>：纯文本标记格式，便于存入笔记 / 知识库；</p>" +
      "<p><b>HTML</b>：标准网页文档，可独立打开或直接打印；</p>" +
      "<p><b>JSON</b>：导出结构化数据，便于二次处理。</p>", f: "导出前请先预览确认排版。" },
    "btn-adapt": { t: "自动适配", h: "<p>按当前所选格式重新调整排版，使内容自动适配到单页 / 双页等目标布局。</p>", f: "适配后可继续点击正文微调。" },
    // ---- 基本信息（可选） ----
    "f-website": { t: "个人网页", h: "<p>填写个人主页 / GitHub / 作品集链接，如 <code>https://github.com/xxx</code>。</p>", f: "可选，能显著增强技术岗投递说服力。" },
    "f-base": { t: "期望城市", h: "<p>填写求职目标城市，如「北京」「深圳」；支持多个用逗号分隔。</p>", f: "可选。" },
    "f-duration": { t: "可实习时长", h: "<p>填写可实习的时长，如「6 个月」；招聘方据此排期。</p>", f: "可选。" },
    "f-start": { t: "到岗时间", h: "<p>填写可到岗时间，如「2026-09-01」或「随时」。</p>", f: "可选。" },
    // ---- 教育经历（动态行） ----
    "edu-in-school": { t: "学校", h: "<p>填写学校全称，如「企鹅大学」。</p>", f: "必填；教育经历至少 1 条。" },
    "edu-in-major": { t: "专业", h: "<p>填写所学专业全称，如「计算机科学」。</p>", f: "必填。" },
    "edu-in-degree": { t: "学历", h: "<p>选择学历：专科 / 学士 / 硕士 / 博士。</p>", f: "必填。" },
    "in-start": { t: "开始时间", h: "<p>选择开始年月（月份选择器），范围限制 <b>2015.01 ~ 2030.12</b>。</p>", f: "填写实际开始年月即可。" },
    "in-end": { t: "结束时间", h: "<p>选择结束年月（月份选择器），范围限制 <b>2015.01 ~ 2030.12</b>。</p>", f: "填写实际结束年月；在读 / 在职可留空。" },
    // ---- 实习经历（动态行） ----
    "int-in-company": { t: "公司", h: "<p>填写公司 / 单位全称。</p>", f: "必填；实习经历可选。" },
    "int-in-position": { t: "职位", h: "<p>填写实习岗位名称，如「算法实习生」。</p>", f: "必填。" },
    "int-in-duties": { t: "职责", h: "<p>用自然语言描述做了什么，每行一条；AI 会自动润色为简历语言。</p>", f: "写「做了什么 + 怎么做的」最有说服力。" },
    // ---- 项目经验（动态行） ----
    "proj-in-name": { t: "项目名称", h: "<p>填写项目名称，如「简历生成助手」。</p>", f: "必填；项目经验可选。" },
    "proj-in-role": { t: "角色", h: "<p>填写在项目中的角色，如「负责人 / 核心开发」。</p>", f: "必填。" },
    "proj-in-stack": { t: "技术栈", h: "<p>填写用到的技术，逗号分隔，如 <code>Python, FastAPI, PyTorch</code>。</p>", f: "可空；有则让 HR 一眼看到技能。" },
    "proj-in-items": { t: "项目要点", h: "<p>自然语言描述项目亮点 / 成果，每行一条；AI 会自动润色。</p>", f: "优先写量化成果：规模、速度、收益。" },
    // ---- 技能特长（动态行） ----
    "skill-in-category": { t: "技能分类", h: "<p>为技能选择分类：专业技能 / 工具与框架 / 语言能力 / 算法与模型 / 数据与统计 / 工程实践等。</p>", f: "分类帮助 HR 快速定位能力项。" },
    "skill-in-name": { t: "技能名称", h: "<p>填写具体技能，如「Python」「PyTorch」「RAG」。</p>", f: "必填；技能特长至少 1 条。" },
    // ---- 证书荣誉（动态行） ----
    "honor-in-name": { t: "奖项", h: "<p>填写获奖 / 证书名称，如「国家奖学金」「CET-6」。</p>", f: "可选。" },
    "honor-in-time": { t: "时间", h: "<p>填写获奖 / 发证时间，如「2024.06」。</p>", f: "可选。" },
    // ---- 目标岗位 JD（动态行） ----
    "job-in-title": { t: "岗位名称", h: "<p>填写投递岗位名称，如「AI 应用开发工程师」。</p>", f: "必填；JD 至少 1 条。" },
    "job-in-jd": { t: "JD 原文", h: "<p>粘贴岗位描述原文（可多段）。AI 据此对齐简历关键词，匹配度更高。</p>", f: "必填；JD 越完整，生成越贴合。" },
    // ---- 保存 / 列表 / 导出 ----
    "btn-save": { t: "保存简历", h: "<p>保存当前填写的简历信息到本地。必填项缺失会提示并高亮定位。</p>", f: "保存后「简历生成」按钮才可用。" },
    "btn-new": { t: "新建简历", h: "<p>清空当前表单，开始填写一份全新简历。</p>", f: "新建不会删除已保存的简历。" },
    "btn-export": { t: "导出", h: "<p>按右侧选定的格式导出：PDF（打印）/ DOCX（Word）/ JSON（数据）。</p>", f: "需先生成简历。" },
    // ---- 高级设置抽屉：默认值 / 新增配置 / 搜索 / 插件 ----
    "s-deep": { t: "默认开启深度搜索", h: "<p>勾选后，新任务默认开启联网搜索（需配置搜索 Key）；不勾选则默认关闭。</p>", f: "生成页的「深度搜索」可单独临时开关。" },
    "s-watermark-formal": { t: "默认无水印", h: "<p>勾选 = 默认正式版（无水印）；取消勾选 = 默认练习版（底部带 AI 生成提示水印）。</p>", f: "防止未经确认的内容被误投递。" },
    "btn-add-provider": { t: "添加配置", h: "<p>把上方「厂商 + 模型 + Key」保存为一套新模型配置，加入配置列表。</p>", f: "多套配置可随时切换激活。" },
    "btn-test-provider": { t: "配置自检", h: "<p>用当前输入的内容向模型平台发起一次最小请求，验证 Key / 模型是否可用，不保存。</p>", f: "失败会给出 401 / 429 等具体原因。" },
    "btn-save-search": { t: "保存搜索 Key", h: "<p>保存 Tavily 搜索密钥，启用联网搜索能力；留空保存 = 关闭。</p>", f: "教程见上方「如何获取 Tavily API Key」。" },
    "btn-save-defaults": { t: "保存默认值", h: "<p>保存「深度搜索 / 水印」两项默认设置，作用于后续新任务。</p>", f: "仅影响默认值，当前生成页选项独立。" },
    "plugin-configure": { t: "一键配置", h: "<p>自动检测并安装该外部 CLI 工具的依赖（Python 包 / 项目文件）。配置成功后「启用」才可选。</p>", f: "失败会给出排查指引，可展开卡片查看详情。" },
    "__default__": { t: "欢迎使用简历生成助手", h:
      "<p>聚焦或点击任意输入项，这里会显示对应操作的<b>详细说明</b>——说明书跟着光标走。</p>", f: "使用主线：① 配置模型 → ② 填写简历 → ③ 生成简历 → ④ 预览导出" },
  };

  function showHelp(id) {
    var h = HELP[id] || HELP.__default__;
    var t = $id("helpTitle"), b = $id("helpBody"), f = $id("helpFoot");
    if (!t || !b || !f) return;
    t.innerHTML = h.t;
    b.innerHTML = h.h;
    f.innerHTML = h.f;
  }

  // 键盘 Tab 聚焦也能命中；支持 id 与动态行的 data-help（sec-字段），并做通用回退（int-in-start → in-start）
  document.addEventListener("focusin", function (e) {
    var t = e.target;
    if (!t) return;
    var key = t.id || (t.getAttribute ? t.getAttribute("data-help") : "") || "";
    if (key && HELP[key]) { showHelp(key); return; }
    if (key.indexOf("-") > 0) {
      var generic = key.slice(key.indexOf("-") + 1);   // 去掉 section 前缀
      if (HELP[generic]) showHelp(generic);
    }
  });
  // 鼠标点击兜底（触屏 / 无焦点场景）
  Object.keys(HELP).forEach(function (id) {
    if (id === "__default__") return;
    var el = $id(id);
    if (el) el.addEventListener("click", function () { showHelp(id); });
  });

  // r23 P4：必填缺失定位 —— 返回缺失项列表（label + 定位元素）
  function checkRequired() {
    var miss = [];
    if (!$id("f-name").value.trim()) miss.push({ label: "基本信息·姓名", el: $id("f-name") });
    if (!$id("edu-rows").querySelectorAll(".row").length) miss.push({ label: "教育经历", el: $id("edu-rows"), sec: "edu" });
    if (!$id("skill-rows").querySelectorAll(".row").length) miss.push({ label: "技能特长", el: $id("skill-rows"), sec: "skill" });
    if (!$id("job-rows").querySelectorAll(".row").length) miss.push({ label: "目标岗位 JD", el: $id("job-rows"), sec: "job" });
    return miss;
  }

  // 滚动 + 红框高亮第一个缺失字段（2.2s 自动移除；空行容器回退到「添加」按钮）
  function locateFirstMissing(missing) {
    if (!missing.length) return null;
    var first = missing[0];
    var el = first.el;
    var target = el.tagName === "INPUT"
      ? el
      : el.querySelector("input, select, button") || document.querySelector('[data-add="' + first.sec + '"]');
    if (target) {
      target.classList.add("err-inp");
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      setTimeout(function () { target.classList.remove("err-inp"); }, 2200);
    }
    return first.label;
  }

  function settingsText() {
    var st = $id("settings-status");
    if (state.activeProvider) {
      st.textContent = "已激活：" + state.activeProvider.name;
      st.className = "key-status ok";
    } else if (state.hasAnyProvider) {
      st.textContent = "未启用任何配置";
      st.className = "key-status warn";
    } else {
      st.textContent = "未配置模型 Key";
      st.className = "key-status warn";
    }
  }

  function renderProviders(providers, activeId) {
    var box = $id("prov-list");
    box.innerHTML = "";
    state.providers = providers || [];
    state.activeProviderId = activeId || "";
    if (!state.providers.length) {
      box.innerHTML = '<div class="muted small">暂无配置：在下方「新增配置」或上方卡片中填写后保存。</div>';
      settingsText();
      return;
    }
    state.providers.forEach(function (p) {
      var item = document.createElement("div");
      item.className = "prov-item" + (p.id === activeId ? " active" : "");
      var head = document.createElement("div");
      head.className = "prov-main";
      var tag = p.enabled
        ? (p.id === activeId ? '<span class="tag required">已激活</span>' : '<span class="tag ok-tag">启用</span>')
        : '<span class="tag optional">停用</span>';
      head.innerHTML = "<b>" + esc(p.name || "未命名") + "</b>" +
        " · 模型 <code>" + esc(modelDisplayName(p.model || "-")) + "</code> " + tag;
      var sub = document.createElement("div");
      sub.className = "prov-sub";
      sub.textContent = "Key: " + (p.apiKeyMasked || "未设置") + " · " + (p.baseUrl || "");
      var ops = document.createElement("div");
      ops.className = "prov-ops";
      if (p.id !== activeId) {
        var act = document.createElement("button");
        act.className = "btn tiny";
        act.textContent = "激活";
        act.addEventListener("click", function () { activateProvider(p.id); });
        ops.appendChild(act);
      }
      var edit = document.createElement("button");
      edit.className = "btn tiny";
      edit.textContent = "编辑";
      edit.addEventListener("click", function () { editProvider(p); });
      ops.appendChild(edit);
      var del = document.createElement("button");
      del.className = "btn tiny danger-t";
      del.textContent = "删除";
      del.addEventListener("click", function () { delProvider(p.id); });
      ops.appendChild(del);
      item.appendChild(head);
      item.appendChild(sub);
      item.appendChild(ops);
      box.appendChild(item);
    });
    // 激活项排最前（优先级）
    var act = state.providers.filter(function (p) { return p.id === activeId; })[0];
    if (act) {
      state.activeProvider = act;
      // 快速配置组展示激活项（仅厂商/模型下拉 + 动态 placeholder，参数自动回填 hidden）
      var vid = matchVendor(act.baseUrl || "", act.model || "");
      var keyEl = $id("s-apikey");
      if (vid) {
        $id("s-vendor").value = vid;
        fillModelSelect($id("s-model"), vid, act.model || "");
        syncHidden($id("s-name"), $id("s-baseurl"), $id("s-model").value, vid);
        keyEl.placeholder = "粘贴 " + PRESETS[vid].label + " API Key（" + PRESETS[vid].keySample +
          "）· 模型 " + modelDisplayName($id("s-model").value);
      } else {
        ensureCustomVendor(act);
        fillModelSelect($id("s-model"), "", act.model || "");
        $id("s-name").value = act.name || "";
        $id("s-baseurl").value = act.baseUrl || "";
        keyEl.placeholder = "sk-...（更新时留空 = 保留原 Key）";
      }
    } else {
      state.activeProvider = null;
      $id("s-name").value = "";
      $id("s-baseurl").value = "";
      $id("s-model").innerHTML = "";
      $id("s-apikey").placeholder = "sk-...";
    }
    state.hasAnyProvider = state.providers.length > 0;
    settingsText();
    // r23 P2/P3：引导条随配置状态切换（已配置 → 第 2 步填简历）
    setFlow(state.activeProvider ? 2 : 1);
  }

  function loadSettings() {
    return fetch("/api/settings").then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      var d = j.data;
      renderProviders(d.providers || [], d.activeProviderId);
      renderPlugins(d.plugins || []);
      $id("s-deep").checked = d.deepSearchDefault !== false;
      $id("s-watermark-formal").checked = d.watermarkDefault !== "practice";
      // 同步生成条默认值
      $id("g-deep").checked = d.deepSearchDefault !== false;
      $id("g-watermark").value = d.watermarkDefault === "practice" ? "practice" : "formal";
      if (d.searchHasKey) {
        $id("search-msg").textContent = "搜索 Key 已配置：" + d.searchApiKeyMasked;
      }
    }).catch(function () {});
  }

  function testProvider(baseUrl, model, apiKey) {
    return fetch("/api/settings/providers/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ baseUrl: baseUrl, model: model, apiKey: apiKey }),
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      return j.data.ok ? "自检通过" : "自检失败：" + (j.data.error || "未知错误");
    });
  }

  // 保存并自检（快速配置组 = 新增或编辑当前 provider；参数由下拉选择自动生成）
  function saveSettings() {
    var hint = $id("settings-hint");
    var vendorId = $id("s-vendor").value;
    var p = PRESETS[vendorId];
    var body = {
      name: $id("s-name").value.trim(),
      baseUrl: $id("s-baseurl").value.trim(),
      model: $id("s-model").value.trim(),
    };
    if (editingProviderId) body.id = editingProviderId;
    var key = $id("s-apikey").value.trim();
    if (key) body.apiKey = key;
    if (!vendorId) { hint.textContent = "请选择 AI 厂商"; return; }
    if (!body.model) { hint.textContent = "请选择模型"; return; }
    if (!body.baseUrl) { hint.textContent = "厂商参数未生成，请重新选择厂商"; return; }
    if (!body.name) body.name = p ? p.label + " · " + modelDisplayName(body.model) : body.model;
    $id("btn-save-settings").disabled = true;
    hint.textContent = "保存中…";
    fetch("/api/settings/providers", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      var saved = (j.data.providers || []).filter(function (p) { return p.id === j.data.activeProviderId; })[0] ||
                  (j.data.providers || [])[0];
      renderProviders(j.data.providers, j.data.activeProviderId);
      $id("s-apikey").value = "";
      editingProviderId = null;
      $id("btn-save-settings").textContent = "保存并自检";
      if (key && saved) {
        return testProvider(saved.baseUrl, saved.model, key).then(function (msg) {
          hint.textContent = "已保存，" + msg;
        });
      }
      hint.textContent = "已保存 " + new Date().toLocaleTimeString();
      return Promise.resolve();
    }).catch(function (e) {
      hint.textContent = "保存失败：" + e.message;
    }).then(function () {
      $id("btn-save-settings").disabled = false;
    });
  }

  // 高级设置：新增配置（同样仅下拉选择，参数自动生成）
  function addProvider() {
    var msg = $id("prov-msg");
    var vendorId = $id("p-vendor").value;
    var p = PRESETS[vendorId];
    var body = {
      name: $id("p-name").value.trim(),
      baseUrl: $id("p-baseurl").value.trim(),
      model: $id("p-model").value.trim(),
      capabilities: "text",   // 默认文本能力（r16：不再提供能力选项）
    };
    var key = $id("p-apikey").value.trim();
    if (!vendorId) { msg.textContent = "请选择 AI 厂商"; return; }
    if (!body.model) { msg.textContent = "请选择模型"; return; }
    if (!body.baseUrl) { msg.textContent = "厂商参数未生成，请重新选择厂商"; return; }
    if (!body.name) body.name = p ? p.label + " · " + modelDisplayName(body.model) : body.model;
    if (key) body.apiKey = key;
    $id("btn-add-provider").disabled = true;
    msg.textContent = "保存中…";
    fetch("/api/settings/providers", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      renderProviders(j.data.providers, j.data.activeProviderId);
      var saved = (j.data.providers || []).filter(function (p) { return p.id === j.data.activeProviderId; })[0];
      // 重置新增配置组：清空 Key，模型回到厂商首模型，placeholder 同步
      $id("p-apikey").value = "";
      fillModelSelect($id("p-model"), $id("p-vendor").value, "");
      onModelChange("add");
      if (key && saved) {
        return testProvider(saved.baseUrl, saved.model, key).then(function (m) { msg.textContent = m; });
      }
      msg.textContent = "已添加配置";
      return Promise.resolve();
    }).catch(function (e) {
      msg.textContent = "添加失败：" + e.message;
    }).then(function () {
      $id("btn-add-provider").disabled = false;
    });
  }

  // 高级设置：用当前卡片字段自检（不落盘）
  function testQuickProvider() {
    var msg = $id("prov-msg");
    var baseUrl = $id("s-baseurl").value.trim() || $id("p-baseurl").value.trim();
    var model = $id("s-model").value.trim() || $id("p-model").value.trim();
    var key = $id("s-apikey").value.trim() || $id("p-apikey").value.trim();
    if (!baseUrl || !model || !key) { msg.textContent = "请填写 Base URL / 模型 / API Key"; return; }
    msg.textContent = "自检中…";
    testProvider(baseUrl, model, key).then(function (m) { msg.textContent = m; });
  }

  function editProvider(p) {
    editingProviderId = p.id;
    var vid = matchVendor(p.baseUrl || "", p.model || "");
    $id("s-vendor").value = vid;
    var keyEl = $id("s-apikey");
    if (vid) {
      fillModelSelect($id("s-model"), vid, p.model || "");
      syncHidden($id("s-name"), $id("s-baseurl"), $id("s-model").value, vid);
      keyEl.placeholder = "粘贴 " + PRESETS[vid].label + " API Key（" + PRESETS[vid].keySample +
        "）· 模型 " + modelDisplayName($id("s-model").value);
    } else {
      ensureCustomVendor(p);
      fillModelSelect($id("s-model"), "", p.model || "");
      $id("s-name").value = p.name || "";
      $id("s-baseurl").value = p.baseUrl || "";
      keyEl.placeholder = "sk-...（更新时留空 = 保留原 Key）";
    }
    $id("s-apikey").value = "";
    $id("btn-save-settings").textContent = "保存修改";
    $id("settings-hint").textContent = "正在编辑：" + p.name + "（Key 留空 = 保留原 Key）";
    closeSettings();
    $id("btn-save-settings").scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function activateProvider(id) {
    fetch("/api/settings/providers/" + id + "/activate", { method: "POST" })
      .then(function (r) { return r.json(); }).then(function (j) {
        if (j.code !== 0) throw new Error(errMsg(j));
        renderProviders(j.data.providers, j.data.activeProviderId);
      }).catch(function (e) { Adapt.showBanner("激活失败：" + e.message, true); });
  }

  function delProvider(id) {
    fetch("/api/settings/providers/" + id, { method: "DELETE" })
      .then(function (r) { return r.json(); }).then(function (j) {
        if (j.code !== 0) throw new Error(errMsg(j));
        if (editingProviderId === id) {
          editingProviderId = null;
          $id("btn-save-settings").textContent = "保存并自检";
        }
        renderProviders(j.data.providers, j.data.activeProviderId);
      }).catch(function (e) { Adapt.showBanner("删除失败：" + e.message, true); });
  }

  function saveSearch() {
    var key = $id("s-searchkey").value.trim();
    fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ searchApiKey: key }),
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      $id("s-searchkey").value = "";
      $id("search-msg").textContent = key ? "已保存搜索 Key" : "已关闭联网搜索";
    }).catch(function (e) {
      $id("search-msg").textContent = "保存失败：" + e.message;
    });
  }

  function saveDefaults() {
    fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deepSearchDefault: $id("s-deep").checked,
        watermarkDefault: $id("s-watermark-formal").checked ? "formal" : "practice",
      }),
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      $id("g-deep").checked = $id("s-deep").checked;
      $id("g-watermark").value = $id("s-watermark-formal").checked ? "formal" : "practice";
      $id("defaults-msg").textContent = "已保存默认值 " + new Date().toLocaleTimeString();
    }).catch(function (e) {
      $id("defaults-msg").textContent = "保存失败：" + e.message;
    });
  }

  // 可集成插件（外部 CLI 工具）：双层启动 —— 第一层「一键配置」+ 第二层「手动勾选」
  function renderPlugins(list) {
    var box = $id("plugin-list");
    box.innerHTML = "";
    state.plugins = list || [];
    if (!state.plugins.length) {
      box.innerHTML = '<div class="muted small">暂无可用插件。</div>';
      return;
    }
    state.plugins.forEach(function (p) {
      var item = document.createElement("div");
      item.className = "plugin-item" + (p.enabled ? " on" : "");
      var main = document.createElement("div");
      main.className = "plugin-main";
      var st = p.configured
        ? '<span class="tag ok-tag">已配置</span>'
        : (p.installStatus === "failed"
            ? '<span class="tag err-tag">配置失败</span>'
            : '<span class="tag optional">待接入</span>');
      if (p.enabled && p.configured) st += '<span class="tag on-tag">已启用</span>';
      main.innerHTML = "<b>" + esc(p.name) + "</b>" +
        " <span class=\"tag cat-tag\">" + esc(p.category) + "</span> " + st;
      var sub = document.createElement("div");
      sub.className = "plugin-sub";
      sub.textContent = p.description + " ";
      var link = document.createElement("a");
      link.href = p.source;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "GitHub";
      sub.appendChild(link);

      // 操作区：第一层「一键配置」+ 第二层「启用」勾选
      var ops = document.createElement("div");
      ops.className = "plugin-ops";
      var cfgBtn = document.createElement("button");
      cfgBtn.type = "button";
      cfgBtn.className = "btn small";
      cfgBtn.setAttribute("data-help", "plugin-configure");   // r25 P9：提醒栏说明
      cfgBtn.innerHTML = p.configured ? "重新配置" : ICO_GEAR + "一键配置";
      cfgBtn.addEventListener("click", function () { configurePlugin(p.id, cfgBtn); });
      ops.appendChild(cfgBtn);
      var toggle = document.createElement("label");
      toggle.className = "chk plugin-toggle";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = p.enabled;
      cb.disabled = !p.configured;   // 未配置前禁用勾选（避免"假启用"）
      cb.addEventListener("change", function () { togglePlugin(p.id, cb.checked); });
      toggle.appendChild(cb);
      toggle.appendChild(document.createTextNode("启用"));
      ops.appendChild(toggle);
      item.appendChild(main);

      // R20-3：配置前醒目提示（如 MediaCrawler 需扫码登录）
      if (p.loginNotice) {
        var notice = document.createElement("div");
        notice.className = "login-notice";
        notice.textContent = "⚠ " + p.loginNotice;
        item.appendChild(notice);
      }
      item.appendChild(sub);
      item.appendChild(ops);

      // 一键配置结果提示（installStatus / installMsg）
      if (p.installMsg || p.installStatus === "failed") {
        var hint = document.createElement("div");
        hint.className = "plugin-hint" + (p.installStatus === "failed" ? " err" : "");
        hint.textContent = p.installMsg || ("状态：" + p.installStatus);
        item.appendChild(hint);
      }

      // 第二层精细化：功能模块勾选（configured 后展示）
      if (p.configured && (p.featuresList || []).length) {
        var feats = document.createElement("div");
        feats.className = "plugin-feats";
        feats.appendChild(document.createTextNode("功能模块："));
        (p.featuresList || []).forEach(function (f) {
          var fl = document.createElement("label");
          fl.className = "chk feat";
          var fc = document.createElement("input");
          fc.type = "checkbox";
          fc.checked = !!p.features[f.id];
          fc.addEventListener("change", function () { toggleFeature(p.id, f.id, fc.checked); });
          fl.appendChild(fc);
          fl.appendChild(document.createTextNode(f.name));
          feats.appendChild(fl);
        });
        item.appendChild(feats);
      }
      box.appendChild(item);
    });
  }

  // 第一层：一键配置（依赖检测 → 自动安装 → 默认参数 → 基础功能预激活）
  function configurePlugin(id, btn) {
    btn.disabled = true;
    btn.textContent = "配置中…";
    fetch("/api/settings/plugins/" + id + "/configure", { method: "POST" })
      .then(function (r) { return r.json(); }).then(function (j) {
        if (j.code !== 0) throw new Error(errMsg(j));
        renderPlugins(j.data.plugins);
        var me = (j.data.plugins || []).filter(function (x) { return x.id === id; })[0];
        $id("plugin-msg").textContent = (me && me.configured
          ? "一键配置完成 "
          : "一键配置失败（详见插件卡片提示） ") + new Date().toLocaleTimeString();
      }).catch(function (e) {
        btn.disabled = false;
        btn.innerHTML = ICO_GEAR + "一键配置";
        Adapt.showBanner("一键配置失败：" + e.message, true);
      });
  }

  // 第二层：功能模块精细控制
  function toggleFeature(id, fid, enabled) {
    fetch("/api/settings/plugins/" + id + "/features/" + fid, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: enabled }),
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      renderPlugins(j.data.plugins);
    }).catch(function (e) {
      Adapt.showBanner("功能模块更新失败：" + e.message, true);
    });
  }

  function togglePlugin(id, enabled) {
    fetch("/api/settings/plugins/" + id, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: enabled }),
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      renderPlugins(j.data.plugins);
      $id("plugin-msg").textContent = "已更新插件状态 " + new Date().toLocaleTimeString();
    }).catch(function (e) {
      // 失败：不盲目取反回滚，改从服务端拉取真实状态同步，并明确提示
      loadSettings().catch(function () {});
      Adapt.showBanner("插件状态保存失败，已恢复原状态：" + e.message + "（请确认后端服务已启动）", true);
    });
  }

  /* ---------------- 高级设置抽屉（顶部常驻按钮，仿 MS-Agent） ---------------- */
  function openSettings() {
    $id("settings-drawer").classList.add("open");
    $id("settings-mask").style.display = "block";
    loadSettings();   // 打开时刷新配置/插件状态
    // 阶段4：打开后焦点移入首个输入框，键盘用户可直接操作
    var first = $id("p-vendor");
    if (first) first.focus();
  }
  function closeSettings() {
    $id("settings-drawer").classList.remove("open");
    $id("settings-mask").style.display = "none";
  }
  // 阶段4：Esc 关闭高级设置抽屉（键盘可达性）
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var d = $id("settings-drawer");
      if (d && d.classList.contains("open")) closeSettings();
    }
  });

  /* ---------------- 生成 + SSE ---------------- */
  function startGenerate() {
    if (!state.resumeId) { Adapt.showBanner("请先保存简历", true); return; }
    // r23 P4：生成前必填缺失定位引导（滚动 + 红框高亮 + 定位文案）
    var missing = checkRequired();
    if (missing.length) {
      locateFirstMissing(missing);
      Adapt.showBanner("必填项未填写：" + missing.map(function (m) { return m.label; }).join("、") +
        "——已定位到第一个缺失项", true);
      setFlow(2);
      return;
    }
    var body = {
      resumeId: state.resumeId,
      pageOption: $id("g-page").value,
      watermarkMode: $id("g-watermark").value,
      deepSearch: $id("g-deep").checked,
    };
    $id("btn-generate").disabled = true;
    $id("btn-cancel").disabled = false;
    $id("progress").classList.remove("hidden");
    $id("progress-fill").style.width = "0%";
    $id("progress-text").textContent = "提交中…";
    Adapt.showBanner("生成中…");
    fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      state.taskId = j.data.taskId;
      openSSE(state.taskId);
    }).catch(function (e) {
      Adapt.showBanner("提交失败：" + e.message, true);
      resetGenerateBtns();
    });
  }

  function openSSE(taskId) {
    closeSSE();
    var curStage = 0, curStageTotal = 1;
    es = new EventSource("/api/task/" + taskId + "/events");
    es.addEventListener("task.stage", function (ev) {
      var d = JSON.parse(ev.data);
      curStage = d.stageIndex || 0;
      curStageTotal = d.stageTotal || 1;
      setProgress((curStage - 1) / curStageTotal, "阶段：" + d.stage + "（" + curStage + "/" + curStageTotal + "）");
    });
    es.addEventListener("block.progress", function (ev) {
      var d = JSON.parse(ev.data);
      setProgress((curStage - 1) / curStageTotal + (d.progress || 0) / curStageTotal,
        "生成板块：" + (d.block || ""));
    });
    es.addEventListener("block.done", function (ev) {
      var d = JSON.parse(ev.data);
      $id("progress-text").textContent = "板块完成：" + (d.block || "") + (d.degraded ? "（降级）" : "");
    });
    es.addEventListener("task.done", function (ev) {
      var d = JSON.parse(ev.data);
      closeSSE();
      state.html = d.html;
      state.config = d.config;
      state.resumeId = d.resumeId || state.resumeId;
      fetch("/api/resume/" + state.resumeId).then(function (r) { return r.json(); }).then(function (j) {
        if (j.code === 0) state.resume = j.data;
      }).catch(function () {}).then(function () {
        Adapt.render(state.html);
        $id("btn-adapt").disabled = false;
        $id("btn-export").disabled = false;
        $id("btn-generate").disabled = false;
        $id("btn-cancel").disabled = true;
        // ux P2：完成时刻 —— 进度条脉冲高亮一次（先移除类重启动画）
        var fill = $id("progress-fill");
        fill.style.width = "100%";
        fill.classList.remove("done");
        void fill.offsetWidth;
        fill.classList.add("done");
        $id("progress-text").textContent = "生成完成，可预览 / 适配 / 编辑";
        Adapt.showBanner("生成完成。请预览确认内容与排版；如需调整可点击正文编辑，或使用「自动适配」。");
        setFlow(4);   // r23 P2/P3：生成完成 → 引导第 4 步预览 / 导出
        loadList();
        // 阶段3：生成完成滚动到预览区，用户无需手动下拉
        var pv = $id("preview");
        if (pv) pv.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });
    es.addEventListener("task.failed", function (ev) {
      var d = JSON.parse(ev.data);
      closeSSE();
      Adapt.showBanner("生成失败：" + (d.error || d.message || "未知错误"), true);
      setFlow(3);   // r23：失败回退到第 3 步
      resetGenerateBtns();
    });
    es.addEventListener("task.canceled", function () {
      closeSSE();
      Adapt.showBanner("任务已取消");
      setFlow(3);   // r23：取消回退到第 3 步
      resetGenerateBtns();
    });
    es.onerror = function () {
      // 终态后服务端会断开；若已有结果则忽略
      if (es && es.readyState === EventSource.CLOSED) closeSSE();
    };
  }

  function setProgress(p, text) {
    $id("progress-fill").style.width = Math.max(0, Math.min(100, Math.round(p * 100))) + "%";
    $id("progress-text").textContent = text;
  }

  function cancelTask() {
    if (!state.taskId) return;
    fetch("/api/task/" + state.taskId + "/cancel", { method: "POST" })
      .then(function (r) { return r.json(); }).catch(function () {});
  }

  function closeSSE() { if (es) { es.close(); es = null; } }
  function resetGenerateBtns() {
    $id("btn-generate").disabled = false;
    $id("btn-cancel").disabled = true;
  }

  /* ---------------- 初始化 ---------------- */
  // ux P1-2：首启一次性引导 —— 左栏第 1 步脉冲高亮 + 顶部提示条；localStorage 记录，仅一次
  function maybeOnboard() {
    try {
      if (localStorage.getItem("jl_onboarded")) return;
    } catch (e) { return; }
    var p1 = document.querySelector("#progress-steps .pstep");
    if (p1) p1.classList.add("pulse-once");
    var tip = document.createElement("div");
    tip.className = "onboard-tip";
    tip.innerHTML = "<span>欢迎使用简历生成助手 —— 第 1 步：先「配置模型」（选厂商 → 选模型 → 填 API Key）→ 点「保存并自检」。之后按左侧流程栏逐步推进即可。</span>" +
      '<button type="button" class="btn small" id="onboard-ok">我知道了</button>';
    var layout = document.querySelector("main.layout");
    if (layout && layout.parentNode) layout.parentNode.insertBefore(tip, layout);
    var okBtn = $id("onboard-ok");
    if (okBtn) okBtn.addEventListener("click", function () {
      try { localStorage.setItem("jl_onboarded", "1"); } catch (e) {}
      tip.remove();
      if (p1) p1.classList.remove("pulse-once");
    });
  }

  function init() {
    health();
    initVendors();   // r23：厂商下拉 + 联动
    loadSettings();
    loadList();
    showHelp("__default__");   // r25 P9：右栏提醒栏初始欢迎态
    maybeOnboard();   // ux P1-2：首启一次性引导（高亮第 1 步 + 提示条）
    $id("btn-new").addEventListener("click", newResume);
    $id("btn-save").addEventListener("click", saveResume);
    $id("btn-save-settings").addEventListener("click", saveSettings);
    $id("btn-add-provider").addEventListener("click", addProvider);
    $id("btn-test-provider").addEventListener("click", testQuickProvider);
    $id("btn-save-search").addEventListener("click", saveSearch);
    $id("btn-save-defaults").addEventListener("click", saveDefaults);
    $id("btn-settings").addEventListener("click", openSettings);
    $id("btn-close-settings").addEventListener("click", closeSettings);
    $id("settings-mask").addEventListener("click", closeSettings);
    $id("btn-generate").addEventListener("click", startGenerate);
    $id("btn-cancel").addEventListener("click", cancelTask);
    document.querySelectorAll("[data-add]").forEach(function (btn) {
      btn.addEventListener("click", function () { addRow(btn.getAttribute("data-add")); });
    });
    updateAddBtns();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
