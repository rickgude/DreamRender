const state = {
  data: null,
  drag: null,
  dashboardDrag: null,
  toggleBusy: null,
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

async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.message || response.statusText);
  return data;
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
  const data = await fetch("/api/state").then(response => response.json());
  state.data = data;
  render(data);
}

function render(data) {
  const config = data.config || {};
  const busy = state.toggleBusy;
  $("#toggle").textContent = busy ? (busy === "start" ? "Starting..." : "Stopping...") : (data.worker_running ? "Stop DreamRender" : "Start DreamRender");
  $("#toggle").classList.toggle("stop", Boolean(data.worker_running));
  $("#toggle").classList.toggle("is-loading", Boolean(busy));
  $("#toggle").disabled = Boolean(busy);
  $("#dashboard-tab").disabled = Boolean(busy) || !data.worker_running;
  $("#dashboard-tab").title = data.worker_running ? "Show the DreamRender dashboard" : "Start DreamRender before opening the dashboard";
  if (!data.worker_running && $("#dashboard-panel").classList.contains("active")) selectTab("setup");
  $("#worker-state").textContent = busy === "start" ? "Starting..." : busy === "stop" ? "Stopping..." : data.worker_running ? `Running as ${config.worker_id}` : "Stopped";
  $("#monitor-state").textContent = busy === "start" ? "Starting..." : busy === "stop" ? "Stopping..." : data.monitor_running ? `Running on port ${config.monitor_port}` : "Stopped";
  $("#app-status").textContent = busy === "start" ? "Starting worker and monitor" : busy === "stop" ? "Stopping services" : data.status || "Ready";
  document.querySelectorAll('[data-widget="worker"], [data-widget="monitor"], [data-widget="status"]').forEach(card => {
    card.classList.toggle("is-working", Boolean(busy));
  });

  $("#share").value = config.share || "";
  $("#c4d").value = config.c4d || "";
  $("#worker-id").value = config.worker_id || "";
  $("#chunk-size").value = config.chunk_size || 5;
  $("#monitor-port").value = config.monitor_port || 8766;
  $("#keep-worker").checked = Boolean(config.keep_worker_running);

  renderHealth(data.health || []);
  renderQueue(data.queue || {});
  renderGpus(data.gpus || [], data.gpu_message);
  renderDashboard(data.queue || {}, data);
  $("#log").value = (data.worker_log || []).join("\n");
}

function jobState(job) {
  const counts = job.counts || {};
  if ((counts.failed || 0) > 0 || job.status === "cancelled") return ["failed", "Error"];
  if (job.status === "done" || job.status === "archived") return ["done", "Done"];
  if ((counts.rendering || 0) > 0) return ["rendering", "Rendering"];
  if (job.status === "paused") return ["queued", "Paused"];
  if (job.status === "draining") return ["rendering", "Draining"];
  return ["queued", "Queued"];
}

