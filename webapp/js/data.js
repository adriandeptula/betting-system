/**
 * data.js – Data loading, processing and financial calculations.
 * Manages coupons_history.json and finance.json state.
 */

const Data = (() => {
  const PATHS = {
    history: 'data/results/coupons_history.json',
    finance: 'data/results/finance.json',
  };

  // In-memory state
  let _history = [];       // raw coupons_history.json content
  let _historySha = null;
  let _finance = {};       // raw finance.json content
  let _financeSha = null;

  // Computed coupon list with global index
  let _coupons = [];       // flat list: { globalIndex, date, ...coupon, playerData }

  // ── Load ─────────────────────────────────────────────────────────────────

  async function loadAll() {
    const [hist, fin] = await Promise.all([
      GitHub.loadFile(PATHS.history),
      GitHub.loadFile(PATHS.finance),
    ]);

    _history = hist.content || [];
    _historySha = hist.sha;

    _finance = fin.content || { initial_balance: 0, transactions: [] };
    _financeSha = fin.sha;

    _buildCouponList();
    return { history: _history, finance: _finance };
  }

  function _buildCouponList() {
    _coupons = [];
    let idx = 0;

    const stakesByIdx = _getStakesByIndex();

    for (const entry of _history) {
      for (const coupon of (entry.coupons || [])) {
        idx++;
        const player = stakesByIdx[String(idx)] || { staked: 0, payout: 0, hasPayout: false };
        _coupons.push({
          globalIndex: idx,
          date: entry.date,
          type: coupon.type,
          legs: coupon.legs || [],
          total_odds: coupon.total_odds,
          combined_prob: coupon.combined_prob,
          kellyStake: coupon.stake,
          expected_value: coupon.expected_value,
          result: coupon.result || 'PENDING',
          resolved_at: coupon.resolved_at || null,
          // Player data
          playerStaked: player.staked,
          playerPayout: player.payout,
          hasPayout: player.hasPayout,
          // Derived status for UI
          uiStatus: _getUiStatus(coupon.result, player),
        });
      }
    }
  }

  function _getUiStatus(result, player) {
    if (result === 'WON') return 'won';
    if (result === 'LOST') return 'lost';
    if (player.staked > 0) return 'playing'; // model PENDING, player staked
    return 'new'; // not staked yet
  }

  function _getStakesByIndex() {
    const txs = _finance.transactions || [];
    const map = {};
    const payoutIds = new Set();

    for (const tx of txs) {
      const cid = String(tx.coupon_id || '');
      if (!cid || cid === '?') continue;
      if (!map[cid]) map[cid] = { staked: 0, payout: 0, hasPayout: false };

      if (tx.type === 'stake') {
        map[cid].staked += Math.abs(tx.amount);
      } else if (tx.type === 'payout') {
        map[cid].payout += Math.abs(tx.amount);
        map[cid].hasPayout = true;
        payoutIds.add(cid);
      }
    }
    return map;
  }

  // ── Accessors ─────────────────────────────────────────────────────────────

  function getCoupons() { return _coupons; }
  function getFinance() { return _finance; }

  function getStats() {
    const txs = _finance.transactions || [];
    const initial = _finance.initial_balance || 0;

    let totalStaked = 0, totalPayout = 0;
    for (const tx of txs) {
      if (tx.type === 'stake') totalStaked += Math.abs(tx.amount);
      if (tx.type === 'payout') totalPayout += Math.abs(tx.amount);
    }

    const net = totalPayout - totalStaked;
    const roi = totalStaked > 0 ? (net / totalStaked) * 100 : 0;
    const overall = initial + net;

    // Coupon counts
    const won = _coupons.filter(c => c.result === 'WON').length;
    const lost = _coupons.filter(c => c.result === 'LOST').length;
    const pending = _coupons.filter(c => c.result === 'PENDING').length;
    const newCoupons = _coupons.filter(c => c.uiStatus === 'new').length;
    const playing = _coupons.filter(c => c.uiStatus === 'playing').length;

    // Model stats
    const modelWon = _coupons.filter(c => c.result === 'WON');
    const modelLost = _coupons.filter(c => c.result === 'LOST');
    let modelStaked = 0, modelReturn = 0;
    for (const c of modelWon) {
      modelStaked += c.kellyStake;
      modelReturn += c.kellyStake * c.total_odds;
    }
    for (const c of modelLost) {
      modelStaked += c.kellyStake;
    }
    const modelRoi = modelStaked > 0 ? ((modelReturn - modelStaked) / modelStaked) * 100 : 0;

    // Pending potential
    const pendingStake = _coupons
      .filter(c => c.result === 'PENDING' && c.playerStaked > 0)
      .reduce((s, c) => s + c.playerStaked, 0);
    const pendingPotential = _coupons
      .filter(c => c.result === 'PENDING' && c.playerStaked > 0)
      .reduce((s, c) => s + c.playerStaked * c.total_odds, 0);

    // ROI chart data (monthly)
    const roiByMonth = _buildMonthlyRoi();

    return {
      initial, totalStaked, totalPayout, net, roi, overall,
      won, lost, pending, newCoupons, playing,
      total: _coupons.length,
      modelRoi, modelStaked, modelReturn,
      pendingStake, pendingPotential,
      roiByMonth,
      worstCase: overall - pendingStake,
      bestCase: overall + pendingPotential,
    };
  }

  function _buildMonthlyRoi() {
    const txs = _finance.transactions || [];
    const byMonth = {};

    for (const tx of txs) {
      const month = tx.date.substring(0, 7); // "2025-04"
      if (!byMonth[month]) byMonth[month] = { staked: 0, payout: 0 };
      if (tx.type === 'stake') byMonth[month].staked += Math.abs(tx.amount);
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

  // ── Write operations ──────────────────────────────────────────────────────

  async function addStake(globalIndex, amount, realOdds, note) {
    const now = new Date().toISOString().replace('T', ' ').substring(0, 16);
    const cid = String(globalIndex);

    // Remove existing stake transactions for this coupon if editing
    const txs = _finance.transactions || [];
    const existing = txs.filter(t => t.coupon_id === cid && t.type === 'stake');
    if (existing.length > 0) {
      _finance.transactions = txs.filter(t => !(t.coupon_id === cid && t.type === 'stake'));
    }

    if (amount > 0) {
      _finance.transactions.push({
        date: now,
        type: 'stake',
        amount: -Math.abs(amount),
        coupon_id: cid,
        real_odds: realOdds || null,
        note: note || `Stawka na kupon #${globalIndex}`,
      });
    }

    await _saveFinance(`webapp: stake #${globalIndex} ${amount} PLN`);
    _buildCouponList();
  }

  async function addPayout(globalIndex, amount) {
    const now = new Date().toISOString().replace('T', ' ').substring(0, 16);
    const cid = String(globalIndex);

    // Remove existing payout for this coupon
    _finance.transactions = (_finance.transactions || [])
      .filter(t => !(t.coupon_id === cid && t.type === 'payout'));

    if (amount > 0) {
      _finance.transactions.push({
        date: now,
        type: 'payout',
        amount: +Math.abs(amount),
        coupon_id: cid,
        note: `Wygrana kupon #${globalIndex}`,
      });
    }

    await _saveFinance(`webapp: payout #${globalIndex} ${amount} PLN`);
    _buildCouponList();
  }

  async function setInitialBalance(amount) {
    _finance.initial_balance = parseFloat(amount);
    await _saveFinance(`webapp: set initial balance ${amount}`);
    _buildCouponList();
  }

  async function _saveFinance(message) {
    const newSha = await GitHub.saveFile(PATHS.finance, _finance, message, _financeSha);
    _financeSha = newSha;
  }

  function getRealOddsForCoupon(globalIndex) {
    const txs = _finance.transactions || [];
    const tx = txs.find(t => t.coupon_id === String(globalIndex) && t.type === 'stake');
    return tx ? (tx.real_odds || null) : null;
  }

  function couponHasStake(globalIndex) {
    const txs = _finance.transactions || [];
    return txs.some(t => t.coupon_id === String(globalIndex) && t.type === 'stake' && Math.abs(t.amount) > 0);
  }

  return {
    loadAll,
    getCoupons,
    getFinance,
    getStats,
    addStake,
    addPayout,
    setInitialBalance,
    getRealOddsForCoupon,
    couponHasStake,
  };
})();
