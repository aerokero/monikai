/**
 * Savings / Money workspace.
 *
 * The first release is a private browser ledger so the Workspace surface is
 * useful immediately. Imported rows are always shown for review before they
 * affect a wallet balance.
 */

import uiModule from './ui.js';
import * as Modals from './modalManager.js';
import { applyEdgeDock, clearRightDock } from './modalSnap.js';
import { makeWindowDraggable } from './windowDrag.js';
import { icon as phosphorIcon } from './iconRegistry.js';

const STORAGE_KEY = 'odysseus-savings-ledger-v1';
const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const CATEGORY_COLORS = {
  Needs: '#8dd6c4',
  Wants: '#ee9fc5',
  Assets: '#9eb8f1',
  Debt: '#f29b91',
  Income: '#8dd6c4',
  Other: '#c4b5d8',
};

let _open = false;
let _activeTab = 'overview';
let _monthOffset = 0;
let _dialog = null;
let _import = null;
let _escHandler = null;
let _expenseWalletId = 'all';
let _expenseKind = 'expense';

function pad(value) {
  return String(value).padStart(2, '0');
}

function monthKey(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;
}

function shiftMonth(key, offset) {
  const [year, month] = String(key).split('-').map(Number);
  const date = new Date(year, (month || 1) - 1 + offset, 1);
  return monthKey(date);
}

function monthTitle(key, short = false) {
  const [year, month] = String(key).split('-').map(Number);
  if (!year || !month) return key;
  if (short) return `${MONTH_NAMES[month - 1]} '${String(year).slice(-2)}`;
  return new Date(year, month - 1, 1).toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  });
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>\"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '\"': '&quot;',
    "'": '&#39;',
  }[character]));
}

function numberValue(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseMoney(value) {
  const raw = String(value ?? '')
    .replace(/(PLN|zł| zł)/gi, '')
    .replace(/\s/g, '')
    .trim();
  if (!raw) return 0;
  const normalized = raw.includes(',')
    ? raw.replace(/\./g, '').replace(',', '.')
    : raw.replace(/,(?=\d{3}(?:\D|$))/g, '');
  return numberValue(normalized, 0);
}

function money(value, digits = 0) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'PLN',
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(numberValue(value));
}

function compactMoney(value) {
  const amount = numberValue(value);
  if (Math.abs(amount) >= 1000) {
    return `${(amount / 1000).toLocaleString('en-US', { maximumFractionDigits: 1 })}k`;
  }
  return Math.round(amount).toLocaleString('en-US');
}

function isoDateForMonth(key, day = 1) {
  const [year, month] = key.split('-').map(Number);
  const maxDay = new Date(year, month, 0).getDate();
  return `${key}-${pad(Math.min(Math.max(1, day), maxDay))}`;
}

function localDateKey(date = new Date()) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function paydayDateFor(reference = new Date(), payday = 25) {
  const day = Math.min(31, Math.max(1, Math.round(numberValue(payday, 25))));
  const current = new Date(reference.getFullYear(), reference.getMonth(), reference.getDate(), 12);
  const dateInMonth = (year, month) => new Date(
    year,
    month,
    Math.min(day, new Date(year, month + 1, 0).getDate()),
    12,
  );
  let target = dateInMonth(current.getFullYear(), current.getMonth());
  // On payday the new period starts; the next target is the following payday.
  if (target <= current) target = dateInMonth(current.getFullYear(), current.getMonth() + 1);
  return target;
}

function daysUntilPayday(reference = new Date(), payday = 25) {
  const current = new Date(reference.getFullYear(), reference.getMonth(), reference.getDate(), 12);
  const target = paydayDateFor(current, payday);
  return Math.max(1, Math.round((target - current) / 86400000));
}

function paydayInfo() {
  const date = paydayDateFor(new Date(), _state?.settings?.payday || 25);
  return {
    date,
    days: daysUntilPayday(new Date(), _state?.settings?.payday || 25),
    label: date.toLocaleDateString('en-US', { day: 'numeric', month: 'long' }),
  };
}

function paydayInputValue() {
  return localDateKey(paydayInfo().date);
}

function dateLabel(value) {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return '—';
  return `${match[3]} ${MONTH_NAMES[Number(match[2]) - 1]}`;
}

function icon(name, size = 15, className = 'savings-icon') {
  return phosphorIcon(name, size, className);
}

const CURRENT_MONTH = monthKey(new Date());

function defaultState() {
  const historyValues = [
    [2450, 1970, 620, 460],
    [2600, 2150, 740, 440],
    [2700, 2260, 760, 430],
    [2800, 2390, 800, 420],
    [2800, 2470, 820, 420],
  ];
  const previousMonths = historyValues.map((values, index) => {
    const key = shiftMonth(CURRENT_MONTH, index - historyValues.length);
    return {
      key,
      income: values[0] + 2300,
      limit: values[0],
      expenses: values[1],
      savings: values[2],
      debt: values[3],
    };
  });
  return {
    settings: {
      currency: 'PLN',
      income: 5650,
      monthlyLimit: 2800,
      payday: 25,
      savingsTarget: 850,
      savingsGoal: 10000,
      emergencyFund: 5180,
      debtTotal: 0,
      debtPayment: 0,
    },
    wallets: [
      { id: 'main', name: 'Main account', balance: 3420, savings: 1800, debt: 9400, includeSavings: false, color: '#ee9fc5' },
      { id: 'cash', name: 'Cash wallet', balance: 460, savings: 0, includeSavings: true, color: '#8dd6c4' },
      { id: 'invest', name: 'Assets / investing', balance: 1250, savings: 3380, includeSavings: false, color: '#9eb8f1' },
    ],
    transactions: [
      { id: 'seed-1', date: isoDateForMonth(CURRENT_MONTH, 2), merchant: 'Rent & utilities', category: 'Needs', amount: 1280, walletId: 'main', source: 'manual' },
      { id: 'seed-2', date: isoDateForMonth(CURRENT_MONTH, 4), merchant: 'Grocery market', category: 'Needs', amount: 186.40, walletId: 'main', source: 'manual' },
      { id: 'seed-3', date: isoDateForMonth(CURRENT_MONTH, 7), merchant: 'Public transport', category: 'Needs', amount: 72, walletId: 'cash', source: 'manual' },
      { id: 'seed-4', date: isoDateForMonth(CURRENT_MONTH, 9), merchant: 'Online course', category: 'Assets', amount: 149, walletId: 'main', source: 'manual' },
      { id: 'seed-5', date: isoDateForMonth(CURRENT_MONTH, 11), merchant: 'Dinner with friends', category: 'Wants', amount: 96, walletId: 'cash', source: 'manual' },
      { id: 'seed-6', date: isoDateForMonth(CURRENT_MONTH, 14), merchant: 'Phone & subscriptions', category: 'Needs', amount: 128, walletId: 'main', source: 'manual' },
      { id: 'seed-7', date: isoDateForMonth(CURRENT_MONTH, 16), merchant: 'Credit repayment', category: 'Debt', amount: 420, walletId: 'main', source: 'manual' },
    ],
    months: previousMonths,
    dailyHistory: Array.from({ length: 7 }, (_, index) => {
      const date = new Date();
      date.setDate(date.getDate() - (7 - index));
      const balance = 4800;
      const daysToPayday = daysUntilPayday(date, 25);
      return {
        date: localDateKey(date),
        balance,
        dailyLimit: balance / daysToPayday,
        daysToPayday,
      };
    }),
  };
}

function normalizeState(raw) {
  const fallback = defaultState();
  if (!raw || typeof raw !== 'object') return fallback;
  const settings = { ...fallback.settings, ...(raw.settings || {}) };
  const wallets = Array.isArray(raw.wallets) && raw.wallets.length
    ? raw.wallets.map((wallet, index) => {
      const rawBalance = numberValue(wallet.balance);
      return {
        id: String(wallet.id || `wallet-${index + 1}`),
        name: String(wallet.name || `Wallet ${index + 1}`),
        balance: Math.max(0, rawBalance),
        savings: Math.max(0, numberValue(wallet.savings)),
        debt: Math.max(0, numberValue(wallet.debt), -rawBalance),
        includeSavings: wallet.includeSavings === true,
        color: wallet.color || CATEGORY_COLORS[Object.keys(CATEGORY_COLORS)[index % 4]],
      };
    })
    : fallback.wallets.map((wallet) => ({ ...wallet }));
  // Older saved ledgers kept one global debt value. Move it to the first
  // wallet once so debt remains a wallet-level value from this point on.
  const legacyDebt = Math.max(0, numberValue(raw.settings?.debtTotal));
  if (legacyDebt > 0 && wallets.length && wallets.every((wallet) => !numberValue(wallet.debt))) {
    wallets[0].debt = legacyDebt;
  }
  return {
    settings,
    wallets,
    transactions: Array.isArray(raw.transactions)
      ? raw.transactions.map((transaction, index) => {
        const rawAmount = numberValue(transaction.amount);
        const direction = transaction.direction === 'income'
          || transaction.type === 'income'
          || (transaction.direction == null && rawAmount < 0)
          ? 'income'
          : 'expense';
        return {
          id: String(transaction.id || `transaction-${index + 1}`),
          externalId: String(transaction.externalId || transaction.external_id || ''),
          date: String(transaction.date || isoDateForMonth(CURRENT_MONTH)),
          merchant: String(transaction.merchant || transaction.name || 'Expense'),
          description: String(transaction.description || ''),
          operationType: String(transaction.operationType || ''),
          category: String(transaction.category || (direction === 'income' ? 'Income' : 'Other')),
          categoryConfidence: numberValue(transaction.categoryConfidence, 0),
          amount: Math.abs(rawAmount),
          direction,
          balanceAfter: transaction.balanceAfter == null ? null : numberValue(transaction.balanceAfter),
          walletId: String(transaction.walletId || wallets[0]?.id || fallback.wallets[0].id),
          source: transaction.source || 'manual',
        };
      })
      : fallback.transactions,
    months: Array.isArray(raw.months) ? raw.months.map((snapshot) => ({
      key: String(snapshot.key),
      income: numberValue(snapshot.income),
      limit: numberValue(snapshot.limit),
      expenses: numberValue(snapshot.expenses),
      savings: numberValue(snapshot.savings),
      debt: numberValue(snapshot.debt),
      incomeOverride: snapshot.incomeOverride == null ? null : numberValue(snapshot.incomeOverride),
      expensesOverride: snapshot.expensesOverride == null ? null : numberValue(snapshot.expensesOverride),
      cleared: snapshot.cleared === true,
    })) : fallback.months,
    dailyHistory: Array.isArray(raw.dailyHistory) ? raw.dailyHistory.map((entry) => ({
      date: String(entry.date || ''),
      balance: numberValue(entry.balance),
      dailyLimit: numberValue(entry.dailyLimit),
      daysToPayday: Math.max(1, numberValue(entry.daysToPayday, 1)),
    })).filter((entry) => /^\d{4}-\d{2}-\d{2}$/.test(entry.date)) : fallback.dailyHistory,
  };
}

