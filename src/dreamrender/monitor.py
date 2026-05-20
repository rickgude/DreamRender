from __future__ import annotations

import json
import mimetypes
import os
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .queue import Share, find_frame_preview, get_job_detail, queue_snapshot, read_frame_log, requeue_failed, requeue_frames, set_job_priorities, set_job_status


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DreamRender Monitor</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #e9e9e7;
      --shell: #f4f8f7;
      --panel: #fbfcfa;
      --panel-2: #f1f4f1;
      --ink: #0e0e0d;
      --text: #151515;
      --muted: #737a7c;
      --line: #dfe4e1;
      --line-strong: #ccd4d0;
      --accent: #ff5538;
      --accent-2: #ffd43d;
      --good: #58c981;
      --rendering: #ff8b3d;
      --info: #8b63f6;
      --bad: #ec6c79;
      --shadow: 0 18px 50px rgba(18, 22, 22, .10);
      --soft-shadow: 0 8px 24px rgba(18, 22, 22, .07);
      font-family: Inter, "Segoe UI", system-ui, sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; min-height: 100vh; background:
        linear-gradient(90deg, rgba(0,0,0,.10) 1px, transparent 1px) 0 0 / 50% 100%,
        linear-gradient(180deg, rgba(0,0,0,.08) 1px, transparent 1px) 0 0 / 100% 50%,
        var(--bg);
      color: var(--text); padding: 24px;
    }
    header {
      display: flex; align-items: center; justify-content: space-between;
      max-width: 1800px; margin: 0 auto; padding: 18px 22px 12px;
      border: 1px solid var(--line); border-bottom: 0; background: var(--shell);
      border-radius: 28px 28px 0 0;
    }
    h1 { margin: 0; font-size: 22px; font-weight: 850; letter-spacing: 0; text-transform: uppercase; }
    .subtle { color: var(--muted); font-size: 13px; }
    main {
      display: grid; grid-template-columns: 260px 1fr; min-height: calc(100vh - 115px);
      max-width: 1800px; margin: 0 auto; border: 1px solid var(--line); background: var(--shell);
      border-radius: 0 0 28px 28px; box-shadow: var(--shadow); overflow: hidden;
    }
    aside { border-right: 1px solid var(--line); padding: 22px 20px; background: #eef4f2; }
    section { padding: 24px 28px; background: var(--shell); }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
    .section-head h2 { margin: 0; }
    h2 { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; margin: 0 0 12px; font-weight: 800; }
    .status-legend { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
    .legend-item {
      display: inline-flex; align-items: center; gap: 7px; min-height: 30px;
      padding: 5px 10px; border: 1px solid var(--line); border-radius: 999px;
      background: #fbfcfa; color: #555e5d; font-size: 12px; font-weight: 750;
      box-shadow: 0 2px 7px rgba(18,22,22,.04);
    }
    .legend-swatch { width: 18px; height: 18px; border-radius: 999px; border: 1px solid transparent; }
    .legend-swatch.done { background: rgba(88, 201, 129, .92); border-color: rgba(88, 201, 129, .98); }
    .legend-swatch.rendering { background: rgba(255, 139, 61, .92); border-color: rgba(255, 116, 48, .98); }
    .legend-swatch.failed { background: rgba(236, 108, 121, .92); border-color: rgba(236, 108, 121, .98); }
    .legend-swatch.queued { background: #e8ede9; border-color: #d9e0dc; }
    .worker {
      display: flex; gap: 12px; align-items: center; padding: 14px 12px; margin-bottom: 10px;
      border: 0; background: var(--worker-color, var(--panel)); border-radius: 20px; box-shadow: var(--soft-shadow);
      color: var(--ink);
    }
    .worker > div:first-of-type { font-weight: 800; }
    .worker .subtle, .worker-card .subtle { color: rgba(14,14,13,.72); font-weight: 650; }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--bad); flex: 0 0 auto; }
    .dot.online { background: rgba(255,255,255,.95); box-shadow: inset 0 0 0 2px rgba(0,0,0,.12); }
    .dot.heartbeat-lost { background: var(--rendering); box-shadow: inset 0 0 0 2px rgba(0,0,0,.12); }
    .jobs { display: grid; gap: 18px; }
    .job-group {
      background: #eef5f2; border: 1px solid #d8e4df; border-radius: 26px;
      padding: 24px; box-shadow: var(--soft-shadow);
    }
    .group-head { display: flex; align-items: start; justify-content: space-between; gap: 18px; margin: 0 0 18px; }
    .group-title { font-size: 25px; font-weight: 900; letter-spacing: 0; text-transform: uppercase; }
    .group-jobs { display: grid; gap: 14px; }
    .job {
      background: #ffffff; border: 1px solid #dbe5e1; border-radius: 24px; overflow: hidden;
      box-shadow: 0 8px 22px rgba(18, 22, 22, .045);
    }
    .job-group .job { background: #ffffff; }
    .job-head { display: grid; grid-template-columns: 1fr auto; gap: 22px; padding: 24px 26px 22px; cursor: pointer; }
    .job-body { display: block; }
    .job.collapsed .job-body { display: none; }
    .job.collapsed .job-detail-lines { display: none; }
    .job.collapsed .job-head { padding-bottom: 24px; }
    .job.collapsed { background: #ffffff; }
    .job-title-row { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
    .job-title { font-size: 23px; font-weight: 900; margin-bottom: 5px; letter-spacing: 0; }
    .job-title-row .job-title { margin-bottom: 0; }
    .job-status {
      display: inline-flex; align-items: center; min-height: 28px; padding: 4px 11px;
      border: 1px solid var(--line); border-radius: 999px; background: #e8ede9;
      color: #555e5d; font-size: 12px; font-weight: 850;
    }
    .job-status.done { background: var(--good); border-color: var(--good); color: white; }
    .job-status.rendering { background: var(--rendering); border-color: var(--rendering); color: white; }
    .job-status.failed { background: var(--bad); border-color: var(--bad); color: white; }
    .job-status.queued { background: #e8ede9; border-color: #d9e0dc; color: #555e5d; }
    .meta { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
    .job-head-main { display: grid; gap: 10px; }
    .job-detail-lines { display: grid; gap: 3px; }
    .actions { display: flex; align-items: start; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
    button {
      height: 38px; border: 1px solid var(--line); border-radius: 999px;
      background: #f8faf8; color: var(--ink); padding: 0 16px;
      cursor: pointer; font-weight: 750; box-shadow: 0 2px 7px rgba(18,22,22,.05);
    }
    button:hover { border-color: var(--ink); transform: translateY(-1px); }
    .actions button:first-child, .group-head .actions button:first-child { background: var(--ink); color: white; border-color: var(--ink); }
    .job-progress {
      width: min(740px, 48vw); max-width: 100%; height: 13px; margin-top: 6px;
      background: #e7eee9; border-radius: 999px; overflow: hidden;
    }
    .bar { height: 100%; background: var(--job-color, var(--accent)); width: 0%; transition: width .25s ease; border-radius: 999px; }
    .stats { display: flex; flex-wrap: wrap; gap: 10px; padding: 15px 26px; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; }
    .stats span {
      background: #eef3ef; color: #555e5d; border: 1px solid var(--line);
      border-radius: 999px; padding: 5px 10px; font-weight: 700;
    }
    .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; padding: 0 26px 18px; }
    .metric { background: #f7faf8; border: 1px solid var(--line); border-radius: 18px; padding: 13px 14px; min-height: 76px; }
    .metric-label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }
    .metric-value { font-size: 24px; font-weight: 900; margin-top: 4px; color: var(--ink); letter-spacing: 0; }
    .worker-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; padding: 0 26px 18px; }
    .worker-card {
      background: var(--worker-color);
      border: 0; border-radius: 18px; padding: 15px 16px; color: var(--ink);
    }
    .worker-card strong { display: block; margin-bottom: 4px; }
    .frames-label {
      padding: 0 26px 8px; color: var(--muted); font-size: 11px;
      font-weight: 800; letter-spacing: .06em; text-transform: uppercase;
    }
    .frames { display: grid; grid-template-columns: repeat(auto-fill, minmax(35px, 1fr)); gap: 6px; padding: 0 26px 24px; }
    .frame {
      height: 25px; border-radius: 10px; background: #e8ede9; color: #596161;
      font-size: 11px; font-weight: 750; display: grid; place-items: center; border: 1px solid transparent;
    }
    .frame.done { background: rgba(88, 201, 129, .20); border-color: rgba(88, 201, 129, .55); color: #19653b; }
    .frame.rendering { background: rgba(255, 139, 61, .30); border-color: rgba(255, 116, 48, .78); color: #8a3e12; }
    .frame.failed { background: rgba(236, 108, 121, .20); border-color: rgba(236, 108, 121, .65); color: #96323d; }
    .frame.queued { background: #e8ede9; }
    .frame.worker-owned {
      background: color-mix(in srgb, var(--worker-color) 28%, white);
      border-color: transparent;
      color: var(--ink);
    }
    .frame.rendering.worker-owned {
      background: var(--worker-color);
      border-color: transparent;
      box-shadow: none;
    }
    .empty { padding: 48px; text-align: center; color: var(--muted); border: 1px dashed var(--line-strong); border-radius: 24px; background: var(--panel); }
    dialog {
      width: min(980px, calc(100vw - 40px)); max-height: calc(100vh - 44px);
      background: var(--panel); color: var(--text); border: 1px solid var(--line);
      border-radius: 24px; padding: 0; box-shadow: 0 28px 90px rgba(18,22,22,.22);
    }
    dialog::backdrop { background: rgba(230,231,230,.72); backdrop-filter: blur(3px); }
    .modal-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 18px; border-bottom: 1px solid var(--line); }
    .modal-body { padding: 16px 18px; overflow: auto; max-height: calc(100vh - 145px); }
    .modal-grid { display: grid; grid-template-columns: 260px 1fr; gap: 16px; }
    .frame-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(44px, 1fr)); gap: 5px; align-content: start; }
    .log-pane {
      min-height: 360px; white-space: pre-wrap; overflow: auto; background: #111111;
      border: 1px solid #111111; border-radius: 18px; padding: 12px; color: #f6f2e8;
      font: 12px/1.45 Consolas, "Cascadia Mono", monospace;
    }
    .preview {
      display: block; width: 100%; max-height: 320px; object-fit: contain;
      background: #111111; border: 1px solid #111111; border-radius: 18px; margin-bottom: 10px;
    }
    .preview-note {
      background: #f7faf8; border: 1px solid var(--line); border-radius: 18px;
      padding: 14px; margin-bottom: 10px;
    }
    .preview-note strong { display: block; margin-bottom: 6px; color: var(--text); }
    .detail-actions { display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 12px; }
    @media (max-width: 820px) {
      body { padding: 10px; }
      main { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .job-head { grid-template-columns: 1fr; }
      header { align-items: flex-start; gap: 12px; }
      .section-head { align-items: flex-start; flex-direction: column; }
      .status-legend { justify-content: flex-start; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>DreamRender</h1>
      <div id="share" class="subtle"></div>
    </div>
    <div id="updated" class="subtle"></div>
  </header>
  <main>
    <aside>
      <h2>Workers</h2>
      <div id="workers"></div>
    </aside>
    <section>
      <div class="section-head">
        <h2>Jobs</h2>
        <div class="status-legend" aria-label="Frame status legend">
          <span class="legend-item"><span class="legend-swatch done"></span>Done</span>
          <span class="legend-item"><span class="legend-swatch rendering"></span>Rendering</span>
          <span class="legend-item"><span class="legend-swatch failed"></span>Error</span>
          <span class="legend-item"><span class="legend-swatch queued"></span>Queued</span>
        </div>
      </div>
      <div id="jobs" class="jobs job-drop-list"></div>
    </section>
  </main>
  <dialog id="detail">
    <div class="modal-head">
      <div>
        <strong id="detail-title">Job Details</strong>
        <div id="detail-meta" class="subtle"></div>
      </div>
      <button onclick="closeDetail()">Close</button>
    </div>
    <div class="modal-body">
      <div class="detail-actions">
        <button onclick="detailAction('pause')">Pause</button>
        <button onclick="detailAction('resume')">Resume</button>
        <button onclick="detailAction('drain')">Drain</button>
        <button onclick="detailAction('cancel')">Cancel</button>
        <button onclick="detailAction('archive')">Archive</button>
        <button onclick="detailAction('requeue')">Requeue Failed</button>
        <button onclick="requeueSelectedFrame()">Requeue Selected</button>
      </div>
      <div class="modal-grid">
        <div>
          <h2>Frames</h2>
          <div id="detail-frames" class="frame-list"></div>
        </div>
        <div>
          <h2>Preview</h2>
          <div id="detail-preview" class="subtle">Select a frame to view its output preview.</div>
          <h2>Log</h2>
          <pre id="detail-log" class="log-pane">Select a frame to view its log.</pre>
        </div>
      </div>
    </div>
  </dialog>
  <script>
    let selectedJobId = null;
    let selectedFrame = null;
    let currentJobOrder = [];
    const collapsedJobs = new Set(JSON.parse(localStorage.getItem("dreamrender.collapsedJobs") || "[]"));
    const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));
    const workerPalette = ["#ffd43d", "#58c981", "#8b63f6", "#ff5538", "#ffb13d", "#41d8a1", "#a16cff", "#ff7a59"];
    const statusColors = {
      done: "#58c981",
      rendering: "#ff8b3d",
      failed: "#ec6c79",
      queued: "#dfe7e2"
    };
    const statusText = counts => Object.entries(counts || {}).sort().map(([k,v]) => `${k}: ${v}`).join("  ");
    function hashWorker(value) {
      let hash = 0;
      for (const char of String(value || "")) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0;
      return Math.abs(hash);
    }
    function workerColor(workerId) {
      return workerPalette[hashWorker(workerId) % workerPalette.length];
    }
    function saveCollapsedJobs() {
      localStorage.setItem("dreamrender.collapsedJobs", JSON.stringify([...collapsedJobs]));
    }
    function toggleJob(jobId) {
      if (collapsedJobs.has(jobId)) collapsedJobs.delete(jobId);
      else collapsedJobs.add(jobId);
      saveCollapsedJobs();
      refresh();
    }
    async function action(kind, jobId) {
      const body = new URLSearchParams({ action: kind, job_id: jobId });
      await fetch("/api/action", { method: "POST", body });
      await refresh();
    }
    async function reorderJobs(jobIds) {
      const body = new URLSearchParams({ action: "reorder" });
      for (const jobId of jobIds) body.append("job_ids", jobId);
      await fetch("/api/action", { method: "POST", body });
      await refresh();
    }
    async function moveJob(jobId, direction) {
      const order = [...currentJobOrder];
      const index = order.indexOf(jobId);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= order.length) return;
      [order[index], order[target]] = [order[target], order[index]];
      await reorderJobs(order);
    }
    async function openRenderFolder(jobId) {
      const body = new URLSearchParams({ action: "open_output", job_id: jobId });
      await fetch("/api/action", { method: "POST", body });
    }
    async function detailAction(kind) {
      if (!selectedJobId) return;
      await action(kind, selectedJobId);
      await openDetail(selectedJobId, selectedFrame);
    }
    async function requeueSelectedFrame() {
      if (!selectedJobId || !selectedFrame) return;
      const body = new URLSearchParams({ action: "requeue_frames", job_id: selectedJobId, frames: selectedFrame });
      await fetch("/api/action", { method: "POST", body });
      await refresh();
      await openDetail(selectedJobId, selectedFrame);
    }
    function frameClass(status) {
      return `frame ${status || "queued"}`;
    }
    function frameStyle(frame) {
      return frame.worker_id ? `style="--worker-color:${workerColor(frame.worker_id)}"` : "";
    }
    function frameTitle(frame) {
      const worker = frame.worker_id ? `, worker ${frame.worker_id}` : "";
      const chunk = frame.chunk_start && frame.chunk_end ? `, chunk ${frame.chunk_start}-${frame.chunk_end}` : "";
      return `Frame ${frame.frame}: ${frame.status}${worker}${chunk}`;
    }
    function activeLabel(active) {
      if (!active) return "";
      if (active.start_frame && active.end_frame) return `job ${esc(active.job_id)}, frames ${esc(active.start_frame)}-${esc(active.end_frame)}`;
      return `job ${esc(active.job_id)}, frame ${esc(active.frame)}`;
    }
    function workerLabel(worker) {
      if (worker.active) {
        const suffix = ["archived", "draining"].includes(worker.active_job_status) ? " (finishing current batch)" : "";
        if (worker.state === "heartbeat_lost") return `heartbeat lost, ${activeLabel(worker.active)}`;
        return `${activeLabel(worker.active)}${suffix}`;
      }
      if (worker.state === "online") return "idle";
      if (worker.state === "heartbeat_lost") return "heartbeat lost while rendering";
      if (worker.last_seen_seconds == null) return "offline";
      return `offline, last seen ${formatSeconds(worker.last_seen_seconds)} ago`;
    }
    function jobStatusLabel(job) {
      if (job.visible_because_active && job.status === "archived") return "finishing current batch";
      if ((job.metadata || {}).archive_when_done && job.status === "draining") return "finishing current batch";
      return job.status;
    }
    function frameMetric(entry) {
      if (!entry) return "--";
      return `${entry.frame} (${formatSeconds(entry.seconds)})`;
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
    function statusColor(statusClass) {
      return statusColors[statusClass] || statusColors.queued;
    }
    function jobActions(job) {
      const counts = job.counts || {};
      const hasRendering = (counts.rendering || 0) > 0;
      const hasQueued = (counts.queued || 0) > 0 || (counts.failed || 0) > 0;
      const isDone = job.status === "done" || job.status === "archived";
      const canCancel = !isDone && job.status !== "cancelled" && (hasRendering || hasQueued || job.status === "paused" || job.status === "draining");
      const actions = [
        `<button title="Move up in queue priority" onclick="moveJob('${job.id}', -1)">Up</button>`,
        `<button title="Move down in queue priority" onclick="moveJob('${job.id}', 1)">Down</button>`,
        `<button onclick="openDetail('${job.id}')">Details</button>`,
        `<button onclick="openRenderFolder('${job.id}')">Open Render Folder</button>`
      ];
      if (job.status === "paused") actions.push(`<button onclick="action('resume','${job.id}')">Resume</button>`);
      else if (!isDone && job.status !== "cancelled") actions.push(`<button onclick="action('pause','${job.id}')">Pause</button>`);
      if (hasRendering) actions.push(`<button title="Stops assigning new frames; currently rendering frames finish." onclick="action('drain','${job.id}')">Stop After Batch</button>`);
      if (job.status !== "archived") actions.push(`<button onclick="action('archive','${job.id}')">Archive</button>`);
      if ((counts.failed || 0) > 0 || job.status === "cancelled") actions.push(`<button onclick="action('requeue','${job.id}')">Requeue Failed</button>`);
      if (canCancel) actions.push(`<button onclick="action('cancel','${job.id}')">Cancel</button>`);
      return actions.join("");
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
    function metrics(job) {
      const stats = job.stats || {};
      return `
        <div class="metrics">
          <div class="metric"><div class="metric-label">Elapsed</div><div class="metric-value">${esc(stats.elapsed || "--")}</div></div>
          <div class="metric"><div class="metric-label">ETA</div><div class="metric-value">${esc(stats.eta || "--")}</div></div>
          <div class="metric"><div class="metric-label">Avg Frame</div><div class="metric-value">${esc(stats.avg || "--")}</div></div>
          <div class="metric"><div class="metric-label">Fastest</div><div class="metric-value">${esc(frameMetric(stats.fastest))}</div></div>
          <div class="metric"><div class="metric-label">Slowest</div><div class="metric-value">${esc(frameMetric(stats.slowest))}</div></div>
        </div>`;
    }
    function workerMetrics(job) {
      const workers = Object.entries((job.stats || {}).workers || {});
      if (!workers.length) return "";
      return `<div class="worker-metrics">${workers.map(([id, stats]) => `
        <div class="worker-card" style="--worker-color:${workerColor(id)}">
          <strong>${esc(id)}</strong>
          <div class="subtle">${esc(stats.frames)} frames done &middot; avg ${esc(stats.avg)} &middot; total ${esc(stats.time)}${stats.failed ? ` &middot; failed ${esc(stats.failed)}` : ""}</div>
        </div>`).join("")}</div>`;
    }
    function groupJobs(jobs) {
      const groups = [];
      const byId = new Map();
      const standalone = [];
      for (const job of jobs) {
        const meta = job.metadata || {};
        if (!meta.group_id) {
          standalone.push(job);
          continue;
        }
        if (!byId.has(meta.group_id)) {
          const group = { id: meta.group_id, name: meta.group_name || job.name, jobs: [] };
          byId.set(meta.group_id, group);
          groups.push(group);
        }
        byId.get(meta.group_id).jobs.push(job);
      }
      for (const group of groups) {
        group.jobs.sort(compareJobsForDisplay);
      }
      standalone.sort(compareJobsForDisplay);
      return { groups, standalone };
    }
    function displayRank(job) {
      const counts = job.counts || {};
      if ((counts.rendering || 0) > 0) return 0;
      if ((counts.failed || 0) > 0 || job.status === "cancelled") return 1;
      if (job.status === "queued" || job.status === "paused" || job.status === "draining") return 2;
      if (job.status === "done" || job.status === "archived") return 3;
      return 4;
    }
    function compareJobsForDisplay(a, b) {
      return displayRank(a) - displayRank(b)
        || (a.priority ?? 5000) - (b.priority ?? 5000)
        || ((a.metadata || {}).group_index || 0) - ((b.metadata || {}).group_index || 0);
    }
    function groupProgress(group) {
      const frames = group.jobs.reduce((sum, job) => sum + Object.values(job.counts || {}).reduce((a, b) => a + b, 0), 0);
      const done = group.jobs.reduce((sum, job) => sum + ((job.counts || {}).done || 0), 0);
      return frames ? done / frames * 100 : 0;
    }
    function groupCounts(group) {
      const counts = {};
      for (const job of group.jobs) {
        for (const [status, count] of Object.entries(job.counts || {})) counts[status] = (counts[status] || 0) + count;
      }
      return counts;
    }
    async function actionGroup(kind, groupId) {
      const data = await fetch("/api/snapshot").then(r => r.json());
      const jobs = data.jobs.filter(job => (job.metadata || {}).group_id === groupId);
      for (const job of jobs) await action(kind, job.id);
      await refresh();
    }
    function renderJob(j) {
      const collapsed = collapsedJobs.has(j.id);
      const [statusClass, statusLabel] = jobState(j);
      return `<article class="job ${collapsed ? "collapsed" : ""}" style="--job-color:${statusColor(statusClass)}" data-job-id="${esc(j.id)}" data-priority="${esc(j.priority ?? 5000)}">
        <div class="job-head" onclick="toggleJob('${j.id}')">
          <div class="job-head-main">
            <div class="job-title-row">
              <span class="job-status ${statusClass}">${esc(statusLabel)}</span>
              <div class="job-title">${esc(j.name)}</div>
            </div>
            <div class="meta">${j.progress.toFixed(1)}% &middot; ${esc(jobStatusLabel(j))} &middot; ${esc(statusText(j.counts))}</div>
            <div class="job-progress"><div class="bar" style="width:${j.progress}%"></div></div>
            <div class="job-detail-lines">
              <div class="meta">${esc((j.metadata || {}).take_name ? `Take: ${(j.metadata || {}).take_name}` : j.scene)}</div>
              <div class="meta">${esc(j.display_output || j.output)}</div>
            </div>
          </div>
          <div class="actions" onclick="event.stopPropagation()">
            ${jobActions(j)}
          </div>
        </div>
        <div class="job-body">
          <div class="stats"><span>${j.progress.toFixed(1)}%</span><span>${esc(jobStatusLabel(j))}</span><span>batch: ${esc((j.metadata || {}).chunk_size || "--")}</span></div>
          ${metrics(j)}
          ${workerMetrics(j)}
          <div class="frames-label">Frames</div>
          <div class="frames">${j.frames.map(f => `<div onclick="openDetail('${j.id}', ${f.frame})" title="${esc(frameTitle(f))}" class="${frameClass(f.status)} ${f.worker_id ? "worker-owned" : ""}" ${frameStyle(f)}>${esc(f.frame)}</div>`).join("")}</div>
        </div>
      </article>`;
    }
    function renderGroup(group) {
      const progress = groupProgress(group);
      const counts = groupCounts(group);
      return `<div class="job-group">
        <div class="group-head">
          <div>
            <div class="group-title">${esc(group.name)}</div>
            <div class="subtle">${esc(group.jobs.length)} takes &middot; ${progress.toFixed(1)}% &middot; ${esc(statusText(counts))}</div>
          </div>
          <div class="actions">
            <button onclick="actionGroup('pause','${group.id}')">Pause All</button>
            <button onclick="actionGroup('resume','${group.id}')">Resume All</button>
            <button onclick="actionGroup('archive','${group.id}')">Archive All</button>
            <button onclick="actionGroup('cancel','${group.id}')">Cancel All</button>
          </div>
        </div>
        <div class="group-jobs job-drop-list">${group.jobs.map(renderJob).join("")}</div>
      </div>`;
    }
    async function openDetail(jobId, frameNumber = null) {
      selectedJobId = jobId;
      selectedFrame = frameNumber;
      const job = await fetch(`/api/job?job_id=${encodeURIComponent(jobId)}`).then(r => r.json());
      document.getElementById("detail-title").textContent = job.name;
      document.getElementById("detail-meta").textContent = `${job.id} - ${job.progress.toFixed(1)}% - ${jobStatusLabel(job)}`;
      document.getElementById("detail-frames").innerHTML = job.frames.map(f => `
        <div onclick="openFrameLog('${job.id}', ${f.frame})" title="${esc(frameTitle(f))}" class="${frameClass(f.status)} ${f.worker_id ? "worker-owned" : ""}" ${frameStyle(f)}>${esc(f.frame)}</div>
      `).join("");
      if (frameNumber) await openFrameLog(jobId, frameNumber);
      document.getElementById("detail").showModal();
    }
    async function openFrameLog(jobId, frameNumber) {
      selectedFrame = frameNumber;
      const data = await fetch(`/api/log?job_id=${encodeURIComponent(jobId)}&frame=${encodeURIComponent(frameNumber)}`).then(r => r.json());
      const head = data.path ? `Log: ${data.path}\n\n` : "";
      document.getElementById("detail-log").textContent = head + data.log;
      const preview = await fetch(`/api/preview?job_id=${encodeURIComponent(jobId)}&frame=${encodeURIComponent(frameNumber)}`).then(r => r.json());
      const previewEl = document.getElementById("detail-preview");
      if (preview.renderable && preview.path) {
        const sourceLine = preview.converted && preview.source_path
          ? `<div class="subtle">Source: ${esc(preview.source_path)}</div>`
          : "";
        previewEl.innerHTML = `
          <img class="preview" src="/api/file?path=${encodeURIComponent(preview.path)}" alt="Frame ${frameNumber} preview">
          <div class="subtle">${esc(preview.path)}</div>
          ${sourceLine}`;
      } else {
        const sourceLine = preview.source_path ? `<div class="subtle">${esc(preview.source_path)}</div>` : "";
        previewEl.innerHTML = `
          <div class="preview-note">
            <strong>Preview unavailable</strong>
            <div class="subtle">${esc(preview.message || `No output image found for frame ${frameNumber}.`)}</div>
          </div>
          ${sourceLine}`;
      }
    }
    function closeDetail() {
      document.getElementById("detail").close();
    }
    async function refresh() {
      const data = await fetch("/api/snapshot").then(r => r.json());
      currentJobOrder = data.jobs.map(job => job.id);
      document.getElementById("share").textContent = data.share;
      document.getElementById("updated").textContent = new Date(data.generated_at).toLocaleString();
      document.getElementById("workers").innerHTML = data.workers.length ? data.workers.map(w => `
        <div class="worker" style="--worker-color:${workerColor(w.worker_id)}">
          <span class="dot ${w.state === "online" ? "online" : ""} ${w.state === "heartbeat_lost" ? "heartbeat-lost" : ""}" style="--worker-color:${workerColor(w.worker_id)}"></span>
          <div>
            <div>${esc(w.worker_id)}</div>
            <div class="subtle">${esc(workerLabel(w))}</div>
          </div>
        </div>`).join("") : `<div class="subtle">No workers have checked in yet.</div>`;
      const grouped = groupJobs(data.jobs);
      document.getElementById("jobs").innerHTML = data.jobs.length
        ? `${grouped.groups.map(renderGroup).join("")}${grouped.standalone.map(renderJob).join("")}`
        : `<div class="empty">No jobs in the queue.</div>`;
    }
    refresh();
    setInterval(refresh, 2500);
  </script>
</body>
</html>
"""


class MonitorHandler(BaseHTTPRequestHandler):
    share: Share

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)
        if route == "/":
            self.send_text(HTML, "text/html; charset=utf-8")
            return
        if route == "/api/snapshot":
            include_archived = query.get("archived", ["0"])[0] == "1"
            self.send_json(queue_snapshot(self.share, include_archived=include_archived))
            return
        if route == "/api/job":
            job_id = query.get("job_id", [""])[0]
            if not job_id:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing job_id")
                return
            self.send_json(get_job_detail(self.share, job_id))
            return
        if route == "/api/log":
            job_id = query.get("job_id", [""])[0]
            frame_text = query.get("frame", [""])[0]
            if not job_id or not frame_text:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing job_id or frame")
                return
            self.send_json(read_frame_log(self.share, job_id, int(frame_text)))
            return
        if route == "/api/preview":
            job_id = query.get("job_id", [""])[0]
            frame_text = query.get("frame", [""])[0]
            if not job_id or not frame_text:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing job_id or frame")
                return
            self.send_json(find_frame_preview(self.share, job_id, int(frame_text)))
            return
        if route == "/api/file":
            file_path = query.get("path", [""])[0]
            if not file_path:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing path")
                return
            self.send_file(Path(file_path))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        if route != "/api/action":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        values = parse_qs(self.rfile.read(length).decode("utf-8"))
        action = values.get("action", [""])[0]
        if action == "reorder":
            job_ids = values.get("job_ids", [])
            if not job_ids:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing job_ids")
                return
            set_job_priorities(self.share, job_ids)
            self.send_json({"ok": True})
            return
        job_id = values.get("job_id", [""])[0]
        if not job_id:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing job_id")
            return
        if action == "pause":
            set_job_status(self.share, job_id, "paused")
        elif action == "resume":
            set_job_status(self.share, job_id, "queued")
        elif action == "cancel":
            set_job_status(self.share, job_id, "cancelled")
        elif action == "drain":
            set_job_status(self.share, job_id, "draining")
        elif action == "archive":
            set_job_status(self.share, job_id, "archived")
        elif action == "requeue":
            requeue_failed(self.share, job_id)
        elif action == "requeue_frames":
            frames = [int(value) for value in values.get("frames", [])]
            requeue_frames(self.share, job_id, frames)
        elif action == "open_output":
            try:
                self.open_output_folder(job_id)
            except OSError as exc:
                self.send_error(HTTPStatus.NOT_FOUND, str(exc))
                return
        else:
            self.send_error(HTTPStatus.BAD_REQUEST, "Unknown action")
            return
        self.send_json({"ok": True})

    def open_output_folder(self, job_id: str) -> None:
        job = get_job_detail(self.share, job_id)
        output_text = str(job.get("output") or "")
        if not output_text:
            raise FileNotFoundError("Job has no output path.")
        output = Path(output_text)
        folder = output.parent if output.suffix else output
        while not folder.exists() and folder != folder.parent:
            folder = folder.parent
        if not folder.exists():
            raise FileNotFoundError(folder)
        if os.name == "nt":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif os.name == "posix":
            opener = "open" if subprocess.run(["which", "open"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0 else "xdg-open"
            subprocess.Popen([opener, str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def send_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, text: str, content_type: str) -> None:
        body = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_monitor(share: Share, host: str, port: int) -> None:
    if not share.root.exists():
        raise FileNotFoundError(share.root)
    handler = type("DreamRenderMonitorHandler", (MonitorHandler,), {"share": share})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"DreamRender monitor running at http://{host}:{port}")
    print(f"Watching share: {Path(share.root)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
    finally:
        server.server_close()
