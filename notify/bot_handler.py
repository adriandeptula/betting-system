"""
notify/bot_handler.py
Dwukierunkowa komunikacja z Telegramem – obsługa komend.

Działa przez polling (getUpdates) uruchamiany co godzinę przez GitHub Actions.
Każde uruchomienie sprawdza nowe wiadomości i odpowiada na komendy.

Dostępne komendy:
  /stats          – statystyki ROI kuponów
  /balance        – status finansowy (P&L)
  /setbalance X   – ustaw punkt startowy (np. /setbalance -1500)
  /stake X        – zaloguj wpłatę na zakłady (np. /stake 100)
  /payout X       – zaloguj wypłatę (np. /payout 500)
  /result         – zaloguj wynik kuponu interaktywnie
  /help           – lista komend
"""
import json
import logging
import os
from datetime import datetime, timezone
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
from notify.telegram import _send, send_stats

log = logging.getLogger(__name__)

OFFSET_FILE = f"{DATA_RESULTS}/tg_offset.json"
API_BASE    = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


# ── Telegram helpers ──────────────────────────────────────────────────────────

def _get_updates(offset: int = 0) -> list:
    """Pobiera nowe wiadomości od ostatniego offset."""
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
    if Path(OFFSET_FILE).exists():
        with open(OFFSET_FILE) as f:
            return json.load(f).get("offset", 0)
    return 0


def _save_offset(offset: int) -> None:
    Path(DATA_RESULTS).mkdir(parents=True, exist_ok=True)
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset, "updated": datetime.now().isoformat()}, f)


def _reply(text: str) -> None:
    """Wysyła odpowiedź (alias _send z notify.telegram)."""
    _send(text)


# ── Obsługa komend ────────────────────────────────────────────────────────────

def _cmd_help() -> None:
    _reply(
        "🤖 <b>AI Betting Bot – Komendy</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📊 Statystyki:</b>\n"
        "  /stats         – ROI i historia kuponów\n"
        "  /balance       – pełny status finansowy\n\n"
        "<b>💰 Finanse:</b>\n"
        "  /setbalance X  – ustaw punkt startowy\n"
        "                   np. /setbalance -1500\n"
        "  /stake X       – zaloguj wpłatę na zakłady\n"
        "                   np. /stake 100\n"
        "  /payout X      – zaloguj wypłatę wygranej\n"
        "                   np. /payout 500\n\n"
        "<b>🎯 Wyniki kuponów:</b>\n"
        "  /won X         – kupon wygrany, wyciągnąłem X PLN\n"
        "                   np. /won 350\n"
        "  /lost          – kupon przegrany (0 PLN zwrotu)\n\n"
        "<b>ℹ️ Inne:</b>\n"
        "  /help          – ta wiadomość"
    )


def _cmd_stats() -> None:
    from model.evaluate import update_coupon_results
    stats = update_coupon_results()
    send_stats(stats)


def _cmd_balance() -> None:
    s = get_summary()
    _reply(format_summary_message(s))


def _cmd_setbalance(args: str) -> None:
    try:
        amount = float(args.strip().replace(",", "."))
        s = set_initial_balance(amount)
        _reply(
            f"✅ Punkt startowy ustawiony: <b>{amount:+.0f} PLN</b>\n\n"
            + format_summary_message(s)
        )
    except ValueError:
        _reply("❌ Podaj liczbę, np. <code>/setbalance -1500</code>")


def _cmd_stake(args: str) -> None:
    try:
        amount = float(args.strip().replace(",", "."))
        if amount <= 0:
            _reply("❌ Kwota musi być większa niż 0.")
            return
        add_stake(amount)
        s = get_summary()
        _reply(
            f"✅ Zalogowano wpłatę: <b>-{amount:.0f} PLN</b>\n\n"
            + format_summary_message(s)
        )
    except ValueError:
        _reply("❌ Podaj kwotę, np. <code>/stake 100</code>")


def _cmd_payout(args: str) -> None:
    try:
        amount = float(args.strip().replace(",", "."))
        if amount < 0:
            _reply("❌ Kwota wypłaty nie może być ujemna.")
            return
        add_payout(amount)
        s = get_summary()
        _reply(
            f"✅ Zalogowano wypłatę: <b>+{amount:.0f} PLN</b>\n\n"
            + format_summary_message(s)
        )
    except ValueError:
        _reply("❌ Podaj kwotę, np. <code>/payout 500</code>")


def _cmd_won(args: str) -> None:
    """Kupon wygrany – pyta o kwotę jeśli nie podana."""
    try:
        amount = float(args.strip().replace(",", "."))
        add_payout(amount, note="Wygrana z kuponu")
        s = get_summary()
        _reply(
            f"🏆 Kupon wygrany! Wypłata: <b>+{amount:.0f} PLN</b>\n\n"
            + format_summary_message(s)
        )
    except ValueError:
        _reply(
            "❓ Podaj kwotę wygranej:\n"
            "Np. <code>/won 350</code> jeśli wyciągnąłeś 350 PLN"
        )


def _cmd_lost() -> None:
    """Kupon przegrany – tylko informacja, stawka już zalogowana przez /stake."""
    s = get_summary()
    _reply(
        "😔 Kupon przegrany. Stawka już była zalogowana.\n\n"
        + format_summary_message(s)
    )


# ── Dispatcher ────────────────────────────────────────────────────────────────

def _dispatch(text: str) -> None:
    """Parsuje i wykonuje komendę."""
    text = text.strip()
    if not text.startswith("/"):
        _reply(
            "ℹ️ Używaj komend zaczynających się od /\n"
            "Wpisz /help żeby zobaczyć listę komend."
        )
        return

    parts = text.split(None, 1)
    cmd   = parts[0].lower().split("@")[0]  # usuń @botname jeśli dodane
    args  = parts[1] if len(parts) > 1 else ""

    handlers = {
        "/help":       lambda: _cmd_help(),
        "/stats":      lambda: _cmd_stats(),
        "/balance":    lambda: _cmd_balance(),
        "/setbalance": lambda: _cmd_setbalance(args),
        "/stake":      lambda: _cmd_stake(args),
        "/payout":     lambda: _cmd_payout(args),
        "/won":        lambda: _cmd_won(args),
        "/lost":       lambda: _cmd_lost(),
        "/start":      lambda: _cmd_help(),
    }

    handler = handlers.get(cmd)
    if handler:
        handler()
    else:
        _reply(
            f"❓ Nieznana komenda: <code>{cmd}</code>\n"
            "Wpisz /help żeby zobaczyć dostępne komendy."
        )


# ── Główna pętla pollingu ─────────────────────────────────────────────────────

def poll_and_respond() -> int:
    """
    Sprawdza nowe wiadomości i odpowiada na komendy.
    Zwraca liczbę przetworzonych wiadomości.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Brak TELEGRAM_TOKEN lub TELEGRAM_CHAT_ID – bot wyłączony.")
        return 0

    offset   = _load_offset()
    updates  = _get_updates(offset)
    processed = 0

    for update in updates:
        update_id = update.get("update_id", 0)
        offset = update_id + 1  # przesuń offset żeby nie przetwarzać ponownie

        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text    = message.get("text", "")

        # Odpowiadaj tylko na wiadomości z autoryzowanego chatu
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
