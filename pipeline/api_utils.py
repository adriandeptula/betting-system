"""
pipeline/api_utils.py – Narzędzia pomocnicze dla wywołań API.

Kluczowa funkcja: api_get() obsługuje listę kluczy API i automatycznie
przełącza się na kolejny klucz gdy bieżący wyczerpie limit requestów
(HTTP 401, 402, 429) lub zwróci błąd.

Użycie:
    from pipeline.api_utils import api_get

    data, used_key = api_get(
        url="https://api.example.com/endpoint",
        keys=config.ODDS_API_KEYS,
        params={"param": "value"},
        key_param="apiKey",           # nazwa parametru URL z kluczem
        key_header=None,              # lub nazwa nagłówka HTTP z kluczem
    )
"""
import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

# Kody HTTP które oznaczają wyczerpanie limitu – przełącz na kolejny klucz
_QUOTA_ERRORS = {401, 402, 403, 429}


def api_get(
    url: str,
    keys: list[str],
    params: dict | None = None,
    headers: dict | None = None,
    key_param: str | None = None,
    key_header: str | None = None,
    timeout: int = 30,
    retry_wait: float = 2.0,
) -> tuple[Any, str]:
    """
    Wykonuje GET request próbując kolejno każdy klucz z listy `keys`.

    Parametry
    ---------
    url         : docelowy endpoint
    keys        : lista kluczy API (kolejność = priorytet)
    params      : query-string parametry (bez klucza)
    headers     : nagłówki HTTP (bez klucza)
    key_param   : jeśli klucz idzie jako query-param, podaj jego nazwę
    key_header  : jeśli klucz idzie jako nagłówek HTTP, podaj jego nazwę
    timeout     : timeout requestu w sekundach
    retry_wait  : pauza między próbami w sekundach

    Zwraca
    ------
    (json_data, użyty_klucz)  – przy sukcesie
    Rzuca RuntimeError         – gdy wszystkie klucze się wyczerpały
    """
    if not keys:
        raise RuntimeError(
            "Brak kluczy API. Sprawdź GitHub Secrets (ODDS_API_KEY / API_FOOTBALL_KEY)."
        )

    params  = dict(params or {})
    headers = dict(headers or {})
    last_error: str = ""

    for idx, key in enumerate(keys, start=1):
        # Wstaw klucz do odpowiedniego miejsca
        req_params  = {**params,  **(({key_param:  key} if key_param  else {}))}
        req_headers = {**headers, **(({key_header: key} if key_header else {}))}

        try:
            resp = requests.get(
                url,
                params=req_params,
                headers=req_headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            log.warning(f"[api_utils] Klucz #{idx}: błąd sieci – {exc}")
            time.sleep(retry_wait)
            continue

        if resp.status_code == 200:
            # The Odds API:  x-requests-remaining
            # api-sports.io: x-ratelimit-requests-remaining
            remaining = (
                resp.headers.get("x-requests-remaining")
                or resp.headers.get("x-ratelimit-requests-remaining")
                or "?"
            )
            log.info(f"[api_utils] Klucz #{idx} OK (pozostało requestów: {remaining})")
            return resp.json(), key

        if resp.status_code in _QUOTA_ERRORS:
            log.warning(
                f"[api_utils] Klucz #{idx} wyczerpany lub nieautoryzowany "
                f"(HTTP {resp.status_code}). "
                f"{'Próbuję klucz #' + str(idx+1) + '...' if idx < len(keys) else 'To był ostatni klucz.'}"
            )
            last_error = f"HTTP {resp.status_code}"
            time.sleep(retry_wait)
            continue

        # Inny błąd HTTP – nie próbuj kolejnego klucza, od razu zgłoś
        resp.raise_for_status()

    raise RuntimeError(
        f"Wszystkie {len(keys)} klucze API wyczerpane lub błędne. "
        f"Ostatni błąd: {last_error}. "
        f"Sprawdź limity kont lub dodaj ODDS_API_KEY_2 / API_FOOTBALL_KEY_2 w GitHub Secrets."
    )
