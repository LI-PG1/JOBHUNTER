/**
 * 面试跟踪助手 - 前端逻辑 v2（零依赖原生 JS）
 *
 * v2 变更（借鉴 BM25 饱和思想 + 成熟求职跟踪项目 pipeline 排序）：
 *  1. 横版卡片列表（每行一条投递，上下翻动，替代横向滚动宽表）
 *  2. 置顶简化为行首星标，仅针对单个投递（移除公司级置顶入口）
 *  3. 有面试时间的投递自动置顶，按面试时间升序（最近的在前）
 *  4. 排序分层：面试置顶 → 手动置顶 → 优先级分（流程深度饱和 + 更新时间指数衰减）→ 终态
 */
'use strict';

/* ============ 全局状态 ============ */
const state = {
  companies: [],
  jobs: [],
  filter: { tab: 'all', kw: '', status: '', city: '', workType: '' },
  editingJobId: null,
  aiDraft: null,        // 智能识别草稿（确认后走新增保存）
  modalMode: 'form',    // form=新增/更新/识别确认（底部「保存并重排」）；parse=识别输入；config=API 设置
  aiOnline: false,      // 在线模式（已配置且校验通过的 API Key）→ 智能识别可用；离线则置灰
  aiForceCat: false,    // 识别确认模式：工作类型必选（识别信息通常不含工作类型）
};

/* 工作类型四选项（并列）：秋招 / 有转正实习 / 日常实习 / 未知 */
const WORK_TYPE_LABEL = { autumn: '秋招', convert: '有转正实习', nonconvert: '日常实习', unknown: '未知' };
const WORK_TYPE_ORDER = ['autumn', 'convert', 'nonconvert', 'unknown'];
const RESULT_LABEL = { offer: 'Offer', fail: '挂', giveup: '放弃' };

/* ============ 流程环节模型 v3（动态面试轮） ============
 * 固定骨架：简历筛选 / 笔试 / HR面（可选，state=skip 表示无此环节）
 * 面试轮次：interviews 动态数组，轮数由实际面试决定（1 面 / 2 面 / 3 面…）
 * 每轮元素：{ date: 'YYYY-MM-DD', state: null|pass|wait|todo|fail|skip }（wait=等结果、todo=待进行）
 */
const CN_NUM = ['一','二','三','四','五','六','七','八','九','十'];
const STAGE_LABELS = { resume: '简历筛选', written: '笔试', hr: 'HR面' };

/* 展开一条投递的有序环节序列（渲染 / 排序 / 提醒共用同一份） */
function stageList(job) {
  const s = job.stages || {};
  const list = [];
  for (const k of ['resume', 'written']) {
    if (s[k]) list.push({ key: k, label: STAGE_LABELS[k], v: s[k] });
  }
  (s.interviews || []).forEach((v, i) => {
    list.push({ key: 'iv' + i, label: (CN_NUM[i] || String(i + 1)) + '面', v: v || { date: '', state: null } });
  });
  if (s.hr) list.push({ key: 'hr', label: STAGE_LABELS.hr, v: s.hr });
  return list;
}

/* 流程深度评分（饱和：越深加分越缓，借鉴 BM25 词频饱和思想；面试第 n 轮 = 0.5+(n-1)*0.15） */
const DEPTH_SCORE = { resume: 0.2, written: 0.35, hr: 1.0 };
function pipelineDepth(job) {
  const s = job.stages || {};
  let depth = 0;
  for (const [k, w] of Object.entries(DEPTH_SCORE)) {
    const v = s[k];
    if (v && v.state === 'pass') depth = Math.max(depth, w);
  }
  (s.interviews || []).forEach((v, i) => {
    if (v && v.state === 'pass') depth = Math.max(depth, Math.min(0.5 + i * 0.15, 0.95));
  });
  return depth;
}

/* ============ 工具 ============ */
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function nowIso() { return new Date().toISOString(); }
function newId() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }
function localToday() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function formatDate(v) { return v ? String(v).slice(0, 10) : ''; }
function formatTime(v) { return v ? String(v).slice(11, 16) : ''; }
/* 纯日期（YYYY-MM-DD）按本地当天 00:00 解析，避免 new Date('YYYY-MM-DD') 按 UTC 解析产生 +8h 偏移 */
function localMidnight(ds) { const t = new Date(String(ds).slice(0, 10) + 'T00:00:00').getTime(); return isNaN(t) ? 0 : t; }
/* 统一格式化时间戳/日期串为本地 'YYYY-MM-DD HH:mm'（用于笔试 DDL 等需精确时刻的场景） */
function fmtDateTime(ts) {
  const d = new Date(ts);
  if (isNaN(d.getTime())) return '';
  const p = (n) => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}
/* 面试时间统一为本地 'YYYY-MM-DD HH:mm'：兼容无时区本地串（保存格式）与历史遗留的 UTC（Z/±hh:mm）串（旧版 toISOString 产物） */
function localIvStr(ts) {
  if (!ts) return '';
  const s = String(ts);
  if (/Z$|[+-]\d{2}:?\d{2}$/.test(s)) {
    const d = new Date(s);
    if (!isNaN(d.getTime())) {
      const p = (n) => String(n).padStart(2, '0');
      return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
    }
  }
  return s.slice(0, 16).replace('T', ' ');
}

function companyOf(job) { return state.companies.find((c) => c.id === job.companyId); }

/* 一个岗位的城市列表（支持多城市，如「北京/上海」→ ['北京','上海']） */
function jobCities(job) {
  return String(job.city || '').split(/[\/、,，;；|]/).map((s) => s.trim()).filter(Boolean);
}

/* ============ API ============ */
async function loadData() {
  const res = await fetch('/api/data');
  if (!res.ok) throw new Error('数据加载失败');
  const data = await res.json();
  state.companies = data.companies || [];
  state.jobs = data.jobs || [];
}

async function saveData() {
  const pill = $('#saveStatus');
  pill.textContent = '保存中…';
  pill.className = 'status-pill saving';
  try {
    const res = await fetch('/api/data', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ companies: state.companies, jobs: state.jobs }),
    });
    if (!res.ok) throw new Error((await res.json()).error || '保存失败');
    pill.textContent = '已保存';
    pill.className = 'status-pill';
  } catch (e) {
    pill.textContent = '保存失败：' + e.message;
    pill.className = 'status-pill error';
    throw e;
  }
}

/* 进度分组（按招聘流程阶段划分）
 * 已投待进展(0)：纯投递且无面试安排（无环节动作、无面试时间）
 * 进行中(1)：已通过简历筛选（resume pass），或已在笔试/面试/HR 等实质环节，或已明确面试时间（interviewAt 非空 = 已进入面试环节，即便环节状态未维护）
 * 已挂/放弃(2)：任一环节 fail 或主动放弃
 * Offer(3)：终态通过
 */
function jobGroup(job) {
  if (job.result === 'offer') return 3;
  if (job.result === 'fail' || job.result === 'giveup') return 2;
  const steps = stageList(job);
  const act = steps.filter((x) => x.v && x.v.state && x.v.state !== 'skip');
  if (act.length === 0 && !job.interviewAt) return 0;   // 纯投递且无面试安排 → 已投待进展
  if (act.some((x) => x.v.state === 'fail')) return 2;  // 任一环节挂 → 已挂
  const first = act[0];
  // 最早动作只是「简历筛选 待筛」且无面试安排 → 仍属已投待进展；有面试时间即视为已进入面试环节（进行中）
  if (first && first.key === 'resume' && first.v.state === 'wait' && act.length === 1 && !job.interviewAt) return 0;
  return 1;                                             // 其余（含已有面试时间）→ 进行中
}

/* 是否「流程环节连续走到底」：至少一个环节通过、无 wait/todo/fail，且最后一个 pass 之后无未到环节（skip 视为无此环节） */
function allStagesPassed(job) {
  const steps = stageList(job);
  const hasPass = steps.some((x) => x.v.state === 'pass');
  if (!hasPass) return false;
  if (steps.some((x) => x.v.state === 'wait' || x.v.state === 'todo' || x.v.state === 'fail')) return false;
  const lastPassIdx = steps.map((x) => x.v.state).lastIndexOf('pass');
  for (let i = lastPassIdx + 1; i < steps.length; i++) {
    const st = steps[i].v.state;
    if (st !== 'pass' && st !== 'skip') return false; // 后面还有「未到」环节 → 流程未走完
  }
  return true;
}
const GROUP_LABEL = { 0: '已投待进展', 1: '进行中', 2: '已挂 / 放弃', 3: 'Offer' };

/* 面试是否已结束：最后一轮面试已出结果（pass/fail/wait 等结果）→ 其预约时间不再置顶/提醒；约了新面试（更新 interviewAt + 加 todo 待进行轮）后自动恢复 */
function interviewSettled(job) {
  const ivs = (job.stages || {}).interviews || [];
  const last = ivs[ivs.length - 1];
  return !!last && (last.state === 'pass' || last.state === 'fail' || last.state === 'wait');
}

/* 有未来的面试时间（面试自动置顶的前提） */
function hasFutureInterview(job) {
  if (!job.interviewAt) return false;
  if (interviewSettled(job)) return false; // 面试已出结果：预定任务完成，不再置顶
  const t = new Date(job.interviewAt).getTime();
  return !isNaN(t) && t > Date.now();
}

/* 笔试 DDL（截止时间，datetime 毫秒；0 表示无）。时间提示只和「待进行/Offer 过期」绑定：等结果（wait）或已结束（pass/fail）→ 取消截止提醒 */
function writtenDeadlineTs(job) {
  const w = (job.stages || {}).written;
  if (!w || !w.deadline) return 0;
  if (w.state === 'pass' || w.state === 'fail' || w.state === 'wait') return 0;
  const t = new Date(w.deadline).getTime();
  return !isNaN(t) ? t : 0;
}

/* 笔试 DDL 紧迫：48h 内截止（借鉴腾讯「48h 内做测评」场景） */
function urgentWrittenDeadline(job) {
  const t = writtenDeadlineTs(job);
  if (!t) return false;
  const diff = t - Date.now();
  return diff > 0 && diff <= 48 * 3600 * 1000;
}

