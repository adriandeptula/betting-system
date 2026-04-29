/**
 * app.js – Main application: UI rendering, tab management, modals.
 */

// ── State ──────────────────────────────────────────────────────────────────
let _activeTab = 'dashboard';
let _couponFilter = 'all';
let _roiChart = null;
let _isLoading = false;

// ── Boot ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadConfig();

  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });

  document.getElementById('btn-reload').addEventListener('click', loadData);
  document.getElementById('btn-save-config').addEventListener('click', saveConfig);
  document.getElementById('btn-test-connection').addEventListener('click', testConnection);

  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _couponFilter = btn.dataset.filter;
      renderCoupons();
    });
  });

  document.getElementById('modal-overlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeModal();
  });

  if (GitHub.isConfigured()) {
    loadData();
  } else {
    switchTab('settings');
    showToast('Skonfiguruj połączenie z GitHub aby zacząć.', 'info');
  }
});

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
  if (!GitHub.isConfigured()) {
    showToast('Skonfiguruj GitHub w ustawieniach.', 'error');
    switchTab('settings');
    return;
  }

  _isLoading = true;
  setLoading(true);

  try {
    await Data.loadAll();
    renderAll();
    showToast('Dane załadowane pomyślnie.', 'success');
  } catch (err) {
    console.error(err);
    showToast(`Błąd ładowania danych: ${err.message}`, 'error');
    document.getElementById('dashboard-error').textContent = `Błąd: ${err.message}`;
    document.getElementById('dashboard-error').style.display = 'block';
  } finally {
    _isLoading = false;
    setLoading(false);
  }
}

function renderAll() {
  document.getElementById('dashboard-error').style.display = 'none';
  renderDashboard();
  renderCoupons();
  renderStats();
}

// ── Dashboard ──────────────────────────────────────────────────────────────
function renderDashboard() {
  const s = Data.getStats();
  const coupons = Data.getCoupons();

  // Summary cards
  document.getElementById('stat-overall').textContent = formatPLN(s.overall, true);
  document.getElementById('stat-overall').className = 'stat-value ' + (s.overall >= 0 ? 'positive' : 'negative');
  document.getElementById('stat-roi').textContent = formatPct(s.roi, true);
  document.getElementById('stat-roi').className = 'stat-value ' + (s.roi >= 0 ? 'positive' : 'negative');
  document.getElementById('stat-staked').textContent = formatPLN(s.totalStaked);
  document.getElementById('stat-payout').textContent = formatPLN(s.totalPayout);

  // Coupon counts
  document.getElementById('count-new').textContent = s.newCoupons;
  document.getElementById('count-playing').textContent = s.playing;
  document.getElementById('count-pending').textContent = s.pending;
  document.getElementById('count-won').textContent = s.won;
  document.getElementById('count-lost').textContent = s.lost;
  document.getElementById('count-total').textContent = s.total;

  // Range
  if (s.pendingStake > 0) {
    document.getElementById('pending-range').style.display = 'flex';
    document.getElementById('range-worst').textContent = formatPLN(s.worstCase, true);
    document.getElementById('range-best').textContent = formatPLN(s.bestCase, true);
    document.getElementById('pending-at-stake').textContent = formatPLN(s.pendingStake);
  } else {
    document.getElementById('pending-range').style.display = 'none';
  }

  // Recent coupons (last 5)
  const recent = [...coupons].reverse().slice(0, 5);
  const container = document.getElementById('recent-coupons');
  container.innerHTML = recent.map(c => renderCouponCard(c, true)).join('');
  attachCouponEvents(container);
}

