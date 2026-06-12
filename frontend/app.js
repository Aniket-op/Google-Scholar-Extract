/**
 * app.js — Google Scholar Extractor frontend logic.
 *
 * Flow:
 *   1. User pastes Scholar URL → POST /api/extract → receive job_id
 *   2. Poll GET /api/status/<job_id> every 1.5s → update stage pipeline + progress bar
 *   3. On done → render profile card + publication list
 *   4. Download buttons → GET /api/download/<job_id>/<type>
 */

'use strict';

// ── Config ───────────────────────────────────────────────────────
const API_BASE  = 'http://localhost:5000/api';
const PAGE_SIZE = 20;
const POLL_MS   = 1500;

// ── State ────────────────────────────────────────────────────────
let currentJobId    = null;
let pollInterval    = null;
let allPublications = [];
let filteredPubs    = [];
let shownCount      = 0;

// ── DOM refs ─────────────────────────────────────────────────────
const urlInput        = document.getElementById('profile-url-input');
const extractBtn      = document.getElementById('extract-btn');
const fillToggle      = document.getElementById('fill-all-toggle');
const proxyToggle     = document.getElementById('proxy-toggle');
const scraperApiInput = document.getElementById('scraper-api-input');
const progressSection = document.getElementById('progress-section');
const progressStatus  = document.getElementById('progress-status');
const progressCount   = document.getElementById('progress-count');
const progressBar     = document.getElementById('progress-bar');
const progressMsg     = document.getElementById('progress-message');
const errorBox        = document.getElementById('error-box');
const resultsSection  = document.getElementById('results-section');
const pubList         = document.getElementById('pub-list');
const showMoreBtn     = document.getElementById('show-more-btn');

// Restore saved ScraperAPI key from localStorage
const _savedKey = localStorage.getItem('scraperapi_key');
if (_savedKey) scraperApiInput.value = _savedKey;

// Stage pipeline step elements
const stepEls = [
  document.getElementById('step-connecting'),
  document.getElementById('step-loading'),
  document.getElementById('step-fetching'),
  document.getElementById('step-done'),
];
const lineEls = Array.from(document.querySelectorAll('.step-line'));

// Maps backend stage key -> pipeline step index (0-3)
const STAGE_TO_IDX = {
  connecting: 0, proxy: 0,
  loading: 1, profile_done: 1,
  fetching_pubs: 2, pub_progress: 2,
  done: 3,
};

// ── URL validation ────────────────────────────────────────────────
urlInput.addEventListener('input', () => {
  const v = urlInput.value.trim();
  if (!v) { urlInput.classList.remove('valid', 'invalid'); return; }
  const ok = isScholarUrl(v);
  urlInput.classList.toggle('valid', ok);
  urlInput.classList.toggle('invalid', !ok);
});

urlInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') startExtraction();
});

function isScholarUrl(url) {
  return (
    url.includes('scholar.google.com/citations') ||
    /^[A-Za-z0-9_-]{10,}$/.test(url.trim())
  );
}

// ── Start extraction ──────────────────────────────────────────────
async function startExtraction() {
  const url = urlInput.value.trim();
  if (!url) { showError('Please enter a Google Scholar profile URL.'); return; }
  if (!isScholarUrl(url)) {
    showError('Please enter a valid Google Scholar profile URL (e.g. https://scholar.google.com/citations?user=XXXX).');
    return;
  }

  hideError();
  hideResults();
  resetPipeline();
  setBusy(true);
  showProgress('Starting extraction...', 0, '');

  // Save ScraperAPI key for next session
  const apiKey = scraperApiInput.value.trim();
  if (apiKey) localStorage.setItem('scraperapi_key', apiKey);

  try {
    const resp = await fetch(`${API_BASE}/extract`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile_url: url,
        fill_all: fillToggle.checked,
        use_free_proxy: proxyToggle.checked,
        scraper_api_key: apiKey || null,
      }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || `Server error ${resp.status}`);
    }

    const data = await resp.json();
    currentJobId = data.job_id;
    startPolling();
  } catch (err) {
    setBusy(false);
    hideProgress();
    showError(`Failed to start extraction: ${err.message}`);
  }
}

// ── Polling ──────────────────────────────────────────────────────
function startPolling() {
  clearInterval(pollInterval);
  pollInterval = setInterval(pollStatus, POLL_MS);
  pollStatus(); // immediate first call
}

