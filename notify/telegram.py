"""
notify/telegram.py
Wysyła kupony i alerty przez Telegram Bot API.
"""
import logging
from datetime import datetime

import requests

from config import LEAGUES, TELEGRAM_CHAT_ID, TELEGRAM_TOKEN

log = logging.getLogger(__name__)

_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(text: str) -> bool:
    """
    Wysyła wiadomość na Telegram. Zwraca True przy sukcesie.

    Publiczne API – używaj tej funkcji zamiast _send z poprzedniej wersji.
    W trybie developerskim (brak tokenu) wypisuje na konsolę.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Brak TELEGRAM_TOKEN lub TELEGRAM_CHAT_ID!")
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
    return {
        "H":  "🏠",
        "D":  "🤝",
        "A":  "✈️",
        "1X": "🏠🤝",
        "X2": "🤝✈️",
        "12": "🏠✈️",
    }.get(outcome, "❓")


def _type_emoji(coupon_type: str) -> str:
    return {"SINGIEL": "🎯", "PODWÓJNY": "⚡", "POTRÓJNY": "🔥"}.get(coupon_type, "📋")


def _confidence_bar(prob: float) -> str:
    filled = round(prob * 10)
    return "█" * filled + "░" * (10 - filled)


def format_coupon(coupon: dict, index: int) -> str:
    """
    Formatuje kupon do wiadomości HTML dla Telegrama.
    Numer #index widoczny w nagłówku – gracz używa go w /stake i /won.
    """
    league_names = {code: info["name"] for code, info in LEAGUES.items()}
    emoji = _type_emoji(coupon["type"])

    lines = [
        f"{emoji} <b>KUPON #{index} — {coupon['type']}</b>",
        f"<i>Użyj /stake {index} [kwota] aby zalogować stawkę</i>",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    for i, leg in enumerate(coupon["legs"], 1):
        league = league_names.get(leg.get("league_code", ""), leg.get("league_code", ""))
        oe     = _outcome_emoji(leg["bet_outcome"])
        conf   = _confidence_bar(leg["model_prob"])

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
        f"🎲 Łączny kurs:     <b>{coupon['total_odds']:.2f}</b>",
        f"📊 Szansa wygranej:  {coupon['combined_prob']:.0%}",
        f"💵 Stawka Kelly:    <b>{coupon['stake']:.0f} PLN</b>",
        f"📈 Oczek. zwrot:    +{coupon['expected_value']:.1%}",
        f"\n➡️ <code>/stake {index} {coupon['stake']:.0f}</code>  lub  "
        f"<code>/stake {index} 0</code> jeśli nie grasz",
    ]

    return "\n".join(lines)


def send_coupons(coupons: list, first_coupon_index: int = 1) -> None:
    """
    Wysyła wszystkie kupony na Telegram.

    Args:
        coupons:            lista kuponów z builder.py
        first_coupon_index: globalny numer pierwszego kuponu w tej wysyłce
                            (pobierany z historii żeby numery były ciągłe)
    """
    date_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    if not coupons:
        send_message(
            f"ℹ️ <b>AI Betting System</b> — {date_str}\n\n"
            "Brak value betów spełniających kryteria.\n"
            "Czekamy na lepsze okazje. 📉"
        )
        return

    send_message(
        f"🤖 <b>AI BETTING SYSTEM</b>\n"
        f"📅 {date_str}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Znaleziono <b>{len(coupons)}</b> kuponów z wartościowymi zakładami.\n\n"
        "⚠️ <i>Zarządzaj bankrollem odpowiedzialnie.\n"
        "Stawiaj tylko stawki Kelly lub mniej.</i>"
    )

    for i, coupon in enumerate(coupons, first_coupon_index):
        send_message(format_coupon(coupon, i))

    total_stake = sum(c["stake"] for c in coupons)
    last_index  = first_coupon_index + len(coupons) - 1
    stake_hints = "  ".join(
        f"<code>/stake {i} ...</code>"
        for i in range(first_coupon_index, last_index + 1)
    )
    send_message(
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💼 Łączne zaangażowanie Kelly: <b>{total_stake:.0f} PLN</b>\n"
        f"📋 Kuponów: {len(coupons)}\n\n"
        f"<b>Zaloguj swoje stawki:</b>\n"
        f"{stake_hints}\n\n"
        "<i>Pamiętaj: to szacunki probabilistyczne,\n"
        "nie gwarancja zysku.</i> 🍀"
    )


def send_alert(message: str) -> None:
    """Wysyła alert o błędzie pipeline'u."""
    send_message(f"🚨 <b>ALERT SYSTEMU</b>\n\n{message[:3000]}")


def send_stats(stats: dict) -> None:
    """Wysyła cotygodniowe statystyki Model ROI."""
    roi_emoji = "📈" if stats.get("model_roi", 0) >= 0 else "📉"
    send_message(
        f"📊 <b>MODEL ROI – STATYSTYKI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Łącznie kuponów:  {stats.get('total_coupons', 0)}\n"
        f"Wygrane:          {stats.get('won', 0)} ✅\n"
        f"Przegrane:        {stats.get('lost', 0)} ❌\n"
        f"Oczekujące:       {stats.get('pending', 0)} ⏳\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{roi_emoji} Model ROI: <b>{stats.get('model_roi', 0):.1f}%</b>\n"
        "<i>(sugerowane stawki Kelly, nie rzeczywiste gracza)\n"
        "Użyj /balance żeby zobaczyć swój rzeczywisty P&L.</i>"
    )