function isCustomLedger(state) {
  if (!state) return false;
  if (Array.isArray(state.transactions)) {
    for (const t of state.transactions) {
      if (!String(t.id).startsWith('seed-') || t.source === 'bank-statement') {
        return true;
      }
    }
    if (state.transactions.length !== 7) return true;
  }
  if (Array.isArray(state.wallets)) {
    if (state.wallets.length !== 3) return true;
    const [w1, w2, w3] = state.wallets;
    if (
      w1?.name !== 'Main account' || w1?.balance !== 3420 || w1?.savings !== 1800 || w1?.debt !== 9400 ||
      w2?.name !== 'Cash wallet' || w2?.balance !== 460 || w2?.savings !== 0 ||
      w3?.name !== 'Assets / investing' || w3?.balance !== 1250 || w3?.savings !== 3380
    ) {
      return true;
    }
  }
  if (state.settings) {
    if (
      state.settings.income !== 5650 ||
      state.settings.monthlyLimit !== 2800 ||
      state.settings.payday !== 25 ||
      state.settings.savingsTarget !== 850 ||
      state.settings.savingsGoal !== 10000 ||
      state.settings.emergencyFund !== 5180
    ) {
      return true;
    }
  }
  return false;
}

function loadState() {
  try {
    return normalizeState(JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null'));
  } catch (_) {
    return defaultState();
  }
}

let _state = loadState();
let _saveTimer = null;
let _isSyncing = false;
let _hasSyncedInitial = false;

const _syncChannel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('odysseus_savings_sync') : null;
if (_syncChannel) {
  _syncChannel.onmessage = (event) => {
    if (event.data?.type === 'savings_updated' && !_dialog) {
      syncWithServer();
    }
  };
}

let _isPushing = false;
async function pushStateToServer() {
  if (_isPushing) return;
  _isPushing = true;
  try {
    const payload = JSON.parse(JSON.stringify(_state));
    await fetch('/api/savings/ledger', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    _syncChannel?.postMessage({ type: 'savings_updated' });
  } catch (error) {
    console.warn('Savings state could not be synced to server:', error);
  } finally {
    _isPushing = false;
  }
}

function saveState(immediate = false) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(_state));
  } catch (error) {
    console.warn('Savings state could not be saved to localStorage:', error);
  }
  if (_saveTimer) {
    clearTimeout(_saveTimer);
    _saveTimer = null;
  }
  if (immediate) {
    pushStateToServer();
  } else {
    _saveTimer = setTimeout(pushStateToServer, 350);
  }
}

async function syncWithServer() {
  if (_isSyncing) return;
  _isSyncing = true;
  try {
    const res = await fetch('/api/savings/ledger');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.initialized && data.ledger) {
      _state = normalizeState(data.ledger);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(_state));
      } catch (_) {}
      _hasSyncedInitial = true;
      if (_open && !_dialog) {
        if (_expenseWalletId !== 'all' && !_state.wallets.some((w) => w.id === _expenseWalletId)) {
          _expenseWalletId = _state.wallets[0]?.id || 'all';
        }
        render();
      }
    } else {
      if (isCustomLedger(_state)) {
        console.log('[Savings] Auto-migrating custom local ledger to server...');
        await pushStateToServer();
        _hasSyncedInitial = true;
      }
    }
  } catch (err) {
    console.warn('[Savings] Server sync check failed (using local cache):', err);
  } finally {
    _isSyncing = false;
  }
}

if (typeof window !== 'undefined') {
  syncWithServer();
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') syncWithServer();
  });
  window.addEventListener('focus', () => {
    syncWithServer();
  });
  window.addEventListener('beforeunload', () => {
    if (_saveTimer) {
      clearTimeout(_saveTimer);
      _saveTimer = null;
      try {
        fetch('/api/savings/ledger', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(_state),
          keepalive: true,
        });
      } catch (_) {}
    }
  });
}

function selectedMonth() {
  return shiftMonth(CURRENT_MONTH, _monthOffset);
}

function transactionsFor(key) {
  return _state.transactions.filter((transaction) => String(transaction.date).startsWith(`${key}-`));
}

function isIncomeTransaction(transaction) {
  return transaction?.direction === 'income' || transaction?.type === 'income';
}

function signedTransactionAmount(transaction) {
  const amount = Math.abs(numberValue(transaction?.amount));
  return isIncomeTransaction(transaction) ? amount : -amount;
}

function affectsWalletBalance(transaction) {
  return transaction?.source !== 'bank-statement' && transaction?.source !== 'document';
}

function expensesFor(key) {
  return transactionsFor(key)
    .filter((transaction) => !isIncomeTransaction(transaction))
    .reduce((total, transaction) => total + Math.abs(numberValue(transaction.amount)), 0);
}

function incomeFor(key) {
  return transactionsFor(key)
    .filter((transaction) => isIncomeTransaction(transaction))
    .reduce((total, transaction) => total + Math.abs(numberValue(transaction.amount)), 0);
}

function snapshotFor(key) {
  const stored = _state.months.find((snapshot) => snapshot.key === key);
  const liveTransactions = transactionsFor(key);
  const liveExpenses = expensesFor(key);
  const liveIncome = incomeFor(key);
  if (stored) {
    return {
      ...stored,
      // The live ledger is the source of truth unless a monthly summary was
      // manually edited. This keeps new entries visible in Statistics.
      expenses: stored.expensesOverride != null
        ? Math.max(0, numberValue(stored.expensesOverride))
        : liveTransactions.length ? liveExpenses : (stored.cleared ? 0 : stored.expenses),
      income: stored.incomeOverride != null
        ? Math.max(0, numberValue(stored.incomeOverride))
        : liveIncome > 0 ? liveIncome : (stored.cleared ? 0 : stored.income),
      cleared: stored.cleared === true && !liveTransactions.length,
    };
  }
  return {
    key,
    income: liveIncome || (key === CURRENT_MONTH ? numberValue(_state.settings.income) : 0),
    limit: numberValue(_state.settings.monthlyLimit),
    expenses: liveExpenses,
    savings: 0,
    debt: 0,
    cleared: false,
  };
}

function recentSnapshots() {
  return Array.from({ length: 6 }, (_, index) => snapshotFor(shiftMonth(CURRENT_MONTH, index - 5)));
}

function totalSavings() {
  return _state.wallets.reduce((total, wallet) => total + numberValue(wallet.savings), 0);
}

function totalDebt() {
  return _state.wallets.reduce((total, wallet) => total + Math.max(0, numberValue(wallet.debt)), 0);
}

function spendingBalanceForWallet(wallet) {
  const balance = numberValue(wallet?.balance);
  const reservedSavings = wallet?.includeSavings ? numberValue(wallet?.savings) : 0;
  return balance - reservedSavings;
}

function spendingBalance() {
  return _state.wallets.reduce((total, wallet) => total + spendingBalanceForWallet(wallet), 0);
}

function availableBalance() {
  return spendingBalance();
}

function grossAssets() {
  return _state.wallets.reduce(
    (total, wallet) => total + numberValue(wallet.balance) + (wallet.includeSavings ? 0 : numberValue(wallet.savings)),
    0,
  );
}

function estimatedMonthlyIncome() {
  const previous = recentSnapshots()
    .filter((snapshot) => snapshot.key !== CURRENT_MONTH)
    .map((snapshot) => numberValue(snapshot.income))
    .filter((income) => income > 0);
  if (!previous.length) return numberValue(_state.settings.income);
  return previous.reduce((total, income) => total + income, 0) / previous.length;
}

function selectedMetrics() {
  const key = selectedMonth();
  const snapshot = snapshotFor(key);
  const transactions = transactionsFor(key);
  const [year, month] = key.split('-').map(Number);
  const daysInMonth = new Date(year, month, 0).getDate();
  const today = new Date();
  const elapsed = key === CURRENT_MONTH ? today.getDate() : daysInMonth;
  const daysLeft = Math.max(1, daysInMonth - elapsed + 1);
  const remainingBudget = snapshot.limit - snapshot.expenses;
  const currentSpendingBalance = spendingBalance();
  const payday = paydayInfo();
  const categoryTotals = transactions.filter((transaction) => !isIncomeTransaction(transaction)).reduce((totals, transaction) => {
    const category = transaction.category || 'Other';
    totals[category] = (totals[category] || 0) + Math.abs(numberValue(transaction.amount));
    return totals;
  }, {});
  const cashflow = snapshot.income - snapshot.expenses - snapshot.savings;
  return {
    key,
    snapshot,
    transactions,
    daysInMonth,
    daysLeft,
    remainingBudget,
    // The live limit is independent from the optional monthly plan: it is
    // exactly the spendable balance divided by days until the next payday.
    dailyLimit: currentSpendingBalance / payday.days,
    spendingBalance: currentSpendingBalance,
    payday,
    categoryTotals,
    cashflow,
    savingsRate: snapshot.income ? snapshot.savings / snapshot.income : 0,
    assets: grossAssets(),
    liabilities: totalDebt(),
  };
}

function refreshMonthLedgerTotals(keys) {
  [...new Set(keys)].forEach((key) => {
    const snapshot = _state.months.find((item) => item.key === key);
    if (!snapshot) return;
    snapshot.expenses = expensesFor(key);
    const actualIncome = incomeFor(key);
    if (actualIncome > 0) snapshot.income = actualIncome;
    if (transactionsFor(key).length) snapshot.cleared = false;
  });
}

function adjustMonthlyOverride(key, field, delta) {
  const snapshot = _state.months.find((item) => item.key === key);
  if (!snapshot || snapshot[field] == null) return;
  snapshot[field] = Math.max(0, numberValue(snapshot[field]) + numberValue(delta));
}

function allCategoryTotals() {
  return _state.transactions
    .filter((transaction) => !isIncomeTransaction(transaction))
    .reduce((totals, transaction) => {
      const category = transaction.category || 'Other';
      totals[category] = (totals[category] || 0) + Math.abs(numberValue(transaction.amount));
      return totals;
    }, {});
}

