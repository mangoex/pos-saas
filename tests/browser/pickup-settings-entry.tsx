// Synthetic local QA entry; never imported by the production app.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MobileBranchSettingsTab } from '../../apps/admin-web/src/features/mobile-admin/MobileBranchSettingsTab';

createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MobileBranchSettingsTab branchId="qa-branch" />
  </QueryClientProvider>,
);
