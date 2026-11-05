import {initAssistant, enterAssistant, resetAssistant, scopeAssistant} from './assistant.js';
const labels = {normal: 'Healthy metrics', critical: 'Critical', warning: 'Warning', pending: 'Pending', running: 'Running', completed: 'Completed', failed: 'Failed', open: 'Open', closed: 'Closed', resolved: 'Resolved', superseded: 'Superseded'};
const state = {view: 'overview', offset: 0, jobOffset: 0, historyOffset: 0, selected: null, csrf: null, busy: false, timer: null, lastSuccess: null, requestVersion: 0, authenticated: false};
const $ = id => document.getElementById(id);

export function element(tag, className = '', text = '') {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text == null ? '' : String(text);
  return node;
}

export function badge(status) {
  return element('span', `badge ${Object.hasOwn(labels, status) ? status : 'neutral'}`, labels[status] || status || 'No job');
}

export function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Unavailable' : new Intl.DateTimeFormat(undefined, {month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', year: 'numeric'}).format(date);
}

export async function requestJSON(path, options = {}, timeout = 7000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(path, {...options, credentials: 'same-origin', signal: controller.signal, headers: {'Accept': 'application/json', ...options.headers}});
    if (!response.ok) {
      const messages = {401: 'Your session has expired. Please sign in again.', 403: 'This request was blocked. Check the local dashboard address.', 429: 'Requests are temporarily limited. Please wait and try again.', 503: 'The service is temporarily unavailable. Please try again.'};
      const error = new Error(messages[response.status] || 'The request could not be completed. Please try again.');
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : await response.json();
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The request timed out. Your last successful data is retained.');
    if (error instanceof TypeError || error instanceof SyntaxError) throw new Error('Could not load workspace data. Check the connection and try again.');
    throw error;
  } finally { clearTimeout(timer); }
}

function empty(target, title, message) {
  const box = element('div', 'empty-state');
  box.append(element('strong', '', title), element('span', '', message));
  target.replaceChildren(box);
}

function serviceButton(incident) {
  const button = element('button', 'service-button', incident.service);
  button.title = incident.service;
  button.addEventListener('click', () => openDetail(incident.id ?? incident.incident_id));
  return button;
}

function table(headers) {
  const t = element('table');
  const head = element('thead');
  const row = element('tr');
  for (const text of headers) { const th = element('th', '', text); th.scope = 'col'; row.append(th); }
  head.append(row);
  const body = element('tbody');
  t.append(head, body);
  return [t, body];
}

function incidentTable(target, items) {
  if (!items.length) return empty(target, 'No incidents to display', 'Try another filter, or wait for a monitoring alert.');
  const [t, body] = table(['SERVICE / INCIDENT', 'SEVERITY', 'OBSERVED METRICS', 'INVESTIGATION', 'CREATED']);
  for (const item of items) {
    const tr = element('tr');
    const name = element('td'); name.append(serviceButton(item), element('span', 'incident-id', `INC-${item.id} · ${item.status}`));
    const severity = element('td'); severity.append(badge(item.severity));
    const metrics = element('td', 'measurements', `${item.error_rate}% error rate`); metrics.append(element('small', '', `${item.latency} ms latency`));
    const job = element('td'); job.append(badge(item.job_status));
    tr.append(name, severity, metrics, job, element('td', 'cell-date', formatDate(item.created_at))); body.append(tr);
  }
  target.replaceChildren(t);
}

function jobTable(items) {
  if (!items.length) return empty($('job-table'), 'No investigation jobs found', 'Historical incidents may not have an automatic job.');
  const [t, body] = table(['SERVICE / JOB', 'STATUS', 'ATTEMPTS', 'LAST UPDATE', 'FAILURE CATEGORY']);
  for (const item of items) {
    const tr = element('tr');
    const name = element('td'); name.append(serviceButton({service: item.service, id: item.incident_id}), element('span', 'incident-id', `JOB-${item.id} · INC-${item.incident_id}`));
    const status = element('td'); status.append(badge(item.status));
    tr.append(name, status, element('td', 'measurements', `${item.attempts} / ${item.max_attempts}`), element('td', 'cell-date', formatDate(item.updated_at)), element('td', '', item.error_category || '—'));
    body.append(tr);
  }
  $('job-table').replaceChildren(t);
}