function recordDailySnapshot() {
  if (!_state) return;
  const info = paydayInfo();
  const balance = spendingBalance();
  const date = localDateKey();
  const entry = {
    date,
    balance,
    dailyLimit: balance / info.days,
    daysToPayday: info.days,
  };
  const index = _state.dailyHistory.findIndex((item) => item.date === date);
  const existing = index >= 0 ? _state.dailyHistory[index] : null;
  if (
    existing &&
    existing.balance === entry.balance &&
    Math.abs(existing.dailyLimit - entry.dailyLimit) < 0.001 &&
    existing.daysToPayday === entry.daysToPayday
  ) {
    return;
  }
  if (index >= 0) _state.dailyHistory[index] = entry;
  else _state.dailyHistory.push(entry);
  _state.dailyHistory = _state.dailyHistory
    .filter((item) => item.date)
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-90);
  saveState();
}

function recentDailyHistory() {
  return [...(_state.dailyHistory || [])]
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(-14);
}

function decreasingLimitStreak() {
  const history = recentDailyHistory();
  let decreases = 0;
  for (let index = history.length - 1; index > 0; index -= 1) {
    const currentDate = new Date(`${history[index].date}T12:00:00Z`);
    const previousDate = new Date(`${history[index - 1].date}T12:00:00Z`);
    const consecutiveDay = Math.round((currentDate - previousDate) / 86400000) === 1;
    if (!consecutiveDay || numberValue(history[index].dailyLimit) >= numberValue(history[index - 1].dailyLimit) - 0.005) break;
    decreases += 1;
  }
  return decreases;
}

function dailyLimitDelta() {
  const history = recentDailyHistory();
  if (history.length < 2) return 0;
  return numberValue(history[history.length - 1].dailyLimit) - numberValue(history[history.length - 2].dailyLimit);
}

function savingsRatio() {
  const assets = Math.max(0, grossAssets());
  return assets ? Math.min(1, Math.max(0, totalSavings() / assets)) : 0;
}

function savingsDonut() {
  const ratio = savingsRatio();
  return `<div class="savings-donut" style="--savings-ratio:${Math.round(ratio * 100)}%" role="img" aria-label="${Math.round(ratio * 100)} percent of assets saved"><span>${Math.round(ratio * 100)}%</span></div>`;
}

function walletDistributionChart() {
  const fallbackColors = ['#ee9fc5', '#8dd6c4', '#9eb8f1', '#f2c14e', '#f29b91', '#c4b5d8'];
  const entries = _state.wallets
    .map((wallet, index) => {
      const balance = Math.max(0, numberValue(wallet.balance));
      const savings = Math.max(0, numberValue(wallet.savings));
      const rawColor = String(wallet.color || '');
      const color = /^#[0-9a-f]{3,8}$/i.test(rawColor) ? rawColor : fallbackColors[index % fallbackColors.length];
      return { wallet, balance, savings, total: balance + (wallet.includeSavings ? 0 : savings), color };
    })
    .filter((entry) => entry.total > 0);
  const total = entries.reduce((sum, entry) => sum + entry.total, 0);
  if (!total) {
    return `<section class="savings-wallet-chart savings-wallet-chart-empty"><div>No balances to chart yet.</div></section>`;
  }

  const center = 110;
  const radius = 76;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const segments = entries.map((entry) => {
    const length = circumference * entry.total / total;
    const segment = `<circle class="savings-wallet-pie-segment" cx="${center}" cy="${center}" r="${radius}" stroke="${escapeHtml(entry.color)}" stroke-dasharray="${length.toFixed(2)} ${(circumference - length).toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}" transform="rotate(-90 ${center} ${center})"><title>${escapeHtml(entry.wallet.name)}: ${money(entry.total, 2)}</title></circle>`;
    offset += length;
    return segment;
  }).join('');
  const chartLabel = entries.map((entry) => `${entry.wallet.name}: ${money(entry.total, 2)}`).join(', ');
  return `<section class="savings-wallet-chart" role="img" aria-label="Wallet distribution including savings: ${escapeHtml(chartLabel)}">
    <svg class="savings-wallet-pie" viewBox="0 0 220 220" aria-hidden="true">
      <circle class="savings-wallet-pie-track" cx="${center}" cy="${center}" r="${radius}" />
      ${segments}
      <text class="savings-wallet-pie-total" x="${center}" y="105" text-anchor="middle">${escapeHtml(compactMoney(total))}</text>
      <text class="savings-wallet-pie-caption" x="${center}" y="123" text-anchor="middle">total assets</text>
    </svg>
  </section>`;
}

function inferCategory(text) {
  const value = String(text || '').toLowerCase();
  if (/salary|payroll|income|deposit|refund|wynagrodzenie|wpływ|przychód|zwrot/.test(value)) return 'Income';
  if (/rent|utility|grocery|market|food|transport|phone|internet|czynsz|prąd|zakup/.test(value)) return 'Needs';
  if (/course|book|education|training|software|kurs|książ/.test(value)) return 'Assets';
  if (/credit|loan|debt|repayment|rat|kredyt|pożycz/.test(value)) return 'Debt';
  if (/dinner|restaurant|coffee|cinema|travel|shopping|restaur|kawa|kino/.test(value)) return 'Wants';
  return 'Other';
}

function parseImportedDate(line, fallbackKey) {
  const iso = String(line).match(/\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b/);
  if (iso) return `${iso[1]}-${pad(iso[2])}-${pad(iso[3])}`;
  const european = String(line).match(/\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b/);
  if (european) return `${european[3]}-${pad(european[2])}-${pad(european[1])}`;
  return isoDateForMonth(fallbackKey, new Date().getDate());
}

