/**
 * github.js — GitHub Contents API (READ-ONLY)
 * Odczytuje dane z repozytorium (coupons_history.json).
 * Zapis danych finansowych jest teraz w Supabase — brak 403.
 * Konfiguracja (token/repo) przechowywana w Supabase, nie localStorage.
 */
const GitHub = (() => {
  let _cfg = { owner: '', repo: '', branch: 'main', token: '' };

  function configure(owner, repo, branch, token) {
    _cfg = { owner, repo: repo || '', branch: branch || 'main', token: token || '' };
  }

  function isConfigured() {
    return !!((_cfg.owner && _cfg.repo && _cfg.token));
  }

  function getConfig() {
    return { ..._cfg };
  }

  function _headers() {
    return {
      'Authorization': `token ${_cfg.token}`,
      'Accept': 'application/vnd.github.v3+json',
    };
  }

  /**
   * Wczytuje plik z repo (JSON).
   * Zwraca { content: parsedObj, sha } lub { content: null, sha: null } gdy 404.
   */
  async function loadFile(path) {
    if (!isConfigured()) throw new Error('GitHub nie skonfigurowany. Uzupełnij ustawienia.');
    const url = `https://api.github.com/repos/${_cfg.owner}/${_cfg.repo}/contents/${path}?ref=${_cfg.branch}&t=${Date.now()}`;
    const resp = await fetch(url, { headers: _headers() });

    if (resp.status === 404) return { content: null, sha: null };
    if (resp.status === 401 || resp.status === 403) {
      throw new Error(`GitHub: Brak dostępu (${resp.status}). Sprawdź PAT token (scope: repo).`);
    }
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(`GitHub API ${resp.status}: ${err.message || resp.statusText}`);
    }

    const data    = await resp.json();
    const decoded = atob(data.content.replace(/\n/g, ''));
    const parsed  = JSON.parse(decoded);
    return { content: parsed, sha: data.sha };
  }

  /**
   * Testuje połączenie z repozytorium.
   */
  async function testConnection() {
    if (!isConfigured()) throw new Error('Uzupełnij dane repozytorium i token.');
    const resp = await fetch(
      `https://api.github.com/repos/${_cfg.owner}/${_cfg.repo}`,
      { headers: _headers() }
    );
    if (!resp.ok) throw new Error(`Nie można połączyć z repo: HTTP ${resp.status}`);
    const data = await resp.json();
    return { name: data.full_name, private: data.private, pushed_at: data.pushed_at };
  }

  return { configure, isConfigured, getConfig, loadFile, testConnection };
})();
