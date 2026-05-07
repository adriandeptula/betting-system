"""
notify/telegram.py
Wysyła kupony i alerty przez Telegram Bot API.

v1.6 zmiany:
  - send_stats(): sekcja CLV (avg_clv, clv_positive_pct, clv_legs)
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
    Numer #index widoczny w nagłówku — gracz używa go w /stake i /won.
    """
    league_names = {code: info["name"] for code, info in LEAGUES.items()}
    emoji        = _type_emoji(coupon["type"])

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
    """Wysyła wszystkie kupony na Telegram."""
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
    """
    Wysyła cotygodniowe statystyki Model ROI + CLV.

    v1.6: dodana sekcja CLV gdy clv_legs >= 5.
    CLV > 0 średnio = model ma rzeczywisty edge nad rynkiem (niezależnie od wyników).
    """
    roi_emoji = "📈" if stats.get("model_roi", 0) >= 0 else "📉"

    msg = (
        f"📊 <b>MODEL ROI — STATYSTYKI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Łącznie kuponów:     {stats.get('total_coupons', 0)}\n"
        f"Wygrane:             {stats.get('won', 0)} ✅\n"
        f"Przegrane:           {stats.get('lost', 0)} ❌\n"
        f"Oczekujące:          {stats.get('pending', 0)} ⏳\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Postawiono (rozl.): <b>{stats.get('staked_resolved', 0):.0f} PLN</b>\n"
        f"💵 Zwrot (WON):        <b>{stats.get('total_model_return', 0):.0f} PLN</b>\n"
        f"{roi_emoji} Model ROI:          <b>{stats.get('model_roi', 0):.1f}%</b>\n"
    )

    clv_legs = stats.get("clv_legs", 0)
    if clv_legs >= 5:
        clv_avg   = stats.get("clv_avg", 0.0)
        clv_pos   = stats.get("clv_positive_pct", 0.0)
        clv_emoji = "🟢" if clv_avg >= 1.0 else ("🟡" if clv_avg >= 0 else "🔴")
        msg += (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📐 <b>CLV (Closing Line Value)</b>\n"
            f"{clv_emoji} Średnie CLV:     <b>{clv_avg:+.2f}%</b>\n"
            f"📊 Dodatnie CLV:   <b>{clv_pos:.0f}%</b> nóg\n"
            f"📋 Próbek CLV:     {clv_legs}\n"
            "<i>CLV &gt; 0% długoterminowo = model ma edge nad rynkiem</i>\n"
        )
    elif clv_legs > 0:
        msg += f"📐 CLV: {clv_legs} nóg (potrzeba ≥5 do analizy)\n"

    msg += (
        "<i>(sugerowane stawki Kelly, nie rzeczywiste gracza)\n"
        "Użyj /balance żeby zobaczyć swój rzeczywisty P&amp;L.</i>"
    )

    send_message(msg)


def format_resolved_notification(resolved: list[dict]) -> str:
    """
    Formatuje powiadomienie o automatycznie rozliczonych kuponach.

    Args:
        resolved: lista slownikow z auto_resolve_pending_coupons()
                  [{coupon_nr, type, result, total_odds, stake, payout, legs, clv_parts}]

    Przyklad wyjscia:
      🤖 Auto-rozliczono 2 kupony

      ✅ #3 SINGIEL @ 2.10
         Man City vs Arsenal → H (wygrana gosp.)
         Kelly: 30 PLN | Zwrot: 63 PLN
         CLV: +2.4%

      ❌ #4 PODWOJNY @ 5.20
         Liverpool vs Chelsea → A
         Dortmund vs Bayern → H
         Kelly: 20 PLN
    """
    if not resolved:
        return ""

    won  = [r for r in resolved if r["result"] == "WON"]
    lost = [r for r in resolved if r["result"] == "LOST"]

    lines = [f"🤖 <b>Auto-rozliczono {len(resolved)} {'kupon' if len(resolved) == 1 else 'kupony' if len(resolved) < 5 else 'kuponow'}</b>"]

    for r in resolved:
        nr         = r["coupon_nr"]
        result     = r["result"]
        coupon_type = r["type"]
        odds       = r["total_odds"]
        stake      = r["stake"]
        payout     = r["payout"]
        clv_parts  = r.get("clv_parts", [])

        emoji = "✅" if result == "WON" else "❌"
        lines.append("")
        lines.append(f"{emoji} <b>#{nr} {coupon_type} @ {odds:.2f}</b>")

        # Nogi kuponu
        for leg in r.get("legs", []):
            home    = leg.get("home_team", "?")[:14]
            away    = leg.get("away_team", "?")[:14]
            outcome = leg.get("bet_outcome", "?")
            label   = leg.get("bet_label", outcome)
            lines.append(f"   {home} vs {away} → <b>{label}</b>")

        # Finansowe
        if result == "WON":
            lines.append(f"   💰 Kelly: {stake:.0f} PLN | Zwrot: <b>{payout:.0f} PLN</b> (+{payout - stake:.0f})")
        else:
            lines.append(f"   💸 Kelly: {stake:.0f} PLN | Strata: -{stake:.0f} PLN")

        # CLV jesli dostepne
        if clv_parts:
            clv_str = " | ".join(clv_parts)
            lines.append(f"   📐 CLV: {clv_str}")

    # Podsumowanie finansowe
    if len(resolved) > 1:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        total_stake  = sum(r["stake"]  for r in resolved)
        total_payout = sum(r["payout"] for r in resolved)
        net          = total_payout - total_stake
        net_emoji    = "✅" if net >= 0 else "❌"
        lines.append(f"{net_emoji} Bilans tej sesji: <b>{net:+.0f} PLN</b>")
        lines.append(f"   Wygrane: {len(won)} | Przegrane: {len(lost)}")

    return "\n".join(lines)


def send_resolved_notification(resolved: list[dict], summary: dict, pending: dict | None = None) -> None:
    """
    Wysyla pelne powiadomienie po auto-rozliczeniu kuponow.

    Args:
        resolved: lista z auto_resolve_pending_coupons()
        summary:  slownik z finance.get_summary()
        pending:  slownik z evaluate.get_pending_summary() (opcjonalny)
    """
    from notify.finance import format_summary_message

    if not resolved:
        return

    # Najpierw szczegoly rozliczonych kuponow
    details_msg = format_resolved_notification(resolved)
    if details_msg:
        send_message(details_msg)

    # Potem aktualny stan finansowy
    send_message(format_summary_message(summary, pending))
