"""
main.py – Główny orkiestrator pipeline'u.
Uruchamiany przez GitHub Actions lub ręcznie.

Tryby użycia:
  python main.py fetch   – pobierz dane historyczne, aktualne kursy i kontuzje
  python main.py train   – trenuj/retrenuj model
  python main.py coupon  – generuj kupony i wyślij na Telegram
  python main.py stats   – oblicz i wyślij statystyki ROI
  python main.py bot     – sprawdź komendy Telegram i odpowiedz
  python main.py full    – fetch + train + coupon (pierwsze uruchomienie)
"""
import logging
import sys
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-25s %(levelname)s %(message)s",
)
log = logging.getLogger("main")


def run_fetch() -> None:
    log.info("══ FETCH: pobieranie danych ══════════════════════")
    from pipeline.fetch_stats import fetch_all_stats
    from pipeline.fetch_odds import fetch_all_odds
    from pipeline.fetch_injuries import fetch_all_injuries
    fetch_all_stats()
    fetch_all_odds()
    fetch_all_injuries()   # v1.1 – kontuzje (opcjonalne, nie blokuje przy braku klucza)


def run_train() -> None:
    log.info("══ TRAIN: trening modelu ═════════════════════════")
    from model.train import train_model
    train_model()


def run_coupon() -> None:
    log.info("══ COUPON: generowanie kuponów ═══════════════════")
    from model.predict import predict_matches
    from coupon.value_engine import find_value_bets
    from coupon.builder import build_coupons, save_coupons
    from notify.telegram import send_coupons, _send

    predictions = predict_matches()
    if not predictions:
        from notify.telegram import send_alert
        send_alert("Brak predykcji! Sprawdź: dane, kursy, model.")
        return

    value_bets = find_value_bets(predictions)
    coupons    = build_coupons(value_bets)
    save_coupons(coupons)
    send_coupons(coupons)

    if coupons:
        _send(
            "💸 <b>Zaloguj swoje zakłady:</b>\n\n"
            "Ile wpłaciłeś na powyższe kupony łącznie?\n\n"
            "  /stake 100  – wpłaciłem 100 PLN\n"
            "  /stake 0    – nie zagrałem nic tym razem\n\n"
            "<i>Możesz wpisać kilka komend osobno dla każdego kuponu.</i>"
        )


def run_stats() -> None:
    log.info("══ STATS: obliczanie ROI ═════════════════════════")
    from model.evaluate import update_coupon_results, get_pending_summary
    from notify.telegram import send_stats, _send
    from notify.finance import get_summary, format_summary_message

    stats = update_coupon_results()
    send_stats(stats)

    s = get_summary()
    if s["total_coupons"] > 0 or s["initial_balance"] != 0:
        pending = get_pending_summary()
        _send(format_summary_message(s, pending))

    _send(
        "🎯 <b>Czas rozliczenia!</b>\n\n"
        "Czy któryś z poprzednich kuponów wygrał?\n\n"
        "  /won 500   – wygrałem, wyciągnąłem 500 PLN\n"
        "  /lost      – kupon przegrał\n\n"
        "<i>Pomiń jeśli już rozliczyłeś wcześniej.</i>"
    )


def run_bot() -> None:
    log.info("══ BOT: polling Telegram ═════════════════════════")
    from notify.bot_handler import poll_and_respond
    n = poll_and_respond()
    log.info(f"Przetworzono {n} komend")


MODES = {
    "fetch":  run_fetch,
    "train":  run_train,
    "coupon": run_coupon,
    "stats":  run_stats,
    "bot":    run_bot,
    "full":   lambda: (run_fetch(), run_train(), run_coupon()),
}


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "coupon"

    if mode not in MODES:
        log.error(f"Nieznany tryb: '{mode}'. Dostępne: {list(MODES.keys())}")
        sys.exit(1)

    log.info(f"Tryb: {mode.upper()}")

    try:
        MODES[mode]()
        log.info(f"✓ Tryb '{mode}' zakończony sukcesem.")
    except Exception:
        error = traceback.format_exc()
        log.error(f"✗ BŁĄD w trybie '{mode}':\n{error}")
        try:
            from notify.telegram import send_alert
            send_alert(f"BŁĄD pipeline [{mode}]:\n{error[:1000]}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
