(() => {
  'use strict';
  const auth = document.querySelector('.auth');
  if (!auth) return;
  const panes = Object.fromEntries([...auth.querySelectorAll('[data-pane]')].map(p => [p.dataset.pane, p]));
  const links = [...auth.querySelectorAll('[data-auth-mode]')];
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let busy = false;
  let coverTimer, finishTimer;
  function apply(mode, focus) {
    for (const [key, pane] of Object.entries(panes)) {
      pane.hidden = key !== mode;
      pane.inert = key !== mode;
    }
    auth.dataset.mode = mode;
    links.forEach(link => {
      if (link.dataset.authMode === mode) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    document.title = (mode === 'login' ? 'Connexion' : (auth.dataset.beta === 'true' ? 'Activer mon invitation' : 'Créer un compte')) + ' — FlowFix';
    if (focus) panes[mode].querySelector('h2').focus({preventScroll: true});
  }
  function finish() {
    auth.classList.remove('is-switching');
    busy = false;
  }
  function switchTo(mode, push = true) {
    if (busy || !panes[mode] || mode === auth.dataset.mode) return;
    busy = true;
    // Native form actions and links remain functional without JavaScript.
    if (push) history.pushState(null, '', '/' + mode + '/' + location.search);
    if (reduced.matches) { apply(mode, true); finish(); return; }
    auth.classList.add('is-switching');
    coverTimer = window.setTimeout(() => apply(mode, true), 430);
    finishTimer = window.setTimeout(finish, 980);
  }
  links.forEach(link => link.addEventListener('click', event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (link.dataset.authMode === 'signup' && auth.dataset.beta === 'true') return;
    event.preventDefault();
    switchTo(link.dataset.authMode);
  }));
  window.addEventListener('popstate', () => {
    clearTimeout(coverTimer); clearTimeout(finishTimer); finish();
    apply(['/signup/', '/beta/'].includes(location.pathname) ? 'signup' : 'login', true);
  });
  document.querySelectorAll('[data-password]').forEach(button => button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.password);
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    button.setAttribute('aria-pressed', String(show));
    button.setAttribute('aria-label', show ? 'Masquer le mot de passe' : 'Afficher le mot de passe');
  }));
  document.querySelectorAll('.auth form').forEach(form => form.addEventListener('submit', () => {
    const button = form.querySelector('[type="submit"]');
    button.disabled = true;
    button.textContent = 'Un instant…';
  }));
  window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
})();
