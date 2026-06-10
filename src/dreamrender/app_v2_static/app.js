const state = {
  data: null,
  drag: null,
  dashboardDrag: null,
  toggleBusy: null,
  dashboardPendingJobs: new Map(),
  dashboardPendingWorkers: new Map(),
  optimisticHiddenJobs: new Set(),
  initialized: false,
};
const layoutKey = "dreamrender.app.bentoLayout.v3";
const expandedJobsKey = "dreamrender.app.expandedJobs.v1";
const expandedJobs = new Set(JSON.parse(localStorage.getItem(expandedJobsKey) || "[]"));

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
}[char]));
const workerPalette = ["#ffd43d", "#58c981", "#8b63f6", "#ff5538", "#ffb13d", "#41d8a1", "#a16cff", "#ff7a59"];
const statusColors = {
  done: "#65cd8b",
  rendering: "#ff8b3d",
  failed: "#ed7884",
  queued: "#dfe7e2",
};

function hashValue(value) {
  let hash = 0;
  for (const char of String(value || "")) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0;
  return Math.abs(hash);
}

function workerColor(workerId) {
  return workerPalette[hashValue(workerId) % workerPalette.length];
}

function statusText(counts) {
  return Object.entries(counts || {}).sort().map(([key, value]) => `${key}: ${value}`).join("  ");
}

function saveExpandedJobs() {
  localStorage.setItem(expandedJobsKey, JSON.stringify([...expandedJobs]));
}

async function fetchJson(path, options = {}, timeoutMs = 12000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.message || response.statusText);
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("DreamRender is taking longer than expected. It may still be starting; check Activity for details.");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

async function post(path, payload, timeoutMs = 12000) {
  return fetchJson(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, timeoutMs);
}

function showInlineMessage(selector, tone, title, detail) {
  const element = $(selector);
  element.hidden = false;
  element.className = `inline-message ${tone}`;
  element.innerHTML = `
    <strong>${esc(title)}</strong>
    ${detail ? `<span>${esc(detail)}</span>` : ""}
  `;
}

function showAppFeedback(tone, message) {
  const element = $("#operation-result");
  element.hidden = false;
  element.className = `app-feedback ${tone}`;
  element.textContent = message;
}

function setToggleBusy(action) {
  state.toggleBusy = action;
  showAppFeedback("working", action === "start" ? "Starting DreamRender..." : "Stopping DreamRender...");
  render(state.data || {});
}

function clearToggleBusy(message) {
  state.toggleBusy = null;
  if (message) {
    showAppFeedback("ok", message);
  }
  render(state.data || {});
}


function dashboardActionLabel(action) {
  return ({
    delete: "Deleting job...",
    repair_job: "Repairing job...",
    repair: "Repairing queue...",
    requeue: "Retrying failed frames...",
    mark_failed_done: "Marking failed frames done...",
    pause: "Pausing job...",
    resume: "Resuming job...",
    cancel: "Cancelling job...",
    move_job: "Saving priority...",
    reorder: "Saving priority order...",
    worker_restart: "Requesting worker restart...",
    worker_toggle_stop: "Updating worker stop mode...",
    worker_stop_now: "Stopping worker...",
  })[action] || "Syncing dashboard...";
}

function setDashboardPending({ action, jobId = "", workerId = "" }) {
  const label = dashboardActionLabel(action);
  if (jobId) state.dashboardPendingJobs.set(jobId, { action, label });
  if (workerId) state.dashboardPendingWorkers.set(workerId, { action, label });
  if (action === "delete" && jobId) state.optimisticHiddenJobs.add(jobId);
  showAppFeedback("working", label);
  renderDashboard(state.data?.queue || {}, state.data || {});
}

function clearDashboardPending({ jobId = "", workerId = "", restoreHidden = false }) {
  if (jobId) {
    state.dashboardPendingJobs.delete(jobId);
    if (restoreHidden) state.optimisticHiddenJobs.delete(jobId);
  }
  if (workerId) state.dashboardPendingWorkers.delete(workerId);
}
function loadLayout() {
  try {
    return JSON.parse(localStorage.getItem(layoutKey) || "{}");
  } catch {
    return {};
  }
}

