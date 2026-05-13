/**
 * app.js — Main UI logic
 * v2.0: Supabase auth + null-safe rendering + bug fixes
 */

// ── State ──────────────────────────────────────────────────────────────────
let _activeTab     = 'dashboard';
let _couponFilter  = 'all';
let _isLoading     = false;

// ── Boot ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  // Bind navigation
  document.querySelectorAll('.nav-tab').forEach(tab =>
    tab.addEventListener('click', () => switchTab(tab.dataset.tab))
  );
  el('btn-reload')?.addEventListener('click', loadData);

  // Filter buttons
  document.querySelectorAll('.filter-btn').forEach(btn =>
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _couponFilter = btn.dataset.filter;
      renderCoupons();
    })
  );

  // Modal close on backdrop
  el('modal-overlay')?.addEventListener('click', e => {
    if (e.target === e.currentTarget) closeModal();
  });

  // Settings save
  el('btn-save-config')?.addEventListener('click', saveConfig);
  el('btn-test-connection')?.addEventListener('click', testConnection);

  // Init Supabase Auth — pokazuje login overlay lub app
  await Auth.init();

  // Callback dla NOWYCH logowań (nie dla odtworzenia sesji przy page load)
  Auth.onLogin(async () => {
    await loadData();
    _populateSettingsForm();
  });

  // Jeśli sesja już istnieje — Auth.init() już ją odtworzył, wystarczy wczytać dane
  // WAŻNE: nie rejestrujemy onLogin przed tym blokiem, bo init() nie odpala callbacków
  // dla istniejącej sesji — tylko onAuthStateChange odpala SIGNED_IN przy page refresh,
  // co wywołałoby podwójne loadData(). Dlatego rozdzielamy: init→isLoggedIn vs onLogin.
  if (Auth.isLoggedIn()) {
    await loadData();
    _populateSettingsForm();
  }
});

// ── Pomocnik getElementById ────────────────────────────────────────────────
function el(id) {
  return document.getElementById(id);
}

// ── Tab management ─────────────────────────────────────────────────────────
function switchTab(tab) {
  _activeTab = tab;
  document.querySelectorAll('.nav-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.tab === tab)
  );
  document.querySelectorAll('.tab-content').forEach(t =>
    t.classList.toggle('active', t.id === `tab-${tab}`)
  );
}

// ── Data loading ───────────────────────────────────────────────────────────
async function loadData() {
  if (_isLoading) return;
  if (!Auth.isLoggedIn()) return;

  _isLoading = true;
  setLoading(true);
  _clearError();

  try {
    await Data.loadAll();
    renderAll();
    showToast('Dane załadowane.', 'success');
  } catch (err) {
    console.error('loadData error:', err);
    showToast(`Błąd: ${err.message}`, 'error');
    _showError(err.message);
  } finally {
    _isLoading = false;
    setLoading(false);
  }
}

function renderAll() {
  _clearError();
  renderDashboard();
  renderCoupons();
  renderStats();
}

// ── Dashboard ──────────────────────────────────────────────────────────────
function renderDashboard() {
  const s = Data.getStats();

  // Null-safe setters
  function setText(id, val) {
    const e = el(id); if (e) e.textContent = val;
  }
  function setClass(id, cls) {
    const e = el(id); if (e) e.className = cls;
  }

  setText('stat-overall', formatPLN(s.overall, true));
  setClass('stat-overall', 'stat-value ' + (s.overall >= 0 ? 'positive' : 'negative'));

  setText('stat-roi', formatPct(s.roi, true));
  setClass('stat-roi', 'stat-value ' + (s.roi >= 0 ? 'positive' : 'negative'));

  setText('stat-staked', formatPLN(s.totalStaked));
  setText('stat-payout', formatPLN(s.totalPayout));

  setText('count-new',     s.newCoupons);
  setText('count-playing', s.playing);
  setText('count-pending', s.pending);
  setText('count-won',     s.won);
  setText('count-lost',    s.lost);
  setText('count-total',   s.total);

  // Pending range
  const rangeEl = el('pending-range');
  if (rangeEl) {
    if (s.pendingStake > 0) {
      rangeEl.style.display = 'flex';
      setText('range-worst',      formatPLN(s.worstCase, true));
      setText('range-best',       formatPLN(s.bestCase, true));
      setText('pending-at-stake', formatPLN(s.pendingStake));
    } else {
      rangeEl.style.display = 'none';
    }
  }

  // Recent 5 coupons
  const container = el('recent-coupons');
  if (container) {
    const recent = [...(Data.getCoupons() || [])].reverse().slice(0, 5);
    container.innerHTML = recent.length
      ? recent.map(c => renderCouponCard(c, true)).join('')
      : '<div class="empty-state"><div class="empty-icon">📭</div><p>Brak kuponów.</p></div>';
  }
}