function parseDocumentText(text, fallbackKey) {
  const rows = [];
  const lines = String(text || '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const amountPattern = /-?\d{1,3}(?:[ .]\d{3})*(?:[,.]\d{2})(?:\s*(?:PLN|zł))?|-?\d+(?:[,.]\d{2})(?:\s*(?:PLN|zł))/i;
  lines.forEach((line, index) => {
    const withoutDate = line.replace(/\b\d{1,4}[./-]\d{1,2}[./-]\d{2,4}\b/g, ' ');
    const amountMatch = withoutDate.match(amountPattern);
    if (!amountMatch) return;
    const signedAmount = parseMoney(amountMatch[0]);
    const amount = Math.abs(signedAmount);
    if (!amount || amount > 100000) return;
    const merchant = withoutDate
      .replace(amountMatch[0], ' ')
      .replace(/[;,|]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/^(transaction|expense|payment|kwota|opis)\s*[:\-]?\s*/i, '')
      .slice(0, 64) || `Imported expense ${index + 1}`;
    const direction = signedAmount > 0 ? 'income' : 'expense';
    rows.push({
      id: `import-${Date.now()}-${index}`,
      externalId: '',
      date: parseImportedDate(line, fallbackKey),
      merchant,
      description: merchant,
      operationType: 'Imported transaction',
      category: direction === 'income' ? 'Income' : inferCategory(merchant),
      categoryConfidence: 0.45,
      amount,
      direction,
      balanceAfter: null,
      walletId: _state.wallets[0]?.id || '',
      selected: true,
    });
  });
  return rows.slice(0, 60);
}

function isTextDocument(file) {
  return /^text\//i.test(String(file?.type || ''))
    || /\.(csv|txt|log|json|tsv)$/i.test(String(file?.name || ''));
}

function isStatementDocument(file) {
  return /\.(pdf|csv|txt|json|tsv|ofx|mt940)$/i.test(String(file?.name || ''))
    || /(?:pdf|csv|text|json|ofx)/i.test(String(file?.type || ''));
}

async function readStatementWithParser(file) {
  const form = new FormData();
  form.append('file', file, file.name);
  const response = await fetch('/api/savings/import-statement', {
    method: 'POST',
    body: form,
    credentials: 'same-origin',
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch (_) {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(payload?.detail || `Statement import failed (${response.status})`);
  }
  return payload || {};
}

async function readImageWithVision(file) {
  // Reuse the workspace's native upload + vision pipeline when the backend is
  // available. The local parser remains the safe fallback for CSV/TXT and for
  // deployments that only serve the static shell.
  try {
    const form = new FormData();
    form.append('files', file, file.name);
    const uploadResponse = await fetch('/api/upload', {
      method: 'POST',
      body: form,
      credentials: 'same-origin',
    });
    if (!uploadResponse.ok) return '';
    const uploadPayload = await uploadResponse.json();
    const uploadId = uploadPayload?.files?.[0]?.id;
    if (!uploadId) return '';
    const visionResponse = await fetch(`/api/upload/${encodeURIComponent(uploadId)}/vision`, {
      credentials: 'same-origin',
    });
    if (!visionResponse.ok) return '';
    const visionPayload = await visionResponse.json();
    return String(visionPayload?.text || '');
  } catch (error) {
    console.warn('Savings vision import unavailable:', error);
    return '';
  }
}

function openDialog(type, id = null) {
  _dialog = { type, id };
  render();
}

function closeDialog() {
  _dialog = null;
  render();
}

function tabButton(id, label, iconName) {
  return `<button type="button" class="savings-tab${_activeTab === id ? ' active' : ''}" data-savings-tab="${id}" aria-selected="${_activeTab === id}">
    ${icon(iconName, 14)}<span>${label}</span>
  </button>`;
}

function metricCard(label, value, detail, tone = 'neutral', iconName = 'wallet') {
  return `<article class="savings-metric-card savings-tone-${tone}">
    <div class="savings-metric-top"><span class="savings-label">${label}</span><span class="savings-metric-icon">${icon(iconName, 15)}</span></div>
    <strong>${value}</strong>
    <span class="savings-muted">${detail}</span>
  </article>`;
}

function simpleMetric(label, value, detail = '') {
  return `<div class="savings-simple-metric"><span>${label}</span><strong>${value}</strong>${detail ? `<small>${detail}</small>` : ''}</div>`;
}

function groupedBarChart(snapshots) {
  const series = [
    { key: 'limit', label: 'Limit', color: 'var(--accent, #ee9fc5)' },
    { key: 'savings', label: 'Savings', color: '#8dd6c4' },
  ];
  const maximum = Math.max(1, ...snapshots.flatMap((snapshot) => series.map((item) => numberValue(snapshot[item.key]))));
  return `<div class="savings-legend">${series.map((item) => `<span><i style="background:${item.color}"></i>${item.label}</span>`).join('')}</div>
    <div class="savings-bar-chart" role="img" aria-label="Monthly limit and savings chart">
      ${snapshots.map((snapshot) => `<div class="savings-bar-group">
        <div class="savings-bars">${series.map((item) => `<span class="savings-bar" title="${item.label}: ${money(snapshot[item.key])}" style="height:${Math.max(5, Math.round((numberValue(snapshot[item.key]) / maximum) * 100))}%;background:${item.color}"></span>`).join('')}</div>
        <span>${monthTitle(snapshot.key, true)}</span>
      </div>`).join('')}
    </div>`;
}

function lineChart(snapshots) {
  const width = 720;
  const height = 220;
  const padLeft = 34;
  const padRight = 12;
  const padTop = 14;
  const padBottom = 32;
  const series = [
    { key: 'limit', label: 'Average limit', color: 'var(--accent, #ee9fc5)' },
    { key: 'savings', label: 'Savings', color: '#8dd6c4' },
  ];
  const max = Math.max(1, ...snapshots.flatMap((snapshot) => series.map((item) => numberValue(snapshot[item.key]))));
  const chartWidth = width - padLeft - padRight;
  const chartHeight = height - padTop - padBottom;
  const x = (index) => padLeft + (snapshots.length <= 1 ? chartWidth / 2 : (index / (snapshots.length - 1)) * chartWidth);
  const y = (value) => padTop + chartHeight - (numberValue(value) / max) * chartHeight;
  const grid = [0, 0.5, 1].map((ratio) => {
    const lineY = padTop + chartHeight - ratio * chartHeight;
    return `<line x1="${padLeft}" y1="${lineY}" x2="${width - padRight}" y2="${lineY}" stroke="currentColor" opacity="0.1"/><text x="2" y="${lineY + 4}" fill="currentColor" opacity="0.42" font-size="10">${compactMoney(max * ratio)}</text>`;
  }).join('');
  const paths = series.map((item) => {
    const points = snapshots.map((snapshot, index) => `${x(index).toFixed(1)},${y(snapshot[item.key]).toFixed(1)}`).join(' ');
    const dots = snapshots.map((snapshot, index) => `<circle cx="${x(index).toFixed(1)}" cy="${y(snapshot[item.key]).toFixed(1)}" r="3" fill="${item.color}" stroke="var(--bg)" stroke-width="2"><title>${item.label}: ${money(snapshot[item.key])}</title></circle>`).join('');
    return `<polyline points="${points}" fill="none" stroke="${item.color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>${dots}`;
  }).join('');
  const labels = snapshots.map((snapshot, index) => `<text x="${x(index).toFixed(1)}" y="${height - 9}" text-anchor="middle" fill="currentColor" opacity="0.48" font-size="10">${monthTitle(snapshot.key, true)}</text>`).join('');
  return `<div class="savings-legend">${series.map((item) => `<span><i style="background:${item.color}"></i>${item.label}</span>`).join('')}</div>
    <svg class="savings-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Monthly average limit and savings trend">${grid}${paths}${labels}</svg>`;
}

function dailyLimitChart() {
  const history = recentDailyHistory();
  const width = 720;
  const height = 190;
  const left = 38;
  const right = 12;
  const top = 16;
  const bottom = 30;
  const values = history.map((entry) => numberValue(entry.dailyLimit));
  const minimum = Math.min(0, ...values);
  const maximum = Math.max(1, ...values);
  const range = Math.max(1, maximum - minimum);
  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;
  const x = (index) => left + (history.length <= 1 ? chartWidth / 2 : (index / (history.length - 1)) * chartWidth);
  const y = (value) => top + ((maximum - numberValue(value)) / range) * chartHeight;
  const points = history.map((entry, index) => `${x(index).toFixed(1)},${y(entry.dailyLimit).toFixed(1)}`).join(' ');
  const zeroY = y(0);
  const labels = history.map((entry, index) => {
    if (index !== 0 && index !== history.length - 1 && index % 3 !== 0) return '';
    return `<text x="${x(index).toFixed(1)}" y="${height - 8}" text-anchor="middle" fill="currentColor" opacity="0.48" font-size="10">${dateLabel(entry.date)}</text>`;
  }).join('');
  return `<svg class="savings-line-chart savings-daily-line-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily spending limit history">
      <line x1="${left}" y1="${zeroY.toFixed(1)}" x2="${width - right}" y2="${zeroY.toFixed(1)}" stroke="currentColor" opacity="0.12" stroke-dasharray="3 4"/>
      <polyline points="${points}" fill="none" stroke="var(--accent, #ee9fc5)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      ${history.map((entry, index) => `<circle cx="${x(index).toFixed(1)}" cy="${y(entry.dailyLimit).toFixed(1)}" r="3.5" fill="var(--accent, #ee9fc5)" stroke="var(--bg)" stroke-width="2"><title>${dateLabel(entry.date)}: ${money(entry.dailyLimit, 2)}</title></circle>`).join('')}
      <text x="3" y="${Math.min(height - bottom, Math.max(top + 10, y(maximum) + 4)).toFixed(1)}" fill="currentColor" opacity="0.42" font-size="10">${compactMoney(maximum)}</text>
      <text x="3" y="${Math.min(height - 8, Math.max(top + 10, y(minimum) + 4)).toFixed(1)}" fill="currentColor" opacity="0.42" font-size="10">${compactMoney(minimum)}</text>
      ${labels}
    </svg>`;
}

function expenseRow(transaction) {
  const wallet = _state.wallets.find((item) => item.id === transaction.walletId);
  const incoming = isIncomeTransaction(transaction);
  const color = CATEGORY_COLORS[transaction.category] || (incoming ? CATEGORY_COLORS.Income : CATEGORY_COLORS.Other);
  return `<div class="savings-expense-row${incoming ? ' savings-income-row' : ''}">
    <span class="savings-expense-mark" style="background:${color}">${icon(incoming ? 'arrowUp' : 'creditCard', 12)}</span>
    <span class="savings-expense-main"><strong>${escapeHtml(transaction.merchant)}</strong><small>${escapeHtml(transaction.category)} · ${escapeHtml(wallet?.name || 'Wallet')}</small></span>
    <strong class="savings-expense-amount${incoming ? ' savings-income-amount' : ''}">${incoming ? '+' : '−'}${money(transaction.amount, 2)}</strong>
    <button type="button" class="savings-small-button savings-edit-expense" data-savings-action="edit-expense" data-transaction-id="${escapeHtml(transaction.id)}" title="Edit expense">Edit</button>
  </div>`;
}

function renderExpenseGroups(transactions) {
  const groups = [];
  transactions.forEach((transaction) => {
    const key = String(transaction.date || '').slice(0, 10);
    let group = groups.find((item) => item.key === key);
    if (!group) {
      group = { key, rows: [] };
      groups.push(group);
    }
    group.rows.push(transaction);
  });
  return groups.map((group) => {
    const total = group.rows.reduce((sum, transaction) => sum + Math.abs(numberValue(transaction.amount)), 0);
    return `<section class="savings-expense-day">
      <div class="savings-expense-day-heading"><strong>${escapeHtml(dateLabel(group.key))}</strong><span>${group.rows.length} · ${money(total, 2)}</span></div>
      <div class="savings-expense-day-list">${group.rows.map(expenseRow).join('')}</div>
    </section>`;
  }).join('');
}

function renderOverview(metrics) {
  const snapshots = recentSnapshots();
  const streak = decreasingLimitStreak();
  const delta = dailyLimitDelta();
  const deltaText = delta > 0 ? `+${money(delta, 2)}` : delta < 0 ? `−${money(Math.abs(delta), 2)}` : '—';
  return `<div class="savings-screen savings-overview-screen">
    <div class="savings-screen-heading"><h2>Spending tracker</h2><div class="savings-screen-actions"><button type="button" class="savings-icon-button" data-savings-action="refresh" title="Refresh calculations">${icon('refresh', 15)}</button><button type="button" class="savings-icon-button" data-savings-action="add-expense" title="Add expense">${icon('plus', 16)}</button></div></div>
    ${streak >= 2 ? `<div class="savings-inline-warning">Limit down ${streak} days in a row</div>` : ''}
    <section class="savings-overview-top">
      <div class="savings-limit-readout"><h3>Daily limit</h3><strong>${money(metrics.dailyLimit, 2)}</strong><span class="savings-limit-change ${delta < 0 ? 'is-negative' : ''}">${deltaText}</span></div>
      <button type="button" class="savings-payday-tile" data-savings-action="open-settings" title="Payday settings"><span>Payday</span><strong>${metrics.payday.label}</strong><small>${metrics.payday.days} days</small></button>
    </section>
    <section class="savings-balance-block">
      <div class="savings-balance-list"><div><span>Balance</span><strong>${money(metrics.spendingBalance, 2)}</strong></div><div><span>Savings</span><strong>${money(totalSavings(), 2)}</strong></div><div><span>Total</span><strong>${money(grossAssets(), 2)}</strong></div></div>
      ${savingsDonut()}
    </section>
    <section class="savings-chart-section"><h3>Limit history</h3>${dailyLimitChart()}</section>
    <section class="savings-chart-section"><h3>Monthly averages</h3>${lineChart(snapshots)}</section>
  </div>`;
}

function walletCard(wallet) {
  const spendable = spendingBalanceForWallet(wallet);
  return `<article class="savings-wallet-row" style="--wallet-color:${escapeHtml(wallet.color || '#ee9fc5')}">
    <span class="savings-wallet-icon">${icon('wallet', 20)}</span>
    <div class="savings-wallet-name"><strong>${escapeHtml(wallet.name)}</strong><small>${wallet.includeSavings ? 'Savings included' : 'Savings separate'}</small></div>
    <div class="savings-wallet-amounts"><strong>${money(spendable, 2)}</strong><small>${money(wallet.savings, 2)} saved${numberValue(wallet.debt) > 0 ? ` · ${money(wallet.debt, 2)} debt` : ''}</small></div>
    <label class="savings-wallet-toggle" title="Include savings in balance" aria-label="Include savings in balance"><input type="checkbox" data-savings-toggle="${escapeHtml(wallet.id)}" ${wallet.includeSavings ? 'checked' : ''}><i></i></label>
    <span class="savings-wallet-actions"><button type="button" class="savings-row-action" data-savings-action="edit-wallet" data-wallet-id="${escapeHtml(wallet.id)}" title="Edit wallet">${icon('pencil', 13)}</button><button type="button" class="savings-row-action" data-savings-action="delete-wallet" data-wallet-id="${escapeHtml(wallet.id)}" title="Delete wallet">${icon('trash', 13)}</button></span>
  </article>`;
}

function renderImportPreview() {
  if (!_import) return '';
  if (!_import.rows.length) {
    return `<div class="savings-import-message savings-import-warning">${icon('info', 14)} ${escapeHtml(_import.message || 'No transactions found in this document.')}</div>`;
  }
  const selected = _import.rows.filter((row) => row.selected).length;
  const statement = _import.statement || {};
  const period = statement.periodStart && statement.periodEnd
    ? `${dateLabel(statement.periodStart)} – ${dateLabel(statement.periodEnd)}`
    : '';
  const summary = [statement.bank, period, statement.account ? `••${statement.account.slice(-4)}` : '']
    .filter(Boolean)
    .join(' · ');
  const categories = ['Needs', 'Wants', 'Assets', 'Debt', 'Other', 'Income'];
  const allSelected = selected === _import.rows.length;
  const canReconcile = allSelected && statement.closingBalance != null;
  const defaultWallet = _state.wallets.find((wallet) => wallet.id === _expenseWalletId)?.name || _state.wallets[0]?.name || 'wallet';
  return `<div class="savings-import-review">
    <div class="savings-import-review-header"><div><span class="savings-eyebrow">REVIEW BEFORE SAVING</span><strong>${selected} of ${_import.rows.length} selected</strong><small>${escapeHtml(_import.fileName)}${summary ? ` · ${escapeHtml(summary)}` : ''}</small></div><div class="savings-inline-actions"><button type="button" class="savings-text-button" data-savings-action="clear-import">Clear</button><button type="button" class="savings-small-button savings-primary-button" data-savings-action="accept-import" ${selected ? '' : 'disabled'}>${icon('check', 13)} Add to ledger</button></div></div>
    <div class="savings-import-summary"><span>${statement.expenseCount || 0} expenses · ${money(statement.expenseTotal || 0, 2)}</span><span>${statement.incomeCount || 0} income · ${money(statement.incomeTotal || 0, 2)}</span>${statement.closingBalance != null ? `<span>Closing balance · ${money(statement.closingBalance, 2)}</span>` : ''}</div>
    ${statement.closingBalance != null ? `<label class="savings-import-reconcile"><input id="savings-import-reconcile" type="checkbox" ${canReconcile ? 'checked' : ''} ${canReconcile ? '' : 'disabled'}><span>Set ${escapeHtml(defaultWallet)} balance to ${money(statement.closingBalance, 2)} after import${allSelected ? '' : ' · select all rows first'}</span></label>` : ''}
    <div class="savings-import-table">${_import.rows.map((row) => `<div class="savings-import-row">
      <input type="checkbox" data-savings-import-selected="${escapeHtml(row.id)}" ${row.selected ? 'checked' : ''}>
      <span class="savings-import-row-details"><input class="savings-import-merchant" type="text" data-savings-import-merchant="${escapeHtml(row.id)}" value="${escapeHtml(row.merchant)}" title="Merchant or description"><small>${dateLabel(row.date)} · ${escapeHtml(row.direction === 'income' ? 'Income' : row.operationType || 'Expense')}${row.externalId ? ` · ${escapeHtml(row.externalId)}` : ''}</small></span>
      <select data-savings-import-category="${escapeHtml(row.id)}" aria-label="Category for ${escapeHtml(row.merchant)}">${categories.map((category) => `<option value="${category}" ${category === (row.category || 'Other') ? 'selected' : ''}>${category}</option>`).join('')}</select>
      <select data-savings-import-wallet="${escapeHtml(row.id)}">${_state.wallets.map((wallet) => `<option value="${escapeHtml(wallet.id)}" ${wallet.id === row.walletId ? 'selected' : ''}>${escapeHtml(wallet.name)}</option>`).join('')}</select>
      <strong class="${row.direction === 'income' ? 'savings-positive' : 'savings-negative'}">${row.direction === 'income' ? '+' : '−'}${money(row.amount, 2)}</strong>
    </div>`).join('')}</div>
  </div>`;
}

function selectedExpenseWalletId() {
  if (_expenseWalletId !== 'all' && _state.wallets.some((wallet) => wallet.id === _expenseWalletId)) return _expenseWalletId;
  return _state.wallets[0]?.id || '';
}

function renderExpenses() {
  const walletId = _expenseWalletId;
  const transactions = _state.transactions
    .filter((transaction) => walletId === 'all' || transaction.walletId === walletId)
    .filter((transaction) => _expenseKind === 'all' || (_expenseKind === 'income' ? isIncomeTransaction(transaction) : !isIncomeTransaction(transaction)))
    .sort((a, b) => `${b.date}|${b.id}`.localeCompare(`${a.date}|${a.id}`));
  const expenseTotal = transactions.reduce((sum, transaction) => sum + Math.abs(numberValue(transaction.amount)), 0);
  const title = _expenseKind === 'income' ? 'Income' : _expenseKind === 'all' ? 'Activity' : 'Expenses';
  return `<div class="savings-screen savings-expenses-screen">
    <div class="savings-screen-heading"><h2>Expenses</h2><div class="savings-screen-actions"><button type="button" class="savings-icon-button" data-savings-action="refresh" title="Refresh calculations">${icon('refresh', 15)}</button><button type="button" class="savings-small-button" data-savings-action="choose-document" title="Import statement">${icon('file', 13)} Import</button><button type="button" class="savings-small-button savings-primary-button" data-savings-action="add-expense" title="Add expense">${icon('plus', 13)} Add expense</button></div></div>
    <div class="savings-expenses-toolbar">
      <label><span>Wallet</span><select data-savings-expense-wallet>${_state.wallets.map((wallet) => `<option value="${escapeHtml(wallet.id)}" ${wallet.id === walletId ? 'selected' : ''}>${escapeHtml(wallet.name)}</option>`).join('')}<option value="all" ${walletId === 'all' ? 'selected' : ''}>All wallets</option></select></label>
      <label><span>Show</span><select data-savings-expense-kind><option value="expense" ${_expenseKind === 'expense' ? 'selected' : ''}>Expenses</option><option value="income" ${_expenseKind === 'income' ? 'selected' : ''}>Income</option><option value="all" ${_expenseKind === 'all' ? 'selected' : ''}>All activity</option></select></label>
    </div>
    <input id="savings-document-input" type="file" accept=".pdf,.csv,.tsv,.txt,.json,.ofx,.mt940,application/pdf,text/csv,text/plain,application/json" hidden>
    ${_import?.busy ? `<div class="savings-expenses-import-state savings-import-loading"><span class="savings-spinner"></span><span><strong>Reading ${escapeHtml(_import.fileName)}…</strong><small>Preparing transactions for review</small></span></div>` : ''}
    ${_import && !_import.busy ? renderImportPreview() : ''}
    <section class="savings-expenses-section"><div class="savings-section-heading"><h3>${title}</h3><span>${transactions.length} · ${money(expenseTotal, 2)}</span></div>${transactions.length ? renderExpenseGroups(transactions) : '<div class="savings-empty">No transactions in this view yet.</div>'}</section>
  </div>`;
}

function renderWallets() {
  const walletTotal = spendingBalance();
  return `<div class="savings-screen savings-wallets-screen">
    <div class="savings-screen-heading"><h2>Wallets</h2><div class="savings-screen-actions"><button type="button" class="savings-icon-button" data-savings-action="refresh" title="Refresh calculations">${icon('refresh', 15)}</button><button type="button" class="savings-icon-button" data-savings-action="show-expenses" title="Open expenses">${icon('file', 16)}</button><button type="button" class="savings-icon-button" data-savings-action="add-wallet" title="Add wallet">${icon('plus', 17)}</button></div></div>
    <div class="savings-wallet-total"><span>Available for spending</span><strong>${money(walletTotal, 2)}</strong></div>
    <div class="savings-wallet-list">${_state.wallets.map(walletCard).join('')}</div>
    ${walletDistributionChart()}
  </div>`;
}

function renderStatistics(metrics) {
  const snapshots = recentSnapshots();
  const average = (key) => snapshots.reduce((sum, snapshot) => sum + numberValue(snapshot[key]), 0) / Math.max(1, snapshots.length);
  const categoryEntries = Object.entries(allCategoryTotals()).sort((a, b) => b[1] - a[1]);
  const categoryMax = Math.max(1, ...categoryEntries.map(([, value]) => value));
  const assets = grossAssets();
  const liabilities = totalDebt();
  const netWorth = assets - liabilities;
  const runway = metrics.snapshot.expenses ? availableBalance() / metrics.snapshot.expenses : 0;
  const allExpenses = categoryEntries.reduce((sum, [, amount]) => sum + amount, 0);
  return `<div class="savings-screen savings-statistics-screen">
    <div class="savings-screen-heading"><h2>Statistics</h2><div class="savings-screen-actions"><button type="button" class="savings-icon-button" data-savings-action="refresh" title="Refresh calculations">${icon('refresh', 15)}</button><button type="button" class="savings-icon-button" data-savings-action="export-csv" title="Export ledger">${icon('download', 15)}</button></div></div>
    <div class="savings-simple-metrics">
      ${simpleMetric('Average expenses', money(average('expenses')))}
      ${simpleMetric('Average savings', money(average('savings')))}
      ${simpleMetric('Estimated income', money(estimatedMonthlyIncome()), 'based on previous months')}
      ${simpleMetric('Net worth', money(netWorth))}
    </div>
    <section class="savings-flat-section"><div class="savings-section-heading"><h3>Monthly history</h3><span>edit or clear a month</span></div><div class="savings-table-scroll"><table class="savings-table savings-monthly-table"><thead><tr><th>Month</th><th>Income</th><th>Expenses</th><th>Savings</th><th>Cash flow</th><th></th></tr></thead><tbody>${snapshots.slice().reverse().map((snapshot) => {
      const cashflow = snapshot.income - snapshot.expenses - snapshot.savings;
      const status = snapshot.cleared ? 'cleared' : snapshot.key === CURRENT_MONTH ? 'current' : '';
      return `<tr><td><strong>${monthTitle(snapshot.key)}</strong>${status ? `<small>${status}</small>` : ''}</td><td>${money(snapshot.income)}</td><td>${money(snapshot.expenses)}</td><td class="savings-positive">${money(snapshot.savings)}</td><td class="${cashflow >= 0 ? 'savings-positive' : 'savings-negative'}">${money(cashflow)}</td><td><span class="savings-table-actions"><button type="button" class="savings-text-button savings-edit-month" data-savings-action="edit-month" data-month-key="${escapeHtml(snapshot.key)}">Edit</button><button type="button" class="savings-text-button savings-clear-month" data-savings-action="clear-month" data-month-key="${escapeHtml(snapshot.key)}">Clear</button></span></td></tr>`;
    }).join('')}</tbody></table></div></section>
    <section class="savings-flat-section"><div class="savings-section-heading"><h3>Spending by category</h3><span>${money(allExpenses)} recorded</span></div><div class="savings-category-list">${categoryEntries.length ? categoryEntries.map(([category, amount]) => `<div class="savings-category-row"><div class="savings-category-label"><span class="savings-category-dot" style="background:${CATEGORY_COLORS[category] || CATEGORY_COLORS.Other}"></span><strong>${escapeHtml(category)}</strong><span>${money(amount)}</span></div><div class="savings-category-track"><i style="width:${Math.round((amount / categoryMax) * 100)}%;background:${CATEGORY_COLORS[category] || CATEGORY_COLORS.Other}"></i></div></div>`).join('') : '<div class="savings-empty">Add expenses to see categories.</div>'}</div></section>
    <section class="savings-flat-section"><div class="savings-section-heading"><h3>Assets and liabilities</h3><span>${metrics.cashflow >= 0 && netWorth >= 0 ? 'Healthy' : 'Review'}</span></div><div class="savings-balance-columns"><div><span class="savings-balance-label">Assets</span><strong class="savings-positive">${money(assets)}</strong></div><div><span class="savings-balance-label">Debt</span><strong class="savings-negative">${money(liabilities)}</strong></div><div><span class="savings-balance-label">Net worth</span><strong>${money(netWorth)}</strong></div></div><div class="savings-balance-bar"><i style="width:${Math.min(100, (assets / Math.max(1, assets + liabilities)) * 100)}%"></i></div>${metrics.snapshot.expenses ? `<small class="savings-monthly-runway">Current spending covers about ${runway.toFixed(1)} months.</small>` : ''}</section>
  </div>`;
}

function clearMonth(key) {
  if (!/^\d{4}-\d{2}$/.test(String(key || ''))) return;
  const monthTransactions = transactionsFor(key);
  if (!monthTransactions.length && _state.months.find((snapshot) => snapshot.key === key)?.cleared) return;
  const monthName = monthTitle(key);
  const remove = async () => {
    const confirmed = uiModule.styledConfirm
      ? await uiModule.styledConfirm(`Clear all entries from ${monthName}?`, { confirmText: 'Clear month', cancelText: 'Cancel', danger: true })
      : window.confirm(`Clear all entries from ${monthName}?`);
    if (!confirmed) return;
    monthTransactions.forEach((transaction) => {
      const wallet = _state.wallets.find((item) => item.id === transaction.walletId);
      if (wallet && affectsWalletBalance(transaction)) {
        wallet.balance = numberValue(wallet.balance) - signedTransactionAmount(transaction);
      }
    });
    _state.transactions = _state.transactions.filter((transaction) => !String(transaction.date || '').startsWith(`${key}-`));
    _state.dailyHistory = (_state.dailyHistory || []).filter((entry) => !String(entry.date || '').startsWith(`${key}-`));
    const snapshot = _state.months.find((item) => item.key === key);
    if (snapshot) Object.assign(snapshot, { income: 0, limit: 0, expenses: 0, savings: 0, debt: 0, incomeOverride: 0, expensesOverride: 0, cleared: true });
    else _state.months.push({ key, income: 0, limit: 0, expenses: 0, savings: 0, debt: 0, incomeOverride: 0, expensesOverride: 0, cleared: true });
    saveState();
    uiModule.showToast(`${monthName} cleared`);
    render();
  };
  remove();
}

function refreshCalculations() {
  refreshMonthLedgerTotals(_state.months.map((snapshot) => snapshot.key));
  recordDailySnapshot();
  saveState();
  uiModule.showToast('Calculations refreshed');
  render();
}

function dialogHtml() {
  if (!_dialog) return '';
  if (_dialog.type === 'expense') {
    const transaction = _state.transactions.find((item) => item.id === _dialog.id);
    const categories = transaction?.direction === 'income'
      ? ['Income', 'Needs', 'Wants', 'Assets', 'Debt', 'Other']
      : ['Needs', 'Wants', 'Assets', 'Debt', 'Other'];
    return `<div class="savings-dialog-backdrop" data-savings-action="close-dialog"><form class="savings-dialog" data-savings-form="expense" data-transaction-id="${escapeHtml(transaction?.id || '')}">
      <div class="savings-dialog-header"><div><span class="savings-eyebrow">LEDGER ENTRY</span><h3>${transaction ? 'Edit expense' : 'Add expense'}</h3></div><button type="button" class="savings-row-action" data-savings-action="close-dialog">${icon('x', 13)}</button></div>
      <label>Merchant / description<input name="merchant" required value="${escapeHtml(transaction?.merchant || '')}" placeholder="e.g. Grocery market"></label>
      <div class="savings-form-grid"><label>Amount (PLN)<input name="amount" required inputmode="decimal" value="${transaction ? escapeHtml(transaction.amount) : ''}" placeholder="0.00"></label><label>Date<input name="date" type="date" required value="${escapeHtml(transaction?.date || isoDateForMonth(selectedMonth(), new Date().getDate()))}"></label></div>
      <div class="savings-form-grid"><label>Category<select name="category">${categories.map((category) => `<option ${category === (transaction?.category || 'Needs') ? 'selected' : ''}>${category}</option>`).join('')}</select></label><label>Wallet<select name="walletId">${_state.wallets.map((wallet) => `<option value="${escapeHtml(wallet.id)}" ${wallet.id === (transaction?.walletId || _state.wallets[0]?.id) ? 'selected' : ''}>${escapeHtml(wallet.name)}</option>`).join('')}</select></label></div>
      <div class="savings-dialog-actions">${transaction ? `<button type="button" class="savings-small-button savings-danger-button" data-savings-action="delete-expense" data-transaction-id="${escapeHtml(transaction.id)}">Delete</button>` : ''}<button type="button" class="savings-small-button" data-savings-action="close-dialog">Cancel</button><button type="submit" class="savings-small-button savings-primary-button">${icon('check', 13)} ${transaction ? 'Save changes' : 'Save expense'}</button></div>
    </form></div>`;
  }
  if (_dialog.type === 'month') {
    const key = String(_dialog.id || CURRENT_MONTH);
    const snapshot = snapshotFor(key);
    return `<div class="savings-dialog-backdrop" data-savings-action="close-dialog"><form class="savings-dialog" data-savings-form="month" data-month-key="${escapeHtml(key)}">
      <div class="savings-dialog-header"><div><span class="savings-eyebrow">MONTHLY SUMMARY</span><h3>Edit ${escapeHtml(monthTitle(key))}</h3></div><button type="button" class="savings-row-action" data-savings-action="close-dialog">${icon('x', 13)}</button></div>
      <p class="savings-dialog-help">Update the saved summary for this month. New entries in Expenses continue to update the statistics automatically.</p>
      <div class="savings-form-grid"><label>Income<input name="income" inputmode="decimal" value="${escapeHtml(snapshot.income)}" placeholder="0.00"></label><label>Expenses<input name="expenses" inputmode="decimal" value="${escapeHtml(snapshot.expenses)}" placeholder="0.00"></label></div>
      <label>Savings<input name="savings" inputmode="decimal" value="${escapeHtml(snapshot.savings)}" placeholder="0.00"></label>
      <div class="savings-dialog-actions"><button type="button" class="savings-small-button" data-savings-action="close-dialog">Cancel</button><button type="submit" class="savings-small-button savings-primary-button">${icon('check', 13)} Save changes</button></div>
    </form></div>`;
  }
  if (_dialog.type === 'wallet') {
    const wallet = _state.wallets.find((item) => item.id === _dialog.id);
    return `<div class="savings-dialog-backdrop" data-savings-action="close-dialog"><form class="savings-dialog" data-savings-form="wallet" data-wallet-id="${escapeHtml(wallet?.id || '')}">
      <div class="savings-dialog-header"><div><span class="savings-eyebrow">WALLET SETUP</span><h3>${wallet ? 'Edit wallet' : 'Add wallet'}</h3></div><button type="button" class="savings-row-action" data-savings-action="close-dialog">${icon('x', 13)}</button></div>
      <label>Wallet name<input name="name" required value="${escapeHtml(wallet?.name || '')}" placeholder="e.g. Travel fund"></label>
      <div class="savings-form-grid"><label>Balance<input name="balance" required inputmode="decimal" value="${escapeHtml(wallet?.balance ?? '')}" placeholder="0.00"></label><label>Savings<input name="savings" required inputmode="decimal" value="${escapeHtml(wallet?.savings ?? '')}" placeholder="0.00"></label></div>
      <label>Debt<input name="debt" required inputmode="decimal" value="${escapeHtml(wallet?.debt ?? '')}" placeholder="0.00"></label>
      <p class="savings-dialog-help">If Balance is negative, it is saved as Debt and the balance becomes zero.</p>
      <label class="savings-dialog-check"><input type="checkbox" name="includeSavings" ${wallet?.includeSavings ? 'checked' : ''}><span>Include savings in balance</span></label>
      <div class="savings-dialog-actions"><button type="button" class="savings-small-button" data-savings-action="close-dialog">Cancel</button><button type="submit" class="savings-small-button savings-primary-button">${icon('check', 13)} Save wallet</button></div>
    </form></div>`;
  }
  return `<div class="savings-dialog-backdrop" data-savings-action="close-dialog"><form class="savings-dialog" data-savings-form="settings">
    <div class="savings-dialog-header"><div><span class="savings-eyebrow">SETTINGS</span><h3>Payday</h3></div><button type="button" class="savings-row-action" data-savings-action="close-dialog">${icon('x', 13)}</button></div>
    <p class="savings-dialog-help">Choose the day your salary arrives. The daily limit recalculates automatically; monthly income is estimated in Statistics.</p>
    <label>Payday date<input name="payday" type="date" required value="${escapeHtml(paydayInputValue())}"></label>
    <div class="savings-dialog-actions"><button type="button" class="savings-small-button" data-savings-action="close-dialog">Cancel</button><button type="submit" class="savings-small-button savings-primary-button">${icon('check', 13)} Save</button></div>
  </form></div>`;
}

function render() {
  const root = document.getElementById('savings-root');
  if (!root) return;
  recordDailySnapshot();
  const metrics = selectedMetrics();
  root.innerHTML = `<div class="savings-app">
    ${_activeTab === 'overview' ? renderOverview(metrics) : ''}${_activeTab === 'expenses' ? renderExpenses() : ''}${_activeTab === 'wallets' ? renderWallets() : ''}${_activeTab === 'stats' ? renderStatistics(metrics) : ''}
    <nav class="savings-bottom-nav" role="tablist" aria-label="Savings sections">${tabButton('overview', 'Overview', 'house')}${tabButton('expenses', 'Expenses', 'file')}${tabButton('wallets', 'Wallets', 'wallet')}${tabButton('stats', 'Statistics', 'chartBar')}</nav>
    ${dialogHtml()}
  </div>`;
  root.querySelectorAll('[data-savings-tab]').forEach((button) => {
    button.addEventListener('click', () => {
      _activeTab = button.dataset.savingsTab;
      _dialog = null;
      render();
    });
  });
}

async function processDocument(file) {
  if (!file) return;
  const importWalletId = selectedExpenseWalletId();
  _import = { busy: true, fileName: file.name, rows: [], walletId: importWalletId, message: '' };
  render();
  let text = '';
  let source = 'local';
  let parsed = null;
  let parserError = '';
  try {
    if (isStatementDocument(file)) {
      parsed = await readStatementWithParser(file);
      source = 'structured';
    } else if (/^image\//i.test(String(file.type || ''))) {
      source = 'vision';
      text = await readImageWithVision(file);
    } else if (isTextDocument(file) && typeof file.text === 'function') {
      text = await file.text();
    }
  } catch (error) {
    parserError = error?.message || 'Could not read the statement';
    console.warn('Savings document read failed:', error);
    // Text files can still be imported when the optional server endpoint is
    // unavailable. Binary PDFs are not guessed from browser-side bytes.
    if (!isStatementDocument(file) && isTextDocument(file) && typeof file.text === 'function') {
      try {
        text = await file.text();
        source = 'local';
      } catch (_) {}
    }
  }
  const rows = (Array.isArray(parsed?.rows) ? parsed.rows : parseDocumentText(text, selectedMonth()))
    .filter((row) => row && numberValue(row.amount) > 0)
    .map((row, index) => ({
      id: String(row.id || `import-${Date.now()}-${index}`),
      externalId: String(row.externalId || row.external_id || ''),
      date: String(row.date || isoDateForMonth(selectedMonth(), new Date().getDate())),
      merchant: String(row.merchant || row.description || `Imported transaction ${index + 1}`),
      description: String(row.description || row.merchant || ''),
      operationType: String(row.operationType || 'Imported transaction'),
      category: String(row.category || (row.direction === 'income' ? 'Income' : 'Other')),
      categoryConfidence: numberValue(row.categoryConfidence, 0),
      amount: Math.abs(numberValue(row.amount)),
      direction: row.direction === 'income' ? 'income' : 'expense',
      balanceAfter: row.balanceAfter == null ? null : numberValue(row.balanceAfter),
      walletId: String(row.walletId || importWalletId),
      selected: row.selected !== false,
    }));
  const statement = parsed?.statement || null;
  _import = {
    busy: false,
    fileName: file.name,
    rows,
    walletId: importWalletId,
    statement,
    source,
    message: rows.length
      ? `${source === 'structured' ? 'Transactions detected. ' : source === 'vision' ? 'AI found possible line items. ' : ''}Review the description, category and wallet before saving.`
      : source === 'vision'
        ? 'AI did not return readable line items. Check Vision in Settings or add an expense manually.'
        : parserError || 'No transactions found in this document. Try a bank PDF/CSV export or add an expense manually.',
  };
  render();
}

function acceptImport() {
  if (!_import?.rows?.length) return;
  const rows = _import.rows.filter((row) => row.selected && row.amount > 0);
  if (!rows.length) return;
  const existingIds = new Set(_state.transactions.map((transaction) => String(transaction.id)));
  const existingExternalIds = new Set(_state.transactions.map((transaction) => String(transaction.externalId || '')).filter(Boolean));
  const seen = new Set();
  const newRows = rows.filter((row) => {
    const externalId = String(row.externalId || '');
    const key = externalId || String(row.id);
    if (existingIds.has(String(row.id)) || (externalId && existingExternalIds.has(externalId)) || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  newRows.forEach((row) => {
    const wallet = _state.wallets.find((item) => item.id === row.walletId) || _state.wallets[0];
    if (!wallet) return;
    _state.transactions.push({
      id: row.id,
      externalId: row.externalId || '',
      date: row.date,
      merchant: row.merchant,
      description: row.description || row.merchant,
      operationType: row.operationType || 'Imported transaction',
      category: row.category,
      categoryConfidence: numberValue(row.categoryConfidence, 0),
      amount: row.amount,
      direction: row.direction === 'income' ? 'income' : 'expense',
      balanceAfter: row.balanceAfter == null ? null : numberValue(row.balanceAfter),
      walletId: wallet.id,
      source: 'bank-statement',
    });
    const monthKeyForRow = String(row.date || '').slice(0, 7);
    adjustMonthlyOverride(monthKeyForRow, row.direction === 'income' ? 'incomeOverride' : 'expensesOverride', row.amount);
  });
  refreshMonthLedgerTotals(newRows.map((row) => String(row.date || '').slice(0, 7)).filter(Boolean));
  const statement = _import.statement || {};
  const reconcile = document.getElementById('savings-import-reconcile')?.checked === true;
  const reconciliationWallet = _state.wallets.find((wallet) => wallet.id === _import.walletId);
  if (newRows.length && reconcile && statement.closingBalance != null && reconciliationWallet) {
    reconciliationWallet.balance = numberValue(statement.closingBalance);
  }
  saveState();
  _import = null;
  if (newRows.length) {
    const duplicateText = newRows.length < rows.length ? ` · ${rows.length - newRows.length} already imported` : '';
    uiModule.showToast(`Added ${newRows.length} ${newRows.length === 1 ? 'transaction' : 'transactions'}${duplicateText}`);
  } else {
    uiModule.showToast('No new transactions — this statement is already imported');
  }
  _activeTab = 'expenses';
  render();
}

function exportCsv() {
  const headers = ['date', 'merchant', 'category', 'direction', 'amount_pln', 'wallet', 'external_id', 'source'];
  const lines = _state.transactions.map((transaction) => {
    const wallet = _state.wallets.find((item) => item.id === transaction.walletId);
    return [transaction.date, transaction.merchant, transaction.category, transaction.direction || 'expense', Math.abs(numberValue(transaction.amount)).toFixed(2), wallet?.name || '', transaction.externalId || '', transaction.source || 'manual']
      .map((value) => `"${String(value).replace(/"/g, '""')}"`).join(',');
  });
  const blob = new Blob([[headers.join(','), ...lines].join('\\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'savings-ledger.csv';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 500);
  uiModule.showToast('Ledger exported');
}

async function handleClick(event) {
  const actionElement = event.target.closest?.('[data-savings-action]');
  if (!actionElement) return;
  const action = actionElement.dataset.savingsAction;
  if (action === 'choose-document') {
    document.getElementById('savings-document-input')?.click();
  } else if (action === 'close-dialog') {
    if (actionElement.classList.contains('savings-dialog-backdrop') && event.target !== actionElement) return;
    if (actionElement.classList.contains('savings-dialog-backdrop') || actionElement.closest('.savings-dialog')) closeDialog();
  } else if (action === 'open-settings') {
    openDialog('settings');
  } else if (action === 'show-wallets') {
    _activeTab = 'wallets';
    _dialog = null;
    render();
  } else if (action === 'show-expenses') {
    _activeTab = 'expenses';
    _dialog = null;
    render();
  } else if (action === 'refresh') {
    refreshCalculations();
  } else if (action === 'prev-month') {
    _monthOffset -= 1;
    _dialog = null;
    render();
  } else if (action === 'next-month' && _monthOffset < 0) {
    _monthOffset += 1;
    _dialog = null;
    render();
  } else if (action === 'add-expense') {
    openDialog('expense');
  } else if (action === 'edit-expense') {
    openDialog('expense', actionElement.dataset.transactionId);
  } else if (action === 'edit-month') {
    openDialog('month', actionElement.dataset.monthKey);
  } else if (action === 'add-wallet') {
    openDialog('wallet');
  } else if (action === 'edit-wallet') {
    openDialog('wallet', actionElement.dataset.walletId);
  } else if (action === 'delete-wallet') {
    const walletId = actionElement.dataset.walletId;
    if (_state.wallets.length <= 1) {
      uiModule.showToast('Keep at least one wallet');
      return;
    }
    const wallet = _state.wallets.find((item) => item.id === walletId);
    const confirmed = uiModule.styledConfirm
      ? await uiModule.styledConfirm(`Delete “${wallet?.name || 'this wallet'}”? Existing expenses stay in the ledger.`, { confirmText: 'Delete', cancelText: 'Cancel', danger: true })
      : window.confirm(`Delete ${wallet?.name || 'this wallet'}?`);
    if (!confirmed) return;
    _state.wallets = _state.wallets.filter((item) => item.id !== walletId);
    _state.transactions.forEach((transaction) => {
      if (transaction.walletId === walletId) transaction.walletId = _state.wallets[0].id;
    });
    saveState();
    render();
  } else if (action === 'clear-month') {
    clearMonth(actionElement.dataset.monthKey);
  } else if (action === 'delete-expense') {
    const transaction = _state.transactions.find((item) => item.id === actionElement.dataset.transactionId);
    if (!transaction) return;
    const confirmed = uiModule.styledConfirm
      ? await uiModule.styledConfirm(`Remove “${transaction.merchant}” from this ledger?`, { confirmText: 'Remove', cancelText: 'Cancel', danger: true })
      : window.confirm(`Remove ${transaction.merchant}?`);
    if (!confirmed) return;
    const wallet = _state.wallets.find((item) => item.id === transaction.walletId);
    if (wallet && affectsWalletBalance(transaction)) {
      wallet.balance = numberValue(wallet.balance) - signedTransactionAmount(transaction);
    }
    const monthKeyForTransaction = String(transaction.date || '').slice(0, 7);
    adjustMonthlyOverride(monthKeyForTransaction, isIncomeTransaction(transaction) ? 'incomeOverride' : 'expensesOverride', -Math.abs(numberValue(transaction.amount)));
    _state.transactions = _state.transactions.filter((item) => item.id !== transaction.id);
    refreshMonthLedgerTotals([monthKeyForTransaction]);
    saveState();
    uiModule.showToast('Expense deleted');
    render();
  } else if (action === 'clear-import') {
    _import = null;
    render();
  } else if (action === 'accept-import') {
    acceptImport();
  } else if (action === 'save-snapshot') {
    const snapshot = snapshotFor(CURRENT_MONTH);
    const index = _state.months.findIndex((item) => item.key === CURRENT_MONTH);
    if (index >= 0) _state.months[index] = snapshot;
    else _state.months.push(snapshot);
    saveState();
    uiModule.showToast(`${monthTitle(CURRENT_MONTH)} snapshot saved`);
    render();
  } else if (action === 'export-csv') {
    exportCsv();
  }
}

function handleChange(event) {
  const target = event.target;
  if (target.matches('[data-savings-toggle]')) {
    const wallet = _state.wallets.find((item) => item.id === target.dataset.savingsToggle);
    if (!wallet) return;
    wallet.includeSavings = target.checked;
    saveState();
    render();
    return;
  }
  if (target.matches('[data-savings-expense-wallet]')) {
    _expenseWalletId = target.value;
    if (_import && _expenseWalletId !== 'all') {
      _import.walletId = _expenseWalletId;
      _import.rows.forEach((row) => { row.walletId = _expenseWalletId; });
    }
    render();
    return;
  }
  if (target.matches('[data-savings-expense-kind]')) {
    _expenseKind = target.value;
    render();
    return;
  }
  if (target.matches('[data-savings-import-selected]')) {
    const row = _import?.rows?.find((item) => item.id === target.dataset.savingsImportSelected);
    if (row) row.selected = target.checked;
    render();
    return;
  }
  if (target.matches('[data-savings-import-wallet]')) {
    const row = _import?.rows?.find((item) => item.id === target.dataset.savingsImportWallet);
    if (row) row.walletId = target.value;
    return;
  }
  if (target.matches('[data-savings-import-category]')) {
    const row = _import?.rows?.find((item) => item.id === target.dataset.savingsImportCategory);
    if (row) row.category = target.value;
    return;
  }
  if (target.id === 'savings-document-input') {
    const file = target.files?.[0];
    target.value = '';
    processDocument(file);
  }
}

function handleInput(event) {
  const target = event.target;
  if (!target.matches('[data-savings-import-merchant]')) return;
  const row = _import?.rows?.find((item) => item.id === target.dataset.savingsImportMerchant);
  if (row) row.merchant = target.value;
}

function handleSubmit(event) {
  const form = event.target.closest('form[data-savings-form]');
  if (!form) return;
  event.preventDefault();
  const formData = new FormData(form);
  const type = form.dataset.savingsForm;
  if (type === 'expense') {
    const amount = Math.abs(parseMoney(formData.get('amount')));
    const walletId = String(formData.get('walletId') || _state.wallets[0]?.id || '');
    const existing = _state.transactions.find((item) => item.id === form.dataset.transactionId);
    const oldMonthKey = existing ? String(existing.date || '').slice(0, 7) : '';
    const direction = existing?.direction === 'income' ? 'income' : 'expense';
    const transaction = {
      id: existing?.id || `transaction-${Date.now()}`,
      externalId: existing?.externalId || '',
      date: String(formData.get('date') || isoDateForMonth(selectedMonth(), new Date().getDate())),
      merchant: String(formData.get('merchant') || 'Expense').trim(),
      description: existing?.description || '',
      operationType: existing?.operationType || 'Manual expense',
      category: String(formData.get('category') || 'Other'),
      categoryConfidence: 1,
      amount,
      direction,
      balanceAfter: null,
      walletId,
      source: existing?.source || 'manual',
    };
    if (!transaction.merchant || !amount) return;
    if (existing) {
      const oldWallet = _state.wallets.find((item) => item.id === existing.walletId);
      const newWallet = _state.wallets.find((item) => item.id === walletId);
      if (oldWallet && affectsWalletBalance(existing)) oldWallet.balance = numberValue(oldWallet.balance) - signedTransactionAmount(existing);
      if (newWallet && affectsWalletBalance(transaction)) newWallet.balance = numberValue(newWallet.balance) + signedTransactionAmount(transaction);
      adjustMonthlyOverride(oldMonthKey, isIncomeTransaction(existing) ? 'incomeOverride' : 'expensesOverride', -Math.abs(numberValue(existing.amount)));
      Object.assign(existing, transaction);
      adjustMonthlyOverride(String(transaction.date || '').slice(0, 7), isIncomeTransaction(transaction) ? 'incomeOverride' : 'expensesOverride', Math.abs(numberValue(transaction.amount)));
    } else {
      const wallet = _state.wallets.find((item) => item.id === walletId);
      if (wallet && affectsWalletBalance(transaction)) wallet.balance += signedTransactionAmount(transaction);
      _state.transactions.push(transaction);
      adjustMonthlyOverride(String(transaction.date || '').slice(0, 7), 'expensesOverride', amount);
    }
    refreshMonthLedgerTotals([oldMonthKey, String(transaction.date || '').slice(0, 7)].filter(Boolean));
    saveState();
    _dialog = null;
    uiModule.showToast(existing ? 'Expense updated' : 'Expense added');
    render();
  } else if (type === 'wallet') {
    const name = String(formData.get('name') || '').trim();
    if (!name) return;
    const existing = _state.wallets.find((item) => item.id === form.dataset.walletId);
    const enteredBalance = parseMoney(formData.get('balance'));
    const convertedDebt = enteredBalance < 0 ? Math.abs(enteredBalance) : 0;
    const data = {
      name,
      balance: Math.max(0, enteredBalance),
      savings: Math.max(0, parseMoney(formData.get('savings'))),
      debt: Math.max(0, parseMoney(formData.get('debt')), convertedDebt),
      includeSavings: formData.get('includeSavings') === 'on',
    };
    if (existing) Object.assign(existing, data);
    else _state.wallets.push({ id: `wallet-${Date.now()}`, ...data, color: '#c4b5d8' });
    saveState();
    _dialog = null;
    uiModule.showToast(existing ? 'Wallet updated' : 'Wallet added');
    render();
  } else if (type === 'month') {
    const key = String(form.dataset.monthKey || CURRENT_MONTH);
    if (!/^\d{4}-\d{2}$/.test(key)) return;
    const values = {
      income: Math.max(0, parseMoney(formData.get('income'))),
      expenses: Math.max(0, parseMoney(formData.get('expenses'))),
      savings: Math.max(0, parseMoney(formData.get('savings'))),
    };
    let snapshot = _state.months.find((item) => item.key === key);
    if (!snapshot) {
      snapshot = { key, limit: key === CURRENT_MONTH ? numberValue(_state.settings.monthlyLimit) : 0, debt: 0 };
      _state.months.push(snapshot);
    }
    Object.assign(snapshot, values, {
      incomeOverride: values.income,
      expensesOverride: values.expenses,
      cleared: false,
    });
    saveState();
    _dialog = null;
    uiModule.showToast('Monthly summary updated');
    render();
  } else if (type === 'settings') {
    const paydayValue = String(formData.get('payday') || '');
    const paydayMatch = paydayValue.match(/^\d{4}-\d{2}-(\d{2})$/);
    if (!paydayMatch) return;
    _state.settings.payday = Math.min(31, Math.max(1, Number(paydayMatch[1])));
    saveState();
    _dialog = null;
    uiModule.showToast('Payday updated');
    render();
  }
}

function setLauncherState(active) {
  document.getElementById('tool-savings-btn')?.classList.toggle('active', active);
  document.getElementById('rail-savings')?.classList.toggle('active-section', active);
}

function teardown() {
  const modal = document.getElementById('savings-modal');
  if (modal?.classList.contains('modal-right-docked') || modal?.classList.contains('modal-left-docked')) {
    try { clearRightDock(modal); } catch (_) {}
  }
  if (modal) modal.remove();
  _open = false;
  _dialog = null;
  _import = null;
  setLauncherState(false);
  if (_escHandler) {
    document.removeEventListener('keydown', _escHandler, true);
    _escHandler = null;
  }
}

export function openSavings() {
  if (_open && document.getElementById('savings-modal')) return;
  _state = loadState();
  _open = true;
  _activeTab = 'overview';
  _monthOffset = 0;
  _expenseWalletId = _state.wallets[0]?.id || 'all';
  _expenseKind = 'expense';
  setLauncherState(true);
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'savings-modal';
  modal.innerHTML = `<div class="modal-content savings-modal-content">
    <div class="modal-header savings-modal-header"><h4>${icon('wallet', 16)} <span>Savings</span></h4><span class="savings-modal-spacer"></span><button class="close-btn" id="savings-close" type="button" title="Close">✕</button></div>
    <div class="modal-body savings-modal-body"><div id="savings-root"></div></div>
  </div>`;
  document.body.appendChild(modal);
  const root = modal.querySelector('#savings-root');
  root.addEventListener('click', handleClick);
  root.addEventListener('change', handleChange);
  root.addEventListener('input', handleInput);
  root.addEventListener('submit', handleSubmit);
  root.addEventListener('dragover', (event) => {
    const zone = event.target.closest?.('#savings-dropzone');
    if (!zone) return;
    event.preventDefault();
    zone.classList.add('is-dragging');
  });
  root.addEventListener('dragleave', (event) => {
    event.target.closest?.('#savings-dropzone')?.classList.remove('is-dragging');
  });
  root.addEventListener('drop', (event) => {
    const zone = event.target.closest?.('#savings-dropzone');
    if (!zone) return;
    event.preventDefault();
    zone.classList.remove('is-dragging');
    processDocument(event.dataTransfer?.files?.[0]);
  });
  modal.querySelector('#savings-close').addEventListener('click', closeSavings);
  modal.addEventListener('click', (event) => {
    if (event.target === modal) {
      event.stopPropagation();
      closeSavings();
    }
  });
  const content = modal.querySelector('.modal-content');
  const header = modal.querySelector('.modal-header');
  if (content && header) makeWindowDraggable(modal, { content, header });
  Modals.register('savings-modal', {
    railBtnId: 'rail-savings',
    sidebarBtnId: 'tool-savings-btn',
    label: 'Savings',
    icon: icon('wallet', 14),
    restoreFn: () => {
      _open = true;
      setLauncherState(true);
    },
    closeFn: teardown,
  });
  Modals.injectMinimizeButton(modal, 'savings-modal');
  _escHandler = (event) => {
    if (event.key !== 'Escape' || !_open) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (_dialog) closeDialog();
    else closeSavings();
  };
  document.addEventListener('keydown', _escHandler, true);
  render();
  syncWithServer();
  // Savings opens as a right-side workspace panel, matching Notes. The
  // shared dock keeps the chat/workspace visible and reserves the panel's
  // width instead of placing a large floating modal over the screen.
  if (window.innerWidth > 768) {
    try { applyEdgeDock(modal, 'right'); } catch (error) { console.warn('Savings dock failed:', error); }
  }
}

export function closeSavings() {
  if (!_open && !document.getElementById('savings-modal')) return;
  if (Modals.isRegistered('savings-modal')) {
    Modals.close('savings-modal');
    return;
  }
  teardown();
}

export function toggleSavings() {
  if (Modals.toggle('savings-modal')) return;
  if (_open) closeSavings();
  else openSavings();
}

const savingsModule = { openSavings, closeSavings, toggleSavings };
export default savingsModule;