function saveLayout() {
  const layout = {};
  document.querySelectorAll(".bento-grid").forEach(grid => {
    const gridName = grid.dataset.grid || "default";
    layout[gridName] = [...grid.querySelectorAll(".bento-card")].map(card => card.dataset.widget);
  });
  localStorage.setItem(layoutKey, JSON.stringify(layout));
}

function applySavedLayout() {
  const layout = loadLayout();
  document.querySelectorAll(".bento-grid").forEach(grid => {
    const gridName = grid.dataset.grid || "default";
    const cards = new Map([...grid.querySelectorAll(".bento-card")].map(card => [card.dataset.widget, card]));
    (layout[gridName] || []).forEach(widget => {
      const card = cards.get(widget);
      if (card) grid.appendChild(card);
    });
  });
}

function swapCards(first, second) {
  const marker = document.createElement("div");
  const parent = first.parentNode;
  parent.insertBefore(marker, first);
  second.parentNode.insertBefore(first, second);
  parent.insertBefore(second, marker);
  marker.remove();
  saveLayout();
}

function cardFromPoint(x, y) {
  const hidden = state.drag?.card;
  if (hidden) hidden.style.pointerEvents = "none";
  const target = document.elementFromPoint(x, y)?.closest(".bento-card");
  if (hidden) hidden.style.pointerEvents = "";
  return target;
}

function clearDropTarget() {
  document.querySelectorAll(".drop-target").forEach(card => card.classList.remove("drop-target"));
}

function selectTab(tabId) {
  const tab = document.querySelector(`.tab[data-tab="${tabId}"]`);
  if (!tab || tab.disabled) return;
  document.querySelectorAll(".tab").forEach(button => button.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.remove("active"));
  tab.classList.add("active");
  document.getElementById(tab.dataset.tab).classList.add("active");
  document.body.classList.toggle("dashboard-active", tabId === "dashboard-panel");
}

async function refresh() {
  const data = await fetchJson("/api/state", {}, 10000);
  state.data = data;
  state.initialized = true;
  render(data);
}

async function safeRefresh() {
  try {
    await refresh();
  } catch (error) {
    showAppFeedback("working", error.message || "DreamRender is still loading.");
  }
}

function render(data) {
  const config = data.config || {};
  const hasConfig = Boolean(data.config);
  const busy = state.toggleBusy;
  const toggleLabel = !hasConfig ? "Loading..." : busy ? (busy === "start" ? "Starting..." : "Stopping...") : (data.worker_running ? "Stop DreamRender" : "Start DreamRender");
  $("#toggle").innerHTML = `<span class="toggle-switch" aria-hidden="true"><span></span></span><span>${esc(toggleLabel)}</span>`;
  $("#toggle").setAttribute("aria-pressed", data.worker_running ? "true" : "false");
  $("#toggle").classList.toggle("stop", Boolean(data.worker_running));
  $("#toggle").classList.toggle("is-loading", Boolean(busy));
  $("#toggle").disabled = Boolean(busy) || !hasConfig;
  $("#dashboard-tab").disabled = Boolean(busy) || !data.worker_running;
  $("#dashboard-tab").title = data.worker_running ? "Show the DreamRender dashboard" : "Start DreamRender before opening the dashboard";
  if (!data.worker_running && $("#dashboard-panel").classList.contains("active")) selectTab("setup");
  $("#worker-state").textContent = busy === "start" ? "Starting..." : busy === "stop" ? "Stopping..." : data.worker_running ? `Running as ${config.worker_id}` : "Stopped";
  $("#monitor-state").textContent = busy === "start" ? "Starting..." : busy === "stop" ? "Stopping..." : data.monitor_running ? "Integrated dashboard" : "Ready";
  $("#app-status").textContent = busy === "start" ? "Starting worker and dashboard" : busy === "stop" ? "Stopping services" : data.status || "Ready";
  $("#app-version").textContent = `App v${data.app_version || "--"} - data ${formatSnapshotAge(data)} - code ${data.code_signature || "--"}`;
  document.querySelectorAll('[data-widget="worker"], [data-widget="monitor"], [data-widget="status"]').forEach(card => {
    card.classList.toggle("is-working", Boolean(busy));
  });

  // The app refreshes every few seconds. Do not overwrite Setup fields while
  // someone is typing a custom render command such as a Redshift wrapper .bat.
  const editing = document.activeElement;
  const setupCard = $("#share")?.closest(".bento-card");
  const isEditingSetup = Boolean(
    setupCard &&
    editing &&
    setupCard.contains(editing) &&
    ["INPUT", "TEXTAREA", "SELECT"].includes(editing.tagName)
  );

  if (hasConfig && !isEditingSetup) {
    $("#share").value = config.share || "";
    $("#c4d").value = config.c4d || "";
    $("#worker-id").value = config.worker_id || "";
    $("#chunk-size").value = config.chunk_size || 5;
    $("#monitor-port").value = config.monitor_port || 8766;
    $("#keep-worker").checked = Boolean(config.keep_worker_running);
  }

  renderHealth(data.health || []);
  renderQueue(data.queue || {});
  renderGpus(data.gpus || [], data.gpu_message);
  try {
    renderDashboard(data.queue || {}, data);
  } catch (error) {
    console.error(error);
    $("#dashboard-jobs").innerHTML = `<div class="dashboard-error">Dashboard refresh failed: ${esc(error.message || error)}</div>`;
  }
  $("#log").value = (data.worker_log || []).join("\n");
}