function pagination(target, page, change) {
  const start = page.total ? page.offset + 1 : 0;
  const info = element('span', '', `${start}–${Math.min(page.offset + page.limit, page.total)} of ${page.total}`);
  const previous = element('button', 'secondary', '← Previous'); previous.disabled = page.offset === 0;
  previous.addEventListener('click', () => change(Math.max(0, page.offset - page.limit)));
  const next = element('button', 'secondary', 'Next →'); next.disabled = page.offset + page.limit >= page.total;
  next.addEventListener('click', () => change(page.offset + page.limit));
  target.replaceChildren(info, previous, next);
}

function renderStats(data) {
  for (const [id, key] of [['total', 'total_incidents'], ['open', 'open_incidents'], ['critical', 'critical_incidents'], ['warning', 'warning_incidents']]) $('stat-' + id).textContent = data[key].toLocaleString();
  const total = Object.values(data.jobs).reduce((a, b) => a + b, 0);
  const rows = [];
  const cards = [];
  for (const [status, count] of Object.entries(data.jobs)) {
    const row = element('div', 'pipeline-row');
    // A data attribute avoids inline styles under the strict CSP. Use a native meter.
    const meter = element('meter', `job-meter ${status}`); meter.min = 0; meter.max = Math.max(1, total); meter.value = count; meter.setAttribute('aria-label', `${labels[status]}: ${count} jobs`);
    row.append(element('span', '', labels[status]), meter, element('strong', '', count)); rows.push(row);
    const card = element('article', 'stat-card'); card.append(badge(status), element('strong', '', count), element('small', '', 'Automatic investigation jobs')); cards.push(card);
  }
  $('pipeline').replaceChildren(...rows); $('job-stats').replaceChildren(...cards);
}

export function renderInvestigation(item) {
  const card = element('article', 'investigation');
  card.id = 'investigation-' + item.id;
  const meta = element('div', 'detail-meta');
  meta.append(element('span', '', `INV-${item.id}`), element('span', '', formatDate(item.created_at)), element('span', 'badge neutral', `${item.confidence} confidence`));
  card.append(meta, element('h4', '', 'Observed evidence'));
  const evidence = element('ul');
  for (const line of Array.isArray(item.evidence) ? item.evidence : []) evidence.append(element('li', '', line));
  card.append(evidence, element('h4', '', 'AI hypothesis · not a confirmed root cause'), element('p', '', item.suspected_root_cause), element('h4', '', 'Recommended next steps · not executed'), element('p', '', item.recommended_action));
  card.append(element('div', 'review-note', item.requires_human_approval ? '◇ Human approval required. No automatic remediation.' : 'Human approval flag was not set on this historical record. No actions are executed here.'));
  return card;
}

function detailContent(data, history) {
  const incident = data.incident;
  const header = element('header', 'detail-header'); header.append(element('span', 'incident-id', `INC-${incident.id}`), element('h2', '', incident.service)); header.lastChild.id = 'detail-title';
  const meta = element('div', 'detail-meta'); meta.append(badge(incident.severity), badge(incident.status), element('span', '', formatDate(incident.created_at))); header.append(meta);
  const askButton = element('button', 'secondary ask-incident', 'Ask assistant about this incident');
  askButton.addEventListener('click', () => {scopeAssistant(incident.id); $('detail-dialog').close(); navigate('assistant');});
  header.append(askButton);
  const facts = element('section', 'detail-section'); facts.append(element('h3', '', 'Observed facts'));
  const grid = element('div', 'fact-grid');
  for (const [label, value] of [['Error rate', `${incident.error_rate}%`], ['Latency', `${incident.latency} ms`]]) { const fact = element('div', 'fact'); fact.append(element('span', '', label), element('strong', '', value)); grid.append(fact); }
  facts.append(grid);
  const job = element('section', 'detail-section'); job.append(element('h3', '', 'Automatic investigation'));
  if (data.job) {
    const info = element('div', 'job-detail'); info.append(badge(data.job.status), element('span', '', `Attempt ${data.job.attempts} of ${data.job.max_attempts}`), element('span', '', `Updated ${formatDate(data.job.updated_at)}`)); job.append(info);
    if (data.job.error_category) job.append(element('p', 'detail-note', `Failure category: ${data.job.error_category}. The worker applies its bounded retry policy; no action is taken by this console.`));
  } else job.append(element('p', 'detail-note', 'No automatic job exists for this incident. Historical incidents are not backfilled.'));
  const investigations = element('section', 'detail-section'); investigations.append(element('h3', '', `Investigation history (${history.total})`), element('p', 'detail-note', 'Metrics are observed facts. AI-generated hypotheses and recommendations require review.'));
  if (history.items.length) for (const item of history.items) investigations.append(renderInvestigation(item));
  else investigations.append(element('p', 'empty-state', 'No saved investigation yet. Job progress will update here.'));
  const pages = element('div', 'pagination'); pagination(pages, history, offset => {state.historyOffset = offset; loadDetail();}); investigations.append(pages);
  $('detail-content').replaceChildren(header, facts, job, investigations);
}

