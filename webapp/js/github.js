/**
 * github.js – GitHub Contents API integration
 * Reads and writes JSON files directly to the repository.
 */

const GitHub = (() => {
  const STORAGE_KEY = 'betting_gh_config';

  let _cfg = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');

  function configure(token, owner, repo, branch = 'main') {
    _cfg = { token, owner, repo, branch };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(_cfg));
  }

  function isConfigured() {
    return !!((_cfg.token && _cfg.owner && _cfg.repo));
  }

  function getConfig() {
    return { ..._cfg };
  }

  function _headers() {
    return {
      'Authorization': `token ${_cfg.token}`,
      'Accept': 'application/vnd.github.v3+json',
      'Content-Type': 'application/json',
    };
  }

  function _apiUrl(path) {
    return `https://api.github.com/repos/${_cfg.owner}/${_cfg.repo}/contents/${path}`;
  }

  /**
   * Load a file from the repo.
   * Returns { content: parsedObject, sha: string } or throws.
   */
  async function loadFile(path) {
    const url = `${_apiUrl(path)}?ref=${_cfg.branch || 'main'}&t=${Date.now()}`;
    const resp = await fetch(url, { headers: _headers() });

    if (resp.status === 404) {
      return { content: null, sha: null };
    }
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(`GitHub API error ${resp.status}: ${err.message || resp.statusText}`);
    }

    const data = await resp.json();
    const decoded = atob(data.content.replace(/\n/g, ''));
    const parsed = JSON.parse(decoded);
    return { content: parsed, sha: data.sha };
  }

  /**
   * Save a file to the repo via PUT.
   * content: JS object (will be JSON-stringified)
   * sha: current file sha (null for new files)
   */
  async function saveFile(path, content, commitMessage, sha) {
    const body = {
      message: commitMessage,
      content: btoa(unescape(encodeURIComponent(JSON.stringify(content, null, 2)))),
      branch: _cfg.branch || 'main',
    };
    if (sha) body.sha = sha;

    const resp = await fetch(_apiUrl(path), {
      method: 'PUT',
      headers: _headers(),
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(`GitHub save error ${resp.status}: ${err.message || resp.statusText}`);
    }

    const result = await resp.json();
    return result.content.sha; // new sha
  }

  /**
   * Test connection and permissions.
   */
  async function testConnection() {
    const resp = await fetch(`https://api.github.com/repos/${_cfg.owner}/${_cfg.repo}`, {
      headers: _headers(),
    });
    if (!resp.ok) throw new Error(`Nie można połączyć z repo: ${resp.status}`);
    const data = await resp.json();
    return { name: data.full_name, private: data.private };
  }

  return { configure, isConfigured, getConfig, loadFile, saveFile, testConnection };
})();
