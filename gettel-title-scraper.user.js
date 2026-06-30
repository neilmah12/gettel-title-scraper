// ==UserScript==
// @name         Gettel Title Scraper
// @namespace    https://github.com/neilmah12/gettel-title-scraper
// @version      1.2.0
// @description  Automate purchasing and downloading land title PDFs from database.gettelnetwork.com
// @author       Refi-Map
// @match        https://database.gettelnetwork.com/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_download
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  // ── Constants ────────────────────────────────────────────────────────────────

  const KEY_RESULTS   = 'gts_results';    // { [pid]: { pid, status, filename, timestamp } }
  const KEY_QUEUE     = 'gts_queue';      // string[] – PIDs still to process
  const KEY_RUNNING   = 'gts_running';    // bool
  const KEY_CURRENT   = 'gts_current';    // string – PID actively being processed

  const DELAY_MIN_MS  = 3000;
  const DELAY_MAX_MS  = 7000;
  const LONG_PAUSE_CHANCE = 0.15;  // 15% chance of a longer human-like pause
  const LONG_PAUSE_MIN_MS = 12000;
  const LONG_PAUSE_MAX_MS = 25000;

  // ── Helpers ──────────────────────────────────────────────────────────────────

  function randDelay() {
    if (Math.random() < LONG_PAUSE_CHANCE) {
      return LONG_PAUSE_MIN_MS + Math.random() * (LONG_PAUSE_MAX_MS - LONG_PAUSE_MIN_MS);
    }
    // Skew toward the lower end (humans tend to act sooner rather than later)
    const r = Math.random() * Math.random();
    return DELAY_MIN_MS + r * (DELAY_MAX_MS - DELAY_MIN_MS);
  }

  function getResults() {
    return GM_getValue(KEY_RESULTS, {});
  }

  function saveResults(r) {
    GM_setValue(KEY_RESULTS, r);
  }

  function getQueue() {
    return GM_getValue(KEY_QUEUE, []);
  }

  function saveQueue(q) {
    GM_setValue(KEY_QUEUE, q);
  }

  function isRunning() {
    return GM_getValue(KEY_RUNNING, false);
  }

  function setRunning(v) {
    GM_setValue(KEY_RUNNING, v);
  }

  function getCurrentPid() {
    return GM_getValue(KEY_CURRENT, null);
  }

  function setCurrentPid(pid) {
    GM_setValue(KEY_CURRENT, pid);
  }

  function getSessionId() {
    const m = location.search.match(/sessionid=([^&]+)/);
    return m ? m[1] : null;
  }

  function parsePids(raw) {
    return raw
      .split(/[\n,]+/)
      .map(s => s.trim())
      .filter(Boolean);
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function log(msg) {
    console.log(`[GTS] ${msg}`);
  }

  // ── CSV export ───────────────────────────────────────────────────────────────

  function exportCsv() {
    const results = getResults();
    const rows = [['PID', 'Status', 'Filename', 'Timestamp']];
    for (const pid of Object.keys(results)) {
      const r = results[pid];
      rows.push([r.pid, r.status, r.filename || '', r.timestamp || '']);
    }
    const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `gettel-titles-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ── Navigation ───────────────────────────────────────────────────────────────

  function navigateToDetail(pid) {
    const sid = getSessionId();
    if (!sid) { log('ERROR: no session ID in URL'); return; }
    log(`Navigating to detail page for PID ${pid}`);
    location.href = `https://database.gettelnetwork.com/WebCore_MainDetails?sessionid=${sid}&pid=${pid}`;
  }

  // ── Page state detection ─────────────────────────────────────────────────────

  function isDetailPage() {
    return location.pathname.includes('WebCore_MainDetails');
  }

  function isCartPage() {
    return location.pathname.includes('WebCore_ButtonHandler');
  }

  // Detect which state the detail page is in:
  //   'downloaded' – downloadLincPDF button present (title available)
  //   'purchase'   – doPurchase button present (need to buy)
  //   'no_title'   – neither button present
  function detectDetailState() {
    const dlBtn  = document.querySelector('input[name="downloadLincPDF"]');
    if (dlBtn) return { state: 'downloaded', button: dlBtn };

    const buyBtn = document.querySelector('input[name="doPurchase"]');
    if (buyBtn) return { state: 'purchase', button: buyBtn };

    return { state: 'no_title', button: null };
  }

  // ── Panel UI ─────────────────────────────────────────────────────────────────

  let panel = null;

  function buildPanel() {
    if (document.getElementById('gts-panel')) return;

    panel = document.createElement('div');
    panel.id = 'gts-panel';
    Object.assign(panel.style, {
      position:        'fixed',
      top:             '10px',
      right:           '10px',
      width:           '320px',
      background:      '#1a1a2e',
      color:           '#e0e0e0',
      border:          '1px solid #444',
      borderRadius:    '8px',
      padding:         '12px',
      zIndex:          '999999',
      fontFamily:      'monospace',
      fontSize:        '12px',
      boxShadow:       '0 4px 16px rgba(0,0,0,0.5)',
      maxHeight:       '90vh',
      overflowY:       'auto',
    });

    panel.innerHTML = `
      <div style="font-size:14px;font-weight:bold;margin-bottom:8px;color:#7eb8f7">
        Gettel Title Scraper
      </div>

      <textarea id="gts-pid-input" rows="5" placeholder="Paste PIDs here (one per line or comma-separated)"
        style="width:100%;box-sizing:border-box;background:#0d0d1a;color:#e0e0e0;border:1px solid #555;
               border-radius:4px;padding:6px;font-family:monospace;font-size:11px;resize:vertical"></textarea>

      <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
        <button id="gts-btn-start"  style="${btnStyle('#2a6496')}">Start New Batch</button>
        <button id="gts-btn-resume" style="${btnStyle('#28783a')}">Resume</button>
        <button id="gts-btn-pause"  style="${btnStyle('#7a3030', 'display:none')}">Pause / Stop</button>
        <button id="gts-btn-export" style="${btnStyle('#555')}">Export CSV</button>
      </div>

      <div id="gts-status" style="margin-top:10px;border-top:1px solid #333;padding-top:8px">
        <div id="gts-current-pid" style="color:#aaa">Idle</div>
        <div id="gts-counts" style="color:#888;margin-top:4px"></div>
      </div>

      <div id="gts-log" style="margin-top:8px;max-height:150px;overflow-y:auto;
           border-top:1px solid #333;padding-top:6px;color:#777;font-size:10px"></div>
    `;

    document.body.appendChild(panel);

    document.getElementById('gts-btn-start').addEventListener('click', onStartBatch);
    document.getElementById('gts-btn-resume').addEventListener('click', onResume);
    document.getElementById('gts-btn-pause').addEventListener('click', onPause);
    document.getElementById('gts-btn-export').addEventListener('click', exportCsv);

    refreshPanel();
  }

  function btnStyle(bg, extra = '') {
    return `background:${bg};color:#fff;border:none;border-radius:4px;padding:5px 10px;
            cursor:pointer;font-size:11px;font-family:monospace;${extra}`;
  }

  function panelLog(msg) {
    const el = document.getElementById('gts-log');
    if (!el) return;
    const line = document.createElement('div');
    line.textContent = `${new Date().toLocaleTimeString()} ${msg}`;
    el.prepend(line);
    // Keep at most 100 lines
    while (el.children.length > 100) el.removeChild(el.lastChild);
  }

  function refreshPanel() {
    const results  = getResults();
    const queue    = getQueue();
    const running  = isRunning();
    const curPid   = getCurrentPid();

    const total      = Object.keys(results).length;
    const done       = Object.values(results).filter(r => r.status !== 'pending').length;
    const remaining  = queue.length + (curPid ? 1 : 0);

    const curEl    = document.getElementById('gts-current-pid');
    const cntEl    = document.getElementById('gts-counts');
    const pauseBtn = document.getElementById('gts-btn-pause');
    const resumeBtn= document.getElementById('gts-btn-resume');

    if (curEl) {
      curEl.textContent = running && curPid ? `Processing: ${curPid}` : 'Idle';
      curEl.style.color = running ? '#7eb8f7' : '#aaa';
    }
    if (cntEl && total > 0) {
      cntEl.textContent = `Done: ${done} | Remaining: ${remaining} | Total: ${total}`;
    }
    if (pauseBtn) pauseBtn.style.display = running ? 'inline-block' : 'none';

    // Show resume button if there's an incomplete batch
    const hasPending = queue.length > 0 || (curPid && !running);
    if (resumeBtn) resumeBtn.style.display = hasPending && !running ? 'inline-block' : 'none';
  }

  // ── Button handlers ──────────────────────────────────────────────────────────

  function onStartBatch() {
    const rawInput = document.getElementById('gts-pid-input')?.value || '';
    const newPids  = parsePids(rawInput);
    if (!newPids.length) { alert('No PIDs entered.'); return; }

    const results = getResults();

    // Merge: only add PIDs not already done
    let added = 0;
    for (const pid of newPids) {
      const existing = results[pid];
      if (!existing || existing.status === 'pending' || existing.status === 'error') {
        results[pid] = { pid, status: 'pending', filename: '', timestamp: '' };
        added++;
      }
    }
    saveResults(results);

    // Build queue from all pending/error entries
    const queue = Object.values(results)
      .filter(r => r.status === 'pending' || r.status === 'error')
      .map(r => r.pid);

    saveQueue(queue);
    setCurrentPid(null);
    setRunning(true);

    log(`Starting batch: ${added} new PIDs added, ${queue.length} in queue`);
    panelLog(`Batch started: ${queue.length} PIDs to process`);
    refreshPanel();
    processNext();
  }

  function onResume() {
    if (isRunning()) return;
    const queue = getQueue();
    if (!queue.length && !getCurrentPid()) { alert('No pending batch to resume.'); return; }
    setRunning(true);
    log('Resuming batch');
    panelLog('Resuming batch');
    refreshPanel();
    processNext();
  }

  function onPause() {
    setRunning(false);
    log('Batch paused');
    panelLog('Paused by user');
    refreshPanel();
  }

  // ── Processing logic ─────────────────────────────────────────────────────────

  function processNext() {
    if (!isRunning()) { log('Paused, not continuing'); return; }

    let queue = getQueue();
    if (!queue.length) {
      // Done
      setRunning(false);
      setCurrentPid(null);
      log('Batch complete');
      panelLog('Batch complete! Use Export CSV to download results.');
      refreshPanel();
      exportCsv();
      return;
    }

    const pid = queue.shift();
    saveQueue(queue);
    setCurrentPid(pid);
    refreshPanel();

    setTimeout(() => navigateToDetail(pid), randDelay());
  }

  function markResult(pid, status, filename = '') {
    const results = getResults();
    results[pid] = { pid, status, filename, timestamp: nowIso() };
    saveResults(results);
    log(`PID ${pid}: ${status}${filename ? ` (${filename})` : ''}`);
    panelLog(`${pid} → ${status}${filename ? ` [${filename}]` : ''}`);
    refreshPanel();
  }

  // ── Page handlers ────────────────────────────────────────────────────────────

  function handleDetailPage() {
    if (!isRunning()) return;

    const pid = getCurrentPid();
    if (!pid) return;

    // Verify URL PID matches what we expect
    const urlPid = new URLSearchParams(location.search).get('pid');
    if (urlPid && urlPid !== pid) {
      log(`URL PID (${urlPid}) doesn't match current PID (${pid}), skipping`);
      return;
    }

    const { state, button } = detectDetailState();

    if (state === 'downloaded') {
      // Extract filename from button value: "Download {filename}.pdf"
      const raw      = button.value || '';
      const filename = raw.replace(/^Download\s+/i, '').trim() || `${pid}.pdf`;

      // Use a natural form submit — fetch() would send different Sec-Fetch-* headers
      // and look like automation. The CSV records the PID→filename mapping instead.
      panelLog(`${pid} → downloading…`);
      button.click();

      markResult(pid, 'downloaded', filename);
      setTimeout(processNext, randDelay());

    } else if (state === 'purchase') {
      log(`PID ${pid}: clicking purchase button`);
      panelLog(`${pid} → purchasing…`);
      button.click();
      // Navigation to cart happens automatically via form submit

    } else {
      // no_title
      markResult(pid, 'no_title');
      setTimeout(processNext, randDelay());
    }
  }

  function handleCartPage() {
    if (!isRunning()) return;

    const pid = getCurrentPid();
    if (!pid) return;

    // Find the back-link to the detail page for the current PID
    const link = [...document.querySelectorAll('a')].find(a => {
      const href = a.getAttribute('href') || '';
      return href.includes('WebCore_MainDetails') && href.includes(`pid=${pid}`);
    });

    if (link) {
      log(`PID ${pid}: on cart page, clicking back-link`);
      panelLog(`${pid} → cart → returning to detail`);
      setTimeout(() => link.click(), randDelay());
    } else {
      // Fallback: navigate directly
      log(`PID ${pid}: back-link not found on cart page, navigating directly`);
      panelLog(`${pid} → cart back-link missing, navigating directly`);
      setTimeout(() => navigateToDetail(pid), randDelay());
    }
  }

  function handleUnexpectedPage() {
    if (!isRunning()) return;

    const pid = getCurrentPid();
    if (!pid) return;

    log(`PID ${pid}: unexpected page at ${location.pathname}, marking error`);
    panelLog(`${pid} → error (unexpected page)`);
    markResult(pid, 'error');
    setTimeout(processNext, randDelay());
  }

  // ── Entry point ──────────────────────────────────────────────────────────────

  function main() {
    buildPanel();

    if (!isRunning()) {
      refreshPanel();
      return;
    }

    // Dispatch based on current page
    if (isDetailPage()) {
      handleDetailPage();
    } else if (isCartPage()) {
      handleCartPage();
    } else {
      // We're on some other page (e.g. dashboard) while a run is active —
      // resume by navigating to the current PID if one is set, else processNext.
      const pid = getCurrentPid();
      if (pid) {
        log(`On non-processing page during run, resuming with PID ${pid}`);
        setTimeout(() => navigateToDetail(pid), randDelay());
      } else {
        processNext();
      }
    }
  }

  // Wrap in try/catch so an unexpected JS error on any page never crashes silently
  try {
    main();
  } catch (err) {
    console.error('[GTS] Fatal error in main():', err);
    const pid = getCurrentPid();
    if (pid) {
      try {
        markResult(pid, 'error');
      } catch (_) {}
      try {
        GM_setValue(KEY_CURRENT, null);
      } catch (_) {}
    }
  }

})();
