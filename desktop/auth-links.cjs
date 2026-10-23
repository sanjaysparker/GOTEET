// Identity providers require a system browser, not an embedded web view.
function isAccountSignIn(url) {
  const parsed = new URL(url);
  return parsed.protocol === 'https:' && !parsed.username && !parsed.password && (
    parsed.hostname === 'accounts.google.com' ||
    (parsed.hostname === 'ynjspephbavvnsslscsl.supabase.co' && parsed.pathname === '/auth/v1/authorize')
  );
}
module.exports = { isAccountSignIn };
