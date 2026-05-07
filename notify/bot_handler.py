"""
notify/bot_handler.py
Dwukierunkowa komunikacja z Telegramem – obsługa komend.

Działa przez polling (getUpdates) uruchamiany co godzinę przez GitHub Actions.
Każde uruchomienie:
  1. Auto-rozlicza PENDING kupony (dynamiczny days_back)
  2. Jeśli coś rozliczył — wysyła szczegółowe powiadomienie (nowa funkcja v1.6)
  3. Sprawdza nowe komendy i odpowiada

Komendy:
  /help              – lista komend
  /stats             – Model ROI + CLV
  /balance           – Player ROI
  /pending           – kupony oczekujące
  /setbalance X      – ustaw punkt startowy
  /stake [nr] X      – zaloguj stawkę na kupon
  /won [nr] X        – kupon wygrany
  /lost [nr]         – kupon przegrany
"""
import json
import logging
from datetime import datetime
from pathlib import Path

import requests

from config import DATA_RESULTS, TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from notify.finance import (
    add_payout,
    add_stake,
    format_summary_message,
    get_summary,
    set_initial_balance,
)
from notify.telegram import send_message, send_stats, send_resolved_notification

log = logging.getLogger(__name__)

OFFSET_FILE = Path(DATA_RESULTS) / "tg_offset.json"
API_BASE    = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


# ── Telegram helpers ──────────────────────────────────────────────────────────

def _get_updates(offset: int = 0) -> list:
    try:
        resp = requests.get(
            f"{API_BASE}/getUpdates",
            params={"offset": offset, "timeout": 5, "allowed_updates": ["message"]},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])
    except Exception as e:
        log.warning(f"getUpdates error: {e}")
        return []


def _load_offset() -> int:
    if OFFSET_FILE.exists():
        with open(OFFSET_FILE) as f:
            return json.load(f).get("offset", 0)
    return 0


def _save_offset(offset: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset, "updated": datetime.now().isoformat()}, f)


def _get_pending():
    try:
        from model.evaluate import get_pending_summary
        return get_pending_summary()
    except Exception:
        return None


def _parse_coupon_nr_and_amount(args: str) -> tuple[str, float | None]:
    parts = args.strip().split()
    if len(parts) == 0:
        return "?", None
    if len(parts) == 1:
        try:
            return "?", float(parts[0].replace(",", "."))
        except ValueError:
            return "?", None
    try:
        coupon_id = parts[0]
        amount    = float(parts[1].replace(",", "."))
        return coupon_id, amount
    except (ValueError, IndexError):
        return "?", None


def _parse_coupon_nr(args: str) -> str:
    parts = args.strip().split()
    return parts[0] if parts else "?"


# ── Obsługa komend ────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    send_message(
        "🤖 <b>AI Betting Bot — Komendy</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📊 Statystyki:</b>\n"
        "  /stats           – Model ROI + CLV\n"
        "  /balance         – Twój rzeczywisty P&amp;L\n"
        "  /pending         – kupony czekające na wynik\n\n"
        "<b>💰 Stawki:</b>\n"
        "  /stake [nr] [kwota]  – postaw na kupon\n"
        "                         np. /stake 1 100\n"
        "                         np. /stake 2 0  (nie grasz)\n\n"
        "<b>🎯 Wyniki:</b>\n"
        "  /won [nr] [kwota]    – kupon wygrany\n"
        "                         np. /won 1 350\n"
        "  /lost [nr]           – kupon przegrany\n"
        "                         np. /lost 2\n\n"
        "<b>⚙️ Ustawienia:</b>\n"
        "  /setbalance X    – punkt startowy\n"
        "                     np. /setbalance -1500\n\n"
        "<i>Nr kuponu widoczny w każdej wiadomości z kuponem (#1, #2, #3).</i>"
    )


def _cmd_stats() -> None:
    from model.evaluate import update_coupon_results
    stats = update_coupon_results()
    send_stats(stats)


def _cmd_balance() -> None:
    s       = get_summary()
    pending = _get_pending()
    send_message(format_summary_message(s, pending))