function jobState(job) {
  const counts = job.counts || {};
  const rendering = counts.rendering || 0;
  const queued = counts.queued || 0;
  const failed = counts.failed || 0;
  if (job.status === "cancelled") return ["failed", "Cancelled"];
  if (job.status === "draining") return ["rendering", failed > 0 ? "Draining + issues" : "Draining"];
  if (rendering > 0) return ["rendering", failed > 0 ? "Rendering + issues" : "Rendering"];
  if (job.status === "paused") return ["queued", failed > 0 ? "Paused + issues" : "Paused"];
  if (job.status === "done" || job.status === "archived") return ["done", "Done"];
  if (failed > 0 && queued > 0) return ["queued", "Queued + issues"];
  if (failed > 0) return ["failed", "Needs Repair"];
  return ["queued", "Queued"];
}

function workerLabel(worker) {
  const active = worker.active || null;
  if (active) {
    const frameText = active.start_frame != null && active.end_frame != null ? `frames ${active.start_frame}-${active.end_frame}` : `frame ${active.frame}`;
    const phase = active.phase || "rendering";
    const job = active.job_name || active.job_id;
    return `${phase}: ${job}, ${frameText}`;
  }
  if (worker.stop_now_requested) return "stop requested";
  if (worker.stop_after_batch) return "will stop after current batch";
  if (worker.restart_requested) return "restart pending";
  if (worker.code_current === false) return "restart needed";
  if (worker.state === "starting") return "starting, waiting for queue heartbeat";
  if (worker.state === "online") return "idle";
  if (worker.state === "heartbeat_lost") return "heartbeat lost";
  return worker.last_seen_seconds == null ? "offline" : `offline, last seen ${formatSeconds(worker.last_seen_seconds)} ago`;
}