async function pollStatus() {
  if (!currentJobId) return;
  try {
    const resp = await fetch(`${API_BASE}/status/${currentJobId}`);
    const data = await resp.json();
    const { status, stage, progress, total, message, profile, publication_count } = data;

    // Always update the stage pipeline
    updatePipeline(stage || status);

    if (status === 'running' || status === 'pending') {
      // Calculate progress %: early stages use indeterminate %, pub-fetch uses real %
      let pct = 5;
      let countText = '';

      if (stage === 'loading' || stage === 'profile_done') {
        pct = 20;
      } else if (stage === 'fetching_pubs' || stage === 'pub_progress') {
        pct = total > 0 ? 20 + Math.round((progress / total) * 78) : 22;
        countText = total > 0
          ? `${progress} of ${total} publications fetched`
          : 'Fetching...';
      }

      showProgress(message || 'Working...', pct, countText);

    } else if (status === 'done') {
      clearInterval(pollInterval);
      updatePipeline('done');
      showProgress('Extraction complete!', 100, `${publication_count} publications found`);

      // Load full result
      try {
        const res    = await fetch(`${API_BASE}/result/${currentJobId}`);
        const result = await res.json();
        renderResults(result.profile, result.publications);
      } catch (e) {
        showError('Extraction succeeded but could not load results: ' + e.message);
      }
      setBusy(false);

    } else if (status === 'error') {
      clearInterval(pollInterval);
      hideProgress();
      setBusy(false);
      showError(data.error || data.message || 'Unknown error occurred.');
    }
  } catch (_) {
    // Network hiccup — keep polling silently
  }
}

// ── Stage pipeline ────────────────────────────────────────────────
function resetPipeline() {
  stepEls.forEach(el => el.classList.remove('active', 'done'));
  lineEls.forEach(el => el.classList.remove('active', 'done'));
  progressSection.classList.add('visible');
}

function updatePipeline(stage) {
  const activeIdx = STAGE_TO_IDX[stage] ?? -1;
  if (activeIdx < 0) return;

  stepEls.forEach((el, i) => {
    el.classList.remove('active', 'done');
    if (i < activeIdx)      el.classList.add('done');
    else if (i === activeIdx) el.classList.add('active');
  });

  lineEls.forEach((line, i) => {
    line.classList.remove('active', 'done');
    if (i < activeIdx)      line.classList.add('done');
    else if (i === activeIdx) line.classList.add('active');
  });
}

// ── Render results ────────────────────────────────────────────────
function renderResults(profile, publications) {
  document.getElementById('prof-name').textContent        = profile.name || 'Unknown';
  document.getElementById('prof-affiliation').textContent = profile.affiliation || '';
  document.getElementById('m-citations').textContent      = fmt(profile.citedby);
  document.getElementById('m-hindex').textContent         = fmt(profile.hindex);
  document.getElementById('m-i10').textContent            = fmt(profile.i10index);
  document.getElementById('m-pubs').textContent           = fmt(profile.total_publications);

  const tagsEl = document.getElementById('prof-interests');
  tagsEl.innerHTML = (profile.interests || [])
    .map(i => `<span class="interest-tag">${esc(i)}</span>`)
    .join('');

  allPublications = publications;
  document.getElementById('pub-total-count').textContent = publications.length;
  applyFilter('all');
  showResults();
}

// ── Publication list ─────────────────────────────────────────────
function applyFilter(type) {
  document.querySelectorAll('.filter-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.type === type)
  );

  if (type === 'all') {
    filteredPubs = [...allPublications];
  } else if (type === 'patent') {
    filteredPubs = allPublications.filter(p =>
      p.type === 'patent-granted' || p.type === 'patent-published'
    );
  } else if (type === 'book-authored') {
    filteredPubs = allPublications.filter(p =>
      p.type === 'book-authored' || p.type === 'book-edited'
    );
  } else {
    filteredPubs = allPublications.filter(p => p.type === type);
  }
  shownCount = 0;
  pubList.innerHTML = '';
  showMore();
}

function filterPubs(btn) {
  applyFilter(btn.dataset.type);
}

function showMore() {
  const batch = filteredPubs.slice(shownCount, shownCount + PAGE_SIZE);
  batch.forEach(pub => pubList.appendChild(buildPubItem(pub)));
  shownCount += batch.length;

  const remaining = filteredPubs.length - shownCount;
  showMoreBtn.style.display = remaining > 0 ? 'block' : 'none';
  if (remaining > 0) {
    showMoreBtn.textContent =
      `Show ${Math.min(remaining, PAGE_SIZE)} more (${remaining} remaining) \u2193`;
  }
}

