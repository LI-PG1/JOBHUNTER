/* adapt.js：预览渲染 + 动态适配闭环（契约 §6）+ 编辑锁定 UI（§5.5）。
 * 挂载到 window.JL（共享状态对象），由 app.js 在 task.done 时调用 render() 并传入 resume。
 */
(function () {
  "use strict";

  var MM = 96 / 25.4;
  var PAGE_H = Math.round((297 - 24) * MM); // A4 内容高 ≈ 1032px（12mm 边距）
  var PAGE_W = Math.round((210 - 24) * MM); // A4 内容宽 ≈ 703px
  var MAX_ROUND = 3;
  var state = window.JL = window.JL || {};

  function $id(id) { return document.getElementById(id); }
  function iframeDoc() {
    var f = $id("preview");
    return f && f.contentDocument;
  }
  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      return j.data;
    });
  }
  function put(url, body) {
    return fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.code !== 0) throw new Error(errMsg(j));
      return j.data;
    });
  }
  function errMsg(j) {
    if (j && j.message) return j.message;
    if (j && Array.isArray(j.detail)) {
      return j.detail.map(function (d) { return d.msg || JSON.stringify(d); }).join("；");
    }
    if (j && j.detail) return String(j.detail);
    return "未知错误";
  }

  /* ---------------- 渲染与标记 ---------------- */

  function render(html) {
    var f = $id("preview");
    var empty = $id("preview-empty");
    if (!html) return;
    f.srcdoc = html;
    if (empty) empty.classList.add("hidden");
    var tip = $id("edit-tip");
    if (tip) { tip.classList.remove("hidden"); tip.classList.add("show"); }   // 阶段3：生成/适配/编辑后绿色高亮提示
    f.onload = function () {
      try {
        injectEditStyles();
        markEdited();
        bindClicks();
      } catch (e) { /* 忽略不可访问 */ }
    };
  }

  function injectEditStyles() {
    var doc = iframeDoc();
    if (!doc) return;
    var st = doc.getElementById("jl-edit-styles");
    if (st) return;
    st = doc.createElement("style");
    st.id = "jl-edit-styles";
    st.textContent =
      ".edited-item{border:1px dashed #fdba74 !important;border-radius:3px;padding:0 2px;}" +
      ".edit-badge{display:inline-block;font-size:8pt;color:#9a3412;background:#fff7ed;" +
      "border:1px solid #fdba74;border-radius:3px;padding:0 4px;margin-left:4px;" +
      "vertical-align:middle;line-height:1.4;white-space:nowrap;}" +
      "[data-block]{cursor:pointer;}";
    doc.head.appendChild(st);
  }

  /* 已编辑条目（§5.5）：对照 resume 数据给 iframe 内元素加「已锁定」标记 */
  function markEdited() {
    var doc = iframeDoc();
    var resume = state.resume || {};
    if (!doc) return;
    var edited = {};
    (resume.summary || []).forEach(function (s, i) { if (s.edited) edited["summary|" + i + "|"] = 1; });
    (resume.internship || []).forEach(function (it, i) {
      (it.duties || []).forEach(function (d, j) { if (d.edited) edited["internship|" + i + "|" + j] = 1; });
    });
    (resume.project || []).forEach(function (p, i) {
      (p.items || []).forEach(function (x, j) { if (x.edited) edited["project|" + i + "|" + j] = 1; });
    });
    var nodes = doc.querySelectorAll("[data-block]");
    for (var k = 0; k < nodes.length; k++) {
      var el = nodes[k];
      var key = el.getAttribute("data-block") + "|" + el.getAttribute("data-index") + "|" +
                (el.getAttribute("data-sub-index") || "");
      var isEd = !!edited[key];
      el.classList.toggle("edited-item", isEd);
      var badge = el.querySelector(":scope > .edit-badge");
      if (isEd && !badge) {
        badge = doc.createElement("span");
        badge.className = "edit-badge";
        badge.textContent = "已锁定";
        el.appendChild(badge);
      } else if (!isEd && badge) {
        badge.parentNode.removeChild(badge);
      }
    }
  }

  /* ---------------- 测量（§6：DOM 高度最接近打印效果） ---------------- */

  function measure() {
    var doc = iframeDoc();
    if (!doc || !doc.body) return null;
    var total = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight);
    var pages = Math.max(1, Math.ceil(total / PAGE_H - 1e-6));
    var fillRatio = Math.max(0, Math.min(2, (total - (pages - 1) * PAGE_H) / PAGE_H));
    var blocks = [];
    var config = state.config || {};
    var est = (config.blocks || {});
    var specs = [["summary", "#sec-summary"], ["internship", "#sec-internship"], ["projects", "#sec-projects"]];
    for (var i = 0; i < specs.length; i++) {
      var el = doc.querySelector(specs[i][1]);
      if (!el) continue;
      var cs = doc.defaultView.getComputedStyle(el);
      var lh = parseFloat(cs.lineHeight) || 18;
      var lines = Math.max(1, Math.round(el.getBoundingClientRect().height / lh));
      blocks.push({
        block: specs[i][0],
        actualLines: lines,
        estimatedLines: est[specs[i][0]] != null ? est[specs[i][0]] : null,
        detailLevel: "标准",
        pageWidth: PAGE_W,
      });
    }
    return { fillRatio: fillRatio, blocks: blocks };
  }

  function applyDensity(density) {
    var doc = iframeDoc();
    if (doc && doc.body) doc.body.setAttribute("data-density", density);
    var sel = $id("p-density");
    if (sel) sel.value = density;
  }

  /* 密度同步到服务端（重装配，§6），随后重建预览并重打锁定标记 */
  function syncDensity(density) {
    if (!state.resumeId) return Promise.resolve();
    return put("/api/resume/" + state.resumeId + "/render", { density: density })
      .then(function (data) {
        state.html = data.html;
        state.config = data.config;
        state.resume = data.resume;
        render(state.html);
      });
  }

  /* ---------------- 自动适配闭环（≤3 轮，§6） ---------------- */

  function run() {
    var btn = $id("btn-adapt");
    var info = $id("adapt-info");
    btn.disabled = true;
    var round = 1;
    var lastAction = "", lastDensity = "";
    var step = function () {
      if (round > MAX_ROUND) {
        info.textContent = "已达 3 轮上限，优先保证不溢出；可改选页数";
        syncDensity(state.density || "normal").catch(function () {}).then(done);
        return;
      }
      var m = measure();
      if (!m) { info.textContent = "预览未就绪"; done(); return; }
      info.textContent = "第 " + round + " 轮 · 填充 " + Math.round(m.fillRatio * 100) + "%";
      post("/api/adjust", {
        taskId: state.taskId,
        measurement: m,
        config: state.config || { density: state.density || "normal" },
        round: round,
      }).then(function (data) {
        var action = data.action;
        var newDensity = (data.config || {}).density || "normal";
        state.config = data.config;
        state.density = newDensity;
        if (action === "ok") {
          info.textContent = "已收敛 · 填充 " + Math.round(m.fillRatio * 100) + "% · 密度 " + newDensity;
          syncDensity(newDensity).catch(function () {}).then(done);
          return;
        }
        if (newDensity === lastDensity && action === lastAction) {
          info.textContent = "已到最" + (action === "over" ? "紧凑" : "松散") + "档仍不理想，可改选页数";
          syncDensity(newDensity).catch(function () {}).then(done);
          return;
        }
        applyDensity(newDensity);
        lastAction = action;
        lastDensity = newDensity;
        round++;
        setTimeout(step, 150); // 等待重排后重测
      }).catch(function (e) {
        info.textContent = "适配失败：" + e.message;
        done();
      });
    };
    var done = function () { btn.disabled = false; };
    step();
  }

  /* ---------------- 编辑锁定 UI（§5.5） ---------------- */

  function bindClicks() {
    var doc = iframeDoc();
    if (!doc) return;
    doc.removeEventListener("click", onLeafClick);
    doc.addEventListener("click", onLeafClick);
  }

  function onLeafClick(ev) {
    var el = ev.target.closest ? ev.target.closest("[data-block]") : null;
    if (!el) return;
    var block = el.getAttribute("data-block");
    var index = parseInt(el.getAttribute("data-index"), 10) || 0;
    var sub = el.getAttribute("data-sub-index");
    var subIndex = sub != null ? parseInt(sub, 10) : null;
    ev.preventDefault();
    ev.stopPropagation();
    openEditModal(block, index, subIndex);
  }

  function leafOf(block, index, subIndex) {
    var resume = state.resume || {};
    if (block === "summary") return { leaf: (resume.summary || [])[index] || {} };
    if (block === "internship") {
      var it = (resume.internship || [])[index] || {};
      return { leaf: (it.duties || [])[(subIndex == null ? 0 : subIndex)] || {} };
    }
    if (block === "project") {
      var p = (resume.project || [])[index] || {};
      return { leaf: (p.items || [])[(subIndex == null ? 0 : subIndex)] || {} };
    }
    return { leaf: {} };
  }

  var editing = null;

  function openEditModal(block, index, subIndex) {
    var leaf = leafOf(block, index, subIndex).leaf;
    var title = block === "summary" ? "编辑自我评价" : (block === "internship" ? "编辑实习职责" : "编辑项目要点");
    editing = { block: block, index: index, subIndex: subIndex, leaf: leaf };
    $id("edit-title").textContent = title + (leaf.edited ? "（已锁定）" : "");
    $id("edit-text").value = leaf.text || "";
    $id("edit-unlock").hidden = !leaf.edited;
    $id("edit-modal").classList.remove("hidden");
    $id("edit-text").focus();
  }

  function closeModal() {
    $id("edit-modal").classList.add("hidden");
    editing = null;
  }

  function afterSave(data) {
    state.resume = data.resume;
    state.html = data.html;
    state.config = data.config;
    state.density = (data.config || {}).density || state.density || "normal";
    render(state.html);
  }

  function saveEdit() {
    if (!editing) return;
    var text = $id("edit-text").value.trim();
    if (!text) { showBanner("文本不能为空", true); return; }
    var body = { block: editing.block, index: editing.index, text: text };
    if (editing.subIndex != null) body.subIndex = editing.subIndex;
    put("/api/resume/" + state.resumeId + "/item", body).then(function (data) {
      afterSave(data);
      closeModal();
      showBanner("已编辑并锁定该条目：AI 生成将不再覆盖此条内容。");
    }).catch(function (e) {
      showBanner("保存失败：" + e.message, true);
    });
  }

  function unlockEdit() {
    if (!editing) return;
    var body = { block: editing.block, index: editing.index };
    if (editing.subIndex != null) body.subIndex = editing.subIndex;
    post("/api/resume/" + state.resumeId + "/item/unlock", body).then(function (data) {
      afterSave(data);
      closeModal();
      showBanner("已解锁该条目：下次自动生成时可被 AI 重写。");
    }).catch(function (e) {
      showBanner("解锁失败：" + e.message, true);
    });
  }

  function showBanner(msg, isError) {
    var b = $id("banner");
    b.textContent = msg;
    b.classList.remove("hidden");
    b.style.background = isError ? "#fef2f2" : "";
    b.style.borderColor = isError ? "#fca5a5" : "";
    b.style.color = isError ? "#b91c1c" : "";
  }

  /* ---------------- 导出（§7 E8 / FR-6）：AI 项确认清单 + 水印必选 + 下载） ---------------- */
  function collectAiItems() {
    var r = state.resume || {};
    var items = [];
    (r.project || []).forEach(function (p, i) {
      if (p.source && p.source !== "user-input") {
        items.push("项目「" + (p.name || "未命名") + "」为 AI " + (p.source === "polished" ? "美化" : "生成") + "内容");
      }
    });
    (r.summary || []).forEach(function (s, i) {
      if (!s.edited) items.push("自我评价第 " + (i + 1) + " 句由 AI 撰写");
    });
    return items;
  }

  function exportWatermarkLabel() {
    var wm = $id("g-watermark") ? $id("g-watermark").value : (state.config && state.config.watermarkMode) || "formal";
    return wm === "practice" ? "练习（有水印）：底部叠加「部分内容由 AI 生成」提示" : "无（正式无水印）：版面干净，适合最终投递";
  }

  function openExportModal(items) {
    var list = $id("export-ai-list");
    list.innerHTML = "";
    items.forEach(function (t) {
      var li = document.createElement("li");
      li.textContent = t;
      list.appendChild(li);
    });
    $id("export-wm-line").textContent = "本次导出水印模式：" + exportWatermarkLabel();
    $id("export-agree").checked = false;
    $id("export-modal").classList.remove("hidden");
  }

  function closeExportModal() {
    $id("export-modal").classList.add("hidden");
  }

  function doExport(fmt) {
    if (fmt === "pdf") {
      if (!state.html) return;
      var w = window.open("", "_blank");
      w.document.write(state.html);
      w.document.close();
      w.focus();
      setTimeout(function () { w.print(); }, 300);
      return;
    }
    if (!state.resumeId) return;
    var a = document.createElement("a");
    a.href = "/api/resume/" + state.resumeId + "/export?format=" + fmt;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function exportResume() {
    if (!state.html && !state.resumeId) return;
    var fmt = $id("p-export-fmt").value || "pdf";
    var items = collectAiItems();
    if (!items.length) { doExport(fmt); return; }
    state.exportFmt = fmt;
    openExportModal(items);
  }

  /* ---------------- 初始化 ---------------- */
  function init() {
    $id("btn-adapt").addEventListener("click", run);
    $id("btn-export").addEventListener("click", exportResume);
    $id("edit-save").addEventListener("click", saveEdit);
    $id("edit-unlock").addEventListener("click", unlockEdit);
    $id("edit-cancel").addEventListener("click", closeModal);
    $id("edit-close").addEventListener("click", closeModal);
    $id("export-do").addEventListener("click", function () {
      if (!$id("export-agree").checked) {
        showBanner("请先勾选确认框再导出", true);
        return;
      }
      closeExportModal();
      doExport(state.exportFmt || "pdf");
    });
    $id("export-cancel").addEventListener("click", closeExportModal);
    $id("export-close").addEventListener("click", closeExportModal);
    // 阶段4：Esc 关闭编辑弹窗（键盘可达性）
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (!$id("edit-modal").classList.contains("hidden")) closeModal();
      else if (!$id("export-modal").classList.contains("hidden")) closeExportModal();
    });
  }

  window.Adapt = {
    init: init,
    render: render,
    run: run,
    measure: measure,
    markEdited: markEdited,
    showBanner: showBanner,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
