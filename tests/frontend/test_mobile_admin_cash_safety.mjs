import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  'apps/admin-web/src/features/mobile-admin/MobileCashShiftTab.tsx',
  'utf8',
);

assert.doesNotMatch(
  source,
  /Idempotency-Key': `(?:open|mov|close)-\$\{Date\.now\(\)\}`/,
  'Los comandos de caja no deben rotar su clave al reintentar un resultado incierto.',
);
assert.match(source, /commandKeyStore\(\)/);
assert.match(source, /commandKeys\.current\.get\(/);
assert.match(source, /commandKeys\.current\.clear\(/);
assert.match(source, /const \[movementEvidence, setMovementEvidence\] = useState\(''\)/);
assert.match(source, /evidence_refs: \[movementEvidence\.trim\(\)\]/);
assert.doesNotMatch(
  source,
  /registro-movil\.jpg/,
  'La UI no debe inventar una referencia de evidencia fija.',
);

console.log('mobile admin cash safety semantic checks passed');
