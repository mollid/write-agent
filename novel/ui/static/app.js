"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  project: null,
  es: null,            // EventSource
  jobId: null,
  targetChapters: 0,
  doneChapters: 0,
  startChapter: 0,
  scoreMin: 80,
};

const STAGE_NAMES = {
  strategist: "策略：生成故事概念",
  worldbuilder: "世界观构建中",
  character: "角色设计中",
  outliner: "大纲编排中",
  concept: "生成故事概念",
  world: "构建世界观",
  characters: "设计人物",
  outline: "编排大纲",
  resume: "从故事圣经恢复",
  writer: "正文写作中",
  writer_rewrite: "按评审意见重写中",
  scorer: "质量评分中",
  continuity: "连续性检查中",
  editor: "编辑润色中",
  extractor: "状态提取与回写中",
};

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function log(text) {
  const el = $("event-log");
  const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  el.textContent += `[${time}] ${text}\n`;
  el.scrollTop = el.scrollHeight;
}

function setStatus(text) { $("status-line").textContent = text || ""; }

function setProgress(frac) {
  $("progress-bar").style.width = `${Math.round(Math.min(1, Math.max(0, frac)) * 100)}%`;
}

// ---------- 项目 ----------

async function refreshProjects() {
  const projects = await api("/api/projects");
  const sel = $("project-select");
  const current = state.project;
  sel.innerHTML = '<option value="">选择项目…</option>' +
    projects.map((p) => `<option value="${p.name}">${p.name}</option>`).join("");
  if (current && projects.some((p) => p.name === current)) sel.value = current;
}

async function openProject(name) {
  state.project = name;
  $("generate-body").hidden = !name;
  $("no-project-hint").hidden = !!name;
  closeGate();
  if (state.es) state.es.close();
  setStatus(""); setProgress(0); $("event-log").textContent = "";
  $("btn-cancel").hidden = true;
  if (!name) return;
  await refreshStatus();
  connectEvents();
}

async function refreshStatus() {
  if (!state.project) return;
  const s = await api(`/api/projects/${state.project}/status`);
  state.scoreMin = s.score_min || 80;
  renderChapters(s.chapters);
  await refreshThreads();
  await refreshReviews();
  if (s.job) {
    state.jobId = s.job.id;
    $("btn-cancel").hidden = false;
    setStatus(`任务进行中（${s.job.kind}）…`);
  } else {
    state.jobId = null;
    $("btn-cancel").hidden = true;
  }
}

function renderChapters(chapters) {
  const wrap = $("chapter-list");
  wrap.innerHTML = "";
  if (!chapters.length) return;
  for (const n of chapters) {
    const chip = document.createElement("span");
    chip.className = "chapter-chip";
    chip.textContent = String(n).padStart(3, "0");
    chip.onclick = () => loadChapter(n, chip);
    wrap.appendChild(chip);
  }
}

async function loadChapter(n, chipEl) {
  document.querySelectorAll(".chapter-chip").forEach((c) => c.classList.remove("active"));
  if (chipEl) chipEl.classList.add("active");
  const data = await api(`/api/projects/${state.project}/chapters/${n}`);
  $("reader").textContent = data.content;
}

async function refreshThreads() {
  if (!state.project) return;
  const threads = await api(`/api/projects/${state.project}/threads`);
  const tbody = $("threads-table").querySelector("tbody");
  tbody.innerHTML = threads.length
    ? threads.map((t) =>
        `<tr><td>${escapeHtml(t.id)}</td><td>${escapeHtml(t.description)}</td><td>${t.status}</td></tr>`).join("")
    : '<tr><td colspan="3" style="color:var(--muted)">暂无</td></tr>';
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- 评分历史 ----------

async function refreshReviews() {
  if (!state.project) return;
  const recs = await api(`/api/projects/${state.project}/reviews`);
  const wrap = $("reviews-list");
  wrap.innerHTML = "";
  if (!recs.length) {
    wrap.innerHTML = '<div class="hint" style="padding:8px 0">暂无评分记录，生成章节后自动留档。</div>';
    return;
  }
  const byChapter = new Map();
  for (const r of recs) {
    if (!byChapter.has(r.chapter)) byChapter.set(r.chapter, []);
    byChapter.get(r.chapter).push(r);
  }
  for (const ch of [...byChapter.keys()].sort((a, b) => a - b)) {
    const attempts = byChapter.get(ch);
    const last = attempts[attempts.length - 1];
    const block = document.createElement("details");
    block.className = "review-block";
    block.innerHTML = `
      <summary>
        <span>第 ${ch} 章</span>
        <span class="review-score-badge${last.passed ? "" : " fail"}">最终 ${last.overall} 分 ${last.passed ? "✅" : "❌"}</span>
        <span class="review-attempts">${attempts.length} 次评分</span>
      </summary>
      <div class="review-detail">${attempts.map(renderAttempt).join("")}</div>`;
    wrap.appendChild(block);
  }
}

function renderAttempt(a) {
  const min = state.scoreMin || 80;
  const dims = Object.entries(a.scores || {}).map(([name, v]) => `
    <div class="review-dim">
      <span class="review-dim-name">${escapeHtml(name)}</span>
      <span class="review-dim-score${v.score >= min ? "" : " fail"}">${v.score}</span>
      <span class="review-dim-critique">${escapeHtml(v.critique || "")}</span>
    </div>`).join("");
  const time = a.timestamp ? a.timestamp.slice(0, 19).replace("T", " ") : "";
  return `
    <div class="review-attempt">
      <div class="review-attempt-title">第 ${a.attempt} 次尝试 · 总分 ${a.overall} · ${a.passed ? "通过" : "未达标"}${time ? ` · ${time}` : ""}</div>
      ${a.summary ? `<div class="review-summary-text">${escapeHtml(a.summary)}</div>` : ""}
      ${dims}
    </div>`;
}

// ---------- SSE ----------

function connectEvents() {
  state.es = new EventSource(`/api/projects/${state.project}/events`);
  state.es.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    handleEvent(m);
  };
  state.es.onerror = () => { /* EventSource 自动重连 */ };
}

