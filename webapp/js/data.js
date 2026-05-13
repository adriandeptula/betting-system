/**
 * data.js — Dane aplikacji
 *
 * Architektura v2.0 (Supabase):
 *   ODCZYT kuponów   → GitHub (coupons_history.json, read-only)
 *   ZAPIS/ODCZYT finansów → Supabase (finance_transactions + user_settings)
 *
 * Rozwiązuje problem 403 — webapp nigdy nie pisze do GitHub repo.
 */
const Data = (() => {
  // ── State ─────────────────────────────────────────────────────────────────
  let _history      = [];   // raw coupons_history.json
  let _transactions = [];   // Supabase finance_transactions
  let _settings     = {};   // Supabase user_settings
  let _coupons      = [];   // processed flat list

  // ── Wczytywanie danych ────────────────────────────────────────────────────

  async function loadAll() {
    const uid = Auth.getUser()?.id;
    if (!uid) throw new Error('Użytkownik niezalogowany.');

    // KROK 1: Wczytaj ustawienia PIERWSZE — trzeba skonfigurować GitHub
    // zanim _loadCouponHistory() sprawdzi GitHub.isConfigured().
    // Promise.all tutaj byłby race condition: history zawsze zwracałoby [].
    _settings = await _loadSettings(uid);

    if (_settings.github_owner) {
      GitHub.configure(
        _settings.github_owner,
        _settings.github_repo,
        _settings.github_branch,
        _settings.github_token,
      );
    }

    // KROK 2: Teraz równolegle transakcje + historia kuponów (GitHub już skonfigurowany)
    const [transactions, histResult] = await Promise.all([
      _loadTransactions(uid),
      _loadCouponHistory(),
    ]);

    _transactions = transactions;
    _history      = histResult;

    _buildCouponList();
    return { history: _history, transactions: _transactions, settings: _settings };
  }

  async function _loadSettings(uid) {
    const { data, error } = await _sb
      .from('user_settings')
      .select('*')
      .eq('user_id', uid)
      .maybeSingle();

    if (error) throw new Error(`Supabase settings: ${error.message}`);
    return data || {
      github_owner: '', github_repo: '', github_branch: 'main',
      github_token: '', initial_balance: 0,
    };
  }

  async function _loadTransactions(uid) {
    const { data, error } = await _sb
      .from('finance_transactions')
      .select('*')
      .eq('user_id', uid)
      .order('created_at', { ascending: true });

    if (error) throw new Error(`Supabase transactions: ${error.message}`);
    return data || [];
  }

  async function _loadCouponHistory() {
    if (!GitHub.isConfigured()) return [];
    try {
      const { content } = await GitHub.loadFile('data/results/coupons_history.json');
      return Array.isArray(content) ? content : [];
    } catch (e) {
      console.warn('Nie udało się wczytać kuponów z GitHub:', e.message);
      return [];
    }
  }

  // ── Budowanie listy kuponów ────────────────────────────────────────────────

  function _buildCouponList() {
    _coupons = [];
    let idx = 0;
    const stakesByIdx = _getStakesByIndex();

    for (const entry of (_history || [])) {
      for (const coupon of (entry?.coupons || [])) {
        idx++;
        const player = stakesByIdx[String(idx)] || { staked: 0, payout: 0, hasPayout: false };
        _coupons.push({
          globalIndex:  idx,
          date:         entry.date || '',
          type:         coupon.type  || 'SINGIEL',
          legs:         coupon.legs  || [],
          total_odds:   Number(coupon.total_odds)    || 1,
          combined_prob: Number(coupon.combined_prob) || 0,
          kellyStake:   Number(coupon.stake)          || 0,
          expected_value: Number(coupon.expected_value) || 0,
          result:       coupon.result || 'PENDING',
          resolved_at:  coupon.resolved_at || null,
          playerStaked: player.staked,
          playerPayout: player.payout,
          hasPayout:    player.hasPayout,
          uiStatus:     _getUiStatus(coupon.result, player),
        });
      }
    }
  }

  function _getUiStatus(result, player) {
    if (result === 'WON')  return 'won';
    if (result === 'LOST') return 'lost';
    if (player.staked > 0) return 'playing';
    return 'new';
  }

  function _getStakesByIndex() {
    const map = {};
    for (const tx of (_transactions || [])) {
      const cid = String(tx.coupon_id || '');
      if (!cid || cid === '?') continue;
      if (!map[cid]) map[cid] = { staked: 0, payout: 0, hasPayout: false };
      if (tx.type === 'stake')  map[cid].staked += Math.abs(tx.amount);
      if (tx.type === 'payout') {
        map[cid].payout    += Math.abs(tx.amount);
        map[cid].hasPayout  = true;
      }
    }
    return map;
  }

  // ── Accessors ─────────────────────────────────────────────────────────────

  function getCoupons()  { return _coupons; }
  function getSettings() { return { ..._settings }; }

  function getStats() {
    const initial    = Number(_settings?.initial_balance) || 0;
    const txs        = _transactions || [];

    let totalStaked = 0, totalPayout = 0;
    for (const tx of txs) {
      if (tx.type === 'stake')  totalStaked += Math.abs(tx.amount);
      if (tx.type === 'payout') totalPayout += Math.abs(tx.amount);
    }

    const net     = totalPayout - totalStaked;
    const roi     = totalStaked > 0 ? (net / totalStaked) * 100 : 0;
    const overall = initial + net;

    const won     = (_coupons || []).filter(c => c.result === 'WON').length;
    const lost    = (_coupons || []).filter(c => c.result === 'LOST').length;
    const pending = (_coupons || []).filter(c => c.result === 'PENDING').length;
    const newCoupons = (_coupons || []).filter(c => c.uiStatus === 'new').length;
    const playing    = (_coupons || []).filter(c => c.uiStatus === 'playing').length;

    // Model ROI
    let modelStaked = 0, modelReturn = 0;
    for (const c of (_coupons || [])) {
      if (c.result === 'WON') { modelStaked += c.kellyStake; modelReturn += c.kellyStake * c.total_odds; }
      if (c.result === 'LOST') modelStaked += c.kellyStake;
    }
    const modelRoi = modelStaked > 0 ? ((modelReturn - modelStaked) / modelStaked) * 100 : 0;

    // Oczekujące z stawką gracza
    const pendingStake = (_coupons || [])
      .filter(c => c.result === 'PENDING' && c.playerStaked > 0)
      .reduce((s, c) => s + c.playerStaked, 0);
    const pendingPotential = (_coupons || [])
      .filter(c => c.result === 'PENDING' && c.playerStaked > 0)
      .reduce((s, c) => s + c.playerStaked * c.total_odds, 0);

    return {
      initial, totalStaked, totalPayout, net, roi, overall,
      won, lost, pending, newCoupons, playing,
      total:          (_coupons || []).length,
      modelRoi, modelStaked, modelReturn,
      pendingStake, pendingPotential,
      roiByMonth:     _buildMonthlyRoi(),
      worstCase:      overall - pendingStake,
      bestCase:       overall + pendingPotential,
    };
  }

  function _buildMonthlyRoi() {
    const byMonth = {};
    for (const tx of (_transactions || [])) {
      const month = (tx.tx_date || '').substring(0, 7);
      if (!month) continue;
      if (!byMonth[month]) byMonth[month] = { staked: 0, payout: 0 };
      if (tx.type === 'stake')  byMonth[month].staked += Math.abs(tx.amount);
      if (tx.type === 'payout') byMonth[month].payout += Math.abs(tx.amount);
    }
    return Object.entries(byMonth)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([month, v]) => ({
        month,
        net: v.payout - v.staked,
        roi: v.staked > 0 ? ((v.payout - v.staked) / v.staked) * 100 : 0,
      }));
  }

  function getRealOddsForCoupon(globalIndex) {
    const tx = (_transactions || []).find(
      t => t.coupon_id === String(globalIndex) && t.type === 'stake'
    );
    return tx?.real_odds || null;
  }

  // ── Operacje zapisu (Supabase) ────────────────────────────────────────────

  async function addStake(globalIndex, amount, realOdds) {
    const uid = Auth.getUser()?.id;
    if (!uid) throw new Error('Niezalogowany');
    const now = _nowStr();
    const cid = String(globalIndex);

    // Usuń istniejącą stawkę dla tego kuponu
    const existing = (_transactions || []).filter(
      t => t.coupon_id === cid && t.type === 'stake'
    );
    if (existing.length > 0) {
      const ids = existing.map(t => t.id);
      const { error } = await _sb.from('finance_transactions').delete().in('id', ids);
      if (error) throw new Error(`Supabase delete: ${error.message}`);
      _transactions = _transactions.filter(t => !ids.includes(t.id));
    }

    if (amount > 0) {
      const row = {
        user_id: uid, tx_date: now, type: 'stake',
        amount: -Math.abs(amount), coupon_id: cid,
        real_odds: realOdds || null,
        note: `Stawka na kupon #${globalIndex}`,
      };
      const { data, error } = await _sb.from('finance_transactions').insert(row).select().single();
      if (error) throw new Error(`Supabase insert stake: ${error.message}`);
      _transactions = [..._transactions, data];
    }

    _buildCouponList();
  }

  async function addPayout(globalIndex, amount) {
    const uid = Auth.getUser()?.id;
    if (!uid) throw new Error('Niezalogowany');
    const now = _nowStr();
    const cid = String(globalIndex);

    // Usuń istniejącą wypłatę
    const existing = (_transactions || []).filter(
      t => t.coupon_id === cid && t.type === 'payout'
    );
    if (existing.length > 0) {
      const ids = existing.map(t => t.id);
      const { error } = await _sb.from('finance_transactions').delete().in('id', ids);
      if (error) throw new Error(`Supabase delete payout: ${error.message}`);
      _transactions = _transactions.filter(t => !ids.includes(t.id));
    }

    if (amount > 0) {
      const row = {
        user_id: uid, tx_date: now, type: 'payout',
        amount: +Math.abs(amount), coupon_id: cid,
        note: `Wygrana kupon #${globalIndex}`,
      };
      const { data, error } = await _sb.from('finance_transactions').insert(row).select().single();
      if (error) throw new Error(`Supabase insert payout: ${error.message}`);
      _transactions = [..._transactions, data];
    }

    _buildCouponList();
  }

  async function setInitialBalance(amount) {
    const uid = Auth.getUser()?.id;
    if (!uid) throw new Error('Niezalogowany');
    const val = parseFloat(amount) || 0;
    const { error } = await _sb.from('user_settings').upsert({
      user_id: uid, initial_balance: val, updated_at: new Date().toISOString(),
    }, { onConflict: 'user_id' });
    if (error) throw new Error(`Supabase upsert balance: ${error.message}`);
    _settings = { ..._settings, initial_balance: val };
    _buildCouponList();
  }

  async function saveGitHubConfig(owner, repo, branch, token) {
    const uid = Auth.getUser()?.id;
    if (!uid) throw new Error('Niezalogowany');
    const row = {
      user_id: uid,
      github_owner:  owner,
      github_repo:   repo,
      github_branch: branch || 'main',
      github_token:  token,
      updated_at:    new Date().toISOString(),
    };
    const { error } = await _sb.from('user_settings').upsert(row, { onConflict: 'user_id' });
    if (error) throw new Error(`Supabase upsert config: ${error.message}`);
    _settings = { ..._settings, ...row };
    GitHub.configure(owner, repo, branch, token);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function _nowStr() {
    return new Date().toISOString().replace('T', ' ').substring(0, 16);
  }

  return {
    loadAll, getCoupons, getStats, getSettings,
    addStake, addPayout, setInitialBalance, saveGitHubConfig,
    getRealOddsForCoupon,
  };
})();