// ── Coupons tab ────────────────────────────────────────────────────────────
function renderCoupons() {
  const all = Data.getCoupons() || [];
  const filtered = _couponFilter === 'all'
    ? all
    : all.filter(c => c.uiStatus === _couponFilter ||
        (_couponFilter === 'pending' && c.result === 'PENDING'));

  // Update badge counts
  const counts = { all: all.length };
  for (const c of all) counts[c.uiStatus] = (counts[c.uiStatus] || 0) + 1;
  document.querySelectorAll('.filter-btn').forEach(btn => {
    const badge = btn.querySelector('.badge');
    if (badge) badge.textContent = counts[btn.dataset.filter] || 0;
  });

  const container = el('coupons-list');
  if (!container) return;

  if (filtered.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">🎯</div><p>Brak kuponów w tej kategorii.</p></div>`;
    return;
  }
  container.innerHTML = [...filtered].reverse().map(c => renderCouponCard(c, false)).join('');
}

function renderCouponCard(coupon, compact) {
  const statusMap = {
    new:     { label: 'NOWY',      cls: 'status-new',     icon: '🆕' },
    playing: { label: 'W GRZE',    cls: 'status-playing', icon: '⚡' },
    won:     { label: 'WYGRANA',   cls: 'status-won',     icon: '✅' },
    lost:    { label: 'PRZEGRANA', cls: 'status-lost',    icon: '❌' },
    pending: { label: 'OCZEKUJE',  cls: 'status-pending', icon: '⏳' },
  };
  const st       = statusMap[coupon.uiStatus] || statusMap.pending;
  const typeIcon = { SINGIEL: '🎯', PODWÓJNY: '⚡', POTRÓJNY: '🔥' };

  const legs = (coupon.legs || []).map(leg => `
    <div class="leg-row">
      <span class="leg-teams">${escHtml(leg.home_team || '?')} vs ${escHtml(leg.away_team || '?')}</span>
      <span class="leg-outcome" data-outcome="${escHtml(leg.bet_outcome || '')}">${outcomeLabel(leg.bet_outcome)}</span>
      <span class="leg-odds">${Number(leg.bet_odds || 0).toFixed(2)}</span>
    </div>`).join('');

  const playerInfo = coupon.playerStaked > 0
    ? `<div class="player-row">
        <span>Twoja stawka: <strong>${formatPLN(coupon.playerStaked)}</strong></span>
        ${coupon.playerPayout > 0 ? `<span class="payout-ok">Wypłata: <strong>${formatPLN(coupon.playerPayout)}</strong></span>` : ''}
       </div>`
    : '';

  return `
  <div class="coupon-card ${st.cls}" data-idx="${coupon.globalIndex}">
    <div class="coupon-header">
      <div class="coupon-title">
        <span class="type-icon">${typeIcon[coupon.type] || '📋'}</span>
        <span class="coupon-type">${escHtml(coupon.type)}</span>
        <span class="coupon-num">#${coupon.globalIndex}</span>
        <span class="status-badge ${st.cls}">${st.icon} ${st.label}</span>
      </div>
      <div class="coupon-meta">
        <span>${formatDate(coupon.date)}</span>
        <span>Kurs: <strong>${Number(coupon.total_odds).toFixed(2)}</strong></span>
        <span>Szansa: ${Math.round((Number(coupon.combined_prob) || 0) * 100)}%</span>
      </div>
    </div>
    ${!compact ? `<div class="coupon-legs">${legs}</div>` : ''}
    <div class="coupon-footer">
      <div class="kelly-info">Kelly: <strong>${formatPLN(coupon.kellyStake)}</strong></div>
      ${playerInfo}
      <div class="coupon-actions">${renderActionButtons(coupon)}</div>
    </div>
  </div>`;
}