// ── Coupons tab ────────────────────────────────────────────────────────────
function renderCoupons() {
  const all = Data.getCoupons();
  const filtered = _couponFilter === 'all'
    ? all
    : all.filter(c => c.uiStatus === _couponFilter ||
        ((_couponFilter === 'pending') && c.result === 'PENDING'));

  // Update filter badge counts
  const counts = { all: all.length };
  for (const c of all) {
    counts[c.uiStatus] = (counts[c.uiStatus] || 0) + 1;
  }
  document.querySelectorAll('.filter-btn').forEach(btn => {
    const key = btn.dataset.filter;
    const badge = btn.querySelector('.badge');
    if (badge) badge.textContent = counts[key] || 0;
  });

  const container = document.getElementById('coupons-list');

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🎯</div>
        <p>Brak kuponów w tej kategorii.</p>
      </div>`;
    return;
  }

  container.innerHTML = [...filtered].reverse().map(c => renderCouponCard(c, false)).join('');
  attachCouponEvents(container);
}

function renderCouponCard(coupon, compact) {
  const statusMap = {
    new:     { label: 'NOWY',       cls: 'status-new',     icon: '🆕' },
    playing: { label: 'W GRZE',     cls: 'status-playing', icon: '⚡' },
    won:     { label: 'WYGRANA',    cls: 'status-won',     icon: '✅' },
    lost:    { label: 'PRZEGRANA',  cls: 'status-lost',    icon: '❌' },
    pending: { label: 'OCZEKUJE',   cls: 'status-pending', icon: '⏳' },
  };
  const st = statusMap[coupon.uiStatus] || statusMap.pending;
  const typeIcon = { SINGIEL: '🎯', PODWÓJNY: '⚡', POTRÓJNY: '🔥' };

  const legs = coupon.legs.map(leg => `
    <div class="leg-row">
      <span class="leg-teams">${escHtml(leg.home_team)} vs ${escHtml(leg.away_team)}</span>
      <span class="leg-outcome ${leg.bet_outcome}">${outcomeLabel(leg.bet_outcome)}</span>
      <span class="leg-odds">${leg.bet_odds.toFixed(2)}</span>
    </div>`).join('');

  const playerInfo = coupon.playerStaked > 0
    ? `<div class="player-row">
        <span>Twoja stawka: <strong>${formatPLN(coupon.playerStaked)}</strong></span>
        ${coupon.playerPayout > 0
          ? `<span class="payout-ok">Wypłata: <strong>${formatPLN(coupon.playerPayout)}</strong></span>`
          : ''}
       </div>`
    : '';

  const actionBtns = renderActionButtons(coupon);

  return `
  <div class="coupon-card ${st.cls}" data-idx="${coupon.globalIndex}">
    <div class="coupon-header">
      <div class="coupon-title">
        <span class="type-icon">${typeIcon[coupon.type] || '📋'}</span>
        <span class="coupon-type">${coupon.type}</span>
        <span class="coupon-num">#${coupon.globalIndex}</span>
        <span class="status-badge ${st.cls}">${st.icon} ${st.label}</span>
      </div>
      <div class="coupon-meta">
        <span class="coupon-date">${formatDate(coupon.date)}</span>
        <span class="coupon-odds">Kurs: <strong>${coupon.total_odds.toFixed(2)}</strong></span>
        <span class="coupon-prob">Szansa: ${Math.round(coupon.combined_prob * 100)}%</span>
      </div>
    </div>

    ${!compact ? `<div class="coupon-legs">${legs}</div>` : ''}

    <div class="coupon-footer">
      <div class="kelly-info">Kelly: <strong>${formatPLN(coupon.kellyStake)}</strong></div>
      ${playerInfo}
      <div class="coupon-actions">${actionBtns}</div>
    </div>
  </div>`;
}

function renderActionButtons(coupon) {
  if (coupon.result === 'WON' || coupon.result === 'LOST') {
    // Resolved — allow editing payout/review
    const editBtn = `<button class="btn btn-sm btn-ghost" onclick="openReviewModal(${coupon.globalIndex})">Podgląd</button>`;
    if (coupon.result === 'WON' && coupon.playerStaked > 0 && !coupon.hasPayout) {
      return `<button class="btn btn-sm btn-success" onclick="openPayoutModal(${coupon.globalIndex})">Wpisz wypłatę</button>${editBtn}`;
    }
    return editBtn;
  }

  if (coupon.playerStaked > 0) {
    // Already staked — allow edit with warning
    return `
      <button class="btn btn-sm btn-warning" onclick="openEditStakeModal(${coupon.globalIndex})">Edytuj stawkę ✏️</button>
      <button class="btn btn-sm btn-success" onclick="openPayoutModal(${coupon.globalIndex})">Wygrana 🏆</button>
      <button class="btn btn-sm btn-danger-ghost" onclick="markLost(${coupon.globalIndex})">Przegrana ❌</button>`;
  }

  // Not staked yet
  return `<button class="btn btn-sm btn-primary" onclick="openStakeModal(${coupon.globalIndex})">Postaw stawkę 💰</button>
          <button class="btn btn-sm btn-ghost" onclick="skipCoupon(${coupon.globalIndex})">Pomiń</button>`;
}

function attachCouponEvents(container) {
  // Events are bound via inline onclick for simplicity
}

// ── Statistics tab ─────────────────────────────────────────────────────────
function renderStats() {
  const s = Data.getStats();

  document.getElementById('model-roi').textContent = formatPct(s.modelRoi, true);
  document.getElementById('model-roi').className = 'stat-value large ' + (s.modelRoi >= 0 ? 'positive' : 'negative');
  document.getElementById('model-staked').textContent = formatPLN(s.modelStaked);
  document.getElementById('model-return').textContent = formatPLN(s.modelReturn);

  // Winrate chart
  renderWinrateChart(s);

  // Monthly ROI chart
  renderMonthlyChart(s.roiByMonth);
}

function renderWinrateChart(s) {
  const canvas = document.getElementById('chart-winrate');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  if (window._winrateChart) window._winrateChart.destroy();

  window._winrateChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Wygrane', 'Przegrane', 'Oczekujące'],
      datasets: [{
        data: [s.won, s.lost, s.pending],
        backgroundColor: ['#22c55e', '#ef4444', '#f59e0b'],
        borderColor: '#1a2236',
        borderWidth: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#e2e8f0', font: { family: 'Barlow', size: 13 } } },
        tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw} kuponów` } },
      },
      cutout: '65%',
    },
  });
}

