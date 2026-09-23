import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const temporaryDirectory = mkdtempSync(join(tmpdir(), 'restaurantos-mobile-modifiers-'));
const productSnapshot = {
  id: 'product-1',
  name: 'Tacos de asada',
  sku: '1234567890123456',
  category_name: 'Tacos',
  station: 'kitchen',
  price_cents: 3499,
  image_url: null,
  status: 'active',
  is_promo: false,
  promo_price_cents: null,
  promo_badge_text: null,
};

try {
  const helperPath = join(root, 'apps/admin-web/src/features/mobile-admin/simpleModifiers.ts');
  execFileSync(process.execPath, [
    join(root, 'node_modules/typescript/bin/tsc'),
    '--target', 'ES2022', '--module', 'CommonJS', '--moduleResolution', 'Node',
    '--outDir', temporaryDirectory, helperPath,
    join(root, 'apps/admin-web/src/features/catalog/ingredientVariationMoney.ts'),
  ], { cwd: root, stdio: 'pipe' });
  const helper = await import(pathToFileURL(join(temporaryDirectory, 'mobile-admin/simpleModifiers.js')).href);

  assert.deepEqual(helper.parseSimpleModifierText('Queso extra, 12.50\nTocino'), [
    { name: 'Queso extra', price_delta_cents: 1250 },
    { name: 'Tocino', price_delta_cents: 0 },
  ]);
  assert.deepEqual(helper.parseSimpleModifierText('Queso, '), [
    { name: 'Queso', price_delta_cents: 0 },
  ], 'an omitted price is free');
  assert.deepEqual(helper.parseSimpleModifierText(' \n\t'), [], 'blank text clears the simple options');
  assert.throws(() => helper.parseSimpleModifierText(', 4'), /nombre/i);
  assert.throws(() => helper.parseSimpleModifierText('Queso, -1'), /importe|precio/i);
  assert.throws(() => helper.parseSimpleModifierText('Queso, 1.001'), /importe|precio/i);
  assert.throws(() => helper.parseSimpleModifierText('Queso, 1x'), /importe|precio/i);
  assert.throws(() => helper.parseSimpleModifierText('Queso, 1, promo'), /coma/i);
  assert.throws(() => helper.parseSimpleModifierText('Queso\n queso, 1'), /duplicad/i);
  assert.equal(helper.parseSimpleModifierText(`${'a'.repeat(120)}`)[0].name.length, 120);
  assert.throws(() => helper.parseSimpleModifierText('a'.repeat(121)), /120 caracteres/i);
  assert.equal(helper.parseSimpleModifierText(Array.from({ length: 100 }, (_, i) => `Opción ${i + 1}`).join('\n')).length, 100);
  assert.throws(() => helper.parseSimpleModifierText(Array.from({ length: 101 }, (_, i) => `Opción ${i + 1}`).join('\n')), /hasta 100/i);
  assert.equal(helper.parseSimpleModifierText('Límite, 21474836.47')[0].price_delta_cents, 2147483647);
  assert.throws(() => helper.parseSimpleModifierText('Excede, 21474836.48'), /máximo permitido/i);
  assert.throws(() => helper.parseSimpleModifiersResponse({
    options: [{ name: 'Excede', price_delta_cents: 2147483648 }], revision: 'bad', editable: true,
  }), /respuesta incluye un modificador no válido/i);

  const loadedResponse = helper.parseSimpleModifiersResponse({
    options: [{ name: 'Extra queso', price_delta_cents: 250 }],
    revision: 'rev-5',
    editable: true,
    product: productSnapshot,
  });
  assert.deepEqual(loadedResponse.product, productSnapshot);
  assert.deepEqual(helper.productSnapshotToForm(loadedResponse.product), {
    name: 'Tacos de asada', sku: '1234567890123456', category_name: 'Tacos', station: 'kitchen',
    price: '34.99', is_promo: false, promo_price: '', promo_badge_text: '', image_url: '', status: 'active',
  });
  const promoBaseline = {
    ...productSnapshot,
    is_promo: true,
    promo_price_cents: 1299,
    promo_badge_text: null,
  };
  const promoForm = helper.productSnapshotToForm(promoBaseline);
  assert.equal(promoForm.promo_badge_text, '', 'a null promo badge must remain blank in the form');
  const promoBaselineFields = Object.fromEntries(Object.entries(promoBaseline).filter(([key]) => key !== 'id'));
  const modifierOnlyPut = {
    ...helper.buildProductFieldsForSave(promoForm, 3499, 1299, promoBaselineFields),
    simple_modifiers: helper.buildSimpleModifiersPayload('Extra queso, 2.50', 'rev-5'),
  };
  assert.deepEqual(modifierOnlyPut, {
    simple_modifiers: {
      options: [{ name: 'Extra queso', price_delta_cents: 250 }],
      expected_revision: 'rev-5',
    },
  }, 'saving only Extras must omit every unchanged product field, including nullable promo badge');
  const nullPriceProduct = { ...productSnapshot, price_cents: null };
  assert.equal(helper.productSnapshotToForm(nullPriceProduct).price, '', 'a null base price must stay blank');
  assert.throws(() => helper.positiveMxnToCentsExact(helper.productSnapshotToForm(nullPriceProduct).price, 'Precio'), /válido/i);
  assert.equal(helper.positiveMxnToCentsExact('12.99', 'Precio'), 1299);
  assert.throws(() => helper.positiveMxnToCentsExact('0', 'Precio'), /mayor a \$0\.00/i);
  assert.throws(() => helper.positiveMxnToCentsExact('12.999', 'Precio'), /máximo dos decimales/i);
  assert.throws(() => helper.parseSimpleModifiersResponse({
    options: [], revision: 'rev-5', editable: true,
  }), /producto actualizado/i);

  const baselineFields = Object.fromEntries(Object.entries(productSnapshot).filter(([key]) => key !== 'id'));
  assert.deepEqual(helper.buildChangedProductFields(baselineFields, baselineFields), {}, 'unchanged product fields must be omitted from PUT');
  assert.deepEqual(
    helper.buildChangedProductFields({ ...baselineFields, price_cents: 3599 }, baselineFields),
    { price_cents: 3599 },
    'only the changed price should enter a PUT payload when price alone changed',
  );

  assert.deepEqual(helper.buildSimpleModifiersPayload('Tocino, 8.25', 'rev-4'), {
    options: [{ name: 'Tocino', price_delta_cents: 825 }],
    expected_revision: 'rev-4',
  });
  assert.match(helper.newDraftProductSku(() => '00000000-0000-4000-8000-123456789abc'), /^\d{12,16}$/);

  const sequence = { current: 0 };
  const appliedRevisions = [];
  const requestErrors = [];
  let resolveOlderRequest;
  const olderRequest = helper.runLatestSimpleModifiersRequest(
    sequence,
    () => new Promise((resolve) => { resolveOlderRequest = resolve; }),
    (response) => appliedRevisions.push(response.revision),
    (error) => requestErrors.push(error),
  );
  const newerRequest = helper.runLatestSimpleModifiersRequest(
    sequence,
    async () => ({ options: [], revision: 'newer', editable: true, product: productSnapshot }),
    (response) => appliedRevisions.push(response.revision),
    (error) => requestErrors.push(error),
  );
  await newerRequest;
  resolveOlderRequest({ options: [], revision: 'older', editable: true, product: productSnapshot });
  await olderRequest;
  assert.deepEqual(appliedRevisions, ['newer'], 'a stale response must not overwrite the active product');
  assert.deepEqual(requestErrors, []);

  let retainedText = 'Bacon, 8.25';
  let loadFailure;
  await helper.runLatestSimpleModifiersRequest(
    sequence,
    async () => { throw new Error('offline'); },
    () => { retainedText = ''; },
    (error) => { loadFailure = error; },
  );
  assert.equal(retainedText, 'Bacon, 8.25', 'a load failure must leave the current editor text untouched');
  assert.match(loadFailure.message, /offline/);

  const component = readFileSync(join(root, 'apps/admin-web/src/features/mobile-admin/MobileMenuManagerTab.tsx'), 'utf8');
  assert.match(component, /\/products\/\$\{productId\}\/simple-modifiers/);
  assert.match(component, /runLatestSimpleModifiersRequest/);
  assert.doesNotMatch(component, /modifier-groups\//, 'the mobile editor must not replace advanced modifier groups');
  assert.match(component, /simple_modifiers:\s*buildSimpleModifiersPayload/);
  assert.match(component, /buildProductFieldsForSave/);
  assert.match(component, /setProductForm\(productSnapshotToForm\(response\.product\)\)/);
  assert.match(component, /simpleModifiersEditable/);
  assert.match(component, /Reintentar/);
  assert.match(component, /Modificadores simples/);
  assert.match(component, /<textarea[\s\S]*?aria-label="Modificadores simples"/);
  assert.match(component, /modifierLoadStatus !== 'loaded'/);
  assert.match(component, /El producto se archivará como agotado/);
  assert.match(component, /value=\{productForm\.sku\}[\s\S]*?setProductForm\(\{ \.\.\.productForm, sku:/);
  assert.equal((component.match(/step="0\.01"/g) ?? []).length, 2, 'base and promo prices must accept one-cent increments');
  assert.equal((component.match(/min="0\.01"/g) ?? []).length, 2, 'base and promo prices must require positive values');
  assert.doesNotMatch(component, /Math\.round\(\(parseFloat\(form\.(?:price|promo_price)/);
} finally {
  rmSync(temporaryDirectory, { recursive: true, force: true });
}

console.log('✓ Mobile product modifier semantic tests passed');