function renderActionButtons(coupon) {
  if (coupon.result === 'WON' || coupon.result === 'LOST') {
    const editBtn = `<button class="btn btn-sm btn-ghost" onclick="openReviewModal(${coupon.globalIndex})">Podgląd</button>`;
    if (coupon.result === 'WON' && coupon.playerStaked > 0 && !coupon.hasPayout) {
      return `<button class="btn btn-sm btn-success" onclick="openPayoutModal(${coupon.globalIndex})">Wpisz wypłatę</button>${editBtn}`;
    }
    return editBtn;
  }
  if (coupon.playerStaked > 0) {
    return `
      <button class="btn btn-sm btn-warning" onclick="openEditStakeModal(${coupon.globalIndex})">Edytuj ✏️</button>
      <button class="btn btn-sm btn-success" onclick="openPayoutModal(${coupon.globalIndex})">Wygrana 🏆</button>
      <button class="btn btn-sm btn-danger-ghost" onclick="markLost(${coupon.globalIndex})">Przegrana ❌</button>`;
  }
  return `
    <button class="btn btn-sm btn-primary" onclick="openStakeModal(${coupon.globalIndex})">Postaw stawkę 💰</button>
    <button class="btn btn-sm btn-ghost" onclick="skipCoupon(${coupon.globalIndex})">Pomiń</button>`;
}

// ── Stats tab ──────────────────────────────────────────────────────────────
function renderStats() {
  const s = Data.getStats();

  function setText(id, val) { const e = el(id); if (e) e.textContent = val; }
  function setClass(id, cls) { const e = el(id); if (e) e.className = cls; }

  setText('model-roi', formatPct(s.modelRoi, true));
  setClass('model-roi', 'stat-value large ' + (s.modelRoi >= 0 ? 'positive' : 'negative'));
  setText('model-staked', formatPLN(s.modelStaked));
  setText('model-return', formatPLN(s.modelReturn));

  renderWinrateChart(s);
  renderMonthlyChart(s.roiByMonth || []);
}

function renderWinrateChart(s) {
  const canvas = el('chart-winrate');
  if (!canvas) return;
  if (window._winrateChart) window._winrateChart.destroy();
  window._winrateChart = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: ['Wygrane', 'Przegrane', 'Oczekujące'],
      datasets: [{
        data: [s.won, s.lost, s.pending],
        backgroundColor: ['#22c55e', '#ef4444', '#f59e0b'],
        borderColor: '#1a2236', borderWidth: 3,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#e2e8f0', font: { family: 'Barlow', size: 13 } } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw}` } },
      },
      cutout: '65%',
    },
  });
}

