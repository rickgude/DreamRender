const state = {
  data: null,
  drag: null,
  toggleBusy: null,
  dashboardLoadedUrl: "",
};
const layoutKey = "dreamrender.app.bentoLayout.v3";

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
}[char]));

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

function clearAppFeedbackLater() {
  window.clearTimeout(state.feedbackTimer);
  state.feedbackTimer = window.setTimeout(() => {
    if (!state.toggleBusy) $("#operation-result").hidden = true;
  }, 4500);
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
    clearAppFeedbackLater();
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
  $("#dashboard").disabled = Boolean(busy) || !data.worker_running;
  $("#dashboard").title = data.worker_running ? "Show the DreamRender dashboard" : "Start DreamRender before opening the dashboard";
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
  renderDashboard(data);
  $("#log").value = (data.worker_log || []).join("\n");
}

function renderDashboard(data) {
  const frame = $("#dashboard-frame");
  const loading = $("#dashboard-loading");
  if (!data.worker_running || !data.monitor_running) {
    state.dashboardLoadedUrl = "";
    frame.removeAttribute("src");
    loading.hidden = false;
    loading.querySelector("strong").textContent = data.worker_running ? "Dashboard starting..." : "Dashboard paused";
    loading.querySelector("span").textContent = data.worker_running ? "The monitor is starting. This will only take a moment." : "Start DreamRender to view render jobs here.";
    return;
  }
  const url = data.monitor_url || "";
  if (url && state.dashboardLoadedUrl !== url) {
    state.dashboardLoadedUrl = url;
    loading.hidden = false;
    frame.src = url;
  }
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
$("#dashboard").addEventListener("click", () => selectTab("dashboard-panel"));
$("#dashboard-frame").addEventListener("load", () => {
  if (state.data?.worker_running && state.data?.monitor_running) $("#dashboard-loading").hidden = true;
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
