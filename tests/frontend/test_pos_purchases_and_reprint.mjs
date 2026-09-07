import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

function testBranchAdminOperationsContainsInteractivePurchases() {
  const fileContent = readFileSync(
    resolve(root, 'apps', 'pos-web', 'src', 'features', 'admin', 'BranchAdminOperations.tsx'),
    'utf-8'
  );

  // Check that BranchAdminPurchases has create, confirm and cancel capabilities
  assert.ok(fileContent.includes('Nueva Compra Directa'), 'Should include button for new direct purchase');
  assert.ok(fileContent.includes('handleConfirm'), 'Should include handleConfirm function for purchase receipts');
  assert.ok(fileContent.includes('handleCancel'), 'Should include handleCancel function for purchase compensations');
  assert.ok(fileContent.includes('paid_from_cash'), 'Should include cash deduction capability');
  assert.ok(fileContent.includes('Partidas de Compra'), 'Should include multi-line items form');
  assert.ok(
    fileContent.includes("const configuredRegisterId = (localStorage.getItem('pos_register_id') || '').trim();"),
    'Branch Admin should resolve its configured register before cash confirmation'
  );
  assert.ok(
    fileContent.includes('...(purchase.paid_from_cash ? { register_id: configuredRegisterId } : {})'),
    'Branch Admin should send register_id only for cash purchases'
  );
  assert.ok(
    fileContent.includes('purchase_confirmation_${purchase.id}'),
    'Branch Admin should retain one idempotency key until confirmation succeeds'
  );

  // Check that BranchAdminSuppliers displays suppliers and presentations directory with central governance note
  assert.ok(fileContent.includes('Directorio de proveedores'), 'Should include suppliers directory');
  assert.ok(fileContent.includes('Presentaciones de compra'), 'Should include presentations directory');
  assert.ok(fileContent.includes('catálogo central permanece en Administración corporativa'), 'Should include central catalog governance note');
}

function testCorporateAdminPurchaseConfirmationUsesTheSameCashContract() {
  const fileContent = readFileSync(
    resolve(root, 'apps', 'admin-web', 'src', 'features', 'purchasing', 'PurchasesList.tsx'),
    'utf-8'
  );

  assert.ok(
    fileContent.includes("const configuredRegisterId = (localStorage.getItem('pos_register_id') || '').trim();"),
    'Admin should resolve its configured register before cash confirmation'
  );
  assert.ok(
    fileContent.includes('...(purchase.paid_from_cash ? { register_id: configuredRegisterId } : {})'),
    'Admin should send register_id only for cash purchases'
  );
  assert.ok(
    fileContent.includes('Configura una caja antes de confirmar una compra en efectivo.'),
    'Admin should fail locally with a clear message when no register is configured'
  );
  assert.ok(
    fileContent.includes('Precio por presentación antes de descuento ($)'),
    'Admin should not call the pre-discount presentation price net'
  );
  assert.ok(
    fileContent.includes('El impuesto no integra el costo de inventario'),
    'Admin should explain the approved inventory cost composition'
  );
  assert.ok(
    fileContent.includes('Sucursal y almacén seleccionados'),
    'Admin should identify the scope of average inventory cost'
  );
}

function testCorporateInventoryAndWarehousesUseCanonicalBranchScope() {
  const appContent = readFileSync(
    resolve(root, 'apps', 'admin-web', 'src', 'App.tsx'),
    'utf-8'
  );
  const layoutContent = readFileSync(
    resolve(root, 'apps', 'admin-web', 'src', 'components', 'AdminLayout.tsx'),
    'utf-8'
  );
  const categorySubNavContent = readFileSync(
    resolve(root, 'apps', 'admin-web', 'src', 'components', 'CategorySubNav.tsx'),
    'utf-8'
  );
  const warehouseContent = readFileSync(
    resolve(root, 'apps', 'admin-web', 'src', 'features', 'branches', 'WarehousesList.tsx'),
    'utf-8'
  );
  const inventoryContent = readFileSync(
    resolve(root, 'apps', 'admin-web', 'src', 'features', 'inventory', 'ItemsList.tsx'),
    'utf-8'
  );

  assert.ok(!categorySubNavContent.includes("path: '/warehouses'"), 'Lite navigation must not expose blocked warehouse setup');
  assert.ok(
    appContent.includes('<Route path="warehouses" element={<ExcludedCommercialModule module="Múltiples almacenes" />} />'),
    'Direct warehouse navigation must explain its commercial exclusion'
  );
  assert.ok(warehouseContent.includes('Cada sucursal conserva un solo almacén'));
  assert.ok(warehouseContent.includes('No puede inactivarse mientras la sucursal esté activa.'));
  assert.ok(inventoryContent.includes('resolveBranchId'));
  assert.ok(inventoryContent.includes('/inventory/items${query}'));
  assert.ok(inventoryContent.includes('Sucursal y almacén seleccionados'));
}

function testHistoryContainsReprintCapability() {
  const historyContent = readFileSync(
    resolve(root, 'apps', 'pos-web', 'src', 'features', 'history', 'History.tsx'),
    'utf-8'
  );

  assert.ok(historyContent.includes('Reimprimir'), 'History should include Reimprimir button');
  assert.ok(historyContent.includes('handleReprint'), 'History should include handleReprint handler');
  assert.ok(historyContent.includes('reprintMessage'), 'History should include reprint status feedback');
}

function testPosCartContainsCourtesyAndSupervisorPin() {
  const posContent = readFileSync(
    resolve(root, 'apps', 'pos-web', 'src', 'features', 'pos', 'PointOfSale.tsx'),
    'utf-8'
  );

  assert.ok(posContent.includes('isCourtesyModalOpen'), 'POS should include courtesy modal state');
  assert.ok(posContent.includes('supervisorPin'), 'POS should require supervisor pin');
  assert.ok(posContent.includes('Autorización de Cortesía o Descuento'), 'POS should include supervisor adjustment authorization modal');
  assert.ok(posContent.includes('effectiveCourtesyCents'), 'POS should render the backend-authorized courtesy');
  assert.ok(posContent.includes('/orders/adjustments/authorize'), 'POS should authorize adjustments through Python');
}

function run() {
  console.log('Running testBranchAdminOperationsContainsInteractivePurchases...');
  testBranchAdminOperationsContainsInteractivePurchases();
  console.log('Running testCorporateAdminPurchaseConfirmationUsesTheSameCashContract...');
  testCorporateAdminPurchaseConfirmationUsesTheSameCashContract();
  console.log('Running testCorporateInventoryAndWarehousesUseCanonicalBranchScope...');
  testCorporateInventoryAndWarehousesUseCanonicalBranchScope();
  console.log('Running testHistoryContainsReprintCapability...');
  testHistoryContainsReprintCapability();
  console.log('Running testPosCartContainsCourtesyAndSupervisorPin...');
  testPosCartContainsCourtesyAndSupervisorPin();
  console.log('All 6 operational stories assertions verified and passed successfully!');
}

run();