function workerLabel(worker) {
  const code = worker.code_current ? `code ${worker.code_signature || ""}` : "restart needed";
  const active = worker.active || null;
  if (active) {
    const frameText = active.start_frame != null && active.end_frame != null ? `frames ${active.start_frame}-${active.end_frame}` : `frame ${active.frame}`;
    return `job ${active.job_id}, ${frameText} - ${code}`;
  }
  if (worker.state === "online") return `idle - ${code}`;
  if (worker.state === "heartbeat_lost") return `heartbeat lost - ${code}`;
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

function renderDashboard(queue, appData) {
  if (state.dashboardDrag) return;
  const workers = queue.workers || [];
  const jobs = queue.jobs || [];
  const oldWorkers = workers.filter(worker => !worker.code_current);
  const repair = queue.repair || {};
  $("#dashboard-health").textContent = appData.worker_running
    ? `${repair.changed ? `Auto-repair updated ${repair.changed} frame(s).` : "Auto-repair: queue clean."}  Code: ${queue.code_signature || "--"}${oldWorkers.length ? ` - ${oldWorkers.length} worker(s) need restart.` : ""}`
    : "Start DreamRender to view live workers and jobs.";
  $("#dashboard-workers").innerHTML = workers.length ? workers.map(worker => {
    const color = workerColor(worker.worker_id);
    const stateClass = worker.state === "heartbeat_lost" ? "lost" : worker.state !== "online" ? "offline" : "";
    return `<article class="dashboard-worker ${stateClass}" style="--worker-color:${color}">
      <span class="dashboard-worker-dot"></span>
      <div>
        <strong>${esc(worker.worker_id)}</strong>
        <div class="muted">${esc(workerLabel(worker))}</div>
        <div class="dashboard-worker-actions">
          <button data-dashboard-action="worker_restart" data-worker="${esc(worker.worker_id)}">${worker.code_current ? "Restart" : "Restart (needed)"}</button>
          <button data-dashboard-action="worker_stop" data-worker="${esc(worker.worker_id)}">Stop After Batch</button>
          <button data-dashboard-action="worker_stop_now" data-worker="${esc(worker.worker_id)}">Stop</button>
        </div>
      </div>
    </article>`;
  }).join("") : `<div class="dashboard-empty"><strong>No workers yet</strong><span>Start DreamRender on a render node.</span></div>`;
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
  const color = statusColors[statusClass] || statusColors.queued;
  const counts = job.counts || {};
  const isDone = job.status === "done" || job.status === "archived";
  const hasRendering = (counts.rendering || 0) > 0;
  const hasQueued = (counts.queued || 0) > 0 || (counts.failed || 0) > 0;
  const canCancel = !isDone && job.status !== "cancelled" && (hasRendering || hasQueued || job.status === "paused" || job.status === "draining");
  const actions = [
    `<button data-dashboard-action="open_output" data-job="${esc(job.id)}">Open Render Folder</button>`,
    `<button data-dashboard-action="repair_job" data-job="${esc(job.id)}">Repair</button>`,
  ];
  if (job.status === "paused") actions.push(`<button data-dashboard-action="resume" data-job="${esc(job.id)}">Resume</button>`);
  else if (!isDone && job.status !== "cancelled") actions.push(`<button data-dashboard-action="pause" data-job="${esc(job.id)}">Pause</button>`);
  if (hasRendering) actions.push(`<button data-dashboard-action="drain" data-job="${esc(job.id)}">Stop After Batch</button>`);
  if ((counts.failed || 0) > 0 || job.status === "cancelled") actions.push(`<button data-dashboard-action="requeue" data-job="${esc(job.id)}">Requeue Failed</button>`);
  if (canCancel) actions.push(`<button data-dashboard-action="cancel" data-job="${esc(job.id)}">Cancel</button>`);
  if (job.status !== "archived") actions.push(`<button data-dashboard-action="delete" data-job="${esc(job.id)}">Delete</button>`);
  return `<article class="dashboard-job ${collapsed ? "collapsed" : ""}" style="--status-color:${color}" data-job-id="${esc(job.id)}">
    <div class="dashboard-job-main" data-dashboard-toggle="${esc(job.id)}">
      <div>
        <div class="dashboard-job-title">
          <button class="dashboard-job-drag" title="Move job priority" aria-label="Move job priority"></button>
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
      ${renderDashboardFrames(job)}
    </div>
  </article>`;
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

function renderHealth(items) {
  $("#health").innerHTML = items.map(item => `
    <div class="health-item">
      <span class="health-dot ${item.ok ? "ok" : ""}"></span>
      <span class="health-label">${esc(item.label)}</span>
      <span class="health-detail">${esc(item.detail)}</span>
    </div>
  `).join("");
}

function renderQueue(queue) {
  const jobs = queue.jobs || [];
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
  return {
    share: $("#share").value,
    c4d: $("#c4d").value,
    worker_id: $("#worker-id").value,
    chunk_size: Number($("#chunk-size").value || 5),
    monitor_port: Number($("#monitor-port").value || 8766),
    keep_worker_running: $("#keep-worker").checked,
  };
}

async function saveConfig() {
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
  const action = state.data?.worker_running ? "stop" : "start";
  setToggleBusy(action);
  try {
    await saveConfig();
    await post("/api/action", { action });
    await refresh();
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
  try {
    await post("/api/action", {
      action: button.dataset.dashboardAction,
      job_id: button.dataset.job || "",
      worker_id: button.dataset.worker || "",
    });
    await refresh();
  } catch (error) {
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
  handle.setPointerCapture(event.pointerId);
  state.dashboardDrag = {
    job,
    list,
    startY: event.clientY,
    active: false,
  };
});

document.addEventListener("pointermove", event => {
  const drag = state.dashboardDrag;
  if (!drag) return;
  if (!drag.active && Math.abs(event.clientY - drag.startY) > 4) {
    drag.active = true;
    drag.job.classList.add("dragging");
    drag.list.classList.add("is-reordering");
  }
  if (!drag.active) return;
  drag.job.style.pointerEvents = "none";
  const target = document.elementFromPoint(event.clientX, event.clientY)?.closest(".dashboard-job");
  drag.job.style.pointerEvents = "";
  if (!target || target === drag.job || target.parentElement !== drag.list) return;
  const rect = target.getBoundingClientRect();
  drag.list.insertBefore(drag.job, event.clientY < rect.top + rect.height / 2 ? target : target.nextSibling);
});

document.addEventListener("pointerup", async () => {
  const drag = state.dashboardDrag;
  if (!drag) return;
  drag.job.classList.remove("dragging");
  drag.list.classList.remove("is-reordering");
  const jobIds = [...drag.list.querySelectorAll(".dashboard-job")].map(job => job.dataset.jobId);
  const changed = drag.active;
  state.dashboardDrag = null;
  if (!changed) return;
  try {
    await post("/api/action", { action: "reorder", job_ids: jobIds });
    await refresh();
  } catch (error) {
    showAppFeedback("error", error.message || "Could not reorder jobs.");
  }
});

document.addEventListener("pointercancel", () => {
  if (!state.dashboardDrag) return;
  state.dashboardDrag.job.classList.remove("dragging");
  state.dashboardDrag.list.classList.remove("is-reordering");
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
refresh();
setInterval(refresh, 2500);
