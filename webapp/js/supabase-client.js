/**
 * supabase-client.js
 * Singleton klienta Supabase.
 * __SUPABASE_URL__ i __SUPABASE_ANON_KEY__ są podmieniane przez static.yml
 * podczas deploymentu GitHub Pages (sed z GitHub Secrets).
 *
 * Lokalny development: podstaw wartości ręcznie poniżej lub ustaw
 * zmienne w pliku .env i zbuduj lokalnie (nie commituj kluczy!).
 */
const SUPABASE_URL      = '__SUPABASE_URL__';
const SUPABASE_ANON_KEY = '__SUPABASE_ANON_KEY__';

const _isPlaceholder = (v) => !v || v.startsWith('__');

let _sb;

if (_isPlaceholder(SUPABASE_URL) || _isPlaceholder(SUPABASE_ANON_KEY)) {
  // Klucze nie zostały wstrzyknięte — tryb bez backendu (tylko GitHub read-only)
  console.error(
    '[Supabase] Brak konfiguracji! Uruchom deploy przez GitHub Actions\n' +
    'z ustawionymi Secrets: SUPABASE_URL i SUPABASE_ANON_KEY.\n' +
    'Logowanie i zapis finansów będą niedostępne.'
  );
  // Stub — zapobiega crashowi przy próbie użycia _sb przed inicjalizacją
  _sb = {
    auth: {
      getSession:         () => Promise.resolve({ data: { session: null } }),
      onAuthStateChange:  () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      signInWithPassword: () => Promise.resolve({ error: { message: 'Supabase nie skonfigurowany' } }),
      signUp:             () => Promise.resolve({ error: { message: 'Supabase nie skonfigurowany' } }),
      signOut:            () => Promise.resolve({}),
    },
    from: () => {
      // Fluent stub — każda metoda zwraca obiekt z kolejnymi metodami łańcucha
      const _stub = {
        select:     () => _stub,
        eq:         () => _stub,
        order:      () => _stub,           // potrzebne przez _loadTransactions
        in:         () => _stub,
        maybeSingle: () => Promise.resolve({ data: null, error: null }),
        single:      () => Promise.resolve({ data: null, error: { message: 'Supabase nie skonfigurowany' } }),
        delete:      () => _stub,
        insert:      () => _stub,
        upsert:      () => Promise.resolve({ error: { message: 'Supabase nie skonfigurowany' } }),
        // Thenable — pozwala użyć await bezpośrednio na chainach bez terminatora
        then: (resolve) => resolve({ data: [], error: null }),
      };
      return _stub;
    },
  };
} else {
  _sb = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
      persistSession:     true,
      autoRefreshToken:   true,
      detectSessionInUrl: true,
    }
  });
}
