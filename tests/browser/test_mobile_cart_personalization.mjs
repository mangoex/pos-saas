// Run with the Browser skill's already-connected tab (Node REPL).
// Start mobile-cart-fixture.mjs first. No standalone browser or production API.
import assert from 'node:assert/strict';

export async function verifyCartEditing(tab) {
  const ui = tab.playwright;
  await ui.getByRole('button', { name: 'Agregar Capuchino 12oz al pedido', exact: true }).click();
  await ui.getByRole('button', { name: 'Abrir carrito de compras', exact: true }).click();
  assert.match(await ui.domSnapshot(), /Sin personalizar/);
  await ui.getByRole('textbox', { name: 'Nombre completo', exact: true }).fill('Persona QA');
  await ui.getByRole('dialog', { name: 'Carrito de compras', exact: true })
    .getByRole('button', { name: 'Personaliza Capuchino 12oz', exact: true }).click();
  await ui.getByRole('button', { name: 'Leche de aceituna (+$25.00 MXN)', exact: true }).click();
  await ui.getByRole('dialog', { name: 'Editar producto', exact: true })
    .getByRole('button', { name: 'Aumentar cantidad', exact: true }).click();
  await ui.getByRole('textbox', { name: 'Instrucciones Especiales', exact: true }).fill('Tibio QA');
  await ui.getByRole('button', { name: 'Guardar cambios • $160.00 MXN', exact: true }).click();
  let snapshot = await ui.domSnapshot();
  assert.match(snapshot, /1 producto seleccionado/);
  assert.match(snapshot, /\$160\.00 MXN/);
  assert.match(snapshot, /Tibio QA/);
  assert.match(snapshot, /Persona QA/);
  await ui.getByRole('button', { name: 'Editar personalización de Capuchino 12oz', exact: true }).click();
  await ui.getByRole('button', { name: 'Leche de aceituna (+$25.00 MXN)', exact: true }).click();
  await ui.getByRole('textbox', { name: 'Instrucciones Especiales', exact: true }).press('Escape');
  snapshot = await ui.domSnapshot();
  assert.match(snapshot, /\$160\.00 MXN/);
  assert.match(snapshot, /Tibio QA/);
  await ui.getByRole('button', { name: 'Editar personalización de Capuchino 12oz', exact: true }).click();
  await ui.getByRole('button', { name: 'Leche de aceituna (+$25.00 MXN)', exact: true }).click();
  await ui.getByRole('button', { name: 'Azúcar mascabado', exact: true }).click();
  await ui.getByRole('button', { name: 'Guardar cambios • $110.00 MXN', exact: true }).click();
  snapshot = await ui.domSnapshot();
  assert.match(snapshot, /Azúcar mascabado/);
  assert.match(snapshot, /\$110\.00 MXN/);
  assert.doesNotMatch(snapshot, /Sin personalizar/);
  assert.match(snapshot, /Persona QA/);
  return 'PASS: quick-add, draft/save, cancel, exact total, free selection, checkout name retained';
}