function urgentIn24h(job) {
  if (!job.interviewAt) return false;
  if (interviewSettled(job)) return false; // 面试已出结果：不再按预约时间提醒紧迫
  const t = new Date(job.interviewAt).getTime();
  if (!t || isNaN(t)) return false;
  const diff = t - Date.now();
  return diff > 0 && diff <= 24 * 3600 * 1000;
}

/* ============ 优先级评分（v2，借鉴 BM25 特征饱和 + 时间衰减） ============ */
function pipelineDepth(job) {
  const s = job.stages || {};
  let depth = 0;
  for (const [k, base] of Object.entries(DEPTH_SCORE)) {
    const v = s[k];
    if (v && v.state === 'pass') depth = Math.max(depth, base);
  }
  return depth;
}

function priorityScore(job) {
  const depth = pipelineDepth(job); // 0~1，饱和
  const hasWait = stageList(job).some((x) => x.v.state === 'wait' || x.v.state === 'todo'); // 等结果 / 待进行：有下一动作
  let recency = 0;
  if (job.updatedAt) {
    const hours = (Date.now() - new Date(job.updatedAt).getTime()) / 3600000;
    recency = Math.exp(-hours / (24 * 7)); // 指数衰减：约 7 天半衰期
  }
  // 第一性原理：求职者关注「有下一动作/待跟进」的投递；等待中的优先于纯投递；有转正实习优先（机会价值更高）
  return depth * 0.6 + recency * 0.4 + (hasWait ? 0.15 : 0) + (job.workType === 'convert' ? 0.1 : 0);
}

/* Offer 待确认：所有已标记 Offer 均处于待确认（无终态 Offer；截止日期仅作展示与组内排序参考） */
function offerPending(job) {
  return job.result === 'offer';
}

/* ============ 排序（v4 分层：面试 → 笔试DDL紧迫 → Offer 待确认 → 手动置顶 → 常规 → 终态挂/放弃） ============ */
function sortGroup(job) {
  if (offerPending(job)) return 1.5;        // Offer 待确认（未立即确认多有顾虑，置顶提示栏单独分区最高优先，列表放进行中之后）
  if (job.result === 'fail' || job.result === 'giveup') return 4; // 终态挂/放弃：不再参与面试/DDL 置顶
  if (hasFutureInterview(job)) return 0;   // 面试自动置顶（按面试时间升序）
  if (urgentWrittenDeadline(job)) return 1; // 笔试 48h 内截止（按截止时间升序）
  if (job.pinnedAt) return 2;              // 手动置顶（按置顶先后）
  return 3;                                // 常规（按优先级分）
}

function sortJobs(jobs) {
  return [...jobs].sort((a, b) => {
    const ga = sortGroup(a), gb = sortGroup(b);
    if (ga !== gb) return ga - gb;
    if (ga === 0) return new Date(a.interviewAt).getTime() - new Date(b.interviewAt).getTime();
    if (ga === 1) return writtenDeadlineTs(a) - writtenDeadlineTs(b);
    if (ga === 1.5) return localMidnight(a.offerDeadline) - localMidnight(b.offerDeadline);
    if (ga === 2) return String(a.pinnedAt).localeCompare(String(b.pinnedAt));
    if (ga === 3) return priorityScore(b) - priorityScore(a);
    return String(b.updatedAt || '').localeCompare(String(a.updatedAt || ''));
  });
}

/* ============ 过滤 ============ */
function filteredJobs() {
  const f = state.filter;
  return state.jobs.filter((job) => {
    if (f.tab === 'offer') {
      if (job.result !== 'offer') return false; // Offer 为结果维度分类
    } else if (f.tab === 'autumn') {
      if (job.workType !== 'autumn') return false; // 秋招 Tab：工作类型=秋招
    } else if (f.tab === 'intern') {
      if (job.workType === 'autumn') return false; // 实习 Tab：非秋招（含未知，可在更新中改为秋招）
    }
    if (f.status !== '' && String(jobGroup(job)) !== f.status) return false;
    if (f.city && !jobCities(job).includes(f.city)) return false;
    if (f.workType && job.workType !== f.workType) return false; // 工作类型筛选（秋招/有转正实习/日常实习/未知）
    if (f.kw) {
      const c = companyOf(job);
      const hay = (job.title || '') + ' ' + (c ? c.name : '');
      if (!hay.toLowerCase().includes(f.kw.toLowerCase())) return false;
    }
    return true;
  });
}

/* ============ 流程环节渲染（chip 流） ============ */
function flowStepHtml(label, v) {
  if (!v || !v.state) return '<span class="f-step"><span class="f-dot"></span>' + label + '</span>';
  const d = formatDate(v.date);
  if (v.state === 'pass') return '<span class="f-step"><span class="f-dot pass"></span>' + label + ' <span class="f-date">' + esc(d) + '</span></span>';
  if (v.state === 'fail') return '<span class="f-step"><span class="f-dot fail"></span>' + label + ' <span class="f-date">' + esc(d) + ' 挂</span></span>';
  if (v.state === 'skip') return '<span class="f-step"><span class="f-dot"></span>' + label + ' <span>跳过</span></span>';
  if (v.state === 'wait') {
    return '<span class="f-step"><span class="f-dot wait"></span>' + label + ' <span class="f-date wait">' + esc(d) + ' 等结果</span></span>';
  }
  if (v.state === 'todo') {
    return '<span class="f-step"><span class="f-dot todo"></span>' + label + ' <span class="f-date todo">' + esc(d) + ' 待</span></span>';
  }
  return '';
}

function resultHtml(job) {
  if (job.result === 'offer') return '<span class="res-offer">Offer</span>';
  if (job.result === 'fail' || job.result === 'giveup') return '<span class="tag" style="background:#f1f3f6;color:#98a2b3;">' + RESULT_LABEL[job.result] + '</span>';
  return '';
}

/* ============ 渲染：卡片列表（横版） ============ */
function starState(job) {
  if (job.result === 'fail' || job.result === 'giveup') return 'off'; // 终态挂/放弃：不显示任何置顶星态
  if (hasFutureInterview(job)) return 'auto'; // 面试自动置顶
  if (job.pinnedAt) return 'on';              // 手动置顶
  return 'off';
}

/* 岗位名是否缺省（空或占位文本）——缺省时卡片标题处显示「补全岗位名」入口，点击直接进入编辑弹窗修改 */
function isPlaceholderTitle(job) {
  const t = String(job.title || '').trim();
  return !t || t === '（岗位名称待补充）' || t === '待补充';
}

/* 单张卡片模板（横版：星标 → 公司/岗位/标签 → 流程条 → meta → 操作） */
function cardHtml(job) {
  const c = companyOf(job) || { name: '?' };
  const offerDeadlineTs = job.offerDeadline ? localMidnight(job.offerDeadline) : 0;
  const offerUrgent = offerDeadlineTs && offerDeadlineTs - Date.now() > 0 && offerDeadlineTs - Date.now() <= 7 * 24 * 3600 * 1000;
  const dead = job.result === 'fail' || job.result === 'giveup';
  const urgent = !dead && (urgentIn24h(job) || urgentWrittenDeadline(job) || (job.result === 'offer' && offerUrgent));
  const star = starState(job);
  const flow = stageList(job).map((x) => flowStepHtml(x.label, x.v)).join('');
  const meta = [];
  if (job.appliedDate) meta.push('<span class="m-item">投递 ' + esc(formatDate(job.appliedDate)) + '</span>');
  if (job.city) meta.push('<span class="m-item">📍 ' + esc(job.city) + '</span>');
  if (job.interviewAt && !dead && job.result !== 'offer' && !interviewSettled(job)) {
    const iv = localIvStr(job.interviewAt);
    meta.push('<span class="m-item ' + (urgentIn24h(job) ? 'urgent' : '') + '">🎯 面试 ' + esc(iv) + (urgentIn24h(job) ? '（24h 内）' : '') + '</span>');
  }
  const wdl = writtenDeadlineTs(job);
  if (wdl && !dead) {
    const wd = fmtDateTime(wdl);
    const uw = urgentWrittenDeadline(job);
    meta.push('<span class="m-item' + (uw ? ' urgent' : '') + '">⏰ 笔试截止 ' + esc(wd) + (uw ? '（48h 内）' : '') + '</span>');
  }
  if (job.result === 'offer') {
    if (job.offerDeadline) {
      const od = job.offerDeadline.slice(5);
      const odUrgent = offerDeadlineTs && offerDeadlineTs - Date.now() > 0 && offerDeadlineTs - Date.now() <= 3 * 24 * 3600 * 1000;
      meta.push('<span class="m-item' + (odUrgent ? ' urgent' : '') + '">🎗 Offer 截止 ' + esc(od) + (odUrgent ? '（3 天内）' : '') + '</span>');
    } else {
      meta.push('<span class="m-item">🎗 有效期待确认</span>');
    }
  }
  if (job.todo && (job.todo.text || job.todo.due) && !dead) {
    const tdue = job.todo.due ? localMidnight(job.todo.due) : 0;
    const urgt = tdue && tdue > Date.now() && tdue - Date.now() <= 48 * 3600 * 1000;
    meta.push('<span class="m-item' + (urgt ? ' urgent' : '') + '" title="' + esc(job.todo.text || '') + '">⏳ 待办' +
      (job.todo.due ? ' 截止 ' + esc(job.todo.due.slice(5)) : '') +
      (job.todo.text ? '：' + esc(job.todo.text) : '') + (urgt ? '（48h 内）' : '') + '</span>');
  }
  if (job.note) meta.push('<span class="m-item m-note" data-act="toggle-note" title="点击展开 / 收起完整备注">📝 <span class="note-text">' + esc(job.note) + '</span><span class="note-toggle"></span></span>');

  return (
    '<div class="job-card' + (urgent ? ' urgent' : '') + (job.result === 'offer' ? ' job-offer' : '') + '" id="card-' + job.id + '">' +
    '<button class="star ' + star + '" data-act="pin" data-id="' + job.id + '" title="' +
      (star === 'auto' ? '面试自动置顶（修改面试时间可调整排序）' : (star === 'on' ? '取消置顶' : '置顶此投递')) + '">' +
      (star === 'off' ? '☆' : '★') + '</button>' +
    '<div class="card-main">' +
      '<div class="card-top">' +
        '<span class="company">' + esc(c.name) + '</span>' +
        (isPlaceholderTitle(job)
          ? '<button class="job-title-fill" data-act="edit" data-id="' + job.id + '" title="岗位名未填，点击补全">＋ 补全岗位名</button>'
          : '<span class="job-title">' + esc(job.title) + '</span>') +
        '<span class="tag ' + esc(job.workType || 'unknown') + '">' + (WORK_TYPE_LABEL[job.workType] || '未知') + '</span>' +
        resultHtml(job) +
      '</div>' +
      '<div class="flow">' + flow + '</div>' +
      '<div class="meta">' + meta.join('') + '</div>' +
    '</div>' +
    '<div class="card-actions">' +
      '<button class="btn primary" data-act="edit" data-id="' + job.id + '">更新</button>' +
    '</div>' +
    '</div>'
  );
}

