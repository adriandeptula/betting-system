"""
notify/finance.py
Śledzenie finansów gracza – rzeczywisty P&L (Player ROI).

Różnica względem Model ROI (evaluate.py):
  Model ROI  – używa sugerowanych stawek Kelly, mierzy jakość predykcji.
  Player ROI – używa RZECZYWISTYCH stawek i wypłat gracza.

v1.6.1 zmiany:
  - format_summary_message(): zamiast rozwiniętej listy kuponów oczekujących
    pokazuje link do dashboardu + skrótowe statystyki (count, stake, return).
    Przy 30 kuponach lista była nieczytelna w Telegramie.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from config import DATA_RESULTS

log = logging.getLogger(__name__)
FINANCE_PATH   = Path(DATA_RESULTS) / "finance.json"
DASHBOARD_URL  = "https://adriandeptula.github.io/betting-system/"


# ── Odczyt / Zapis ────────────────────────────────────────────────────────────

def _load() -> dict:
    if not FINANCE_PATH.exists():
        return {"initial_balance": 0.0, "transactions": []}
    with open(FINANCE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    FINANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FINANCE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Operacje ──────────────────────────────────────────────────────────────────

def set_initial_balance(amount: float, note: str = "") -> dict:
    data = _load()
    data["initial_balance"] = float(amount)
    _save(data)
    return get_summary()


def add_stake(amount: float, coupon_id: str = "", note: str = "") -> None:
    data         = _load()
    coupon_label = f"#{coupon_id}" if coupon_id else ""
    data["transactions"].append({
        "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        "type":      "stake",
        "amount":    -abs(float(amount)),
        "coupon_id": str(coupon_id),
        "note":      note or f"Stawka na kupon {coupon_label}",
    })
    _save(data)


def add_payout(amount: float, coupon_id: str = "", note: str = "") -> None:
    data         = _load()
    coupon_label = f"#{coupon_id}" if coupon_id else ""
    data["transactions"].append({
        "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        "type":      "payout",
        "amount":    +abs(float(amount)),
        "coupon_id": str(coupon_id),
        "note":      note or f"Wygrana z kuponu {coupon_label}",
    })
    _save(data)


def get_summary() -> dict:
    data    = _load()
    txs     = data.get("transactions", [])
    initial = float(data.get("initial_balance", 0.0))

    total_staked  = sum(-t["amount"] for t in txs if t["type"] == "stake")
    total_payout  = sum( t["amount"] for t in txs if t["type"] == "payout")
    net_from_bets = total_payout - total_staked
    overall       = initial + net_from_bets

    stakes_by_coupon:       dict[str, dict] = {}
    coupon_ids_with_payout: set[str]        = set()

    for t in txs:
        cid = t.get("coupon_id", "")
        if not cid:
            continue
        if cid not in stakes_by_coupon:
            stakes_by_coupon[cid] = {"staked": 0.0, "payout": 0.0}
        if t["type"] == "stake":
            stakes_by_coupon[cid]["staked"] += abs(t["amount"])
        elif t["type"] == "payout":
            stakes_by_coupon[cid]["payout"] += t["amount"]
            coupon_ids_with_payout.add(cid)

    won_coupons  = sum(1 for v in stakes_by_coupon.values() if v["payout"] > v["staked"])
    lost_coupons = sum(
        1 for cid, v in stakes_by_coupon.items()
        if v["payout"] == 0 and v["staked"] > 0 and cid not in coupon_ids_with_payout
        and any(
            t.get("coupon_id") == cid and t["type"] == "stake"
            for t in txs
        )
    )
    pending_player_coupons = sum(
        1 for cid, v in stakes_by_coupon.items()
        if v["staked"] > 0 and v["payout"] == 0 and cid not in coupon_ids_with_payout
    )

    roi = (net_from_bets / total_staked * 100) if total_staked > 0 else 0.0

    return {
        "initial_balance":        initial,
        "total_staked":           round(total_staked, 2),
        "total_payout":           round(total_payout, 2),
        "net_from_bets":          round(net_from_bets, 2),
        "overall":                round(overall, 2),
        "roi":                    round(roi, 2),
        "won_coupons":            won_coupons,
        "lost_coupons":           lost_coupons,
        "pending_player_coupons": pending_player_coupons,
        "total_coupons":          won_coupons + lost_coupons,
        "transactions_count":     len(txs),
    }


def get_coupon_stakes() -> dict[str, dict]:
    data   = _load()
    txs    = data.get("transactions", [])
    stakes: dict[str, dict] = {}
    for t in txs:
        cid = t.get("coupon_id", "")
        if not cid:
            continue
        if cid not in stakes:
            stakes[cid] = {"staked": 0.0, "payout": 0.0}
        if t["type"] == "stake":
            stakes[cid]["staked"] += abs(t["amount"])
        elif t["type"] == "payout":
            stakes[cid]["payout"] += t["amount"]
    return stakes


def format_summary_message(s: dict, pending: dict | None = None) -> str:
    """
    Formatuje podsumowanie finansowe gracza do wiadomości Telegram.

    v1.6.1: zamiast rozwiniętej listy PENDING kuponów (nieczytelna przy >5)
    pokazuje link do dashboardu + skrótowe statystyki.

    Args:
        s:       słownik z get_summary()
        pending: opcjonalny słownik z get_pending_summary() z evaluate.py
    """
    overall = s["overall"]
    net     = s["net_from_bets"]
    roi     = s["roi"]

    overall_emoji = "📈" if overall >= 0 else "📉"
    net_emoji     = "✅" if net >= 0 else "❌"
    roi_emoji     = "🟢" if roi >= 5 else ("🟡" if roi >= 0 else "🔴")

    initial_str = (
        f"{'📉' if s['initial_balance'] < 0 else '📊'} "
        f"Start: <b>{s['initial_balance']:+.0f} PLN</b>"
    )

    pending_player = s.get("pending_player_coupons", 0)

    msg = (
        f"💼 <b>STATUS FINANSOWY (Player ROI)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{initial_str}\n\n"
        f"<b>Rzeczywiste zakłady:</b>\n"
        f"  💸 Wpłacono łącznie:   <b>{s['total_staked']:.0f} PLN</b>\n"
        f"  💰 Wypłacono łącznie:  <b>{s['total_payout']:.0f} PLN</b>\n"
        f"  {net_emoji} Wynik z zakładów:   <b>{net:+.0f} PLN</b>\n"
        f"  {roi_emoji} ROI (gracz):       <b>{roi:+.1f}%</b>\n\n"
        f"<b>Kupony gracza:</b>\n"
        f"  ✅ Wygrane:   {s['won_coupons']}\n"
        f"  ❌ Przegrane: {s['lost_coupons']}\n"
        f"  ⏳ Oczekujące: {pending_player}\n"
        f"  📋 Łącznie:   {s['total_coupons']}\n"
    )

    # Sekcja kuponów oczekujących — skrót + link zamiast pełnej listy
    if pending and pending.get("count", 0) > 0:
        p = pending
        msg += (
            f"\n⏳ <b>Kupony oczekujące (model): {p['count']}</b>\n"
            f"  🎲 Sug. stawka Kelly:  <b>{p['total_staked_model']:.0f} PLN</b>\n"
            f"  🏆 Potencjalny zwrot:  <b>{p['potential_return']:.0f} PLN</b>\n"
            f"  📊 <a href=\"{DASHBOARD_URL}\">Zobacz szczegóły → Dashboard</a>\n"
        )

    msg += (
        f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{overall_emoji} <b>CAŁOŚCIOWY WYNIK: {overall:+.0f} PLN</b>"
    )

    if pending and pending.get("count", 0) > 0:
        worst_case = overall - pending["total_staked_model"]
        best_case  = overall + pending["potential_return"]
        msg += (
            f"\n📊 Zakres z uwzgl. oczekujących:\n"
            f"  Worst: <b>{worst_case:+.0f} PLN</b> | "
            f"Best: <b>{best_case:+.0f} PLN</b>"
        )

    return msg