async function loadDetail() {
  const id = state.selected;
  const offset = state.historyOffset;
  if (id == null) return;
  try {
    const [detail, history] = await Promise.all([requestJSON(`/dashboard/api/incidents/${id}`), requestJSON(`/dashboard/api/incidents/${id}/history?limit=5&offset=${offset}`)]);
    if (state.selected === id && state.historyOffset === offset) detailContent(detail, history);
  } catch (error) {
    if (error.status === 401) return showLogin('Your session has expired. Please sign in again.');
    if (state.selected === id) { $('detail-content').querySelector('.detail-error')?.remove(); const notice = element('p', 'notice error-notice detail-error', error.message); $('detail-content').prepend(notice); }
  }
}

async function openDetail(id, investigationId = null) {
  state.selected = id; state.historyOffset = 0;
  empty($('detail-content'), 'Loading incident…', 'Retrieving observed metrics and saved investigations.');
  if (!$('detail-dialog').open) $('detail-dialog').showModal();
  await loadDetail();
  if (investigationId) document.getElementById('investigation-' + investigationId)?.scrollIntoView({block: 'center'});
}

function showLogin(message = '') {
  state.authenticated = false; state.csrf = null; state.requestVersion++;
  resetAssistant();
  clearTimeout(state.timer); $('workspace').hidden = true; $('login').hidden = false;
  $('detail-dialog').close(); state.selected = null; $('detail-content').replaceChildren();
  for (const id of ['recent-table', 'incident-table', 'job-table', 'pipeline', 'job-stats', 'incident-pagination', 'job-pagination']) $(id).replaceChildren();
  for (const id of ['total', 'open', 'critical', 'warning']) $('stat-' + id).textContent = '\u2014';
  state.lastSuccess = null;
  $('password').value = ''; $('login-error').textContent = message;
}

function schedule() {
  clearTimeout(state.timer);
  if (state.authenticated && !document.hidden && state.view !== 'assistant') state.timer = setTimeout(refresh, 8000);
}

async function refresh() {
  if (state.view === 'assistant') {clearTimeout(state.timer); return;}
  if (state.busy || !state.authenticated || document.hidden) return;
  state.busy = true; $('refresh').disabled = true;
  const version = state.requestVersion;
  const view = state.view;
  $('refresh-status').textContent = state.lastSuccess ? 'Refreshing · previous data remains visible' : 'Loading your workspace…';
  try {
    const queries = [requestJSON('/dashboard/api/overview')];
    if (view === 'overview') queries.push(requestJSON('/dashboard/api/incidents?limit=6'));
    if (view === 'incidents') {
      const params = new URLSearchParams({limit: 20, offset: state.offset, service: $('service-filter').value});
      if ($('severity-filter').value) params.set('severity', $('severity-filter').value);
      if ($('status-filter').value) params.set('status', $('status-filter').value);
      queries.push(requestJSON('/dashboard/api/incidents?' + params));
    }
    if (view === 'automation') {
      const params = new URLSearchParams({limit: 20, offset: state.jobOffset});
      if ($('job-filter').value) params.set('status', $('job-filter').value);
      queries.push(requestJSON('/dashboard/api/jobs?' + params));
    }
    const [summary, page] = await Promise.all(queries);
    if (version !== state.requestVersion) return;
    renderStats(summary);
    if (view === 'overview') incidentTable($('recent-table'), page.items);
    if (view === 'incidents') { incidentTable($('incident-table'), page.items); pagination($('incident-pagination'), page, offset => {state.offset = offset; refresh();}); }
    if (view === 'automation') {jobTable(page.items); pagination($('job-pagination'), page, offset => {state.jobOffset = offset; refresh();});}
    state.lastSuccess = new Date(); $('data-error').hidden = true;
    $('refresh-status').textContent = `Last successful refresh · ${state.lastSuccess.toLocaleTimeString()}`;
    if (state.selected !== null) await loadDetail();
  } catch (error) {
    if (version !== state.requestVersion) return;
    if (error.status === 401) return showLogin('Your session has expired. Please sign in again.');
    $('data-error').hidden = false; $('data-error').textContent = error.message;
    $('refresh-status').textContent = state.lastSuccess ? `Stale data · last success ${state.lastSuccess.toLocaleTimeString()}` : 'No successful refresh yet';
  } finally {
    state.busy = false; $('refresh').disabled = false;
    if (version !== state.requestVersion && state.authenticated) refresh(); else schedule();
  }
}