function renderMonthlyChart(data) {
  const canvas = el('chart-monthly');
  if (!canvas || !data.length) return;
  if (window._monthlyChart) window._monthlyChart.destroy();
  window._monthlyChart = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: data.map(d => d.month),
      datasets: [{
        label: 'Wynik (PLN)',
        data: data.map(d => d.net),
        backgroundColor: data.map(d => d.net >= 0 ? '#22c55e99' : '#ef444499'),
        borderColor:     data.map(d => d.net >= 0 ? '#22c55e'   : '#ef4444'),
        borderWidth: 2, borderRadius: 6,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#94a3b8', callback: v => v + ' PLN' }, grid: { color: '#1e293b' } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

// ── Modals ─────────────────────────────────────────────────────────────────
function openModal(html) {
  const body    = el('modal-body');
  const overlay = el('modal-overlay');
  if (!body || !overlay) { console.error('Modal DOM elements missing'); return; }
  body.innerHTML = html;
  overlay.classList.add('active');
}
function closeModal() {
  el('modal-overlay')?.classList.remove('active');
}

function openStakeModal(idx) {
  const coupon = (Data.getCoupons() || []).find(c => c.globalIndex === idx);
  if (!coupon) return;
  openModal(`
    <div class="modal-icon">💰</div>
    <h2>Stawka na kupon #${idx}</h2>
    <p class="modal-subtitle">${escHtml(coupon.type)} • Kurs: <strong>${Number(coupon.total_odds).toFixed(2)}</strong> • Kelly: <strong>${formatPLN(coupon.kellyStake)}</strong></p>
    <div class="legs-preview">
      ${(coupon.legs || []).map(l => `<div class="leg-mini">${escHtml(l.home_team || '')} vs ${escHtml(l.away_team || '')} — <strong>${outcomeLabel(l.bet_outcome)}</strong></div>`).join('')}
    </div>
    <div class="form-group">
      <label>Twoja stawka (PLN)</label>
      <input type="number" id="inp-stake" value="${coupon.kellyStake}" min="0" step="5" class="form-input">
    </div>
    <div class="form-group">
      <label>Kurs u bukmachera (opcjonalnie)</label>
      <input type="number" id="inp-real-odds" placeholder="${Number(coupon.total_odds).toFixed(2)}" step="0.01" min="1" class="form-input">
    </div>
    <div class="potential-preview">Potencjalna wygrana: <span id="potential-val">—</span></div>
    <div class="modal-actions">
      <button class="btn btn-primary btn-lg" onclick="confirmStake(${idx})">Potwierdź stawkę</button>
      <button class="btn btn-ghost" onclick="closeModal()">Anuluj</button>
    </div>
  `);
  const calcWin = () => {
    const stake = parseFloat(el('inp-stake')?.value) || 0;
    const odds  = parseFloat(el('inp-real-odds')?.value) || coupon.total_odds;
    const pv    = el('potential-val');
    if (pv) pv.textContent = stake > 0 ? formatPLN(stake * odds) : '—';
  };
  el('inp-stake')?.addEventListener('input', calcWin);
  el('inp-real-odds')?.addEventListener('input', calcWin);
  calcWin();
}

async function confirmStake(idx) {
  const amount   = parseFloat(el('inp-stake')?.value);
  const realOdds = parseFloat(el('inp-real-odds')?.value) || null;
  if (isNaN(amount) || amount < 0) { showToast('Podaj prawidłową kwotę.', 'error'); return; }
  closeModal();
  setLoading(true);
  try {
    await Data.addStake(idx, amount, realOdds);
    renderAll();
    showToast(amount === 0 ? `Kupon #${idx} pominięty.` : `Stawka ${formatPLN(amount)} zapisana!`, 'success');
  } catch (e) { showToast(`Błąd: ${e.message}`, 'error'); }
  finally { setLoading(false); }
}

function openEditStakeModal(idx) {
  openModal(`
    <div class="modal-icon warning">⚠️</div>
    <h2>Edycja stawki #${idx}</h2>
    <p class="modal-warning">Kupon jest już w grze. Zmiana stawki wpłynie na Player ROI.</p>
    <div class="modal-actions">
      <button class="btn btn-warning btn-lg" onclick="closeModal(); openStakeModal(${idx})">Tak, edytuj</button>
      <button class="btn btn-ghost" onclick="closeModal()">Anuluj</button>
    </div>
  `);
}

function openPayoutModal(idx) {
  const coupon   = (Data.getCoupons() || []).find(c => c.globalIndex === idx);
  if (!coupon) return;
  const realOdds = Data.getRealOddsForCoupon(idx) || coupon.total_odds;
  const suggested = coupon.playerStaked > 0 ? (coupon.playerStaked * realOdds).toFixed(0) : '';
  openModal(`
    <div class="modal-icon">🏆</div>
    <h2>Wygrana z kuponu #${idx}</h2>
    <p class="modal-subtitle">Stawka: <strong>${formatPLN(coupon.playerStaked)}</strong> • Kurs: <strong>${Number(realOdds).toFixed(2)}</strong></p>
    <div class="form-group">
      <label>Kwota wypłaty od bukmachera (PLN)</label>
      <input type="number" id="inp-payout" value="${suggested}" min="0" step="1" class="form-input">
      <small class="hint">Wpisz całą kwotę jaką dostałeś (łącznie ze stawką).</small>
    </div>
    <div class="modal-actions">
      <button class="btn btn-success btn-lg" onclick="confirmPayout(${idx})">Zapisz wygraną 🏆</button>
      <button class="btn btn-ghost" onclick="closeModal()">Anuluj</button>
    </div>
  `);
}

async function confirmPayout(idx) {
  const amount = parseFloat(el('inp-payout')?.value);
  if (isNaN(amount) || amount <= 0) { showToast('Podaj kwotę wypłaty.', 'error'); return; }
  closeModal();
  setLoading(true);
  try {
    await Data.addPayout(idx, amount);
    renderAll();
    showToast(`Wygrana ${formatPLN(amount)} zapisana! 🎉`, 'success');
  } catch (e) { showToast(`Błąd: ${e.message}`, 'error'); }
  finally { setLoading(false); }
}

async function markLost(idx) {
  if (!confirm(`Zaznaczyć kupon #${idx} jako przegrany?`)) return;
  showToast(`Kupon #${idx} — stawka już zalogowana przez /stake.`, 'info');
}

async function skipCoupon(idx) {
  // "Pomiń" nie zapisuje niczego w Supabase — kupon pozostaje "nowy"
  // i dalej będzie wyświetlany przy następnym odświeżeniu.
  // Jeśli chcesz trwale ukryć kupon, użyj /stake 0 w Telegramie.
  showToast(`Kupon #${idx} pominięty (nie zalogowano stawki).`, 'info');
}

function openReviewModal(idx) {
  const coupon   = (Data.getCoupons() || []).find(c => c.globalIndex === idx);
  if (!coupon) return;
  const realOdds = Data.getRealOddsForCoupon(idx);
  const net      = coupon.playerPayout - coupon.playerStaked;
  openModal(`
    <div class="modal-icon">${coupon.result === 'WON' ? '🏆' : '❌'}</div>
    <h2>Kupon #${idx} — ${escHtml(coupon.type)}</h2>
    <p class="modal-subtitle">${formatDate(coupon.date)}</p>
    <div class="review-grid">
      <div class="review-row"><span>Status</span><span class="${coupon.result === 'WON' ? 'positive' : 'negative'}">${coupon.result}</span></div>
      <div class="review-row"><span>Kurs Kelly</span><span>${Number(coupon.total_odds).toFixed(2)}</span></div>
      ${realOdds ? `<div class="review-row"><span>Kurs u bukmachera</span><span>${Number(realOdds).toFixed(2)}</span></div>` : ''}
      <div class="review-row"><span>Stawka Kelly</span><span>${formatPLN(coupon.kellyStake)}</span></div>
      <div class="review-row"><span>Twoja stawka</span><span>${coupon.playerStaked > 0 ? formatPLN(coupon.playerStaked) : '—'}</span></div>
      <div class="review-row"><span>Twoja wypłata</span><span>${coupon.playerPayout > 0 ? formatPLN(coupon.playerPayout) : '—'}</span></div>
      ${coupon.playerStaked > 0 ? `<div class="review-row total"><span>Twój wynik</span><span class="${net >= 0 ? 'positive' : 'negative'}">${formatPLN(net, true)}</span></div>` : ''}
    </div>
    <div class="coupon-legs review-legs">
      ${(coupon.legs || []).map(l => `
        <div class="leg-row">
          <span class="leg-teams">${escHtml(l.home_team || '')} vs ${escHtml(l.away_team || '')}</span>
          <span class="leg-outcome" data-outcome="${escHtml(l.bet_outcome || '')}">${outcomeLabel(l.bet_outcome)}</span>
          <span class="leg-odds">${Number(l.bet_odds || 0).toFixed(2)}</span>
        </div>`).join('')}
    </div>
    <div class="modal-actions">
      ${coupon.playerStaked > 0 && coupon.result === 'WON' && !coupon.hasPayout
        ? `<button class="btn btn-success btn-lg" onclick="closeModal();openPayoutModal(${idx})">Wpisz wypłatę 💰</button>`
        : `<button class="btn btn-ghost" onclick="closeModal()">Zamknij</button>`}
    </div>
  `);
}

function openBalanceModal() {
  const s = Data.getStats();
  openModal(`
    <div class="modal-icon">💼</div>
    <h2>Punkt startowy</h2>
    <p class="modal-subtitle">Wpisz 0 jeśli zaczynasz od zera, lub ujemną wartość jeśli masz już stratę.</p>
    <div class="form-group">
      <label>Punkt startowy (PLN)</label>
      <input type="number" id="inp-initial" value="${s.initial || 0}" step="50" class="form-input">
    </div>
    <div class="modal-actions">
      <button class="btn btn-primary btn-lg" onclick="confirmInitialBalance()">Zapisz</button>
      <button class="btn btn-ghost" onclick="closeModal()">Anuluj</button>
    </div>
  `);
}

async function confirmInitialBalance() {
  const val = parseFloat(el('inp-initial')?.value);
  if (isNaN(val)) { showToast('Podaj prawidłową wartość.', 'error'); return; }
  closeModal();
  setLoading(true);
  try {
    await Data.setInitialBalance(val);
    renderAll();
    showToast(`Punkt startowy: ${formatPLN(val, true)}`, 'success');
  } catch (e) { showToast(`Błąd: ${e.message}`, 'error'); }
  finally { setLoading(false); }
}

// ── Settings ───────────────────────────────────────────────────────────────
function _populateSettingsForm() {
  const cfg = Data.getSettings();
  const _set = (id, val) => { const e = el(id); if (e) e.value = val || ''; };
  _set('cfg-owner',  cfg.github_owner);
  _set('cfg-repo',   cfg.github_repo);
  _set('cfg-branch', cfg.github_branch || 'main');
  _set('cfg-token',  cfg.github_token);
  _updateConfigStatus();
}

async function saveConfig() {
  const owner  = el('cfg-owner')?.value.trim();
  const repo   = el('cfg-repo')?.value.trim();
  const branch = el('cfg-branch')?.value.trim() || 'main';
  const token  = el('cfg-token')?.value.trim();
  if (!owner || !repo || !token) { showToast('Uzupełnij wszystkie wymagane pola.', 'error'); return; }
  setLoading(true);
  try {
    await Data.saveGitHubConfig(owner, repo, branch, token);
    _updateConfigStatus();
    showToast('Konfiguracja zapisana w Supabase!', 'success');
    await loadData();
  } catch (e) { showToast(`Błąd zapisu: ${e.message}`, 'error'); }
  finally { setLoading(false); }
}

async function testConnection() {
  if (!GitHub.isConfigured()) { showToast('Zapisz konfigurację najpierw.', 'error'); return; }
  const btn = el('btn-test-connection');
  if (btn) { btn.textContent = 'Testowanie...'; btn.disabled = true; }
  try {
    const info = await GitHub.testConnection();
    showToast(`✅ Połączono: ${info.name} (${info.private ? 'prywatne' : 'publiczne'})`, 'success');
  } catch (e) { showToast(`❌ ${e.message}`, 'error'); }
  finally { if (btn) { btn.textContent = 'Testuj połączenie'; btn.disabled = false; } }
}

function _updateConfigStatus() {
  const statusEl = el('config-status');
  if (!statusEl) return;
  if (GitHub.isConfigured()) {
    const cfg = GitHub.getConfig();
    statusEl.innerHTML = `<span class="status-ok">✅ Połączono: ${escHtml(cfg.owner)}/${escHtml(cfg.repo)} (${escHtml(cfg.branch)})</span>`;
  } else {
    statusEl.innerHTML = `<span class="status-err">⚠️ Nie skonfigurowano</span>`;
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function setLoading(on) {
  const bar = el('loading-bar');
  const btn = el('btn-reload');
  if (bar) bar.style.display = on ? 'block' : 'none';
  if (btn) btn.disabled = on;
}

function _clearError() {
  const e = el('dashboard-error');
  if (e) { e.textContent = ''; e.style.display = 'none'; }
}

function _showError(msg) {
  const e = el('dashboard-error');
  if (e) { e.textContent = `Błąd: ${msg}`; e.style.display = 'block'; }
}

function formatPLN(val, sign = false) {
  const v = parseFloat(val) || 0;
  const s = Math.abs(v).toLocaleString('pl-PL', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  if (sign) return (v >= 0 ? '+' : '−') + s + ' PLN';
  return s + ' PLN';
}

function formatPct(val, sign = false) {
  const v   = parseFloat(val) || 0;
  const str = Math.abs(v).toFixed(1);
  if (sign) return (v >= 0 ? '+' : '−') + str + '%';
  return str + '%';
}

function formatDate(str) { return str ? String(str).substring(0, 10) : '—'; }

function escHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function outcomeLabel(outcome) {
  const map = { H: '1 (Dom)', D: 'X (Remis)', A: '2 (Gość)', '1X': '1X', X2: 'X2', '12': '12' };
  return map[outcome] || (outcome || '?');
}

function showToast(msg, type = 'info') {
  const container = el('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 4000);
}
