import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';

const source = readFileSync(new URL('../frontend/app.js', import.meta.url));
const ui = await import('data:text/javascript;base64,' + source.toString('base64'));

class SafeNode {
  constructor(tag) {this.tagName = tag; this.children = []; this.value = '';}
  set innerHTML(_) {throw new Error('Unsafe HTML sink used');}
  set textContent(value) {this.value = String(value); this.children = [];}
  get textContent() {return this.value + this.children.map(x => x.textContent).join('');}
  append(...nodes) {this.children.push(...nodes);}
}

test('all job statuses have distinct rendered labels and safe classes', () => {
  globalThis.document = {createElement: tag => new SafeNode(tag)};
  for (const status of ['pending', 'running', 'completed', 'failed']) {
    const node = ui.badge(status);
    assert.equal(node.className, 'badge ' + status);
    assert.match(node.textContent.toLowerCase(), new RegExp(status));
  }
  assert.equal(ui.badge('<script>attack</script>').className, 'badge neutral');
});

test('malicious AI text remains literal text, never executable markup', () => {
  globalThis.document = {createElement: tag => new SafeNode(tag)};
  const attack = '<img src=x onerror="globalThis.compromised=true"><script>evil()</script>';
  const card = ui.renderInvestigation({id: 1, created_at: 'invalid', confidence: 'low', suspected_root_cause: attack, evidence: [attack], recommended_action: attack, requires_human_approval: true});
  assert.ok(card.textContent.includes(attack));
  assert.equal(globalThis.compromised, undefined);
  assert.ok(card.textContent.includes('Human approval required'));
  assert.equal(ui.formatDate('invalid'), 'Unavailable');
});

test('request helper uses same-origin credentials and parses responses', async () => {
  globalThis.fetch = async (path, options) => {
    assert.equal(path, '/dashboard/api/overview');
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.headers.Authorization, undefined);
    return new Response(JSON.stringify({total_incidents: 0}), {status: 200});
  };
  assert.deepEqual(await ui.requestJSON('/dashboard/api/overview'), {total_incidents: 0});
});

test('server errors and malformed responses never expose raw details', async () => {
  globalThis.fetch = async () => new Response('private database credentials', {status: 503});
  await assert.rejects(ui.requestJSON('/dashboard/api/overview'), error => !error.message.includes('private') && error.status === 503);
  globalThis.fetch = async () => new Response('not json', {status: 200});
  await assert.rejects(ui.requestJSON('/dashboard/api/overview'), /Could not load workspace data/);
});

test('request timeout is bounded and presents a useful stale-data message', async () => {
  globalThis.fetch = async (_, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('private timeout', 'AbortError')));
  });
  await assert.rejects(ui.requestJSON('/dashboard/api/overview', {}, 10), /timed out.*retained/);
});
