import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const output = mkdtempSync(join(tmpdir(), 'restaurantos-mobile-voice-'));

try {
  const source = join(root, 'apps/mobile-web/src/features/voice/voiceOrderDraft.ts');
  execFileSync(process.execPath, [
    join(root, 'node_modules/typescript/bin/tsc'),
    '--target', 'ES2022',
    '--module', 'NodeNext',
    '--moduleResolution', 'NodeNext',
    '--outDir', output,
    source,
  ]);
  const voice = await import(pathToFileURL(join(output, 'voiceOrderDraft.js')).href);

  assert.equal(voice.appendVoiceTranscript('Dos tacos', 'y una coca'), 'Dos tacos y una coca');
  assert.equal(voice.appendVoiceTranscript('Dos tacos', 'Dos tacos'), 'Dos tacos');

  const product = {
    id: 'p1',
    name: 'Hamburguesa',
    sku: 'H1',
    price_cents: 10000,
    modifier_groups: [{
      id: 'bread',
      name: 'Pan',
      is_required: true,
      minimum_selections: 1,
      maximum_selections: 1,
      options: [{ id: 'whole', name: 'Integral', price_delta_cents: 500, selection_kind: 'modifier' }],
    }],
  };
  const question = {
    line_index: 0,
    group_id: 'bread',
    prompt: 'Elige pan',
    minimum_selections: 1,
    maximum_selections: 1,
    options: [{ id: 'whole', name: 'Integral', price_delta_cents: 500, kind: 'modifier' }],
  };
  const draft = {
    customer_name: '',
    phone: '',
    order_type: null,
    lines: [{ product_id: 'p1', product_name: 'Hamburguesa', quantity: 2, selected_options: [] }],
    questions: [question],
    option_groups: [question],
    status: 'needs_input',
    model: 'synthetic',
  };
  assert.equal(voice.isVoiceDraftComplete(draft), false);
  assert.throws(() => voice.voiceDraftToCartItems(draft, [product], () => 'cart-1'));

  const complete = voice.toggleVoiceDraftOption(draft, question, question.options[0]);
  assert.equal(voice.isVoiceDraftComplete(complete), true);
  const items = voice.voiceDraftToCartItems(complete, [product], () => 'cart-1');
  assert.equal(items[0].line_total_cents, 21000);
  assert.equal(items[0].modifiers[0].option_id, 'whole');
  assert.equal(items[0].modifiers[0].price_delta_cents, 500);

  const modal = readFileSync(join(root, 'apps/mobile-web/src/components/VoiceOrderModal.tsx'), 'utf8');
  assert.match(modal, /publicKey/, 'voice endpoint must use public storefront identity');
  assert.match(modal, /sessionTokenRef/, 'stale speech callbacks must be ignored');
  assert.match(modal, /appendVoiceTranscript/, 'dictation sessions must append without duplicates');
  assert.match(modal, /isVoiceDraftComplete/, 'incomplete required options must block cart application');
  assert.match(modal, /draft\?\.option_groups \?\? draft\?\.questions/, 'all canonical groups must remain editable');
  assert.doesNotMatch(modal, /onAddCartItems:\s*\(newItems:\s*any\[\]/, 'cart boundary must be typed');
} finally {
  rmSync(output, { recursive: true, force: true });
}

console.log('Mobile voice order contract passed');
