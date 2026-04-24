"""
notify/finance.py
Śledzenie finansów gracza – rzeczywisty P&L (Player ROI).

Różnica względem Model ROI (evaluate.py):
  Model ROI  – używa sugerowanych stawek Kelly, niezależny od gracza,
               mierzy jakość predykcji modelu.
  Player ROI – używa RZECZYWISTYCH stawek i wypłat gracza, liczy ile
               faktycznie zarobił/stracił.

Stawki przypisane PER KUPON (nie sumarycznie per wysyłka):
  /stake 1 100  – postawiłem 100 PLN na kupon #1
  /stake 2 50   – postawiłem 50 PLN na kupon #2
  /stake 3 0    – nie postawiłem na kupon #3

Wypłaty z wygranej podawane przez gracza (kurs bukmachera może się różnić):
  /won 1 350    – kupon #1 wygrał, dostałem 350 PLN
  /lost 2       – kupon #2 przegrał

Struktura finance.json:
{
  "initial_balance": -1500,      # punkt startowy (ujemny = zaczynasz ze stratą)
  "transactions": [
    {
      "date":       "2025-04-25 10:30",
      "type":       "stake",            # stake | payout | adjustment
      "amount":     -100,               # ujemne = wydatek, dodatnie = wpływ
      "coupon_id":  "3",                # numer kuponu (string)
      "note":       "Kupon #3 SINGIEL"
    }
  ]
}
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from config import DATA_RESULTS

log = logging.getLogger(__name__)
FINANCE_PATH = Path(DATA_RESULTS) / "finance.json"


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
    """
    Ustawia punkt startowy (np. -1500 jeśli zaczynasz ze stratą przed systemem).
    Nadpisuje poprzednią wartość – wywołaj tylko raz na początku.
    """
    data = _load()
    data["initial_balance"] = float(amount)
    _save(data)
    return get_summary()


def add_stake(amount: float, coupon_id: str = "", note: str = "") -> None:
    """
    Zapisuje stawkę gracza na konkretny kupon.

    Args:
        amount:    kwota stawki w PLN (> 0)
        coupon_id: numer kuponu jako string (np. "1", "2", "3")
        note:      opcjonalny opis
    """
    data = _load()
    coupon_label = f"#{coupon_id}" if coupon_id else ""
    data["transactions"].append({
        "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        "type":      "stake",
        "amount":    -abs(float(amount)),      # wydatek = ujemny
        "coupon_id": str(coupon_id),
        "note":      note or f"Stawka na kupon {coupon_label}",
    })
    _save(data)


def add_payout(amount: float, coupon_id: str = "", note: str = "") -> None:
    """
    Zapisuje wypłatę z wygranego kuponu (kwota podana przez gracza –
    może różnić się od kursu modelu bo gracz gra u konkretnego bukmachera).

    Args:
        amount:    kwota wypłaty w PLN (> 0)
        coupon_id: numer kuponu jako string
        note:      opcjonalny opis
    """
    data = _load()
    coupon_label = f"#{coupon_id}" if coupon_id else ""
    data["transactions"].append({
        "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        "type":      "payout",
        "amount":    +abs(float(amount)),      # wpływ = dodatni
        "coupon_id": str(coupon_id),
        "note":      note or f"Wygrana z kuponu {coupon_label}",
    })
    _save(data)


def get_summary() -> dict:
    """
    Oblicza pełne podsumowanie finansowe gracza (Player ROI).

    Player ROI oparty o RZECZYWISTE stawki i wypłaty z finance.json –
    niezależny od Model ROI z evaluate.py.
    """
    data    = _load()
    txs     = data.get("transactions", [])
    initial = float(data.get("initial_balance", 0.0))

    total_staked  = sum(-t["amount"] for t in txs if t["type"] == "stake")
    total_payout  = sum( t["amount"] for t in txs if t["type"] == "payout")
    net_from_bets = total_payout - total_staked
    overall       = initial + net_from_bets

    # Statystyki per kupon (tylko kupony z coupon_id)
    stakes_by_coupon: dict[str, dict] = {}
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

    won_coupons  = sum(1 for v in stakes_by_coupon.values() if v["payout"] > v["staked"])
    lost_coupons = sum(
        1 for v in stakes_by_coupon.values()
        if v["payout"] == 0 and v["staked"] > 0
    )
    # Kupony zastawione ale bez wypłaty i bez info o przegranej – jeszcze w grze
    pending_player = sum(
        1 for v in stakes_by_coupon.values()
        if v["staked"] > 0 and v["payout"] == 0
        and all(
            t.get("coupon_id") != cid or t["type"] != "payout"
            for t in txs
            for cid in stakes_by_coupon
        )
    )

    roi = (net_from_bets / total_staked * 100) if total_staked > 0 else 0.0

    return {
        "initial_balance":    initial,
        "total_staked":       round(total_staked, 2),
        "total_payout":       round(total_payout, 2),
        "net_from_bets":      round(net_from_bets, 2),
        "overall":            round(overall, 2),
        "roi":                round(roi, 2),
        "won_coupons":        won_coupons,
        "lost_coupons":       lost_coupons,
        "total_coupons":      won_coupons + lost_coupons,
        "transactions_count": len(txs),
    }


def get_coupon_stakes() -> dict[str, dict]:
    """
    Zwraca słownik per-kupon stawek i wypłat gracza.
    Używany przez bota do sprawdzenia czy kupon był zagrany.

    Format: {"1": {"staked": 100.0, "payout": 350.0}, "2": {"staked": 50.0, "payout": 0.0}}
    """
    data = _load()
    txs  = data.get("transactions", [])
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
        f"  📋 Łącznie:   {s['total_coupons']}\n"
    )

    if pending and pending.get("count", 0) > 0:
        p = pending
        msg += (
            f"\n⏳ <b>Kupony oczekujące (model): {p['count']}</b>\n"
            f"  🎲 Sug. stawka Kelly:    <b>{p['total_staked_model']:.0f} PLN</b>\n"
            f"  🏆 Potencjalny zwrot:    <b>{p['potential_return']:.0f} PLN</b>\n"
            f"  <i>(wynik powyżej nie uwzględnia kuponów w grze)</i>\n"
        )
        for leg in p["legs_summary"]:
            msg += f"  • <code>{leg}</code>\n"

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