/* 分组渲染（第一性原理：求职者先看「进行中」，终态沉底；组内仍按紧迫性排序） */
function renderList() {
  const list = $('#jobList');
  const jobs = sortJobs(filteredJobs());
  if (jobs.length === 0) {
    list.innerHTML = '';
    const itHint = state.filter.workType
      ? '暂无「' + (WORK_TYPE_LABEL[state.filter.workType] || state.filter.workType) + '」的岗位。可在「更新」弹窗中选择工作类型后保存，或用智能识别录入。'
      : '暂无符合条件的投递记录';
    $('#emptyRow').textContent = itHint;
    $('#emptyRow').style.display = 'block';
    return;
  }
  $('#emptyRow').style.display = 'none';

  // 分组顺序（Offer 待确认不放最前：用户未立即确认通常有顾虑/想法，仍需跟进但非最紧迫）
  const groups = [
    { g: '1', label: '进行中', icon: '⚡' },
    { g: '1.5', label: 'Offer 待确认', icon: '🎗', test: offerPending },
    { g: '0', label: '已投待进展', icon: '📥' },
    { g: '2', label: '已挂 / 放弃', icon: '✖' }, // 所有 Offer 均归入「Offer 待确认」，无终态 Offer 分组
  ];
  let html = '';
  for (const gr of groups) {
    const list2 = jobs.filter((j) => (gr.test ? gr.test(j) : String(jobGroup(j)) === gr.g));
    if (list2.length === 0) continue;
    html += '<div class="group-head"><span class="gi">' + gr.icon + '</span>' + gr.label +
      '<span class="cnt">' + list2.length + '</span></div>' +
      list2.map(cardHtml).join('');
  }
  list.innerHTML = html;
}

/* 是否出现在置顶栏（Offer 待确认 / 未来面试自动置顶 / 手动置顶）——置顶与待办互斥去重：置顶已展示的岗位，待办不再重复出现 */
function inPinnedBar(job) {
  if (job.result === 'fail' || job.result === 'giveup') return false; // 终态不参与置顶
  if (offerPending(job)) return true;                                 // Offer 待确认分区
  const ia = job.interviewAt ? new Date(job.interviewAt).getTime() : null;
  if (ia && !isNaN(ia) && ia > Date.now()) return true;               // 面试自动置顶
  return !!job.pinnedAt;                                              // 手动置顶
}

/* ============ 渲染：置顶栏（Offer 待确认分区最高优先 + 面试/手动置顶分区） ============ */
function renderPinnedBar() {
  const box = $('#pinnedItems');
  const offerItems = [];
  const items = [];
  for (const job of state.jobs) {
    const cname = (companyOf(job) || {}).name;
    // 终态（挂/放弃）不参与置顶：没有后续待跟进动作
    if (job.result === 'fail' || job.result === 'giveup') continue;
    if (offerPending(job)) {
      offerItems.push({ id: job.id, name: cname + '｜' + job.title, time: 'Offer 截止 ' + (job.offerDeadline || '').slice(5) });
      continue;
    }
    const ia = job.interviewAt ? new Date(job.interviewAt).getTime() : null;
    if (ia && !isNaN(ia) && ia > Date.now()) {
      items.push({ t: ia, key: 'interview:' + job.id, kind: '面试', name: cname + '｜' + job.title, time: '面试 ' + localIvStr(job.interviewAt), remove: null, id: job.id });
    } else if (job.pinnedAt) {
      items.push({ t: new Date(job.pinnedAt).getTime(), key: 'pinned:' + job.id, kind: '置顶', name: cname + '｜' + job.title, time: '', remove: 'unpin-job', id: job.id });
    }
  }
  // 分组排序：面试置顶组（kind='面试'）优先，手动置顶组（kind='置顶'）次之；组内按时间升序
  items.sort((a, b) => (a.kind === b.kind ? a.t - b.t : (a.kind === '面试' ? -1 : 1)));

  if (offerItems.length === 0 && items.length === 0) {
    box.innerHTML = '<span class="pinned-empty">暂无置顶 · 有面试的投递会自动置顶，也可点击行首星标手动置顶</span>';
    return;
  }
  const chip = (it, offer) =>
    '<span class="pin-chip' + (offer ? ' offer' : '') + '" data-id="' + it.id + '" title="点击跳转到该投递">' +
    (offer ? '<span class="k">🎗</span>' : '<span class="k">' + it.kind + '</span>') +
    '<b>' + esc(it.name) + '</b>' +
    (it.time ? '<span class="tag" style="background:var(--blue-bg);color:var(--blue);">' + esc(it.time) + '</span>' : '') +
    (it.remove ? '<button class="unpin" data-act="' + it.remove + '" data-id="' + it.id + '" title="取消置顶">✕</button>' : '') +
    '</span>';

  let html = '';
  if (offerItems.length) {
    html += '<div class="pin-sec"><span class="pin-sec-title">🎗 Offer 待确认</span>' +
      offerItems.map((it) => chip(it, true)).join('') + '</div>';
  }
  if (items.length) {
    html += '<div class="pin-sec"><span class="pin-sec-title">📌 置顶</span>' + items.map((it) => chip(it, false)).join('') + '</div>';
  }
  box.innerHTML = html;
}

/* ============ 渲染：节点提醒（时间升序 + 同投递同天去重 + 未来 7 天） ============ */
function renderReminders() {
  const bar = $('#reminderBar');
  const items = [];
  const now = Date.now();
  const day7 = now + 7 * 24 * 3600 * 1000;
  const day14 = now + 14 * 24 * 3600 * 1000; // Offer 有效期窗口（错过即失效，需更长提醒期）
  const todayStart = localMidnight(localToday());

  for (const job of state.jobs) {
    const cname = (companyOf(job) || {}).name;
    // 终态（挂/放弃）不再提醒：没有后续待跟进动作
    if (job.result === 'fail' || job.result === 'giveup') continue;
    // 置顶栏已展示的岗位：待办不再重复出现（同一岗位的提醒只出现在一个入口）
    if (inPinnedBar(job)) continue;
    // 面试时间（有具体时刻，信息量最高；面试已出结果则不再提醒）
    if (job.interviewAt && !interviewSettled(job)) {
      const t = new Date(job.interviewAt).getTime();
      if (!isNaN(t) && t >= now && t <= day7) {
        items.push({ key: job.id + '|' + fmtDateTime(t).slice(0, 10), pri: 3, ts: t, ddl: false, id: job.id, text: fmtDateTime(t).slice(5) + ' 面试｜' + cname + ' ' + job.title });
      }
    }
    // Offer 有效期（最重要：不按期确认 Offer 会失效，窗口 14 天）
    if (job.offerDeadline) {
      const t = localMidnight(job.offerDeadline);
      if (t && t >= now && t <= day14) {
        items.push({ key: job.id + '|' + job.offerDeadline, pri: 4, ts: t, ddl: true, id: job.id, text: job.offerDeadline.slice(5) + ' Offer 截止｜' + cname + ' ' + job.title });
      }
    }
    // 笔试截止（有具体时刻）
    const wdl = writtenDeadlineTs(job);
    if (wdl && wdl >= now && wdl <= day7) {
      items.push({ key: job.id + '|' + fmtDateTime(wdl).slice(0, 10), pri: 2, ts: wdl, ddl: true, id: job.id, text: fmtDateTime(wdl).slice(5) + ' 笔试截止｜' + cname + ' ' + job.title });
    }
    // 期限待办（如「8-15 前完成注册」：纯日期，按当天 00:00；未过期且在 7 天内提醒）
    if (job.todo && job.todo.due) {
      const t = localMidnight(job.todo.due);
      if (t && t >= now && t <= day7) {
        items.push({ key: job.id + '|' + job.todo.due, pri: 2, ts: t, ddl: true, id: job.id, text: job.todo.due.slice(5) + ' 待办截止｜' + cname + ' ' + job.title + (job.todo.text ? '：' + job.todo.text : '') });
      }
    }
    // 待进行中的环节（仅日期，按当天 00:00 处理；时间提示只和「待进行」绑定，等结果不提醒）
    for (const x of stageList(job)) {
      if (x.v && x.v.state === 'todo' && x.v.date) {
        const t = localMidnight(x.v.date);
        if (t && t >= todayStart && t <= day7) {
          items.push({ key: job.id + '|' + x.v.date, pri: 1, ts: t, ddl: false, id: job.id, text: x.v.date.slice(5) + ' ' + x.label + '｜' + cname + ' ' + job.title });
        }
      }
    }
  }
  // 同一投递同一天只保留一条：Offer 截止 > 面试 > 笔试截止/待办截止 > 等待环节
  const byKey = new Map();
  for (const it of items) {
    const cur = byKey.get(it.key);
    if (!cur || it.pri > cur.pri) byKey.set(it.key, it);
  }
  const top = [...byKey.values()].sort((a, b) => a.ts - b.ts).slice(0, 10);

  let html = '';
  if (top.length === 0) {
    html += '<span class="rem-item none">未来 7 天暂无节点</span>';
  } else {
    html += top.map((it) => {
      // 有截止时间的节点（笔试/待办/Offer 截止）恒标红；其余 24h 内标红
      const urgent = it.ddl || (it.ts - now > 0 && it.ts - now <= 24 * 3600 * 1000);
      return '<span class="rem-item' + (urgent ? ' urgent' : '') + '" data-id="' + it.id + '" title="点击跳转到该投递">' + esc(it.text) + '</span>';
    }).join('');
  }
  bar.innerHTML = html;
}