function renderMonthlyChart(data) {
  const canvas = document.getElementById('chart-monthly');
  if (!canvas || data.length === 0) return;
  const ctx = canvas.getContext('2d');

  if (window._monthlyChart) window._monthlyChart.destroy();

  window._monthlyChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => d.month),
      datasets: [{
        label: 'Wynik miesięczny (PLN)',
        data: data.map(d => d.net),
        backgroundColor: data.map(d => d.net >= 0 ? '#22c55e99' : '#ef444499'),
        borderColor: data.map(d => d.net >= 0 ? '#22c55e' : '#ef4444'),
        borderWidth: 2,
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#94a3b8', callback: v => v + ' PLN' }, grid: { color: '#1e293b' } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: ctx => ` ${ctx.raw >= 0 ? '+' : ''}${ctx.raw.toFixed(0)} PLN`,
        }},
      },
    },
  });
}

// ── Modals ─────────────────────────────────────────────────────────────────
function openModal(html) {
  document.getElementById('modal-body').innerHTML = html;
  document.getElementById('modal-overlay').classList.add('active');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('active');
}

function openStakeModal(idx) {
  const coupons = Data.getCoupons();
  const coupon = coupons.find(c => c.globalIndex === idx);
  if (!coupon) return;

  openModal(`
    <div class="modal-icon">💰</div>
    <h2>Stawka na kupon #${idx}</h2>
    <p class="modal-subtitle">${coupon.type} • Kurs: <strong>${coupon.total_odds.toFixed(2)}</strong> • Kelly: <strong>${formatPLN(coupon.kellyStake)}</strong></p>
    <div class="legs-preview">
      ${coupon.legs.map(l => `<div class="leg-mini">${escHtml(l.home_team)} vs ${escHtml(l.away_team)} — <strong>${outcomeLabel(l.bet_outcome)}</strong></div>`).join('')}
    </div>
    <div class="form-group">
      <label>Twoja stawka (PLN)</label>
      <input type="number" id="inp-stake" value="${coupon.kellyStake}" min="0" step="5" class="form-input">
    </div>
    <div class="form-group">
      <label>Kurs u bukmachera (opcjonalnie)</label>
      <input type="number" id="inp-real-odds" placeholder="${coupon.total_odds.toFixed(2)}" step="0.01" min="1" class="form-input">
    </div>
    <div id="potential-win-preview" class="potential-preview">
      Potencjalna wygrana: <span id="potential-val">—</span>
    </div>
    <div class="modal-actions">
      <button class="btn btn-primary btn-lg" onclick="confirmStake(${idx})">Potwierdź stawkę</button>
      <button class="btn btn-ghost" onclick="closeModal()">Anuluj</button>
    </div>
  `);

  // Live calculation
  const stakeInput = document.getElementById('inp-stake');
  const oddsInput = document.getElementById('inp-real-odds');
  const preview = document.getElementById('potential-val');
  const calcWin = () => {
    const stake = parseFloat(stakeInput.value) || 0;
    const odds = parseFloat(oddsInput.value) || coupon.total_odds;
    preview.textContent = stake > 0 ? formatPLN(stake * odds) : '—';
  };
  stakeInput.addEventListener('input', calcWin);
  oddsInput.addEventListener('input', calcWin);
  calcWin();
}

