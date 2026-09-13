export interface MobileOrderAlertCandidate {
  id: string;
  created_at?: string;
  status?: string;
  is_public_intent?: boolean;
}

export interface MobileOrderAlertState {
  branchId: string;
  cursorCreatedAt: string;
  idsAtCursor: string[];
}

export interface MobileOrderAlertResult {
  state: MobileOrderAlertState;
  newOrderIds: string[];
}

const isPendingPublicIntent = (order: MobileOrderAlertCandidate): boolean => {
  const status = (order.status || '').toUpperCase();
  return order.is_public_intent === true && ['PENDING', 'PENDING_REVIEW'].includes(status);
};

const orderedUniqueOrders = (
  orders: MobileOrderAlertCandidate[],
): MobileOrderAlertCandidate[] => {
  const byId = new Map<string, MobileOrderAlertCandidate>();
  orders
    .filter(isPendingPublicIntent)
    .filter((order) => Boolean(order.id))
    .forEach((order) => byId.set(order.id, order));
  return [...byId.values()].sort((left, right) => {
      const byTime = (left.created_at || '').localeCompare(right.created_at || '');
      return byTime || left.id.localeCompare(right.id);
    });
};

const stateAtNewestCursor = (
  branchId: string,
  orders: MobileOrderAlertCandidate[],
): MobileOrderAlertState => {
  const cursorCreatedAt = orders.at(-1)?.created_at || '';
  return {
    branchId,
    cursorCreatedAt,
    idsAtCursor: orders
      .filter((order) => (order.created_at || '') === cursorCreatedAt)
      .map((order) => order.id),
  };
};

export const reconcileMobileOrderAlerts = (
  previous: MobileOrderAlertState | null,
  branchId: string,
  orders: MobileOrderAlertCandidate[],
): MobileOrderAlertResult => {
  const currentOrders = orderedUniqueOrders(orders);
  if (!previous || previous.branchId !== branchId) {
    return {
      state: stateAtNewestCursor(branchId, currentOrders),
      newOrderIds: [],
    };
  }

  const idsAtCursor = new Set(previous.idsAtCursor);
  const newOrders = currentOrders.filter((order) => {
    const createdAt = order.created_at || '';
    return createdAt > previous.cursorCreatedAt
      || (createdAt === previous.cursorCreatedAt && !idsAtCursor.has(order.id));
  });
  const newestObserved = orderedUniqueOrders([...currentOrders, ...newOrders]);
  const newestState = stateAtNewestCursor(branchId, newestObserved);
  const state = newestState.cursorCreatedAt > previous.cursorCreatedAt
    ? newestState
    : {
        branchId,
        cursorCreatedAt: previous.cursorCreatedAt,
        idsAtCursor: [...new Set([
          ...previous.idsAtCursor,
          ...newOrders
            .filter((order) => (order.created_at || '') === previous.cursorCreatedAt)
            .map((order) => order.id),
        ])].sort(),
      };
  return {
    state,
    newOrderIds: newOrders.map((order) => order.id),
  };
};