function navigate(view) {
  state.view = view; state.requestVersion++;
  const content = {
    assistant: ['Assistant', 'Your operations assistant', 'CONVERSATION, GROUNDED IN EVIDENCE', 'Ask about incidents, investigations and runbooks. Read-only, cited and under your control.'],
    overview: ['Overview', 'Operations overview', 'YOUR OPERATIONS, IN FOCUS', 'A clear view of your incidents and AI investigation pipeline.'],
    incidents: ['Incident explorer', 'Incident explorer', 'FOLLOW THE EVIDENCE', 'Explore service signals, observed facts and saved AI investigations.'],
    automation: ['Automation monitor', 'Automation monitor', 'FROM SIGNAL TO SAVED INSIGHT', 'Follow durable investigation jobs through every attempt.']
  }[view];
  $('breadcrumb').textContent = content[0]; $('page-title').replaceChildren(document.createTextNode(content[1]), element('span', 'accent', '.')); $('page-eyebrow').textContent = content[2]; $('page-description').textContent = content[3];
  for (const node of document.querySelectorAll('[data-view]')) { if (node.dataset.view === view) node.setAttribute('aria-current', 'page'); else node.removeAttribute('aria-current'); }
  for (const name of ['overview', 'incidents', 'automation', 'assistant']) $(name + '-view').hidden = name !== view;
  $('refresh').hidden = view === 'assistant';
  document.querySelector('.poll-label').hidden = view === 'assistant';
  if (view === 'assistant') {clearTimeout(state.timer); $('refresh-status').textContent = 'Session-only history \u00b7 fresh evidence retrieved for each question'; enterAssistant();} else refresh();
}

function authenticated(session) {
  state.csrf = session.csrf_token; state.authenticated = true;
  $('password').value = ''; $('login').hidden = true; $('workspace').hidden = false;
  if (state.view === 'assistant') enterAssistant(); else refresh();
}

async function boot() {
  initAssistant({element, requestJSON, getCSRF: () => state.csrf, openIncident: openDetail, onAuthFailure: () => showLogin('Your session has expired. Please sign in again.')});
  for (const node of document.querySelectorAll('[data-view]')) node.addEventListener('click', () => navigate(node.dataset.view));
  $('view-all').addEventListener('click', () => navigate('incidents'));
  $('open-automation').addEventListener('click', () => navigate('automation'));
  $('refresh').addEventListener('click', refresh);
  $('close-detail').addEventListener('click', () => $('detail-dialog').close());
  $('detail-dialog').addEventListener('close', () => {state.selected = null; state.historyOffset = 0;});
  $('incident-filters').addEventListener('submit', event => {event.preventDefault(); state.offset = 0; state.requestVersion++; refresh();});
  $('incident-filters').addEventListener('reset', () => setTimeout(() => {state.offset = 0; state.requestVersion++; refresh();}, 0));
  $('job-filter').addEventListener('change', () => {state.jobOffset = 0; state.requestVersion++; refresh();});
  document.addEventListener('visibilitychange', () => {if (document.hidden) clearTimeout(state.timer); else refresh();});
  $('login-form').addEventListener('submit', async event => {
    event.preventDefault(); $('login-submit').disabled = true; $('login-error').textContent = '';
    try {authenticated(await requestJSON('/dashboard/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({password: $('password').value})}));}
    catch (error) {$('password').value = ''; $('login-error').textContent = error.status === 401 ? 'Incorrect dashboard password. Please try again.' : error.message;}
    finally {$('login-submit').disabled = false;}
  });
  $('logout').addEventListener('click', async () => {
    try {await requestJSON('/dashboard/logout', {method: 'POST', headers: {'X-CSRF-Token': state.csrf}}); showLogin();}
    catch (error) {if (error.status === 401) showLogin(); else {$('data-error').hidden = false; $('data-error').textContent = error.message;}}
  });
  try {authenticated(await requestJSON('/dashboard/session'));}
  catch (error) {showLogin(error.status === 401 ? '' : error.message);}
}

if (typeof document !== 'undefined' && document.getElementById('login')) boot();
