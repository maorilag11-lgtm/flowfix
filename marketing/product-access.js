(() => {
  'use strict';
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  let origin = window.FLOWFIX_PRODUCT_ORIGIN || (local ? 'http://127.0.0.1:8767' : '');
  try {
    const url = new URL(origin);
    if (url.username || url.password || url.pathname !== '/' || url.search || url.hash ||
        (url.protocol !== 'https:' && !(local && url.origin === 'http://127.0.0.1:8767'))) throw new Error('Invalid product origin');
    origin = url.origin;
  } catch {
    origin = '';
  }
  document.querySelectorAll('a[data-product-route]').forEach(link => {
    if (origin) link.href = origin + link.dataset.productRoute;
  });
  const start = document.querySelector('[data-product-start]');
  if (start) start.addEventListener('submit', event => {
    event.preventDefault();
    location.assign(origin ? origin + '/signup/' : 'login.html?mode=signup');
  });
  if (!document.body.hasAttribute('data-product-access')) return;
  const status = document.getElementById('access-status');
  const link = document.getElementById('product-login');
  if (!origin) {
    status.textContent = 'Product sign-in will be available once the app is online.';
    link.hidden = true;
    return;
  }
  const signup = new URLSearchParams(location.search).get('mode') === 'signup';
  link.href = origin + (signup ? '/signup/' : '/login/');
  link.hidden = false;
  status.textContent = 'Opening FlowFix sign-in…';
  location.replace(link.href);
})();