/* ============ 备注展开（模块化自动判断）：渲染后测量，仅内容被截断的备注显示「展开」按键 ============ */
function initNoteToggles() {
  document.querySelectorAll('.m-note').forEach((el) => {
    if (el.closest('.job-card') && el.closest('.job-card').classList.contains('note-open')) return; // 展开态不重复判断
    const text = el.querySelector('.note-text');
    if (!text) return;
    const truncated = text.scrollWidth > text.clientWidth + 1;
    el.classList.toggle('expandable', truncated);
  });
}

/* ============ 统一渲染 ============ */
function render() {
  renderPinnedBar();
  renderList();
  renderReminders();
  renderCityOptions();
  renderQuickParse();
  initNoteToggles();
}

function renderCityOptions() {
  const sel = $('#cityFilter');
  const cities = [...new Set(state.jobs.flatMap((j) => jobCities(j)))].sort();
  const cur = sel.value;
  sel.innerHTML = '<option value="">城市：全部</option>' + cities.map((c) => '<option value="' + esc(c) + '">' + esc(c) + '</option>').join('');
  sel.value = state.filter.city || cur;
}

/* 跳转到指定投递卡片（节点提醒点击）：若被当前筛选隐藏，先重置过滤再定位 + 高亮 */
function jumpToJob(jobId) {
  if (!state.jobs.some((j) => j.id === jobId)) return;
  if (!filteredJobs().some((j) => j.id === jobId)) {
    state.filter = { tab: 'all', kw: '', status: '', city: '' };
    $('#searchInput').value = '';
    $('#statusFilter').value = '';
    $('#cityFilter').value = '';
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.toggle('active', b.dataset.tab === 'all'));
    render();
  }
  const el = document.getElementById('card-' + jobId);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 2400);
}

/* 实时时钟：跟随系统时间，24H 制，格式 YYYY/MM/DD  HH:mm（每秒刷新，分钟切换即时） */
function startClock() {
  const el = $('#nowClock');
  if (!el) return;
  const upd = () => {
    const d = new Date();
    const p = (n) => String(n).padStart(2, '0');
    el.textContent = d.getFullYear() + '/' + p(d.getMonth() + 1) + '/' + p(d.getDate()) + '  ' + p(d.getHours()) + ':' + p(d.getMinutes());
  };
  upd();
  setInterval(upd, 1000);
}

/* 离线/在线模式：未配置 API Key（或校验未通过）→ 智能识别栏置灰不可用 */
function renderQuickParse() {
  const sec = document.querySelector('.quick-parse');
  const ta = $('#qpText');
  const btn = $('#btnQp');
  const hint = document.querySelector('.qp-hint');
  const off = !state.aiOnline;
  sec.classList.toggle('off', off);
  ta.disabled = off;
  btn.disabled = off;
  hint.textContent = off
    ? '离线模式：未配置 API Key，智能识别不可用 · 点「⚙ API」配置后启用'
    : '识别结果先进入确认表单，核对无误后再保存';
}

/* 在线/离线判定：后端以最小请求校验 API Key 与模型连通性（通过 → 在线模式） */
async function checkAiOnline() {
  try {
    const res = await fetch('/api/ai/test', { method: 'POST' });
    const d = await res.json();
    state.aiOnline = !!(d && d.ok);
  } catch (_) {
    state.aiOnline = false;
  }
  renderQuickParse();
}

/* ============ 工作类型预填（标题含秋招/校招/应届 → 秋招；其余默认未知，不瞎猜转正与否） ============ */
function guessWorkType(title) {
  if (/秋招|校招|应届/i.test(title)) return 'autumn';
  return 'unknown';
}

/* 新增弹窗：选择已有公司 → 新建公司（切换显示输入框） */
function companySelChange() {
  const sel = $('#f-company-sel');
  const inp = $('#f-company');
  const isNew = sel.value === '__new__';
  inp.style.display = isNew ? 'block' : 'none';
  if (isNew) inp.focus();
}
function citySelChange() {
  const sel = $('#f-city-sel');
  const inp = $('#f-city');
  const isOther = sel.value === '__other__';
  inp.style.display = isOther ? 'block' : 'none';
  if (isOther) inp.focus();
}

/* ============ 智能识别（AI）与 API 配置 ============ */
/* 把识别值填入某一行环节控件（固定/面试轮均可） */
function setStageRow(key, v) {
  const row = document.querySelector('#modalBody .stage-row[data-key="' + key + '"]');
  if (!row) return;
  row.querySelector('[data-f="state"]').value = (v && v.state) || '';
  row.querySelector('[data-f="date"]').value = ((v && v.date) || '').slice(0, 10);
  const dl = row.querySelector('[data-f="deadline"]');
  if (dl && v && v.deadline) dl.value = String(v.deadline).slice(0, 16);
}

/* 识别结果 → 确认表单（复用新增表单 + 环节控件，全部可编辑，用户确认后再保存） */
function renderAiConfirm(data) {
  state.aiDraft = data || {};
  openAddModal({ forceCat: true }); // 识别信息通常不含实习/秋招 → 确认界面强制选择
  const d = state.aiDraft;

  // 公司：已有公司下拉优先，否则新建
  const comp = (d.company || '').trim();
  const compSel = $('#f-company-sel');
  if (comp && [...compSel.options].some((o) => o.value === comp)) compSel.value = comp;
  else if (comp) { compSel.value = '__new__'; $('#f-company').value = comp; $('#f-company').style.display = 'block'; }
  $('#f-title').value = d.title || '';
  // 工作类型：识别出明确类型才预填；识别不出则留空强制用户选择（不得默认）
  if (d.workType && WORK_TYPE_LABEL[d.workType]) {
    const wtEl = $('#f-work-type');
    if (wtEl) wtEl.value = d.workType;
  }
  if (d.city) {
    const citySel = $('#f-city-sel');
    if ([...citySel.options].some((o) => o.value === d.city)) citySel.value = d.city;
    else { citySel.value = '__other__'; $('#f-city').value = d.city; $('#f-city').style.display = 'block'; }
  }
  $('#f-url').value = d.url || '';
  $('#f-applied').value = (d.appliedDate || '').slice(0, 10);
  if (d.interviewAt) $('#f-interview').value = String(d.interviewAt).replace(' ', 'T').slice(0, 16); // datetime-local 需 T 分隔（识别归一化输出为空格格式）
  $('#f-note').value = d.note || '';
  // 期限待办预填（如「8-15 前完成注册并预约面试」→ todo）
  if (d.todo) {
    $('#f-todo-text').value = d.todo.text || '';
    $('#f-todo-due').value = String(d.todo.due || '').slice(0, 10);
  }
  // Offer 有效期预填（如「8-24 前确认接受」→ offerDeadline）
  if (d.offerDeadline) $('#f-offer-deadline').value = String(d.offerDeadline).slice(0, 10);

  // 环节预填（固定 + 动态面试轮）
  // 先按与「手动添加保存」相同的状态机归一化（fail→后续清空；pass→下一环节 todo；隐含前置通过），保证识别与手填走同一数据模型与算法
  const s = d.stages || {};
  // 隐含前置通过：识别到面试信息 → 简历/笔试自动默认通过；无面试轮时自动补「一面 待进行」
  if (d.interviewAt) {
    s.resume = s.resume || { date: '', state: null, deadline: null };
    s.written = s.written || { date: '', state: null, deadline: null };
    if (!s.interviews) s.interviews = [];
    if (s.interviews.length === 0) s.interviews.push({ date: String(d.interviewAt).slice(0, 10), state: 'todo' });
  }
  // 与「手动添加保存」相同的状态机归一化（fail→后续清空；pass→下一环节 todo；隐含前置通过）
  if (s.resume || s.written || (s.interviews || []).length || s.hr) normalizeStages(s, { interviewAt: d.interviewAt || null });
  if (s.resume) setStageRow('resume', s.resume);
  if (s.written) setStageRow('written', s.written);
  (s.interviews || []).forEach((v, i) => {
    if (!v || !(v.state || v.date)) return;
    addRoundRow(); // 每轮都建行（含第一轮：AI 确认表单无默认 iv0 行）
    setStageRow('iv' + i, v);
  });
  if (s.hr) setStageRow('hr', s.hr);

  // 不确定项提示（置于表单顶部）
  const unc = (d.uncertain || []).filter(Boolean);
  if (unc.length) {
    const box = document.createElement('div');
    box.className = 'offer-hint';
    box.innerHTML = '⚠️ 以下信息请核对后保存：' + unc.map(esc).join('；');
    $('#modalBody').insertBefore(box, $('#modalBody').firstChild);
  }
  $('#modalTitle').textContent = '确认识别结果（可修改）';
  state.modalMode = 'form';
  showModal(true);
}

/* 识别核心（常驻输入栏调用）：调用 /api/ai/parse → 确认表单 */
async function doAiParse(text) {
  try {
    const res = await fetch('/api/ai/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 400 && /API Key/.test(data.error || '')) {
        toast(data.error, true);
        openAiConfigModal(); // 未配置 → 引导去设置
        return;
      }
      throw new Error(data.error || '识别失败');
    }
    renderAiConfirm(data.data);
  } catch (e) {
    toast(e.message, true);
  }
}

/* 常驻智能识别栏：提交 → 自动识别并进入确认表单 */
async function quickParse() {
  const text = $('#qpText').value.trim();
  if (!text) { toast('请先粘贴需要识别的信息', true); $('#qpText').focus(); return; }
  $('#btnQp').disabled = true;
  $('#btnQp').textContent = '识别中…';
  try {
    await doAiParse(text);
    $('#qpText').value = '';
  } finally {
    $('#btnQp').disabled = false;
    $('#btnQp').textContent = '识别补充';
  }
}

