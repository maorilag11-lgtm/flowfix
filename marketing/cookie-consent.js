/* ============================================================================
   Bandeau cookies FlowFix.
   Un seul fichier a inclure sur chaque page : il pose son propre style et son
   propre balisage, aux couleurs du site.

   - rien n'est depose tant que la personne n'a pas choisi
   - refuser est aussi simple qu'accepter (meme rang, meme visibilite)
   - le choix est garde 13 mois puis redemande
   - un lien "Cookie settings" est ajoute tout seul dans la colonne Legal du
     pied de page, pour revenir sur son choix a tout moment

   Pour brancher un outil de mesure plus tard :
     window.addEventListener('flowfix:consent', function (e) {
       if (e.detail.analytics) { // charger le script ici
       }
     });
   ========================================================================== */
(function () {
  'use strict';

  var KEY = 'flowfix.consent.v1';
  var MAX_AGE = 13 * 30 * 24 * 3600 * 1000;   /* 13 mois, duree de reference CNIL */
  var CATS = [
    { id: 'essential', name: 'Strictly necessary',
      desc: 'Keeps you signed in and remembers this very choice. The site cannot work without them.',
      locked: true },
    { id: 'analytics', name: 'Analytics',
      desc: 'Anonymous page counts, so we know which docs pages actually get read.' },
    { id: 'marketing', name: 'Marketing',
      desc: 'Measures which campaign brought you here. Off by default.' }
  ];

  function read() {
    try {
      var v = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (!v || typeof v !== 'object' || !v.ts) return null;
      if (Date.now() - v.ts > MAX_AGE) return null;
      return v;
    } catch (e) { return null; }
  }
  function write(v) {
    v.ts = Date.now();
    try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) {}
    window.dispatchEvent(new CustomEvent('flowfix:consent', { detail: v }));
    return v;
  }

  var CSS = [
    '.ck-root{position:fixed;left:0;bottom:0;z-index:2147483000;display:flex;justify-content:flex-start;',
    ' padding:20px;pointer-events:none;font-family:"Source Sans 3","Segoe UI",system-ui,sans-serif;}',
    '.ck-card{position:relative;pointer-events:auto;box-sizing:border-box;width:min(436px,calc(100vw - 40px));',
    ' max-height:calc(100vh - 40px);overflow:auto;',
    ' padding:20px 20px 18px;border-radius:16px;background:#0B0715;border:1px solid rgba(255,255,255,.14);',
    ' box-shadow:inset 0 1.5px 0 rgba(255,255,255,.16),inset 0 -1.5px 1px rgba(0,0,0,.7),',
    '            0 26px 60px -24px rgba(0,0,0,1),0 6px 16px -8px rgba(0,0,0,.9);',
    ' transform:translateY(16px) scale(.97);opacity:0;transition:transform .4s cubic-bezier(.18,.9,.28,1),opacity .3s ease;}',
    '.ck-root.on .ck-card{transform:none;opacity:1;}',
    '.ck-head{display:flex;align-items:center;gap:12px;margin-bottom:10px;}',
    '.ck-img{width:44px;height:44px;flex-shrink:0;display:block;',
    ' filter:drop-shadow(0 6px 14px rgba(124,77,245,.45));}',
    '.ck-t{margin:0;font-family:Montserrat,"Segoe UI",system-ui,sans-serif;font-size:15.5px;font-weight:600;',
    ' letter-spacing:-.018em;color:#FFFFFF;}',
    '.ck-p{margin:0;font-size:13.5px;line-height:1.55;color:#A9A3BD;}',
    '.ck-p a{color:#9A8CFF;text-decoration:none;}.ck-p a:hover{text-decoration:underline;}',
    '.ck-acts{display:flex;flex-wrap:wrap;align-items:center;gap:9px;margin-top:16px;}',
    '.ck-b{flex:1 1 auto;min-height:40px;padding:10px 16px;border-radius:99px;cursor:pointer;',
    ' font-family:inherit;font-size:13.5px;font-weight:500;letter-spacing:-.005em;transition:filter .2s ease,background .2s ease;}',
    '.ck-b:active{transform:scale(.985);}',
    '.ck-b-y{border:none;color:#FFFFFF;background:linear-gradient(135deg,#7C4DF5,#5B45F0);',
    ' box-shadow:0 10px 26px -12px rgba(124,77,245,.95);}',
    '.ck-b-y:hover{filter:brightness(1.08);}',
    '.ck-b-n{color:#EDE9FF;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.14);}',
    '.ck-b-n:hover{background:rgba(255,255,255,.09);}',
    '.ck-b-s{flex:0 0 auto;padding:8px 4px;border:none;background:none;color:#8C85A6;font-size:13px;',
    ' text-decoration:underline;text-underline-offset:3px;cursor:pointer;font-family:inherit;}',
    '.ck-b-s:hover{color:#C6BFE4;}',
    '.ck-b:focus-visible,.ck-b-s:focus-visible,.ck-sw:focus-visible{outline:2px solid #A78BFA;outline-offset:2px;}',
    '.ck-prefs{margin-top:16px;padding-top:15px;border-top:1px solid rgba(255,255,255,.10);',
    ' display:flex;flex-direction:column;gap:14px;}',
    /* display:flex l'emporte sur le [hidden] du navigateur : il faut le dire ici */
    '.ck-prefs[hidden]{display:none;}',
    '.ck-row{display:flex;align-items:flex-start;gap:12px;}',
    '.ck-rc{flex:1 1 auto;min-width:0;}',
    '.ck-rn{display:block;font-size:13.5px;font-weight:500;color:#EDE9FF;}',
    '.ck-rd{display:block;margin-top:2px;font-size:12.5px;line-height:1.5;color:#8C85A6;}',
    '.ck-sw{position:relative;flex:0 0 auto;width:40px;height:23px;margin-top:2px;padding:0;border-radius:99px;',
    ' cursor:pointer;border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.06);',
    ' transition:background .22s ease,border-color .22s ease;}',
    '.ck-sw::after{content:"";position:absolute;top:2px;left:2px;width:17px;height:17px;border-radius:50%;',
    ' background:#8C85A6;transition:transform .22s cubic-bezier(.3,.9,.3,1),background .22s ease;}',
    '.ck-sw[aria-checked="true"]{background:linear-gradient(135deg,#7C4DF5,#5B45F0);border-color:transparent;}',
    '.ck-sw[aria-checked="true"]::after{transform:translateX(17px);background:#FFFFFF;}',
    '.ck-sw[disabled]{cursor:not-allowed;opacity:.55;}',
    '@media (max-width:560px){.ck-root{right:0;padding:12px;}.ck-card{width:100%;padding:17px 16px 15px;}',
    ' .ck-b{flex:1 1 100%;}.ck-b-s{flex:1 1 100%;text-align:center;}}',
    '@media (prefers-reduced-motion:reduce){.ck-root,.ck-card{transition:none;}.ck-card{transform:none;opacity:1;}',
    ' .ck-sw::after{transition:none;}}',
    '@media print{.ck-root{display:none;}}'
  ].join('');

  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }

  var root = null;

  /* Banniere de coin, pas fenetre modale : on ne vole ni le focus ni le
     defilement, la page reste utilisable pendant qu'on choisit. */
  function close() {
    if (!root) return;
    root.classList.remove('on');
    var n = root;
    root = null;
    setTimeout(function () { if (n.parentNode) n.parentNode.removeChild(n); }, 400);
  }

  function build(current) {
    if (root) return;
    if (!document.getElementById('ck-style')) {
      var st = el('style'); st.id = 'ck-style'; st.textContent = CSS;
      document.head.appendChild(st);
    }

    var state = {};
    CATS.forEach(function (c) {
      state[c.id] = c.locked ? true : !!(current && current[c.id]);
    });

    root = el('div', 'ck-root');
    var card = el('div', 'ck-card');
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-labelledby', 'ck-title');
    card.setAttribute('aria-describedby', 'ck-desc');

    var head = el('div', 'ck-head');
    var img = el('img', 'ck-img');
    img.src = 'cookie.png'; img.width = 44; img.height = 44; img.alt = '';
    img.setAttribute('aria-hidden', 'true');
    var title = el('h2', 'ck-t', 'Cookies on FlowFix'); title.id = 'ck-title';
    head.appendChild(img); head.appendChild(title);

    var desc = el('p', 'ck-p'); desc.id = 'ck-desc';
    desc.innerHTML = 'We only need the essential ones to run the site. Anything that measures how you ' +
      'use FlowFix stays off until you say yes. Details in the ' +
      '<a href="privacy.html">privacy notice</a>.';

    var acts = el('div', 'ck-acts');
    var yes = el('button', 'ck-b ck-b-y', 'Accept all');
    var no = el('button', 'ck-b ck-b-n', 'Essential only');
    var more = el('button', 'ck-b-s', 'Choose');
    yes.type = no.type = more.type = 'button';
    acts.appendChild(yes); acts.appendChild(no); acts.appendChild(more);

    /* le panneau de reglage, replie tant qu'on ne le demande pas */
    var prefs = el('div', 'ck-prefs'); prefs.hidden = true;
    CATS.forEach(function (c) {
      var row = el('div', 'ck-row');
      var box = el('div', 'ck-rc');
      box.appendChild(el('span', 'ck-rn', c.name));
      box.appendChild(el('span', 'ck-rd', c.desc));
      var sw = el('button', 'ck-sw');
      sw.type = 'button';
      sw.setAttribute('role', 'switch');
      sw.setAttribute('aria-checked', state[c.id] ? 'true' : 'false');
      sw.setAttribute('aria-label', c.name);
      if (c.locked) { sw.disabled = true; }
      else {
        sw.addEventListener('click', function () {
          state[c.id] = !state[c.id];
          sw.setAttribute('aria-checked', state[c.id] ? 'true' : 'false');
        });
      }
      row.appendChild(box); row.appendChild(sw);
      prefs.appendChild(row);
    });
    var save = el('button', 'ck-b ck-b-y', 'Save my choices');
    save.type = 'button';
    var saveWrap = el('div', 'ck-acts'); saveWrap.appendChild(save);
    prefs.appendChild(saveWrap);

    function decide(all) {
      var out = {};
      CATS.forEach(function (c) { out[c.id] = c.locked ? true : (all == null ? state[c.id] : all); });
      write(out);
      close();
    }
    yes.addEventListener('click', function () { decide(true); });
    no.addEventListener('click', function () { decide(false); });
    save.addEventListener('click', function () { decide(null); });
    more.addEventListener('click', function () {
      prefs.hidden = false;
      more.remove();
      prefs.querySelector('.ck-sw:not([disabled])').focus();
    });

    card.appendChild(head); card.appendChild(desc);
    card.appendChild(acts); card.appendChild(prefs);
    root.appendChild(card);
    document.body.appendChild(root);

    requestAnimationFrame(function () { root.classList.add('on'); });
  }

  /* Lien de retour : ajoute dans la colonne "Legal" du pied de page, sans
     toucher au HTML des pages. */
  function footerLink() {
    var labels = document.querySelectorAll('#foot .m');
    for (var i = 0; i < labels.length; i++) {
      if ((labels[i].textContent || '').trim().toLowerCase() !== 'legal') continue;
      var col = labels[i].parentElement;
      if (!col || col.querySelector('[data-cookie-settings]')) return;
      var a = el('button', null, 'Cookie settings');
      a.type = 'button';
      a.setAttribute('data-cookie-settings', '');
      a.style.cssText = 'padding:0;border:none;background:none;text-align:left;cursor:pointer;' +
        'font-family:inherit;font-size:13.5px;color:#9A9AA6;';
      a.addEventListener('mouseenter', function () { a.style.color = '#FFFFFF'; });
      a.addEventListener('mouseleave', function () { a.style.color = '#9A9AA6'; });
      col.appendChild(a);   /* le clic est branche juste apres, avec les autres */
      return;
    }
  }

  window.FlowFixConsent = {
    get: function () { return read(); },
    accepted: function (cat) { var v = read(); return !!(v && v[cat]); },
    open: function () { build(read()); },
    reset: function () { try { localStorage.removeItem(KEY); } catch (e) {} build(null); }
  };

  function init() {
    footerLink();
    /* tout element marque data-cookie-settings rouvre le panneau */
    document.querySelectorAll('[data-cookie-settings]').forEach(function (n) {
      n.addEventListener('click', function (e) { e.preventDefault(); build(read()); });
    });
    var saved = read();
    if (saved) { window.dispatchEvent(new CustomEvent('flowfix:consent', { detail: saved })); return; }
    build(null);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