def _cmd_pending() -> None:
    pending = _get_pending()
    if not pending or pending["count"] == 0:
        send_message("✅ Brak kuponów oczekujących na rozliczenie.")
        return
    p   = pending
    msg = (
        f"⏳ <b>Kupony oczekujące: {p['count']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    for leg in p["legs_summary"]:
        msg += f"  • <code>{leg}</code>\n"
    msg += (
        f"\n🎲 Sug. stawka Kelly:  <b>{p['total_staked_model']:.0f} PLN</b>\n"
        f"🏆 Potencjalny zwrot: <b>{p['potential_return']:.0f} PLN</b>\n\n"
        f"<i>Użyj /won [nr] [kwota] lub /lost [nr] aby rozliczyć.</i>"
    )
    send_message(msg)


def _cmd_setbalance(args: str) -> None:
    try:
        amount  = float(args.strip().replace(",", "."))
        s       = set_initial_balance(amount)
        pending = _get_pending()
        send_message(
            f"✅ Punkt startowy ustawiony: <b>{amount:+.0f} PLN</b>\n\n"
            + format_summary_message(s, pending)
        )
    except ValueError:
        send_message("❌ Podaj liczbę, np. <code>/setbalance -1500</code>")


def _cmd_stake(args: str) -> None:
    coupon_id, amount = _parse_coupon_nr_and_amount(args)
    if amount is None:
        send_message(
            "❌ Nieprawidłowy format.\n"
            "Użyj: <code>/stake [nr_kuponu] [kwota]</code>\n"
            "Np. <code>/stake 1 100</code>  lub  <code>/stake 1 0</code>"
        )
        return
    if amount < 0:
        send_message("❌ Kwota stawki nie może być ujemna.")
        return
    if amount == 0:
        coupon_label = f"#{coupon_id}" if coupon_id != "?" else ""
        send_message(f"ℹ️ Zanotowano: nie grasz na kupon {coupon_label}.")
        return

    add_stake(amount, coupon_id=coupon_id)
    s            = get_summary()
    pending      = _get_pending()
    coupon_label = f"#{coupon_id}" if coupon_id != "?" else ""
    send_message(
        f"✅ Stawka na kupon {coupon_label}: <b>-{amount:.0f} PLN</b>\n\n"
        + format_summary_message(s, pending)
    )


def _cmd_won(args: str) -> None:
    coupon_id, amount = _parse_coupon_nr_and_amount(args)
    if amount is None:
        send_message(
            "❓ Podaj numer kuponu i kwotę wygranej:\n"
            "Np. <code>/won 1 350</code>"
        )
        return
    if amount < 0:
        send_message("❌ Kwota wypłaty nie może być ujemna.")
        return

    add_payout(amount, coupon_id=coupon_id, note=f"Wygrana kupon #{coupon_id}")
    s            = get_summary()
    pending      = _get_pending()
    coupon_label = f"#{coupon_id}" if coupon_id != "?" else ""
    send_message(
        f"🏆 Kupon {coupon_label} wygrany! Wypłata: <b>+{amount:.0f} PLN</b>\n\n"
        + format_summary_message(s, pending)
    )


def _cmd_lost(args: str) -> None:
    coupon_id    = _parse_coupon_nr(args)
    coupon_label = f"#{coupon_id}" if coupon_id != "?" else ""
    s            = get_summary()
    pending      = _get_pending()
    send_message(
        f"😔 Kupon {coupon_label} przegrany. Stawka już zalogowana przez /stake.\n\n"
        + format_summary_message(s, pending)
    )


# ── Dispatcher ────────────────────────────────────────────────────────────────

def _dispatch(text: str) -> None:
    text = text.strip()
    if not text.startswith("/"):
        send_message(
            "ℹ️ Używaj komend zaczynających się od /\n"
            "Wpisz /help żeby zobaczyć listę komend."
        )
        return

    parts = text.split(None, 1)
    cmd   = parts[0].lower().split("@")[0]
    args  = parts[1] if len(parts) > 1 else ""

    handlers = {
        "/help":       lambda: _cmd_help(),
        "/stats":      lambda: _cmd_stats(),
        "/balance":    lambda: _cmd_balance(),
        "/pending":    lambda: _cmd_pending(),
        "/setbalance": lambda: _cmd_setbalance(args),
        "/stake":      lambda: _cmd_stake(args),
        "/won":        lambda: _cmd_won(args),
        "/lost":       lambda: _cmd_lost(args),
        "/start":      lambda: _cmd_help(),
        "/payout":     lambda: _cmd_won(args),
    }

    handler = handlers.get(cmd)
    if handler:
        handler()
    else:
        send_message(
            f"❓ Nieznana komenda: <code>{cmd}</code>\n"
            "Wpisz /help żeby zobaczyć dostępne komendy."
        )


# ── Główna pętla pollingu ─────────────────────────────────────────────────────

def poll_and_respond() -> int:
    """
    Sprawdza nowe wiadomości i odpowiada na komendy.
    Przy każdym wywołaniu auto-rozlicza PENDING kupony.

    v1.6: używa send_resolved_notification() — szczegółowe powiadomienie
    z listą rozliczonych kuponów (wynik, nogi, finansowe, CLV).
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Brak TELEGRAM_TOKEN lub TELEGRAM_CHAT_ID – bot wyłączony.")
        return 0

    try:
        from model.evaluate import auto_resolve_pending_coupons
        resolved = auto_resolve_pending_coupons()
        if resolved:
            pending = _get_pending()
            send_resolved_notification(resolved, get_summary(), pending)
    except Exception as e:
        log.warning(f"Auto-resolve error: {e}")

    offset    = _load_offset()
    updates   = _get_updates(offset)
    processed = 0

    for update in updates:
        update_id = update.get("update_id", 0)
        offset    = update_id + 1

        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text    = message.get("text", "")

        if chat_id != str(TELEGRAM_CHAT_ID):
            log.warning(f"Wiadomość z nieznanego chat_id: {chat_id} – ignoruję")
            continue

        if text:
            log.info(f"Komenda od użytkownika: {text!r}")
            _dispatch(text)
            processed += 1

    _save_offset(offset)
    log.info(f"Przetworzono {processed} wiadomości (nowy offset: {offset})")
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    poll_and_respond()
