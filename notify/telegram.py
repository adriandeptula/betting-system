"""
notify/telegram.py
Wysyła kupony i alerty przez Telegram Bot API.
"""
import logging
from datetime import datetime

import requests

from config import LEAGUES, TELEGRAM_CHAT_ID, TELEGRAM_TOKEN

log = logging.getLogger(__name__)

_API_URL = f"https://api.telegram.org/bot{{token}}/sendMessage"


def _send(text: str) -> bool:
    """Wysyła wiadomość. Zwraca True jeśli sukces."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Brak TELEGRAM_TOKEN lub TELEGRAM_CHAT_ID!")
        # W trybie developerskim wypisz na konsole
        print("\n" + "=" * 60)
        print(text)
        print("=" * 60 + "\n")
        return False

    url = _API_URL.format(token=TELEGRAM_TOKEN)
    try:
        resp = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Błąd Telegram: {e}")
        return False


def _outcome_emoji(outcome: str) -> str:
    return {"H": "🏠", "D": "🤝", "A": "✈️"}.get(outcome, "❓")


def _type_emoji(coupon_type: str) -> str:
    return {"SINGIEL": "🎯", "PODWÓJNY": "⚡", "POTRÓJNY": "🔥"}.get(coupon_type, "📋")


def _confidence_bar(prob: float) -> str:
    """Wizualny pasek pewności modelu."""
    filled = round(prob * 10)
    return "█" * filled + "░" * (10 - filled)


def format_coupon(coupon: dict, index: int) -> str:
    """Formatuje kupon do czytelnej wiadomości HTML dla Telegrama."""
    league_names = {code: info["name"] for code, info in LEAGUES.items()}
    emoji = _type_emoji(coupon["type"])

    lines = [
        f"{emoji} <b>KUPON {index} — {coupon['type']}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for i, leg in enumerate(coupon["legs"], 1):
        league = league_names.get(leg.get("league_code", ""), leg.get("league_code", ""))
        oe = _outcome_emoji(leg["bet_outcome"])
        conf = _confidence_bar(leg["model_prob"])

        lines += [
            f"\n<b>{i}. {leg['home_team']} vs {leg['away_team']}</b>",
            f"   🏆 {league}",
            f"   {oe} <b>{leg['bet_label']}</b>",
            f"   💰 Kurs: <b>{leg['bet_odds']:.2f}</b>",
            f"   📊 Model: {leg['model_prob']:.0%}  [{conf}]",
            f"   🎯 Rynek: {leg['market_prob']:.0%}",
            f"   📈 Edge: <b>+{leg['edge']:.1%}</b>",
        ]
        if i < len(coupon["legs"]):
            lines.append("   ─────────────────────")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🎲 Łączny kurs:    <b>{coupon['total_odds']:.2f}</b>",
        f"📊 Szansa wygranej: {coupon['combined_prob']:.0%}",
        f"💵 Stawka Kelly:   <b>{coupon['stake']:.0f} PLN</b>",
        f"📈 Oczek. zwrot:   +{coupon['expected_value']:.1%}",
    ]

    return "\n".join(lines)


def send_coupons(coupons: list) -> None:
    """Wysyła wszystkie kupony na Telegram."""
    date_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    if not coupons:
        _send(
            f"ℹ️ <b>AI Betting System</b> — {date_str}\n\n"
            "Brak value betów spełniających kryteria.\n"
            "Czekamy na lepsze okazje. 📉"
        )
        return

    # Nagłówek
    _send(
        f"🤖 <b>AI BETTING SYSTEM</b>\n"
        f"📅 {date_str}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Znaleziono <b>{len(coupons)}</b> kuponów z wartościowymi zakładami.\n\n"
        "⚠️ <i>Zarządzaj bankrollem odpowiedzialnie.\n"
        "Stawiaj tylko stawki Kelly lub mniej.</i>"
    )

    # Każdy kupon osobno
    for i, coupon in enumerate(coupons, 1):
        _send(format_coupon(coupon, i))

    # Stopka ze statystykami
    total_stake = sum(c["stake"] for c in coupons)
    _send(
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 Łączne zaangażowanie: <b>{total_stake:.0f} PLN</b>\n"
        f"📋 Kuponów: {len(coupons)}\n\n"
        "<i>Pamiętaj: to szacunki probabilistyczne,\n"
        "nie gwarancja zysku.</i> 🍀"
    )


def send_alert(message: str) -> None:
    """Wysyła alert o błędzie pipeline'u."""
    _send(f"🚨 <b>ALERT SYSTEMU</b>\n\n{message[:3000]}")


def send_stats(stats: dict) -> None:
    """Wysyła cotygodniowe statystyki ROI."""
    roi_emoji = "📈" if stats.get("roi", 0) >= 0 else "📉"
    _send(
        f"📊 <b>STATYSTYKI TYGODNIOWE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Łącznie kuponów:  {stats.get('total_coupons', 0)}\n"
        f"Wygrane:          {stats.get('won', 0)} ✅\n"
        f"Przegrane:        {stats.get('lost', 0)} ❌\n"
        f"Oczekujące:       {stats.get('pending', 0)} ⏳\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{roi_emoji} ROI: <b>{stats.get('roi', 0):.1f}%</b>"
    )
