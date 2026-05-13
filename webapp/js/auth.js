/**
 * auth.js — Supabase Auth (email + hasło)
 * Zarządza sesją, pokazuje/ukrywa overlay logowania.
 */
const Auth = (() => {
  let _user = null;
  const _callbacks = [];

  // ── Inicjalizacja ─────────────────────────────────────────────────────────
  async function init() {
    const { data: { session } } = await _sb.auth.getSession();
    if (session?.user) {
      _user = session.user;
      _setAppVisible(true);
    } else {
      _setAppVisible(false);
    }

    // _sessionRestored = true po pierwszym getSession → onAuthStateChange
    // wie czy to odtworzenie sesji (nie wolać callbacków) czy nowe logowanie.
    let _sessionRestored = !!session;

    _sb.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_IN' && session?.user) {
        _user = session.user;
        _setAppVisible(true);
        // Wywołaj callbacki TYLKO przy nowym logowaniu, nie przy odtworzeniu sesji
        if (!_sessionRestored) {
          _callbacks.forEach(cb => cb(_user));
        }
        _sessionRestored = false; // reset — kolejne SIGNED_IN to już nowe logowanie
      } else if (event === 'SIGNED_OUT') {
        _user = null;
        _sessionRestored = false;
        _setAppVisible(false);
      }
    });
  }

  // ── Publiczne API ─────────────────────────────────────────────────────────
  function getUser()    { return _user; }
  function isLoggedIn() { return !!_user; }
  function onLogin(cb)  { _callbacks.push(cb); }

  async function signIn(email, password) {
    const { error } = await _sb.auth.signInWithPassword({ email, password });
    if (error) throw new Error(_translateError(error.message));
  }

  async function signUp(email, password) {
    const { error } = await _sb.auth.signUp({ email, password });
    if (error) throw new Error(_translateError(error.message));
  }

  async function signOut() {
    await _sb.auth.signOut();
  }

  // ── DOM helpers ───────────────────────────────────────────────────────────
  function _setAppVisible(visible) {
    const authEl = document.getElementById('auth-overlay');
    const appEl  = document.getElementById('main-app');
    if (!authEl || !appEl) return;
    authEl.style.display = visible ? 'none'  : 'flex';
    appEl.style.display  = visible ? 'block' : 'none';

    // Aktualizuj email w headerze
    const userEl = document.getElementById('header-user-email');
    if (userEl && _user) userEl.textContent = _user.email;
  }

  function _translateError(msg) {
    const map = {
      'Invalid login credentials': 'Nieprawidłowy email lub hasło.',
      'Email not confirmed': 'Potwierdź email przed zalogowaniem.',
      'User already registered': 'Ten adres email jest już zarejestrowany.',
      'Password should be at least 6 characters': 'Hasło musi mieć co najmniej 6 znaków.',
    };
    return map[msg] || msg;
  }

  // ── Event listeners (wywoływane po DOMContentLoaded) ─────────────────────
  function _bindEvents() {
    const emailEl    = document.getElementById('auth-email');
    const passwordEl = document.getElementById('auth-password');
    const errEl      = document.getElementById('auth-error');
    const loginBtn   = document.getElementById('btn-auth-login');
    const signupBtn  = document.getElementById('btn-auth-signup');
    const logoutBtn  = document.getElementById('btn-logout');

    // Enter → login
    [emailEl, passwordEl].forEach(el => el?.addEventListener('keydown', e => {
      if (e.key === 'Enter') loginBtn?.click();
    }));

    loginBtn?.addEventListener('click', async () => {
      const email = emailEl?.value.trim();
      const pass  = passwordEl?.value;
      if (!email || !pass) { _showError('Uzupełnij email i hasło.'); return; }
      _setAuthLoading(true);
      try {
        if (errEl) errEl.textContent = '';
        await signIn(email, pass);
      } catch (e) {
        _showError(e.message);
        _setAuthLoading(false);
      }
    });

    signupBtn?.addEventListener('click', async () => {
      const email = emailEl?.value.trim();
      const pass  = passwordEl?.value;
      if (!email || !pass) { _showError('Uzupełnij email i hasło.'); return; }
      if (pass.length < 6)  { _showError('Hasło musi mieć co najmniej 6 znaków.'); return; }
      _setAuthLoading(true);
      try {
        if (errEl) errEl.textContent = '';
        await signUp(email, pass);
        if (errEl) {
          errEl.className   = 'auth-success';
          errEl.textContent = '✅ Sprawdź email, by potwierdzić rejestrację!';
        }
      } catch (e) {
        _showError(e.message);
      } finally {
        _setAuthLoading(false);
      }
    });

    logoutBtn?.addEventListener('click', () => signOut());

    // Tab toggle login/signup
    document.querySelectorAll('.auth-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.auth-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const mode = btn.dataset.mode;
        document.getElementById('btn-auth-login').style.display  = mode === 'login'  ? '' : 'none';
        document.getElementById('btn-auth-signup').style.display = mode === 'signup' ? '' : 'none';
        if (errEl) errEl.textContent = '';
      });
    });
  }

  function _showError(msg) {
    const errEl = document.getElementById('auth-error');
    if (errEl) { errEl.className = 'auth-error'; errEl.textContent = msg; }
  }

  function _setAuthLoading(on) {
    const loginBtn  = document.getElementById('btn-auth-login');
    const signupBtn = document.getElementById('btn-auth-signup');
    if (loginBtn)  { loginBtn.disabled  = on; if (!on) loginBtn.textContent  = 'Zaloguj się'; }
    if (signupBtn) { signupBtn.disabled = on; if (!on) signupBtn.textContent = 'Zarejestruj się'; }
    if (on) {
      const active = document.querySelector('.auth-tab-btn.active')?.dataset.mode;
      if (active === 'login'  && loginBtn)  loginBtn.textContent  = 'Logowanie...';
      if (active === 'signup' && signupBtn) signupBtn.textContent = 'Rejestracja...';
    }
  }

  document.addEventListener('DOMContentLoaded', _bindEvents);

  return { init, getUser, isLoggedIn, onLogin, signOut };
})();