async function confirmStake(idx) {
  const amount = parseFloat(document.getElementById('inp-stake').value);
  const realOdds = parseFloat(document.getElementById('inp-real-odds').value) || null;

  if (isNaN(amount) || amount < 0) {
    showToast('Podaj prawidłową kwotę.', 'error');
    return;
  }

  closeModal();
  setLoading(true);
  try {
    await Data.addStake(idx, amount, realOdds);
    renderAll();
    showToast(amount === 0 ? `Kupon #${idx} pominięty.` : `Stawka ${formatPLN(amount)} na kupon #${idx} zapisana!`, 'success');
  } catch (e) {
    showToast(`Błąd: ${e.message}`, 'error');
  } finally {
    setLoading(false);
  }
}

function openEditStakeModal(idx) {
  openModal(`
    <div class="modal-icon warning">⚠️</div>
    <h2>Edycja stawki #${idx}</h2>
    <p class="modal-warning">Kupon jest już w grze. Zmiana stawki wpłynie na obliczenia Player ROI.<br>Czy na pewno chcesz kontynuować?</p>
    <div class="modal-actions">
      <button class="btn btn-warning btn-lg" onclick="proceedEditStake(${idx})">Tak, edytuj stawkę</button>
      <button class="btn btn-ghost" onclick="closeModal()">Anuluj</button>
    </div>
  `);
}

function proceedEditStake(idx) {
  closeModal();
  openStakeModal(idx);
}

function openPayoutModal(idx) {
  const coupons = Data.getCoupons();
  const coupon = coupons.find(c => c.globalIndex === idx);
  if (!coupon) return;

  const realOdds = Data.getRealOddsForCoupon(idx) || coupon.total_odds;
  const suggested = coupon.playerStaked > 0 ? (coupon.playerStaked * realOdds).toFixed(0) : '';

  openModal(`
    <div class="modal-icon">🏆</div>
    <h2>Wygrana z kuponu #${idx}</h2>
    <p class="modal-subtitle">Stawka gracza: <strong>${formatPLN(coupon.playerStaked)}</strong> • Kurs: <strong>${realOdds.toFixed(2)}</strong></p>
    <div class="form-group">
      <label>Kwota wypłaty od bukmachera (PLN)</label>
      <input type="number" id="inp-payout" value="${suggested}" min="0" step="1" class="form-input">
      <small class="hint">Wpisz całą kwotę jaką dostałeś, łącznie ze stawką.</small>
    </div>
    <div class="modal-actions">
      <button class="btn btn-success btn-lg" onclick="confirmPayout(${idx})">Zapisz wygraną 🏆</button>
      <button class="btn btn-ghost" onclick="closeModal()">Anuluj</button>
    </div>
  `);
}

async function confirmPayout(idx) {
  const amount = parseFloat(document.getElementById('inp-payout').value);
  if (isNaN(amount) || amount <= 0) {
    showToast('Podaj kwotę wypłaty.', 'error');
    return;
  }
  closeModal();
  setLoading(true);
  try {
    await Data.addPayout(idx, amount);
    renderAll();
    showToast(`Wygrana ${formatPLN(amount)} z kuponu #${idx} zapisana! 🎉`, 'success');
  } catch (e) {
    showToast(`Błąd: ${e.message}`, 'error');
  } finally {
    setLoading(false);
  }
}