function formatSeconds(seconds) {
  if (seconds == null) return "--";
  seconds = Math.max(0, Math.round(seconds));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m) return `${m}m ${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}
function formatSnapshotAge(data) {
  const generated = Number(data?.live_generated_at || 0);
  if (!generated) return data?.live_refreshing ? "refreshing" : "not loaded yet";
  const age = Math.max(0, Date.now() / 1000 - generated);
  const label = `${formatSeconds(age)} old`;
  return data?.live_refreshing ? `${label}, refreshing` : label;
}

function renderDashboard(queue, appData) {
  if (state.dashboardDrag) return;
  const workers = queue.workers || [];
  const jobs = (queue.jobs || []).filter(job => !state.optimisticHiddenJobs.has(job.id));
  const repair = queue.repair || {};
  const freshness = `App v${appData.app_version || "--"} - data ${formatSnapshotAge(appData)} - code ${queue.code_signature || appData.code_signature || "--"}`;
  const queuePath = queue.share || appData.queue_share || appData.share_path || appData.config?.share || "";
  const localWorkerId = appData.local_worker_id || appData.config?.worker_id || "this machine";
  const diagnostics = [];
  if (appData.worker_running && appData.live_generated_at && appData.local_worker_visible === false) {
    diagnostics.push(`${esc(localWorkerId)} is running, but no heartbeat was found in this queue. Check that this machine uses the exact same queue folder.`);
  }
  if (queue.error) diagnostics.push(`Queue read error: ${esc(queue.error)}`);
  const queueState = queue.stale ? "Showing last known queue data while DreamRender reconnects." : appData.worker_running ? "Dashboard live." : "Start DreamRender to view live workers and jobs.";
  const repairText = repair.changed ? ` Repair updated ${repair.changed} frame(s).` : "";
  $("#dashboard-health").innerHTML = `
    <div>${esc(queueState)}${esc(repairText)} ${esc(freshness)}</div>
    <div class="dashboard-queue-path">Queue: ${esc(queuePath || "not configured")}${appData.local_worker_visible === false ? ` - Local worker heartbeat pending: ${esc(localWorkerId)}` : ""}</div>
    ${diagnostics.map(message => `<div class="dashboard-alert">${message}</div>`).join("")}
  `;
  $("#dashboard-workers").innerHTML = workers.length ? workers.map(worker => {
    const color = workerColor(worker.worker_id);
    const stateClass = worker.state === "heartbeat_lost" ? "lost" : worker.state === "starting" ? "starting" : worker.state !== "online" ? "offline" : worker.active ? "rendering" : "";
    const pending = state.dashboardPendingWorkers.get(worker.worker_id);
    const stopAfterBatch = Boolean(worker.stop_after_batch);
    return `<article class="dashboard-worker ${stateClass} ${pending ? "is-syncing" : ""}" style="--worker-color:${color}" data-worker-id="${esc(worker.worker_id)}">
      <span class="dashboard-worker-dot"></span>
      <div>
        <strong>${esc(worker.worker_id)}</strong>
        <div class="muted">${esc(workerLabel(worker))}</div>
        ${pending ? `<div class="dashboard-sync-label">${esc(pending.label)}</div>` : ""}
        <div class="dashboard-worker-actions">
          <button data-dashboard-action="worker_restart" data-worker="${esc(worker.worker_id)}">${worker.code_current === false ? "Restart needed" : "Restart"}</button>
          <button class="dashboard-toggle ${stopAfterBatch ? "active" : ""}" data-dashboard-action="worker_toggle_stop" data-worker="${esc(worker.worker_id)}" aria-pressed="${stopAfterBatch ? "true" : "false"}">
            <span></span>Stop after batch
          </button>
          <button data-dashboard-action="worker_stop_now" data-worker="${esc(worker.worker_id)}">Stop</button>
        </div>
      </div>
    </article>`;
  }).join("") : `<div class="dashboard-empty"><strong>No workers in this queue.</strong><span>${appData.worker_running ? `This app is running as ${esc(appData.local_worker_id || "this machine")}, but this queue has no worker heartbeat. Check the Queue path on every machine.` : "Start DreamRender on a render node."}</span></div>`;
  if (queue.error) {
    $("#dashboard-jobs").innerHTML = `<div class="dashboard-error">${esc(queue.error)}</div>`;
    return;
  }
  $("#dashboard-jobs").className = "dashboard-job-list";
  $("#dashboard-jobs").innerHTML = jobs.length ? jobs.map(renderDashboardJob).join("") : `
    <div class="dashboard-empty">
      <strong>No jobs in the queue yet.</strong>
      <span>Submit from Cinema 4D with Extensions &gt; DreamRender Submit Render.</span>
    </div>`;
}

function renderDashboardJob(job) {
  const collapsed = !expandedJobs.has(job.id);
  const [statusClass, statusLabel] = jobState(job);
  const pending = state.dashboardPendingJobs.get(job.id);
  const color = statusColors[statusClass] || statusColors.queued;
  const counts = job.counts || {};
  const isDone = job.status === "done" || job.status === "archived";
  const hasRendering = (counts.rendering || 0) > 0;
  const hasQueued = (counts.queued || 0) > 0 || (counts.failed || 0) > 0;
  const canCancel = !isDone && job.status !== "cancelled" && (hasRendering || hasQueued || job.status === "paused" || job.status === "draining");
  const actions = [
    `<button data-dashboard-action="move_job" data-direction="up" data-job="${esc(job.id)}">Up</button>`,
    `<button data-dashboard-action="move_job" data-direction="down" data-job="${esc(job.id)}">Down</button>`,
    `<button data-dashboard-action="open_output" data-job="${esc(job.id)}">Open Render Folder</button>`,
    `<button data-dashboard-action="repair_job" data-job="${esc(job.id)}">Repair</button>`,
  ];
  if (job.status === "paused") actions.push(`<button data-dashboard-action="resume" data-job="${esc(job.id)}">Resume</button>`);
  else if (!isDone && job.status !== "cancelled") actions.push(`<button data-dashboard-action="pause" data-job="${esc(job.id)}">Pause</button>`);
  if ((counts.failed || 0) > 0 || job.status === "cancelled") {
    actions.push(`<button data-dashboard-action="requeue" data-job="${esc(job.id)}">Retry Failed</button>`);
    if ((counts.failed || 0) > 0) actions.push(`<button data-dashboard-action="mark_failed_done" data-job="${esc(job.id)}">Mark Failed Done</button>`);
  }
  if (canCancel) actions.push(`<button data-dashboard-action="cancel" data-job="${esc(job.id)}">Cancel</button>`);
  if (job.status !== "archived") actions.push(`<button data-dashboard-action="delete" data-job="${esc(job.id)}">Delete</button>`);
  return `<article class="dashboard-job ${collapsed ? "collapsed" : ""} ${pending ? "is-syncing" : ""}" style="--status-color:${color}" data-job-id="${esc(job.id)}">
    ${pending ? `<div class="dashboard-sync-label">${esc(pending.label)}</div>` : ""}
    <div class="dashboard-job-main" data-dashboard-toggle="${esc(job.id)}">
      <div>
        <div class="dashboard-job-title">
          <button class="dashboard-job-drag drag-handle" type="button" title="Move job priority" aria-label="Move job priority"></button>
          <span class="dashboard-status ${statusClass}">${esc(statusLabel)}</span>
          <strong>${esc(job.name)}</strong>
        </div>
        <div class="dashboard-meta">${Number(job.progress || 0).toFixed(1)}% &middot; ${esc(job.status || "queued")} &middot; ${esc(statusText(counts))}</div>
        <div class="dashboard-progress"><div style="width:${Number(job.progress || 0).toFixed(1)}%"></div></div>
      </div>
      <div class="dashboard-job-actions">${actions.join("")}</div>
    </div>
    <div class="dashboard-job-body">
      ${renderDashboardMetrics(job)}
      <div class="dashboard-job-paths">
        <div>${esc(job.scene || "")}</div>
        <div>${esc(job.display_output || job.output || "")}</div>
      </div>
      ${renderDashboardJobInfo(job)}
      ${renderFailureSummary(job)}
      ${renderDashboardFrames(job)}
    </div>
  </article>`;
}

function renderDashboardJobInfo(job) {
  const metadata = job.metadata || {};
  const items = [
    ["Submitted", metadata.source_scene_saved_at || job.created_at || "--"],
    ["Source scene", metadata.source_scene || job.source_scene || "--"],
    ["Renderer", metadata.render_engine || "--"],
    ["Preflight", metadata.preflight_summary || "--"],
  ];
  if (metadata.take_name) items.push(["Take", metadata.take_name]);
  return `<div class="dashboard-job-info">${items.map(([label, value]) => `
    <div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>
  `).join("")}</div>`;
}

function renderFailureSummary(job) {
  const summary = job.failure_summary || {};
  if (!summary.failed) return "";
  const counts = job.counts || {};
  const stillActive = (counts.rendering || 0) > 0 || (counts.queued || 0) > 0;
  const reasons = summary.reasons || [];
  return `<div class="dashboard-failure ${stillActive ? "incident" : ""}">
    <strong>${esc(summary.failed)} failed frame(s)${stillActive ? " while job continues" : ""}</strong>
    ${reasons.map(item => `<span>${esc(item.count)}x ${esc(item.reason)}</span>`).join("")}
    ${summary.first_frame ? `<span>First failed frame: ${esc(summary.first_frame)}</span>` : ""}
    ${summary.first_log ? `<span>Log: ${esc(summary.first_log)}</span>` : ""}
  </div>`;
}

function renderDashboardMetrics(job) {
  const stats = job.stats || {};
  const items = [
    ["Elapsed", stats.elapsed || "--"],
    ["ETA", stats.eta || "--"],
    ["Avg Frame", stats.avg || "--"],
  ];
  return `<div class="dashboard-metrics">${items.map(([label, value]) => `
    <div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>
  `).join("")}</div>`;
}

function renderDashboardFrames(job) {
  const frames = job.frames || [];
  if (!frames.length) return "";
  return `<div class="dashboard-frames">${frames.map(frame => {
    const worker = frame.worker_id ? ` style="--frame-color:${workerColor(frame.worker_id)}"` : "";
    return `<span class="${esc(frame.status || "queued")} ${frame.worker_id ? "worker-owned" : ""}"${worker}>${esc(frame.frame)}</span>`;
  }).join("")}</div>`;
}

function dashboardJobIds(list) {
  return [...list.querySelectorAll(".dashboard-job")].map(job => job.dataset.jobId);
}

function dashboardJobFromPoint(x, y) {
  const hidden = state.dashboardDrag?.job;
  if (hidden) hidden.style.pointerEvents = "none";
  const target = document.elementFromPoint(x, y)?.closest(".dashboard-job");
  if (hidden) hidden.style.pointerEvents = "";
  return target;
}

function clearDashboardDropTarget() {
  document.querySelectorAll(".dashboard-job.drop-target").forEach(job => job.classList.remove("drop-target"));
}

function swapDashboardJobs(first, second) {
  const marker = document.createElement("div");
  const parent = first.parentNode;
  parent.insertBefore(marker, first);
  second.parentNode.insertBefore(first, second);
  parent.insertBefore(second, marker);
  marker.remove();
}

async function saveDashboardOrder(list) {
  list.classList.add("is-syncing");
  showAppFeedback("working", dashboardActionLabel("reorder"));
  try {
    await post("/api/action", { action: "reorder", job_ids: dashboardJobIds(list) }, 20000);
    await refresh();
    showAppFeedback("ok", "Priority order saved.");
  } finally {
    list.classList.remove("is-syncing");
  }
}

function renderHealth(items) {
  $("#health").innerHTML = items.map(item => `
    <div class="health-item">
      <span class="health-dot ${esc(item.tone || (item.ok ? "ok" : "error"))}"></span>
      <span class="health-label">${esc(item.label)}</span>
      <span class="health-detail">${esc(item.detail)}</span>
    </div>
  `).join("");
}

function renderQueue(queue) {
  const jobs = (queue.jobs || []).filter(job => !state.optimisticHiddenJobs.has(job.id));
  const workers = queue.workers || [];
  const activeWorkers = workers.filter(worker => worker.state === "online").length;
  const current = jobs[0];
  if (!jobs.length) {
    $("#queue-summary").innerHTML = `
      <div><strong>${activeWorkers}</strong> worker(s) online</div>
      <div>No queued jobs.</div>
      <div>Submit from Cinema 4D with Extensions &gt; DreamRender Submit Render.</div>
      <div>Code ${esc(queue.code_signature || "")}</div>
    `;
    return;
  }
  const stats = current.stats || {};
  $("#queue-summary").innerHTML = `
    <div><strong>${activeWorkers}</strong> worker(s) online</div>
    <div><strong>${esc(current.name)}</strong></div>
    <div>${Number(current.progress || 0).toFixed(1)}% complete</div>
    <div>Average ${esc(stats.avg || "--")} - ETA ${esc(stats.eta || "--")}</div>
  `;
}

function renderGpus(gpus, message) {
  if (!gpus.length) {
    $("#gpus").innerHTML = `<p>${esc(message || "No GPU data available.")}</p>`;
    return;
  }
  $("#gpus").innerHTML = gpus.map(gpu => `
    <article class="gpu">
      <div class="gpu-head">
        <span>GPU ${esc(gpu.index)} - ${esc(gpu.name)}</span>
        <span>${esc(gpu.util)}% load - ${esc(gpu.memory_used)}/${esc(gpu.memory_total)} MB VRAM</span>
      </div>
      <div class="gpu-track"><div class="gpu-fill" style="width:${Math.max(1, Number(gpu.util || 0))}%"></div></div>
    </article>
  `).join("");
}

function readConfigForm() {
  const existing = state.data?.config || {};
  const textValue = (selector, key) => {
    const value = $(selector).value.trim();
    return value || existing[key] || "";
  };
  return {
    share: textValue("#share", "share"),
    c4d: textValue("#c4d", "c4d"),
    worker_id: textValue("#worker-id", "worker_id"),
    chunk_size: Number($("#chunk-size").value || 5),
    monitor_port: Number($("#monitor-port").value || 8766),
    keep_worker_running: $("#keep-worker").checked,
  };
}

async function saveConfig() {
  if (!state.initialized || !state.data?.config) {
    showAppFeedback("working", "DreamRender is still loading setup.");
    return;
  }
  await post("/api/config", readConfigForm());
  await refresh();
}

document.addEventListener("click", async event => {
  const tab = event.target.closest(".tab");
  if (tab) {
    selectTab(tab.dataset.tab);
  }
});

document.addEventListener("pointerdown", event => {
  const handle = event.target.closest(".drag-handle");
  if (!handle) return;
  const card = handle.closest(".bento-card");
  if (!card) return;
  event.preventDefault();
  handle.setPointerCapture(event.pointerId);
  state.drag = {
    card,
    handle,
    grid: card.parentElement,
    startX: event.clientX,
    startY: event.clientY,
    active: false,
  };
});

document.addEventListener("pointermove", event => {
  const drag = state.drag;
  if (!drag) return;
  const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
  if (!drag.active && distance > 4) {
    drag.active = true;
    drag.card.classList.add("dragging");
    document.body.classList.add("is-dragging-widget");
  }
  if (!drag.active) return;
  clearDropTarget();
  const target = cardFromPoint(event.clientX, event.clientY);
  if (target && target !== drag.card && target.parentElement === drag.grid) {
    target.classList.add("drop-target");
  }
});

document.addEventListener("pointerup", event => {
  const drag = state.drag;
  if (!drag) return;
  const target = cardFromPoint(event.clientX, event.clientY);
  if (drag.active && target && target !== drag.card && target.parentElement === drag.grid) {
    swapCards(drag.card, target);
  }
  drag.card.classList.remove("dragging");
  document.body.classList.remove("is-dragging-widget");
  clearDropTarget();
  state.drag = null;
});

document.addEventListener("pointercancel", () => {
  if (state.drag?.card) state.drag.card.classList.remove("dragging");
  document.body.classList.remove("is-dragging-widget");
  clearDropTarget();
  state.drag = null;
});

$("#toggle").addEventListener("click", async () => {
  if (!state.initialized || !state.data?.config) {
    showAppFeedback("working", "DreamRender is still loading setup.");
    return;
  }
  const action = state.data?.worker_running ? "stop" : "start";
  setToggleBusy(action);
  try {
    await saveConfig();
    const result = await post("/api/action", { action }, action === "start" ? 20000 : 12000);
    if (result.state) {
      state.data = result.state;
      state.initialized = true;
      render(result.state);
    } else {
      try {
        await refresh();
      } catch (error) {
        showAppFeedback("working", error.message);
      }
    }
    clearToggleBusy(action === "start" ? "DreamRender is running." : "DreamRender stopped.");
  } catch (error) {
    state.toggleBusy = null;
    showAppFeedback("error", error.message || "DreamRender could not change state.");
    render(state.data || {});
  }
});
$("#native-dashboard").addEventListener("click", async event => {
  const button = event.target.closest("[data-dashboard-action]");
  if (!button) {
    const toggle = event.target.closest("[data-dashboard-toggle]");
    if (toggle && !event.target.closest(".dashboard-job-drag")) {
      const jobId = toggle.dataset.dashboardToggle;
      if (expandedJobs.has(jobId)) expandedJobs.delete(jobId);
      else expandedJobs.add(jobId);
      saveExpandedJobs();
      renderDashboard(state.data?.queue || {}, state.data || {});
    }
    return;
  }
  button.disabled = true;
  button.classList.add("is-loading");
  const action = button.dataset.dashboardAction;
  const workerId = button.dataset.worker || "";
  const jobId = button.dataset.job || "";
  const usesPending = action !== "open_output";
  if (usesPending) setDashboardPending({ action, jobId, workerId });
  if (action === "worker_toggle_stop") {
    const nextState = button.getAttribute("aria-pressed") !== "true";
    button.classList.toggle("active", nextState);
    button.setAttribute("aria-pressed", nextState ? "true" : "false");
    showAppFeedback("working", nextState ? `${workerId} will stop after the current batch.` : `${workerId} will keep rendering new batches.`);
  }
  try {
    const result = await post("/api/action", {
      action,
      job_id: jobId,
      worker_id: workerId,
      direction: button.dataset.direction || "",
    }, action === "repair" || action === "repair_job" ? 30000 : 20000);
    if (result.state) {
      state.data = result.state;
      state.initialized = true;
      render(result.state);
    } else {
      await refresh();
    }
    if (usesPending) {
      clearDashboardPending({ jobId, workerId });
      if (action === "delete" && jobId) state.optimisticHiddenJobs.delete(jobId);
      showAppFeedback("ok", action === "delete" ? "Job deleted." : "Dashboard synced.");
      renderDashboard(state.data?.queue || {}, state.data || {});
    }
  } catch (error) {
    if (usesPending) {
      clearDashboardPending({ jobId, workerId, restoreHidden: true });
      renderDashboard(state.data?.queue || {}, state.data || {});
    }
    showAppFeedback("error", error.message || "Dashboard action failed.");
  } finally {
    button.disabled = false;
    button.classList.remove("is-loading");
  }
});

$("#native-dashboard").addEventListener("pointerdown", event => {
  const handle = event.target.closest(".dashboard-job-drag");
  if (!handle) return;
  const job = handle.closest(".dashboard-job");
  const list = handle.closest(".dashboard-job-list");
  if (!job || !list) return;
  event.preventDefault();
  event.stopPropagation();
  try { handle.setPointerCapture(event.pointerId); } catch {}
  state.dashboardDrag = {
    job,
    handle,
    list,
    startX: event.clientX,
    startY: event.clientY,
    active: false,
  };
});

document.addEventListener("pointermove", event => {
  const drag = state.dashboardDrag;
  if (!drag) return;
  const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
  if (!drag.active && distance > 4) {
    drag.active = true;
    drag.job.classList.add("dragging");
    drag.list.classList.add("is-reordering");
    document.body.classList.add("is-dragging-dashboard");
  }
  if (!drag.active) return;
  clearDashboardDropTarget();
  const target = dashboardJobFromPoint(event.clientX, event.clientY);
  if (target && target !== drag.job && target.parentElement === drag.list) {
    target.classList.add("drop-target");
  }
});

document.addEventListener("pointerup", async event => {
  const drag = state.dashboardDrag;
  if (!drag) return;
  const target = dashboardJobFromPoint(event.clientX, event.clientY);
  if (drag.active && target && target !== drag.job && target.parentElement === drag.list) {
    swapDashboardJobs(drag.job, target);
  }
  drag.job.classList.remove("dragging");
  drag.list.classList.remove("is-reordering");
  document.body.classList.remove("is-dragging-dashboard");
  clearDashboardDropTarget();
  const changed = drag.active;
  const list = drag.list;
  state.dashboardDrag = null;
  if (!changed) return;
  try {
    await saveDashboardOrder(list);
  } catch (error) {
    showAppFeedback("error", error.message || "Could not reorder jobs.");
  }
});

document.addEventListener("pointercancel", () => {
  if (!state.dashboardDrag) return;
  state.dashboardDrag.job.classList.remove("dragging");
  state.dashboardDrag.list.classList.remove("is-reordering");
  document.body.classList.remove("is-dragging-dashboard");
  clearDashboardDropTarget();
  state.dashboardDrag = null;
});
$("#save-config").addEventListener("click", saveConfig);
$("#repair").addEventListener("click", async () => {
  await post("/api/action", { action: "repair" });
  await refresh();
});
$("#open-queue").addEventListener("click", () => post("/api/action", { action: "open_queue" }));
$("#install-plugin").addEventListener("click", async () => {
  const button = $("#install-plugin");
  button.disabled = true;
  button.textContent = "Installing...";
  showInlineMessage("#plugin-result", "working", "Installing Cinema 4D plugin", "DreamRender is copying the submitter into your Cinema 4D preferences.");
  try {
    const result = await post("/api/action", { action: "install_plugin" });
    showInlineMessage("#plugin-result", "ok", "Cinema 4D plugin installed", result.message || "Restart Cinema 4D and open Extensions > DreamRender Submit Render.");
  } catch (error) {
    showInlineMessage("#plugin-result", "error", "Plugin install failed", error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Install C4D Plugin";
  }
  await refresh();
});
$("#copy-log").addEventListener("click", async () => {
  await navigator.clipboard.writeText($("#log").value);
});

applySavedLayout();
safeRefresh();
setInterval(safeRefresh, 1500);