function handleEvent(m) {
  if (m.job_id && m.job_id !== state.jobId) state.jobId = m.job_id;
  const stageName = (s) => STAGE_NAMES[s] || s;

  switch (m.type) {
    case "stage":
      if (m.chapter) {
        setStatus(`第 ${m.chapter} 章 · ${stageName(m.stage)}…`);
        log(`第 ${m.chapter} 章 · ${stageName(m.stage)}`);
      } else {
        setStatus(stageName(m.stage) + "…");
        log(stageName(m.stage));
      }
      break;
    case "chapter_start":
      state.startChapter = state.startChapter || m.chapter;
      log(`▶ 开始第 ${m.chapter} 章${m.title ? `「${m.title}」` : ""}`);
      setStatus(`第 ${m.chapter} 章 · 写作中…`);
      break;
    case "review":
      log(`  评审：总分 ${m.overall}（第 ${m.attempt} 次尝试）${m.passed ? "✅ 通过" : "❌ 未达标"}`);
      break;
    case "chapter_done":
      state.doneChapters += 1;
      setProgress(state.targetChapters ? state.doneChapters / state.targetChapters : 1);
      log(`✔ 第 ${m.chapter} 章完成并已保存`);
      break;
    case "chapter_skipped":
      log(`✖ 第 ${m.chapter} 章被跳过：${m.reason}`);
      break;
    case "premise_done":
      log(`✔ 故事概念已生成（genre=${m.genre}）`);
      break;
    case "setup_stage":
      if (m.skipped && m.reason === "aborted")
        log(`设定阶段 ${m.stage} 未通过，设定已停止（已通过的阶段已保留）`);
      else if (m.skipped) log(`设定阶段 ${m.stage} 已通过，跳过`);
      else log(`设定阶段 ${m.stage}：第 ${m.attempt} 次生成（见审批卡片）`);
      break;
    case "gate":
      showGate(m);
      break;
    case "job_end":
      onJobEnd(m);
      break;
  }
}

function onJobEnd(m) {
  $("btn-cancel").hidden = true;
  state.jobId = null;
  closeGate();
  if (m.status === "done") {
    setStatus("✅ 任务完成");
    log("✅ 任务完成");
    setProgress(1);
  } else if (m.status === "cancelled") {
    setStatus("任务已取消");
    log("任务已取消");
  } else {
    setStatus(`❌ 任务失败：${m.error || "未知错误"}`);
    log(`❌ 任务失败：${m.error}`);
  }
  refreshStatus();
}

// ---------- 审批 ----------

function showGate(m) {
  $("gate-card").hidden = false;
  if (String(m.label).startsWith("setup:")) {
    const st = m.label.slice(6);
    $("gate-label").textContent = `设定阶段：${SETUP_STAGE_NAMES[st] || st} — 通过还是修改？`;
  } else {
    $("gate-label").textContent = GATE_LABELS[m.label] || m.label;
  }
  $("gate-artifact").textContent = (m.artifact || "").slice(0, 4000);
  const isSetup = String(m.label).startsWith("setup:");
  $("gate-feedback").hidden = !isSetup;
  $("gate-feedback").value = "";
  $("btn-approve").disabled = false;
  $("btn-reject").disabled = false;
  $("btn-reject").textContent = isSetup ? "带反馈重生成" : "拒绝";
  $("gate-card").dataset.gateId = m.gate_id;
  log(`⚠ 等待审批：${m.label}`);
  setStatus("等待审批…");
}