async function markLost(idx) {
  if (!confirm(`Zaznaczyć kupon #${idx} jako przegrany?`)) return;
  // Just a UX note — the actual result is in coupons_history.json managed by GitHub Actions
  // Player just notes they lost via /lost in Telegram. Here we note no payout.
  showToast(`Kupon #${idx} oznaczony jako przegrany. Stawka już zalogowana.`, 'info');
}

async function skipCoupon(idx) {
  setLoading(true);
  try {
    await Data.addStake(idx, 0, null, `Pominięto kupon #${idx}`);
    renderAll();
    showToast(`Kupon #${idx} pominięty.`, 'info');
  } catch (e) {
    showToast(`Błąd: ${e.message}`, 'error');
  } finally {
    setLoading(false);
  }
}

function openReviewModal(idx) {
  const coupons = Data.getCoupons();
  const coupon = coupons.find(c => c.globalIndex === idx);
  if (!coupon) return;

  const realOdds = Data.getRealOddsForCoupon(idx);
  const playerNet = coupon.playerPayout - coupon.playerStaked;

  openModal(`
    <div class="modal-icon">${coupon.result === 'WON' ? '🏆' : '❌'}</div>
    <h2>Kupon #${idx} — ${coupon.type}</h2>
    <p class="modal-subtitle">${formatDate(coupon.date)}</p>
    <div class="review-grid">
      <div class="review-row"><span>Status modelu</span><span class="${coupon.result === 'WON' ? 'positive' : 'negative'}">${coupon.result}</span></div>
      <div class="review-row"><span>Kurs Kelly</span><span>${coupon.total_odds.toFixed(2)}</span></div>
      ${realOdds ? `<div class="review-row"><span>Kurs bukmachera</span><span>${realOdds.toFixed(2)}</span></div>` : ''}
      <div class="review-row"><span>Stawka Kelly</span><span>${formatPLN(coupon.kellyStake)}</span></div>
      <div class="review-row"><span>Twoja stawka</span><span>${coupon.playerStaked > 0 ? formatPLN(coupon.playerStaked) : '—'}</span></div>
      <div class="review-row"><span>Twoja wypłata</span><span>${coupon.playerPayout > 0 ? formatPLN(coupon.playerPayout) : '—'}</span></div>
      ${coupon.playerStaked > 0 ? `<div class="review-row total"><span>Twój wynik</span><span class="${playerNet >= 0 ? 'positive' : 'negative'}">${formatPLN(playerNet, true)}</span></div>` : ''}
    </div>
    <div class="coupon-legs review-legs">
      ${coupon.legs.map(l => `
        <div class="leg-row">
          <span class="leg-teams">${escHtml(l.home_team)} vs ${escHtml(l.away_team)}</span>
          <span class="leg-outcome ${l.bet_outcome}">${outcomeLabel(l.bet_outcome)}</span>
          <span class="leg-odds">${l.bet_odds.toFixed(2)}</span>
        </div>`).join('')}
    </div>
    ${coupon.playerStaked > 0 && coupon.result === 'WON' && !coupon.hasPayout ? `
      <div class="modal-actions">
        <button class="btn btn-success btn-lg" onclick="closeModal(); openPayoutModal(${idx})">Wpisz wypłatę 💰</button>
      </div>` : `
      <div class="modal-actions">
        <button class="btn btn-ghost" onclick="closeModal()">Zamknij</button>
      </div>`}
  `);
}

// ── Settings ───────────────────────────────────────────────────────────────
function loadConfig() {
  const cfg = GitHub.getConfig();
  if (cfg.owner) document.getElementById('cfg-owner').value = cfg.owner;
  if (cfg.repo)  document.getElementById('cfg-repo').value = cfg.repo;
  if (cfg.token) document.getElementById('cfg-token').value = cfg.token;
  if (cfg.branch) document.getElementById('cfg-branch').value = cfg.branch;

  updateConfigStatus();
}

