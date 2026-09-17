import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const geoModulePath = join(root, 'apps/mobile-web/src/utils/geolocation.ts');

assert.equal(existsSync(geoModulePath), true, 'geolocation utility module must exist');

const temporaryDirectory = mkdtempSync(join(tmpdir(), 'restaurantos-mobile-gps-'));
process.on('exit', () => rmSync(temporaryDirectory, { recursive: true, force: true }));

const {
  parseReverseGeocodeResponse,
  formatGpsAddressNotes,
  reverseGeocode,
} = await (async () => {
  execFileSync(
    process.execPath,
    [
      join(root, 'node_modules/typescript/bin/tsc'),
      '--target', 'ES2022', '--module', 'NodeNext', '--moduleResolution', 'NodeNext',
      '--outDir', temporaryDirectory, geoModulePath,
    ],
    { cwd: root, stdio: 'pipe' },
  );
  return import(pathToFileURL(join(temporaryDirectory, 'geolocation.js')).href);
})();

test('parseReverseGeocodeResponse correctly extracts street, number, neighborhood from OpenStreetMap Nominatim', () => {
  const mockNominatim = {
    address: {
      road: 'Avenida Álvaro Obregón',
      house_number: '168',
      neighbourhood: 'Roma Norte',
      suburb: 'Cuauhtémoc',
      city: 'Ciudad de México',
      postcode: '06700',
    },
    display_name: '168, Avenida Álvaro Obregón, Roma Norte, Cuauhtémoc, Ciudad de México, 06700, México',
  };

  const result = parseReverseGeocodeResponse(mockNominatim, 19.418245, -99.162381);

  assert.equal(result.street, 'Avenida Álvaro Obregón');
  assert.equal(result.number, '168');
  assert.equal(result.neighborhood, 'Roma Norte');
  assert.equal(result.city, 'Ciudad de México');
  assert.equal(result.postalCode, '06700');
  assert.equal(result.mapsUrl, 'https://maps.google.com/?q=19.418245,-99.162381');
});

test('parseReverseGeocodeResponse handles missing house_number gracefully', () => {
  const mockPartial = {
    address: {
      road: 'Calle Colima',
      suburb: 'Roma Norte',
      city: 'Ciudad de México',
    },
  };

  const result = parseReverseGeocodeResponse(mockPartial, 19.419, -99.161);

  assert.equal(result.street, 'Calle Colima');
  assert.equal(result.number, '');
  assert.equal(result.neighborhood, 'Roma Norte');
  assert.equal(result.mapsUrl, 'https://maps.google.com/?q=19.419000,-99.161000');
});

test('formatGpsAddressNotes appends satellite navigation pin without duplicating', () => {
  const mapsUrl = 'https://maps.google.com/?q=19.418245,-99.162381';

  // Empty initial notes
  const note1 = formatGpsAddressNotes('', mapsUrl);
  assert.equal(note1, '📍 GPS: https://maps.google.com/?q=19.418245,-99.162381');

  // Existing custom note
  const note2 = formatGpsAddressNotes('Portón café, timbre blanco', mapsUrl);
  assert.equal(note2, 'Portón café, timbre blanco • 📍 GPS: https://maps.google.com/?q=19.418245,-99.162381');

  // Re-running GPS must not duplicate maps link
  const note3 = formatGpsAddressNotes(note2, mapsUrl);
  assert.equal(note3, note2);
});

test('reverseGeocode falls back to satellite coordinates url when external geocoding fails', async () => {
  const failingFetch = async () => {
    throw new Error('Network error / offline');
  };

  const fallbackResult = await reverseGeocode(19.4000, -99.1500, failingFetch);

  assert.equal(fallbackResult.mapsUrl, 'https://maps.google.com/?q=19.400000,-99.150000');
  assert.equal(typeof fallbackResult.formattedSummary, 'string');
});