const GATE_LABELS = {
  outline: "大纲已生成，是否批准？",
  chapter: "本章已完成，是否继续？",
  chapter_review_failed: "本章多次重写后仍未达标，是否强行放行？",
};

const SETUP_STAGE_NAMES = {
  concept: "故事概念",
  world: "世界观",
  characters: "人物",
  outline: "大纲",
};

function closeGate() {
  $("gate-card").hidden = true;
}

async function resolveGate(approve) {
  const id = $("gate-card").dataset.gateId;
  if (!id) return;
  let feedback = "";
  if (!approve && !$("gate-feedback").hidden) {
    feedback = $("gate-feedback").value.trim();
    if (!feedback) { alert("请填写修改意见，或点击「通过」"); return; }
  }
  $("btn-approve").disabled = true;
  $("btn-reject").disabled = true;
  await api(`/api/gates/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approve, feedback }),
  });
  log(approve ? "已批准" : "已提交反馈，重新生成中…");
  closeGate();
}

// ---------- 动作 ----------

async function startPremise() {
  const text = $("premise-input").value.trim();
  if (!text) return alert("请输入创意");
  try {
    const r = await api(`/api/projects/${state.project}/premise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    state.jobId = r.job_id;
    $("btn-cancel").hidden = false;
    setStatus("策略智能体生成概念中…");
    log(`▶ 生成概念：${text}`);
  } catch (e) { alert(e.message); }
}

async function startSetup() {
  const premiseText = $("premise-input").value.trim();
  try {
    const r = await api(`/api/projects/${state.project}/setup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ premise: premiseText }),
    });
    state.jobId = r.job_id;
    $("btn-cancel").hidden = false;
    log(`▶ 开始分阶段设定${premiseText ? `：${premiseText}` : ""}`);
    setStatus("设定流程启动…");
  } catch (e) { alert(e.message); }
}

async function startWrite() {
  const n = parseInt($("chapter-count").value, 10) || 1;
  try {
    const r = await api(`/api/projects/${state.project}/write-chapter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n }),
    });
    state.jobId = r.job_id;
    state.targetChapters = n;
    state.doneChapters = 0;
    state.startChapter = 0;
    $("btn-cancel").hidden = false;
    setProgress(0);
    log(`▶ 开始生成 ${n} 章`);
    setStatus("启动中…");
  } catch (e) { alert(e.message); }
}

async function cancelJob() {
  if (!state.jobId) return;
  try {
    await api(`/api/jobs/${state.jobId}/cancel`, { method: "POST" });
    log("已请求取消…");
  } catch (e) { alert(e.message); }
}

async function exportNovel() {
  try {
    const r = await api(`/api/projects/${state.project}/export`, { method: "POST" });
    $("export-result").textContent = `已导出: ${r.path}`;
    log(`已导出: ${r.path}`);
  } catch (e) { alert(e.message); }
}

// ---------- 初始化 ----------

async function initMode() {
  // 模式徽标：与后端一致，由 NOVEL_LIVE 环境变量决定
  const s = await fetch("/api/mode").then((r) => r.ok ? r.json() : { live: false }).catch(() => ({ live: false }));
  const badge = $("mode-badge");
  if (s.live) {
    badge.textContent = "真实模型模式";
    badge.classList.add("live");
  } else {
    badge.textContent = "演示模式";
  }
}

$("project-select").onchange = (ev) => openProject(ev.target.value);
$("btn-new-project").onclick = () => $("new-project-dialog").showModal();
$("btn-cancel-new").onclick = () => $("new-project-dialog").close();
$("new-project-form").onsubmit = async (ev) => {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  try {
    await api("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: fd.get("name"), genre: fd.get("genre") }),
    });
    ev.target.reset();
    $("new-project-dialog").close();
    await refreshProjects();
    $("project-select").value = fd.get("name");
    await openProject(fd.get("name"));
  } catch (e) { alert(e.message); }
};
$("btn-premise").onclick = startPremise;
$("btn-setup").onclick = startSetup;
$("btn-write").onclick = startWrite;
$("btn-cancel").onclick = cancelJob;
$("btn-approve").onclick = () => resolveGate(true);
$("btn-reject").onclick = () => resolveGate(false);
$("btn-export").onclick = exportNovel;
$("btn-refresh-reviews").onclick = () => refreshReviews().catch((e) => alert(e.message));

refreshProjects().then(initMode);