/* API 配置弹窗（遵循「选择而非填空」：厂商 + 模型下拉，接口地址自动匹配，仅需输入 Key）
 * 模型准入标准：需能稳定遵循复杂 JSON schema 抽取（排除本地小模型与厂商轻量/免费级模型，保证识别准确率） */
const AI_PROVIDERS = [
  { name: 'DeepSeek', baseURL: 'https://api.deepseek.com/v1', models: [{ name: 'DeepSeek-V4-Flash', api: 'deepseek-v4-flash' }, { name: 'DeepSeek-V4-Pro', api: 'deepseek-v4-pro' }] },
  { name: '智谱 GLM', baseURL: 'https://open.bigmodel.cn/api/paas/v4', models: ['glm-4-plus', 'glm-4-air'] },
  { name: 'OpenAI', baseURL: 'https://api.openai.com/v1', models: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini'] },
  { name: '通义千问', baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-plus', 'qwen-max', 'qwen3-max'] },
  { name: 'Moonshot Kimi', baseURL: 'https://api.moonshot.cn/v1', models: ['kimi-k2.6', 'kimi-k3'] },
  { name: '腾讯混元', baseURL: 'https://api.hunyuan.cloud.tencent.com/v1', models: ['hunyuan-turbos-latest', 'hunyuan-turbo-latest'] },
  { name: '百度千帆', baseURL: 'https://qianfan.baidubce.com/v2', models: [{ name: 'ERNIE-4.0-8K', api: 'ernie-4.0-8k' }, { name: 'ERNIE-3.5-8K', api: 'ernie-3.5-8k' }] },
  { name: '讯飞星火', baseURL: 'https://spark-api-open.xf-yun.com/v1', models: ['spark-pro', 'spark-max'] },
  { name: 'MiniMax', baseURL: 'https://api.minimaxi.chat/v1', models: ['MiniMax-M2', 'abab6.5s-chat'] },
  { name: '零一万物', baseURL: 'https://api.lingyiwanwu.com/v1', models: ['yi-lightning', 'yi-large'] },
  { name: '硅基流动', baseURL: 'https://api.siliconflow.cn/v1', models: ['Qwen/Qwen2.5-72B-Instruct', 'deepseek-ai/DeepSeek-V3'] },
  { name: 'Groq', baseURL: 'https://api.groq.com/openai/v1', models: ['llama-3.3-70b-versatile'] },
];

/* 模型条目统一存取：字符串=官方 API 名（显示同值）；对象={name 常见名, api 官方 API 名}（下拉显示常见名，发送用官方名） */
const aiModelApi = (m) => (typeof m === 'string' ? m : m.api);
const aiModelLabel = (m) => (typeof m === 'string' ? m : m.name);
/* 官方 API 名 → 常见显示名（查看态展示用）；查不到则原样返回 */
function aiModelLabelOf(api) {
  for (const p of AI_PROVIDERS) {
    const hit = p.models.find((m) => aiModelApi(m) === api);
    if (hit) return aiModelLabel(hit);
  }
  return api;
}

/* 切换厂商 → 刷新模型下拉（保留已选模型） */
function aiProviderChange() {
  const prov = AI_PROVIDERS.find((p) => p.name === $('#ai-provider').value) || AI_PROVIDERS[0];
  const cur = $('#ai-model').value;
  $('#ai-model').innerHTML = prov.models.map((m) => '<option value="' + esc(aiModelApi(m)) + '">' + esc(aiModelLabel(m)) + '</option>').join('');
  if (prov.models.some((m) => aiModelApi(m) === cur)) $('#ai-model').value = cur;
}

/* ============ API Key 管理控制台（查看态：状态徽标 + 配置卡 + 测试/编辑/清除；编辑态：厂商/模型/Key） ============ */
function aiCfgRow(k, v) {
  return '<div class="ai-row"><span class="ai-k">' + k + '</span><span class="ai-v">' + v + '</span></div>';
}

async function openAiConfigModal() {
  state.modalMode = 'config';
  $('#modalTitle').textContent = 'API Key 管理控制台';
  showModal(true);
  $('#modalBody').innerHTML = '<div class="ai-status warn">加载配置状态…</div>';
  try {
    const res = await fetch('/api/ai/config');
    const d = await res.json();
    state.__aiCfg = d;
    if (d.configured) renderAiConfigView(d);
    else renderAiConfigEdit(true); // 未配置 → 直接进入编辑态
  } catch (e) {
    $('#modalBody').innerHTML = '<div class="ai-status warn">加载配置失败：' + esc(e.message) + '</div>';
  }
}

/* 查看态：状态徽标（自动测试连接）+ 当前配置卡 + 操作按钮 */
async function renderAiConfigView(cfg) {
  const prov = AI_PROVIDERS.find((p) => p.baseURL === cfg.baseURL);
  const provName = prov ? prov.name : (cfg.baseURL ? '自定义（' + cfg.baseURL + '）' : '—');
  $('#modalBody').innerHTML =
    '<div class="ai-badge-row" id="aiBadgeRow"><span class="ai-badge loading">◌ 校验中…</span><span class="ai-sub">正在测试 API Key 连通性</span></div>' +
    '<div class="ai-cfg-card">' +
      aiCfgRow('厂商', esc(provName)) +
      aiCfgRow('模型', esc(aiModelLabelOf(cfg.model))) +
      aiCfgRow('接口', esc(cfg.baseURL)) +
      '<div class="ai-row"><span class="ai-k">API Key</span><span class="ai-v">' + esc(cfg.apiKeyMasked) + '（已配置）</span></div>' +
    '</div>' +
    '<div class="ai-ops">' +
      '<button class="btn primary" data-act="ai-config-test">🔄 测试连接</button>' +
      '<button class="btn" data-act="ai-config-edit">✏️ 重新配置</button>' +
      '<button class="btn danger" data-act="ai-config-clear">🗑 清除配置</button>' +
    '</div>' +
    '<div class="ai-test-result" id="aiTestResult"></div>' +
    '<div class="hint">在线模式：智能识别 / 自动分类可用；离线（未配置或校验失败）：相关功能置灰，其余功能不受影响。</div>';
  aiTestNow(); // 进入即自动测试一次
}

/* 编辑态：厂商 / 模型 / API Key（接口地址自动匹配） */
function renderAiConfigEdit(first) {
  const base = (state.__aiCfg && state.__aiCfg.baseURL) || '';
  const prov = AI_PROVIDERS.find((p) => p.baseURL === base) || AI_PROVIDERS[0];
  const model = (state.__aiCfg && state.__aiCfg.model) || aiModelApi(prov.models[0]);
  $('#modalBody').innerHTML =
    '<div class="hint">选择厂商与模型，填入 API Key 即可——接口地址自动匹配，无需手动填写。</div>' +
    '<div class="form-grid" style="margin-top:10px;">' +
    '<div class="form-item"><label>厂商</label><select id="ai-provider" onchange="aiProviderChange()">' +
      AI_PROVIDERS.map((p) => '<option value="' + esc(p.name) + '">' + esc(p.name) + '</option>').join('') + '</select></div>' +
    '<div class="form-item"><label>模型</label><select id="ai-model"></select></div>' +
    '<div class="form-item full"><label>API Key</label><input id="ai-key" type="password" placeholder="粘贴 API Key（sk-…）" autocomplete="off"></div>' +
    '</div>' +
    '<div class="ai-ops">' +
      '<button class="btn primary" data-act="ai-config-save">保存配置</button>' +
      (first ? '' : '<button class="btn" data-act="ai-config-cancel">取消</button>') +
    '</div>' +
    '<div class="hint">配置仅在本地保存（config.json），不会上传到任何第三方。首次保存后会自动测试连接并解锁智能识别。</div>';
  $('#ai-provider').value = prov.name;
  aiProviderChange();
  if (prov.models.some((m) => aiModelApi(m) === model)) $('#ai-model').value = model;
}

/* 测试连接：最小请求校验 Key / 模型 / 接口，结果写入徽标与结果区 */
async function aiTestNow() {
  const row = $('#aiBadgeRow');
  const out = $('#aiTestResult');
  if (row) row.innerHTML = '<span class="ai-badge loading">◌ 测试中…</span><span class="ai-sub">请稍候</span>';
  if (out) out.innerHTML = '<div class="ai-status warn">测试中…</div>';
  try {
    const res = await fetch('/api/ai/test', { method: 'POST' });
    const d = await res.json();
    if (res.ok && d.ok) {
      if (row) row.innerHTML = '<span class="ai-badge ok">● 在线 · 智能识别可用</span><span class="ai-sub">API Key 校验通过</span>';
      if (out) out.innerHTML = '<div class="ai-status ok">✓ 连接正常：API Key / 模型 / 接口均校验通过</div>';
    } else {
      const err = (d && d.error) || ('HTTP ' + res.status);
      if (row) row.innerHTML = '<span class="ai-badge err">○ 离线 · 校验失败</span><span class="ai-sub">' + esc(err) + '</span>';
      if (out) out.innerHTML = '<div class="ai-status warn">✗ ' + esc(err) + '</div>';
    }
  } catch (e) {
    if (row) row.innerHTML = '<span class="ai-badge err">○ 离线 · 校验失败</span>';
    if (out) out.innerHTML = '<div class="ai-status warn">✗ ' + esc(e.message) + '</div>';
  }
}

/* 清除配置：确认后清空，回到离线（智能识别置灰） */
async function clearAiConfig() {
  if (!confirm('确定清除 API Key 配置？清除后智能识别将不可用。')) return;
  try {
    const res = await fetch('/api/ai/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clear: true }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || '清除失败');
    toast('API 配置已清除');
    state.__aiCfg = { configured: false, baseURL: '', model: '' };
    renderAiConfigEdit(true);
    checkAiOnline();
  } catch (e) {
    toast(e.message, true);
  }
}

async function saveAiConfig() {
  const prov = AI_PROVIDERS.find((p) => p.name === $('#ai-provider').value) || AI_PROVIDERS[0];
  const model = $('#ai-model').value;
  const apiKey = $('#ai-key').value.trim();
  if (!prov || !model || !apiKey) { toast('请选择厂商与模型并填写 API Key', true); return; }
  try {
    const res = await fetch('/api/ai/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ baseURL: prov.baseURL, model, apiKey }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || '保存失败');
    toast('API 配置已保存');
    // 回到查看态：重新拉取配置（含 Key 掩码）并自动测试连接
    const cfg = await (await fetch('/api/ai/config')).json();
    state.__aiCfg = cfg;
    renderAiConfigView(cfg);
    checkAiOnline(); // 保存后立即刷新离线/在线状态（成功 → 智能识别栏解除置灰）
  } catch (e) {
    toast(e.message, true);
  }
}

/* ============ 表单：新增（尽量选择而非输入：公司/城市下拉 + 自定义） ============ */
function openAddModal(opts) {
  opts = opts || {};
  state.editingJobId = null;
  state.modalMode = 'form';
  state.aiForceCat = !!opts.forceCat; // 识别确认模式：工作类型必选（识别信息通常不含工作类型）
  $('#modalTitle').textContent = '新增投递';
  // 工作类型四选项并列（秋招/有转正实习/日常实习/未知）；普通新增默认「未知」；识别确认模式不预填强制选择
  const wtOpts = opts.forceCat
    ? '<option value="">请选择工作类型…</option><option value="autumn">秋招</option><option value="convert">有转正实习</option><option value="nonconvert">日常实习</option><option value="unknown">未知</option>'
    : '<option value="unknown">未知</option><option value="autumn">秋招</option><option value="convert">有转正实习</option><option value="nonconvert">日常实习</option>';
  const companyOpts = state.companies.map((c) => '<option value="' + esc(c.name) + '">' + esc(c.name) + '</option>').join('');
  const cityOpts = [...new Set(state.jobs.flatMap((j) => jobCities(j)))].sort().map((c) => '<option value="' + esc(c) + '">' + esc(c) + '</option>').join('');
  $('#modalBody').innerHTML =
    '<div class="form-grid">' +
    '<div class="form-item"><label>公司名 <span class="req">*</span></label>' +
      '<select id="f-company-sel" onchange="companySelChange()"><option value="">请选择公司…</option>' + companyOpts + '<option value="__new__">＋ 新建公司…</option></select>' +
      '<input id="f-company" placeholder="输入新公司名" style="display:none;margin-top:6px;"></div>' +
    '<div class="form-item"><label>岗位名 <span class="req">*</span></label><input id="f-title" placeholder="如：大模型推理优化实习生"></div>' +
    '<div class="form-item"><label>工作类型 <span class="req" style="display:' + (opts.forceCat ? 'inline' : 'none') + '">*</span><span class="req-tip" style="display:' + (opts.forceCat ? 'inline' : 'none') + '">（识别信息不含工作类型，请确认）</span></label><select id="f-work-type">' +
      wtOpts +
    '</select></div>' +
    '<div class="form-item"><label>城市（选填）</label>' +
      '<select id="f-city-sel" onchange="citySelChange()"><option value="">不限</option>' + cityOpts + '<option value="__other__">自定义…</option></select>' +
      '<input id="f-city" placeholder="输入城市（多个用 / 分隔，如 北京/上海）" style="display:none;margin-top:6px;"></div>' +
    '<div class="form-item"><label>链接（选填）</label><input id="f-url" placeholder="https://…"></div>' +
    '<div class="form-item"><label>投递日期（选填）</label><input id="f-applied" type="date" value="' + localToday() + '"></div>' +
    '<div class="form-item"><label>面试时间（选填，用于提醒与置顶）</label><input id="f-interview" type="datetime-local"></div>' +
    '<div class="form-item full"><label>备注 / 下一动作（选填）</label><textarea id="f-note" rows="2" placeholder="如：48h 内完成测评；08-15 二面…"></textarea></div>' +
  '<div class="form-item"><label>待办事项（选填）</label><input id="f-todo-text" placeholder="如：8-15 前完成注册并预约面试"></div>' +
  '<div class="form-item"><label>待办截止日期（选填）</label><input id="f-todo-due" type="date"></div>' +
  '<div id="f-offer-deadline-wrap" style="display:none;"><div class="form-item"><label>Offer 截止日期（选填，获 Offer 后填写）</label><input id="f-offer-deadline" type="date" title="Offer 有效期，如 8-24 前确认"></div></div>' +
  '</div>' +
    '<div class="hint" style="margin:10px 0 4px;">流程环节（选填，可先留空，后续在「更新」中推进）：</div>' +
    stageRowHtml('resume', STAGE_LABELS.resume, { date: '', state: null }, false) +
    stageRowHtml('written', STAGE_LABELS.written, { date: '', state: null }, false) +
    '<div id="roundWrap"><button type="button" class="btn add-round" data-act="add-round">＋ 添加一轮面试</button></div>' +
    stageRowHtml('hr', STAGE_LABELS.hr, { date: '', state: null }, false) +
    '<div class="hint">必填项（<span class="req">*</span>）：公司名、岗位名、工作类型；其余均为选填。</div>';
  showModal(true);
}

/* Offer 截止日期栏显隐：仅「最终结果 = Offer」时显示（无最终结果选项的弹窗默认隐藏） */
function syncOfferDeadline() {
  const w = $('#f-offer-deadline-wrap');
  if (!w) return;
  const r = $('#f-result');
  w.style.display = (r && r.value === 'offer') ? '' : 'none';
}

/* ============ 表单：更新（v3 动态环节） ============ */
/* 一行环节控件（固定环节或动态面试轮）；笔试行附带「截止时间」输入（DDL） */
function stageRowHtml(key, label, v, removable) {
  const st = (v && v.state) || '';
  const d = formatDate((v && v.date) || '');
  const dl = (v && v.deadline) ? v.deadline.slice(0, 16) : '';
  const dlInput = key === 'written'
    ? '<input type="datetime-local" data-f="deadline" value="' + esc(dl) + '" title="笔试截止时间（DDL，如 48h 内做测评）">'
    : '';
  return (
    '<div class="stage-row" data-kind="' + (String(key).startsWith('iv') ? 'iv' : 'fx') + '" data-key="' + key + '">' +
    '<span class="sn">' + label + '</span>' +
    '<select data-f="state">' +
      '<option value="">留空（未到）</option>' +
      '<option value="pass"' + (st === 'pass' ? ' selected' : '') + '>通过</option>' +
      '<option value="wait"' + (st === 'wait' ? ' selected' : '') + '>等结果</option>' +
      '<option value="todo"' + (st === 'todo' ? ' selected' : '') + '>待进行（有预约/截止时间）</option>' +
      '<option value="fail"' + (st === 'fail' ? ' selected' : '') + '>被挂</option>' +
      '<option value="skip"' + (st === 'skip' ? ' selected' : '') + '>跳过（无此环节）</option>' +
    '</select>' +
    '<input type="date" data-f="date" value="' + esc(d) + '">' +
    dlInput +
    (removable ? '<button type="button" class="rm" data-rm="1" title="删除该轮面试">✕</button>' : '') +
    '</div>'
  );
}
function readStageRow(row) {
  const st = row.querySelector('[data-f="state"]').value;
  const date = row.querySelector('[data-f="date"]').value;
  const dlEl = row.querySelector('[data-f="deadline"]');
  const dl = dlEl ? dlEl.value : '';
  if (!st && !date && !dl) return { date: '', state: null };
  const out = { date: date || '', state: st || null };
  if (dl) out.deadline = dl + ':00'; // datetime-local 为本地时间，存本地串（不带 Z），显示/比较均按本地解析
  return out;
}
function hasStageContent(v) { return !!(v && (v.state || v.date)); }

/* 追加一轮面试（动态编号：一面 / 二面 / 三面…） */
function addRoundRow() {
  const wrap = $('#roundWrap');
  const btn = wrap.querySelector('[data-act="add-round"]');
  const n = wrap.querySelectorAll('.stage-row[data-kind="iv"]').length;
  const tmp = document.createElement('div');
  tmp.innerHTML = stageRowHtml('iv' + n, (CN_NUM[n] || String(n + 1)) + '面', { date: '', state: null }, true);
  btn.insertAdjacentElement('beforebegin', tmp.firstElementChild);
}

/* 保存时一致性推导（状态机合法性转移）：
 * 规则1：某环节 fail → 其后所有环节清空（流程终止）
 * 规则2：某环节 pass → 紧邻下一环节若空则自动置 todo（一次只推进一格）
 * 规则3：隐含前置通过——有面试 → 简历/笔试自动通过；笔试通过 → 简历自动通过 */
function normalizeStages(stages, job) {
  const seq = [];
  for (const k of ['resume', 'written']) if (stages[k]) seq.push(stages[k]);
  seq.push(...(stages.interviews || []));
  if (stages.hr) seq.push(stages.hr);
  // 规则 0（终态挂/放弃）：最近一个有动作的环节置 fail（保留日期），后续由 fail 规则清空
  if (job && (job.result === 'fail' || job.result === 'giveup')) {
    let lastAct = -1;
    for (let i = 0; i < seq.length; i++) {
      const v = seq[i];
      if (v && (v.state === 'pass' || v.state === 'wait' || v.state === 'todo' || v.state === 'fail' || v.date)) lastAct = i;
    }
    if (lastAct >= 0 && seq[lastAct].state !== 'fail') seq[lastAct].state = 'fail';
  }
  let failIdx = -1;
  for (let i = 0; i < seq.length; i++) {
    if (seq[i] && seq[i].state === 'fail') { failIdx = i; break; }
  }
  if (failIdx >= 0) {
    seq.forEach((v, i) => { if (i > failIdx) { v.date = ''; v.state = null; v.deadline = null; } });
  }
  for (let i = 0; i < seq.length - 1; i++) {
    if (seq[i] && seq[i].state === 'pass' && seq[i + 1] && !seq[i + 1].state) {
      seq[i + 1].state = 'todo'; // 通过后下一环节自动「待进行」（有预约/截止时间则产生时间提示）
      seq[i + 1].date = seq[i + 1].date || '';
    }
  }
  // 规则3（隐含前置通过）：能进入后续环节 = 前置环节已通过——
  // 有面试信息（interviewAt 或已填面试轮）→ 简历+笔试自动通过；笔试已通过 → 简历自动通过（不覆盖用户明确设置的 skip）
  const resume = stages.resume, written = stages.written;
  const ivs = stages.interviews || [];
  const hasInterviewInfo = !!(job && job.interviewAt) || ivs.some((v) => v && v.state && v.state !== 'skip');
  if (written && written.state === 'pass' && resume && !resume.state) resume.state = 'pass';
  if (hasInterviewInfo) {
    if (written && !written.state) written.state = 'pass';
    if (resume && !resume.state) resume.state = 'pass';
  }
  return stages;
}

function openEditModal(jobId) {
  const job = state.jobs.find((j) => j.id === jobId);
  if (!job) return;
  state.editingJobId = jobId;
  state.modalMode = 'form';
  const c = companyOf(job);
  $('#modalTitle').textContent = '更新进度｜' + (c ? c.name : '') + ' ' + job.title;

  const s = job.stages || {};
  let rows = '';
  for (const k of ['resume', 'written']) {
    rows += stageRowHtml(k, STAGE_LABELS[k], s[k] || { date: '', state: null }, false);
  }
  let ivRows = '';
  (s.interviews || []).forEach((v, i) => {
    ivRows += stageRowHtml('iv' + i, (CN_NUM[i] || String(i + 1)) + '面', v, true);
  });
  const hrRow = stageRowHtml('hr', STAGE_LABELS.hr, s.hr || { date: '', state: null }, false);
  const offerHint = (allStagesPassed(job) && !job.result)
    ? '<div class="offer-hint">🎉 流程环节全部通过——若已拿到 Offer，点击「🏆 标记为 Offer」或在下方选择最终结果。</div>'
    : '';

  $('#modalBody').innerHTML =
    '<div class="form-grid">' +
    '<div class="form-item"><label>公司名称 <span class="req">*</span></label><input id="f-company" value="' + esc(c ? c.name : '') + '" placeholder="修改后将同步该公司全部岗位"></div>' +
    '<div class="form-item"><label>岗位名称 <span class="req">*</span></label><input id="f-title" value="' + esc(job.title || '') + '" placeholder="如：大模型推理优化实习生"></div>' +
    '<div class="form-item"><label>工作类型（选填）</label><select id="f-work-type">' +
      '<option value="autumn"' + (job.workType === 'autumn' ? ' selected' : '') + '>秋招</option>' +
      '<option value="convert"' + (job.workType === 'convert' ? ' selected' : '') + '>有转正实习</option>' +
      '<option value="nonconvert"' + (job.workType === 'nonconvert' ? ' selected' : '') + '>日常实习</option>' +
      '<option value="unknown"' + (job.workType === 'unknown' || !job.workType ? ' selected' : '') + '>未知</option>' +
    '</select></div>' +
    '<div class="form-item"><label>面试时间（选填，用于提醒与置顶）</label><input id="f-interview" type="datetime-local" value="' + esc(job.interviewAt ? localIvStr(job.interviewAt).replace(' ', 'T') : '') + '"></div>' +
    '<div class="form-item"><label>最终结果</label><div class="result-row"><select id="f-result" onchange="syncOfferDeadline()">' +
      '<option value="">无（流程中）</option>' +
      '<option value="offer"' + (job.result === 'offer' ? ' selected' : '') + '>Offer</option>' +
      '<option value="fail"' + (job.result === 'fail' ? ' selected' : '') + '>挂</option>' +
      '<option value="giveup"' + (job.result === 'giveup' ? ' selected' : '') + '>放弃</option>' +
    '</select>' +
    '<button type="button" class="btn btn-offer" data-act="mark-offer" title="全部环节标记为通过并设为 Offer">🏆 标记为 Offer</button></div></div>' +
  '<div id="f-offer-deadline-wrap" style="display:' + (job.result === 'offer' ? '' : 'none') + ';"><div class="form-item"><label>Offer 截止日期（有效期，选填）</label><input id="f-offer-deadline" type="date" value="' + esc(job.offerDeadline || '') + '" title="如 8-24 前确认"></div></div>' +
  '<div class="form-item"><label>待办事项（期限类，选填）</label><input id="f-todo-text" value="' + esc((job.todo || {}).text || '') + '" placeholder="如：8-15 前完成注册并预约面试"></div>' +
    '<div class="form-item"><label>待办截止日期</label><input id="f-todo-due" type="date" value="' + esc((job.todo || {}).due || '') + '"></div>' +
    '</div>' +
    offerHint +
    '<div class="hint" style="margin:10px 0 4px;">流程环节（留空＝未到；通过后下一环节自动「待进行」，被挂后自动终止）：</div>' +
    rows +
    '<div id="roundWrap">' + ivRows + '<button type="button" class="btn add-round" data-act="add-round">＋ 添加一轮面试</button></div>' +
    hrRow +
    '<div class="form-item full" style="margin-top:10px;"><label>备注 / 下一动作</label><textarea id="f-note" rows="2">' + esc(job.note || '') + '</textarea></div>';
  showModal(true);
  // 岗位名缺省时自动聚焦岗位名输入框，引导用户补全
  if (isPlaceholderTitle(job)) {
    setTimeout(() => { const t = $('#f-title'); if (t) t.focus(); }, 60);
  }
}

/* ============ 表单：保存 ============ */
async function saveForm() {
  try {
    let offerPending = false;
    if (state.editingJobId === null) {
      // 先清除上次错误标记，再统一校验必填项（公司/岗位/工作类型；识别确认模式工作类型必选）
      document.querySelectorAll('#modalBody .err').forEach((el) => el.classList.remove('err'));
      const sel = $('#f-company-sel');
      const company = (sel && sel.value && sel.value !== '__new__') ? sel.value : $('#f-company').value.trim();
      const title = $('#f-title').value.trim();
      const wtEl = $('#f-work-type');
      const workType = wtEl ? wtEl.value : 'unknown';
      let miss = [];
      if (!company) { miss.push('公司名'); $('#f-company-sel').classList.add('err'); $('#f-company').classList.add('err'); }
      if (!title) { miss.push('岗位名'); $('#f-title').classList.add('err'); }
      if (state.aiForceCat && !workType) { miss.push('工作类型'); if (wtEl) wtEl.closest('.form-item').classList.add('err'); }
      if (miss.length) {
        toast('请完成必填项：' + miss.join('、'), true);
        return;
      }
      const dup = state.jobs.find((j) => j.title === title && (companyOf(j) || {}).name === company);
      if (dup) {
        toast('该公司下已存在同名岗位，建议改为「更新」', true);
        return;
      }
      let c = state.companies.find((cc) => cc.name === company);
      if (!c) {
        c = { id: newId(), name: company, pinnedAt: null, note: '' };
        state.companies.push(c);
      }
      const citySel = $('#f-city-sel');
      const city = (citySel && citySel.value && citySel.value !== '__other__') ? citySel.value : $('#f-city').value.trim();
      // 收集流程环节（新增表单带环节控件，可先留空）
      const stages = {};
      document.querySelectorAll('#modalBody .stage-row[data-kind="fx"]').forEach((row) => {
        stages[row.dataset.key] = readStageRow(row);
      });
      const iv = [];
      document.querySelectorAll('#modalBody .stage-row[data-kind="iv"]').forEach((row) => {
        iv.push(readStageRow(row));
      });
      while (iv.length > 0 && !hasStageContent(iv[iv.length - 1])) iv.pop(); // 清洗尾部空轮
      stages.interviews = iv;
      const job = {
        id: newId(),
        companyId: c.id,
        title,
        workType,
        city,
        url: $('#f-url').value.trim(),
        appliedDate: $('#f-applied').value || localToday(),
        interviewAt: $('#f-interview').value || null, // datetime-local 值为本地时间（无时区），不转 UTC 避免显示偏移
        note: $('#f-note').value.trim(),
        todo: (() => { const t = $('#f-todo-text').value.trim(); const d = $('#f-todo-due').value; return (t || d) ? { text: t, due: d || '' } : null; })(),
        offerDeadline: $('#f-offer-deadline').value || null,
        stages,
        result: null,
        updatedAt: nowIso(),
        pinnedAt: null,
      };
      normalizeStages(stages, job); // 状态机（含隐含前置通过：有面试 → 简历/笔试自动通过）
      // 环节被挂 → 结果自动联动
      if (stageList(job).some((x) => x.v.state === 'fail')) job.result = 'fail';
      state.jobs.push(job);
    } else {
      const job = state.jobs.find((j) => j.id === state.editingJobId);
      if (!job) return;
      // 公司名称 / 岗位名称可修改（必填校验）
      document.querySelectorAll('#modalBody .err').forEach((el) => el.classList.remove('err'));
      const cName = $('#f-company').value.trim();
      const tName = $('#f-title').value.trim();
      let miss = [];
      if (!cName) { miss.push('公司名称'); $('#f-company').classList.add('err'); }
      if (!tName) { miss.push('岗位名称'); $('#f-title').classList.add('err'); }
      if (miss.length) {
        toast('请完成必填项：' + miss.join('、'), true);
        return;
      }
      const cEdit = companyOf(job);
      if (cEdit && cEdit.name !== cName) cEdit.name = cName; // 修改公司实体名（该公司全部岗位同步显示）
      if (job.title !== tName) job.title = tName;
      job.interviewAt = $('#f-interview').value || null; // 本地时间（无时区），不转 UTC 避免显示偏移
      job.result = $('#f-result').value || null;
      // 终态（挂/放弃）不再有未来面试：清除残留面试时间，避免继续被面试置顶/提醒
      if (job.result === 'fail' || job.result === 'giveup') job.interviewAt = null;
      job.note = $('#f-note').value.trim();
      const wtEl = $('#f-work-type');
      if (wtEl) job.workType = wtEl.value || 'unknown'; // 编辑弹窗含工作类型控件时回写；不含则不覆盖
      const tt = $('#f-todo-text').value.trim();
      const dd = $('#f-todo-due').value;
      job.todo = (tt || dd) ? { text: tt, due: dd || '' } : null;
      job.offerDeadline = job.result === 'offer' ? ($('#f-offer-deadline').value || null) : null; // 截止日期仅在 Offer 时有效

      // 收集环节（固定 + 动态面试轮）
      const stages = {};
      document.querySelectorAll('#modalBody .stage-row[data-kind="fx"]').forEach((row) => {
        stages[row.dataset.key] = readStageRow(row);
      });
      const iv = [];
      document.querySelectorAll('#modalBody .stage-row[data-kind="iv"]').forEach((row) => {
        iv.push(readStageRow(row));
      });
      while (iv.length > 0 && !hasStageContent(iv[iv.length - 1])) iv.pop(); // 清洗尾部空轮
      stages.interviews = iv;
      normalizeStages(stages, job);
      job.stages = stages;

      // 环节被挂 → 结果自动联动（用户显式选择优先）
      if (stageList(job).some((x) => x.v.state === 'fail') && !job.result) job.result = 'fail';
      job.updatedAt = nowIso();
      offerPending = allStagesPassed(job) && !job.result;
    }
    await saveData();
    showModal(false);
    state.aiDraft = null;
    render();
    toast(offerPending ? '已保存：流程环节全部通过，可更新最终结果为 Offer' : '已保存并按优先级重排');
  } catch (e) {
    toast('保存失败：' + e.message, true);
  }
}

/* ============ 置顶（行首星标，仅单投递） ============ */
function togglePinJob(jobId) {
  const job = state.jobs.find((j) => j.id === jobId);
  if (!job) return;
  if (hasFutureInterview(job)) {
    toast('该投递由面试自动置顶，修改面试时间即可调整排序');
    return;
  }
  job.pinnedAt = job.pinnedAt ? null : nowIso();
  job.updatedAt = nowIso();
  saveData().then(() => {
    render();
    // 置顶/取消后自动定位到该卡片，让用户直观看到它重排后的位置
    const el = document.getElementById('card-' + job.id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('flash');
      setTimeout(() => el.classList.remove('flash'), 2400);
    }
    toast(job.pinnedAt ? '已置顶（置顶栏按置顶先后排列）' : '已取消置顶');
  }).catch(() => {});
}

/* ============ 匹配度排序入口 ============ */
async function openRankingModal() {
  $('#modalTitle').textContent = '岗位匹配度排序';
  $('#modalBody').innerHTML = '<div class="rank-empty">加载中…</div>';
  showModal(true);
  try {
    const res = await fetch('/api/rankings');
    const data = await res.json();
    if (!data.rankings || data.rankings.length === 0) {
      $('#modalBody').innerHTML =
        '<div class="rank-empty">暂无排序文档。</div>' +
        '<div class="hint">匹配度排序基于「01_简历基准/参与边界卡.md」五维评分（技能30 / 经历30 / 方向15 / 证据15 / 硬性10）。' +
        '在对话中把同公司多个岗位（链接或 JD）发给面试跟踪助手，助手生成后存入「20_岗位排序/」，即可在此查看。</div>';
      return;
    }
    $('#modalBody').innerHTML =
      '<div class="hint">已有排序文档（点击查看）：</div>' +
      '<ul class="rank-list">' + data.rankings.map((r) =>
        '<li data-rank="' + esc(r.name) + '"><b>' + esc(r.name) + '</b><span class="m">更新于 ' + new Date(r.modified).toLocaleString('zh-CN') + '</span></li>'
      ).join('') + '</ul>';
  } catch (e) {
    $('#modalBody').innerHTML = '<div class="rank-empty">读取失败：' + esc(e.message) + '</div>';
  }
}

async function viewRanking(name) {
  try {
    const res = await fetch('/api/ranking?name=' + encodeURIComponent(name));
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '读取失败');
    $('#modalTitle').textContent = '排序文档｜' + name;
    $('#modalBody').innerHTML = '<pre class="rank-content">' + esc(data.content) + '</pre>' +
      '<button class="btn" style="margin-top:10px;" id="rankBack">← 返回列表</button>';
    $('#rankBack').addEventListener('click', openRankingModal);
  } catch (e) {
    toast(e.message, true);
  }
}

/* ============ 弹层 / toast ============ */
function showModal(show) {
  $('#modalMask').style.display = show ? 'flex' : 'none';
  const save = $('#modalSave');
  if (!show) return;
  // 仅「新增/更新/识别确认」表单模式显示底部保存；识别输入与 API 设置在内容区自行操作
  if (state.modalMode === 'form') {
    save.style.display = '';
    save.onclick = saveForm;
  } else {
    save.style.display = 'none';
    save.onclick = null;
  }
}
function toast(msg, isError) {
  const t = $('#toast');
  t.textContent = msg;
  t.style.background = isError ? '#dc2626' : '#1f2733';
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 2600);
}

/* ============ 事件绑定 ============ */
function bindEvents() {
  $('#btnAdd').addEventListener('click', openAddModal);
  $('#btnAi').addEventListener('click', openAiConfigModal);
  $('#btnQp').addEventListener('click', quickParse);
  $('#modalClose').addEventListener('click', () => showModal(false));
  $('#modalCancel').addEventListener('click', () => showModal(false));
  $('#modalMask').addEventListener('click', (e) => { if (e.target === e.currentTarget) showModal(false); });
  $('#searchInput').addEventListener('input', (e) => { state.filter.kw = e.target.value.trim(); render(); });
  $('#statusFilter').addEventListener('change', (e) => { state.filter.status = e.target.value; render(); });
  $('#cityFilter').addEventListener('change', (e) => { state.filter.city = e.target.value; render(); });
  $('#workTypeFilter').addEventListener('change', (e) => { state.filter.workType = e.target.value; render(); });
  $('#tabs').addEventListener('click', (e) => {
    const btn = e.target.closest('.tab-btn');
    if (!btn) return;
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.toggle('active', b === btn));
    state.filter.tab = btn.dataset.tab;
    render();
  });
  $('#jobList').addEventListener('click', (e) => {
    const pin = e.target.closest('[data-act="pin"]');
    const edit = e.target.closest('[data-act="edit"]');
    const note = e.target.closest('[data-act="toggle-note"]');
    if (pin) togglePinJob(pin.dataset.id);
    else if (edit) openEditModal(edit.dataset.id);
    else if (note) { const nEl = note.closest('.m-note'); if (nEl && nEl.classList.contains('expandable')) { const card = note.closest('.job-card'); if (card) card.classList.toggle('note-open'); } }
  });
  $('#pinnedItems').addEventListener('click', (e) => {
    const unpin = e.target.closest('[data-act="unpin-job"]');
    if (unpin) { togglePinJob(unpin.dataset.id); return; }
    // 置顶 / Offer 待确认 chip → 点击跳转到对应投递卡片（若被筛选隐藏先重置过滤）
    const chip = e.target.closest('.pin-chip[data-id]');
    if (chip) jumpToJob(chip.dataset.id);
  });
  // 待办事项提醒 → 点击跳转到对应投递卡片（若被筛选隐藏先重置过滤）
  $('#reminderBar').addEventListener('click', (e) => {
    const it = e.target.closest('.rem-item[data-id]');
    if (it) jumpToJob(it.dataset.id);
  });
  // 回到顶部（常驻按钮，滚动超阈值后显示）
  const backTop = $('#backTop');
  if (backTop) {
    backTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
    window.addEventListener('scroll', () => {
      backTop.classList.toggle('show', window.scrollY > 400);
    }, { passive: true });
  }
  // 窗口尺寸变化 → 重新测量备注是否截断（展开按键的显示随可用宽度自动增减）
  window.addEventListener('resize', () => {
    clearTimeout(window.__noteToggleTimer);
    window.__noteToggleTimer = setTimeout(initNoteToggles, 150);
  });
  $('#modalBody').addEventListener('click', (e) => {
    const cfgSave = e.target.closest('[data-act="ai-config-save"]');
    if (cfgSave) { saveAiConfig(); return; }
    const cfgTest = e.target.closest('[data-act="ai-config-test"]');
    if (cfgTest) { aiTestNow(); return; }
    const cfgEdit = e.target.closest('[data-act="ai-config-edit"]');
    if (cfgEdit) { renderAiConfigEdit(false); return; }
    const cfgClear = e.target.closest('[data-act="ai-config-clear"]');
    if (cfgClear) { clearAiConfig(); return; }
    const cfgCancel = e.target.closest('[data-act="ai-config-cancel"]');
    if (cfgCancel) { openAiConfigModal(); return; }
    const add = e.target.closest('[data-act="add-round"]');
    if (add) { addRoundRow(); return; }
    const rm = e.target.closest('[data-rm]');
    if (rm) { rm.closest('.stage-row').remove(); return; }
    const mo = e.target.closest('[data-act="mark-offer"]');
    if (mo) {
      // 一键 Offer：所有非「跳过」环节置为通过（留空/wait/fail 一并视为已通过），最终结果设 Offer
      document.querySelectorAll('#modalBody .stage-row select[data-f="state"]').forEach((sel) => {
        if (sel.value !== 'skip') sel.value = 'pass';
      });
      $('#f-result').value = 'offer';
      syncOfferDeadline(); // 联动显示 Offer 截止日期栏
      return;
    }
    const rank = e.target.closest('[data-rank]');
    if (rank) viewRanking(rank.dataset.rank);
  });
}

/* ============ 启动 ============ */
(async function init() {
  bindEvents();
  startClock(); // 实时时钟（跟随系统时间）
  try {
    await loadData();
    render();
    checkAiOnline(); // 异步校验 API Key → 决定离线/在线模式（智能识别置灰与否）
  } catch (e) {
    $('#saveStatus').textContent = '数据加载失败：' + e.message;
    $('#saveStatus').className = 'status-pill error';
    $('#emptyRow').textContent = '数据加载失败：' + e.message + '（请确认服务已启动）';
    $('#emptyRow').style.display = 'block';
  }
})();
