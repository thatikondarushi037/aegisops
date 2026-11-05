// No model HTML, model links, localStorage or browser API credentials.
let config;
let turns = [];
let busy = false;
let generation = 0;
const $ = id => document.getElementById(id);
const categories = {observation: 'Observed / recorded', hypothesis: 'Saved hypothesis · unconfirmed', recommendation: 'Suggested checks · review required', limitation: 'Evidence boundary'};

export function renderAssistantTurn(turn, element, openIncident) {
  const wrapper = element('div', 'assistant-turn');
  const user = element('article', 'chat-message user-message');
  user.append(element('span', 'message-author', 'YOU'), element('p', '', turn.message));
  const assistant = element('article', 'chat-message assistant-message');
  assistant.append(element('span', 'message-author', 'AEGIS ASSISTANT'), element('p', 'assistant-introduction', turn.answer.introduction));
  for (const fact of turn.answer.facts) {
    const category = Object.hasOwn(categories, fact.category) ? fact.category : 'limitation';
    const card = element('section', 'assistant-fact ' + category);
    card.append(element('h3', '', categories[category]), element('p', '', fact.text));
    if (Number.isInteger(fact.incident_id) && fact.incident_id > 0) {
      const reference = element('button', 'source-reference', fact.source + ' ↗');
      reference.type = 'button';
      reference.addEventListener('click', () => openIncident(fact.incident_id, fact.investigation_id));
      card.append(reference);
    } else card.append(element('span', 'source-reference source-label', fact.runbook_source ? 'Runbook source · ' + fact.runbook_source : fact.source));
    assistant.append(card);
  }
  assistant.append(element('p', 'assistant-notice', turn.answer.notice));
  const audit = element('span', 'tool-audit', 'Read-only retrieval · ' + turn.answer.tools_used.join(' → '));
  assistant.append(audit);
  if (turn.answer.status === 'degraded') assistant.append(element('span', 'badge warning', 'Verified fallback · AI or retrieval unavailable'));
  wrapper.append(user, assistant);
  return wrapper;
}

function render() {
  const h = config.element;
  const content = turns.map(turn => renderAssistantTurn(turn, h, config.openIncident));
  if (!content.length) {
    const empty = h('div', 'assistant-welcome');
    empty.append(h('span', 'assistant-emblem', '✧'), h('h2', '', 'Ask a question. Follow the evidence.'), h('p', '', 'Explore actual incidents, saved investigations and local runbooks. Every answer stays inside a read-only boundary.'));
    content.push(empty);
  }
  if (busy) {
    const loading = h('div', 'assistant-loading', 'Retrieving records and checking relevant evidence…');
    loading.setAttribute('role', 'status'); content.push(loading);
  }
  $('assistant-messages').replaceChildren(...content);
  $('assistant-send').disabled = busy;
  $('assistant-clear').disabled = busy;
  $('assistant-input').disabled = busy;
  $('assistant-context').disabled = busy;
  for (const button of document.querySelectorAll('[data-assistant-prompt]')) button.disabled = busy;
  $('assistant-send').textContent = busy ? 'Working…' : 'Send question ↗';
}

function error(message) {
  $('assistant-error').textContent = message;
  $('assistant-error').hidden = !message;
}

export function resetAssistant() {
  generation++; turns = []; busy = false;
  if (config) {
    $('assistant-input').value = ''; $('assistant-context').value = ''; error(''); render();
  }
}

export function scopeAssistant(id) {
  $('assistant-context').value = id;
  $('assistant-input').value = 'What happened to this incident, and what evidence supports its investigation?';
}

export async function enterAssistant() {
  if (!config || busy) return;
  const version = generation;
  error('');
  try {
    const data = await config.requestJSON('/dashboard/api/assistant');
    if (version !== generation) return;
    turns = data.turns;
    if (!$('assistant-context').value && data.context_incident_id) $('assistant-context').value = data.context_incident_id;
    render();
  } catch (err) {
    if (version !== generation) return;
    if (err.status === 401) config.onAuthFailure(); else error(err.message);
  }
}

async function sendQuestion() {
  if (busy || !$('assistant-form').reportValidity()) return;
  const message = $('assistant-input').value.trim();
  if (!message) return;
  const id = $('assistant-context').value ? Number($('assistant-context').value) : null;
  const version = generation;
  busy = true; error(''); render();
  $('assistant-messages').scrollTop = $('assistant-messages').scrollHeight;
  try {
    const turn = await config.requestJSON('/dashboard/api/assistant', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': config.getCSRF()},
      body: JSON.stringify({message, incident_id: id})
    }, 75000);
    if (version !== generation) return;
    turns = [...turns, turn].slice(-6);
    $('assistant-input').value = '';
    $('assistant-context').value = turn.answer.context_incident_id || '';
  } catch (err) {
    if (version !== generation) return;
    if (err.status === 401) config.onAuthFailure();
    else error(err.status === 409 ? 'A response is still in progress. Wait before sending another question.' : err.message);
  } finally {
    if (version === generation) {
      busy = false; render();
      $('assistant-messages').scrollTop = $('assistant-messages').scrollHeight;
      $('assistant-input').focus();
    }
  }
}

export function initAssistant(options) {
  config = options;
  $('assistant-form').addEventListener('submit', event => {event.preventDefault(); sendQuestion();});
  $('assistant-input').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); sendQuestion();}
  });
  for (const button of document.querySelectorAll('[data-assistant-prompt]')) button.addEventListener('click', () => {
    $('assistant-input').value = button.dataset.assistantPrompt;
    $('assistant-input').focus();
  });
  $('assistant-clear').addEventListener('click', async () => {
    if (busy) return;
    const version = generation;
    try {
      await config.requestJSON('/dashboard/api/assistant/clear', {method: 'POST', headers: {'X-CSRF-Token': config.getCSRF()}});
      if (version === generation) resetAssistant();
    } catch (err) {if (err.status === 401) config.onAuthFailure(); else error(err.message);}
  });
  render();
}