function saveConfig() {
  const token  = document.getElementById('cfg-token').value.trim();
  const owner  = document.getElementById('cfg-owner').value.trim();
  const repo   = document.getElementById('cfg-repo').value.trim();
  const branch = document.getElementById('cfg-branch').value.trim() || 'main';
  const webappUrl = document.getElementById('cfg-webapp-url').value.trim();

  if (!token || !owner || !repo) {
    showToast('Uzupełnij wszystkie wymagane pola.', 'error');
    return;
  }

  GitHub.configure(token, owner, repo, branch);
  if (webappUrl) localStorage.setItem('betting_webapp_url', webappUrl);
  updateConfigStatus();
  showToast('Konfiguracja zapisana!', 'success');
  loadData();
}

async function testConnection() {
  if (!GitHub.isConfigured()) {
    showToast('Zapisz konfigurację najpierw.', 'error');
    return;
  }
  const btn = document.getElementById('btn-test-connection');
  btn.textContent = 'Testowanie...';
  btn.disabled = true;
  try {
    const info = await GitHub.testConnection();
    showToast(`✅ Połączono z: ${info.name} (${info.private ? 'prywatne' : 'publiczne'})`, 'success');
  } catch (e) {
    showToast(`❌ Błąd: ${e.message}`, 'error');
  } finally {
    btn.textContent = 'Testuj połączenie';
    btn.disabled = false;
  }
}

function updateConfigStatus() {
  const el = document.getElementById('config-status');
  if (GitHub.isConfigured()) {
    const cfg = GitHub.getConfig();
    el.innerHTML = `<span class="status-ok">✅ Połączono z: ${escHtml(cfg.owner)}/${escHtml(cfg.repo)} (${escHtml(cfg.branch || 'main')})</span>`;
  } else {
    el.innerHTML = `<span class="status-err">⚠️ Nie skonfigurowano</span>`;
  }
}

// ── Initial balance modal ─────────────────────────────────────────────────
function openBalanceModal() {
  const s = Data.getStats();
  openModal(`
    <div class="modal-icon">💼</div>
    <h2>Punkt startowy</h2>
    <p class="modal-subtitle">Ustaw swój wynik przed rozpoczęciem korzystania z systemu.<br>Wpisz 0 jeśli zaczynasz od zera, lub ujemną wartość jeśli masz już stratę.</p>
    <div class="form-group">
      <label>Punkt startowy (PLN)</label>
      <input type="number" id="inp-initial" value="${s.initial}" step="50" class="form-input">
    </div>
    <div class="modal-actions">
      <button class="btn btn-primary btn-lg" onclick="confirmInitialBalance()">Zapisz</button>
      <button class="btn btn-ghost" onclick="closeModal()">Anuluj</button>
    </div>
  `);
}

async function confirmInitialBalance() {
  const val = parseFloat(document.getElementById('inp-initial').value);
  if (isNaN(val)) { showToast('Podaj prawidłową wartość.', 'error'); return; }
  closeModal();
  setLoading(true);
  try {
    await Data.setInitialBalance(val);
    renderAll();
    showToast(`Punkt startowy ustawiony: ${formatPLN(val, true)}`, 'success');
  } catch (e) {
    showToast(`Błąd: ${e.message}`, 'error');
  } finally {
    setLoading(false);
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function setLoading(on) {
  document.getElementById('loading-bar').style.display = on ? 'block' : 'none';
  document.getElementById('btn-reload').disabled = on;
}

function formatPLN(val, sign = false) {
  const v = parseFloat(val) || 0;
  const str = Math.abs(v).toLocaleString('pl-PL', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  if (sign) return (v >= 0 ? '+' : '−') + str + ' PLN';
  return str + ' PLN';
}

function formatPct(val, sign = false) {
  const v = parseFloat(val) || 0;
  const str = Math.abs(v).toFixed(1);
  if (sign) return (v >= 0 ? '+' : '−') + str + '%';
  return str + '%';
}

function formatDate(str) {
  if (!str) return '—';
  return str.substring(0, 10);
}

function escHtml(str) {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function outcomeLabel(outcome) {
  const map = { H: '1 (Dom)', D: 'X (Remis)', A: '2 (Gość)', '1X': '1X', X2: 'X2', '12': '12' };
  return map[outcome] || outcome;
}

// ── Toast notifications ────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
