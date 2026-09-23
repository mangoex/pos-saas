// Run with connected Browser tabs against pickup-grace-fixture.mjs.
import assert from 'node:assert/strict';

export async function configurePickup(admin, value) {
  const input = admin.playwright.getByRole('textbox', { name: 'Tiempo disponible después de la hora programada (minutos)', exact: true });
  if (value === '') {
    await input.press('Control+A');
    await input.press('Backspace');
  } else await input.fill(value);
  await admin.playwright.getByRole('button', { name: 'Guardar Configuración', exact: true }).click();
}

export async function verifyPickupNotice(client, expected) {
  const snapshot = await client.playwright.domSnapshot();
  if (expected == null) assert.doesNotMatch(snapshot, /Respetaremos tu pedido/);
  else assert.match(snapshot, new RegExp(`Respetaremos tu pedido durante ${expected} minutos después de tu hora programada`));
}