function buildPubItem(pub) {
  const el = document.createElement('div');
  el.className = 'pub-item';

  const type   = pub.type || 'other';
  const title  = pub.title || pub.citation || 'Untitled';
  const year   = pub.year ? `${pub.year}` : '';
  const venue  = getVenue(pub);
  const authors = Array.isArray(pub.authors) && pub.authors.length
    ? `<span>${esc(pub.authors.slice(0, 3).join(', '))}${pub.authors.length > 3 ? ' et al.' : ''}</span>`
    : '';

  el.innerHTML = `
    <div>
      <span class="pub-type-badge ${badgeClass(type)}">${typeLabel(type)}</span>
    </div>
    <div>
      <div class="pub-title">${esc(title)}</div>
      <div class="pub-meta">
        ${authors}
        ${year ? `<span>&#128197; ${year}</span>` : ''}
        ${venue ? `<span class="pub-venue">&#128214; ${esc(venue)}</span>` : ''}
        ${pub.doi ? `<span>DOI: ${esc(pub.doi)}</span>` : ''}
      </div>
    </div>
  `;
  return el;
}

function getVenue(pub) {
  return pub.journal || pub.conference || pub.ResearchPublications || '';
}

function typeLabel(type) {
  return {
    'journal':               'Journal',
    'conference':            'Conference',
    'book-authored':         'Book',
    'book-edited':           'Edited Book',
    'patent-granted':        'Patent (Granted)',
    'patent-published':      'Patent (Published)',
    'Research-Publications': 'Research',
    'other':                 'Other',
  }[type] || type;
}

function badgeClass(type) {
  return {
    'journal':               'badge-journal',
    'conference':            'badge-conference',
    'book-authored':         'badge-book-authored',
    'book-edited':           'badge-book-edited',
    'patent-granted':        'badge-patent-granted',
    'patent-published':      'badge-patent-published',
    'Research-Publications': 'badge-research',
  }[type] || 'badge-other';
}

// ── Download ──────────────────────────────────────────────────────
function downloadFile(type, event) {
  event.preventDefault();
  if (!currentJobId) return;
  window.location.href = `${API_BASE}/download/${currentJobId}/${type}`;
}

// ── UI helpers ────────────────────────────────────────────────────
function setBusy(busy) {
  extractBtn.disabled = busy;
  if (busy) {
    document.getElementById('btn-icon').innerHTML = '<span class="spinner"></span>';
    document.getElementById('btn-text').textContent = 'Extracting...';
  } else {
    document.getElementById('btn-icon').textContent = String.fromCodePoint(0x1F50D);
    document.getElementById('btn-text').textContent = 'Extract';
  }
}

function showProgress(label, pct, countText) {
  progressSection.classList.add('visible');
  progressStatus.textContent = label;
  progressCount.textContent  = countText || '';
  progressBar.style.width    = `${Math.min(pct, 100)}%`;
}

function hideProgress() {
  progressSection.classList.remove('visible');
}

let countdownInterval = null;

function showError(msg) {
  clearInterval(countdownInterval);
  document.getElementById('error-main').innerHTML = `<strong>Error:</strong> ${esc(msg)}`;
  errorBox.classList.add('visible');

  const isRateLimit = msg.includes('rate-limit') || msg.includes('429') ||
                      msg.includes('CAPTCHA') || msg.includes('blocked') ||
                      msg.includes('unusual traffic');

  const hintEl  = document.getElementById('error-hint');
  const timerEl = document.getElementById('rate-limit-timer');

  if (isRateLimit) {
    hintEl.textContent = 'Google Scholar temporarily blocked this IP due to too many requests. This is common when running locally. Wait 15-30 minutes, or get a free ScraperAPI key at scraperapi.com and enter it in the URL options.';
    timerEl.style.display = 'block';
    let secs = 15 * 60; // 15 minutes
    const display = document.getElementById('countdown-display');
    countdownInterval = setInterval(() => {
      secs--;
      const m = String(Math.floor(secs / 60)).padStart(2, '0');
      const s = String(secs % 60).padStart(2, '0');
      display.textContent = `${m}:${s}`;
      if (secs <= 0) {
        clearInterval(countdownInterval);
        display.textContent = 'Ready to retry!';
      }
    }, 1000);
  } else {
    hintEl.textContent = '';
    timerEl.style.display = 'none';
  }
}

function hideError() {
  clearInterval(countdownInterval);
  errorBox.classList.remove('visible');
  document.getElementById('error-main').innerHTML = '';
  document.getElementById('error-hint').textContent = '';
  document.getElementById('rate-limit-timer').style.display = 'none';
}

function showResults() {
  resultsSection.classList.add('visible');
}

function hideResults() {
  resultsSection.classList.remove('visible');
  pubList.innerHTML = '';
  allPublications   = [];
}

function fmt(n) {
  if (n === null || n === undefined) return '\u2014';
  return Number(n).toLocaleString();
}

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
