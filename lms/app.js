/* ===========================================================================
 * lms/app.js
 * ===========================================================================
 *
 * The part that makes the site behave like an installed app.
 *
 * Three jobs, all optional, all silent when unavailable:
 *
 *   1. Register the service worker at the site root, so pages a reader has
 *      already opened keep opening without a connection.
 *   2. Offer installation to a home screen when the browser says it is
 *      possible, and stay out of the way otherwise. Chrome and Edge fire
 *      `beforeinstallprompt`; Safari does not, and installs through the Share
 *      menu instead, which is why an iPhone gets a sentence rather than a
 *      button.
 *   3. Say something when the reader goes offline, and when they come back.
 *      A page that silently fails to load a chapter is worse than a page that
 *      says the connection went.
 *
 * Everything here is progressive. No service worker support, an insecure
 * origin, a browser with the feature disabled: the site is exactly what it
 * was before, a static book.
 * =========================================================================== */

(function () {
  'use strict';

  var LANG = (document.documentElement.lang || 'en').slice(0, 2) === 'id' ? 'id' : 'en';

  var T = {
    en: {
      install: 'Install as an app',
      installShort: 'Install',
      otherLang: 'ID', otherLangTitle: 'Baca dalam Bahasa Indonesia',
      installed: 'Installed. It opens from your home screen now.',
      iosHint: 'On iPhone and iPad: Share, then Add to Home Screen.',
      offline: 'You are offline. Chapters you have already opened still work.',
      backOnline: 'Back online.',
      updated: 'A new version of the book is available.',
      reload: 'Reload'
    },
    id: {
      install: 'Pasang sebagai aplikasi',
      installShort: 'Pasang',
      otherLang: 'EN', otherLangTitle: 'Read in English',
      installed: 'Terpasang. Sekarang bisa dibuka dari layar utama Anda.',
      iosHint: 'Di iPhone dan iPad: Bagikan, lalu Tambahkan ke Layar Utama.',
      offline: 'Anda sedang luring. Bab yang sudah pernah dibuka tetap bisa dibaca.',
      backOnline: 'Kembali daring.',
      updated: 'Tersedia versi baru dari buku ini.',
      reload: 'Muat ulang'
    }
  }[LANG];

  /* ------------------------------------------------------------------ */
  /* Where the site root is                                              */
  /* ------------------------------------------------------------------ */

  // The books live one directory below the root, the landing page at it, and
  // the whole site may itself sit under a repository name on GitHub Pages.
  // The service worker has to be registered from the root for its scope to
  // cover both editions, so the depth is worked out from the path rather
  // than assumed.
  function rootPath() {
    var path = location.pathname;
    var m = path.match(/\/(en|id)\/[^/]*$/);
    if (m) return path.slice(0, m.index + 1);
    return path.replace(/[^/]*$/, '');
  }

  /* ------------------------------------------------------------------ */
  /* A small bar, used for all three messages                            */
  /* ------------------------------------------------------------------ */

  var bar = null;

  function notice(message, action) {
    dismiss();

    bar = document.createElement('div');
    bar.className = 'lms-appbar';
    bar.setAttribute('role', 'status');

    var text = document.createElement('span');
    text.className = 'lms-appbar-text';
    text.textContent = message;
    bar.appendChild(text);

    if (action) {
      var btn = document.createElement('button');
      btn.className = 'lms-appbar-btn';
      btn.type = 'button';
      btn.textContent = action.label;
      btn.addEventListener('click', function () { action.onClick(); });
      bar.appendChild(btn);
    }

    var close = document.createElement('button');
    close.className = 'lms-appbar-close';
    close.type = 'button';
    close.setAttribute('aria-label', 'Close');
    close.textContent = '×';
    close.addEventListener('click', dismiss);
    bar.appendChild(close);

    document.body.appendChild(bar);
    return bar;
  }

  function dismiss() {
    if (bar && bar.parentNode) bar.parentNode.removeChild(bar);
    bar = null;
  }

  /* ------------------------------------------------------------------ */
  /* 1. Service worker                                                   */
  /* ------------------------------------------------------------------ */

  function registerWorker() {
    if (!('serviceWorker' in navigator)) return;
    // A worker needs a secure context. localhost counts, which is what makes
    // local testing possible; a file:// preview does not, and that is fine.
    if (location.protocol !== 'https:' && location.hostname !== 'localhost'
        && location.hostname !== '127.0.0.1') return;

    var root = rootPath();

    navigator.serviceWorker.register(root + 'sw.js', { scope: root })
      .then(function (reg) {
        // An update found while the page is open means the reader is holding
        // a stale copy. Offer the reload rather than forcing it: nobody
        // wants a page to jump while they are reading it.
        reg.addEventListener('updatefound', function () {
          var installing = reg.installing;
          if (!installing) return;
          installing.addEventListener('statechange', function () {
            if (installing.state === 'installed' && navigator.serviceWorker.controller) {
              notice(T.updated, {
                label: T.reload,
                onClick: function () {
                  if (reg.waiting) reg.waiting.postMessage('skip-waiting');
                  location.reload();
                }
              });
            }
          });
        });
      })
      .catch(function (err) {
        console.warn('service worker not registered:', err);
      });
  }

  /* ------------------------------------------------------------------ */
  /* 2. Installation                                                     */
  /* ------------------------------------------------------------------ */

  /* One small group of buttons right after the book title, outside the
     collapsible menu, so the header stays a single row on a phone:
     [title] [ID|EN] [Install]. */
  function headerTools() {
    var tools = document.getElementById('book-tools');
    if (tools) return tools;
    var brand = document.querySelector('#quarto-header .navbar-brand-container') ||
                document.querySelector('#quarto-header .navbar-brand');
    if (!brand) return null;
    tools = document.createElement('div');
    tools.id = 'book-tools';
    tools.className = 'book-tools';
    brand.insertAdjacentElement('afterend', tools);

    // Language: the same page in the other edition (both use the same file names).
    var path = location.pathname;
    var other = path.indexOf('/id/') > -1 ? path.replace('/id/', '/en/')
              : path.indexOf('/en/') > -1 ? path.replace('/en/', '/id/') : null;
    if (other) {
      var a = document.createElement('a');
      a.className = 'book-tool book-lang';
      a.href = other + location.hash;
      a.textContent = T.otherLang;
      a.title = T.otherLangTitle;
      a.setAttribute('aria-label', T.otherLangTitle);
      tools.appendChild(a);
    }
    return tools;
  }

  function wireInstall() {
    var slot = document.getElementById('lms-install');
    // Inside the book there is no slot in the page body: put a compact one in
    // the header tools, next to the language button, so it is on every page.
    if (!slot) {
      var tools = headerTools();
      slot = document.createElement('span');
      slot.id = 'lms-install';
      slot.className = tools ? 'book-install' : 'lms-install-float';
      slot.hidden = true;
      (tools || document.body).appendChild(slot);
    }
    var compact = slot.className === 'book-install';
    // Remember the edition the reader chose, so the site root opens it next time.
    try {
      var here = location.pathname.indexOf('/id/') > -1 ? 'id' : 'en';
      localStorage.setItem('book-lang', here);
    } catch (e) {}
    var standalone = window.matchMedia('(display-mode: standalone)').matches ||
                     navigator.standalone === true;

    // Already installed: there is nothing to offer.
    if (standalone) {
      if (slot) slot.hidden = true;
      return;
    }

    var prompt = null;

    window.addEventListener('beforeinstallprompt', function (e) {
      // Keeping the event is what lets the offer appear where it belongs
      // rather than as the browser's own bar at the top of the page.
      e.preventDefault();
      prompt = e;

      if (!slot) return;
      slot.hidden = false;
      slot.innerHTML = '';

      var btn = document.createElement('button');
      btn.className = compact ? 'book-tool' : 'lms-install-btn';
      btn.type = 'button';
      btn.textContent = compact ? T.installShort : T.install;
      btn.title = T.install;
      btn.addEventListener('click', function () {
        if (!prompt) return;
        prompt.prompt();
        prompt.userChoice.then(function (choice) {
          if (choice.outcome === 'accepted') slot.hidden = true;
          prompt = null;
        }).catch(function () { prompt = null; });
      });
      slot.appendChild(btn);
    });

    window.addEventListener('appinstalled', function () {
      if (slot) slot.hidden = true;
      notice(T.installed);
    });

    // iOS never fires the event, so the slot gets the instruction instead of
    // a button that cannot work.
    var iOS = /iP(hone|ad|od)/.test(navigator.platform || '') ||
              (/Mac/.test(navigator.platform || '') && navigator.maxTouchPoints > 1);
    if (slot && iOS) {
      slot.hidden = false;
      if (compact) {
        // No room for a sentence in the header: the button shows the hint.
        slot.innerHTML = '';
        var hint = document.createElement('button');
        hint.className = 'book-tool';
        hint.type = 'button';
        hint.textContent = T.installShort;
        hint.title = T.iosHint;
        hint.addEventListener('click', function () { notice(T.iosHint); });
        slot.appendChild(hint);
      } else {
        slot.innerHTML = '<span class="lms-install-hint"></span>';
        slot.querySelector('.lms-install-hint').textContent = T.iosHint;
      }
    }
  }

  /* ------------------------------------------------------------------ */
  /* 3. Connection                                                       */
  /* ------------------------------------------------------------------ */

  function wireConnection() {
    window.addEventListener('offline', function () { notice(T.offline); });
    window.addEventListener('online', function () {
      notice(T.backOnline);
      setTimeout(dismiss, 2600);
    });
  }

  function start() {
    try { registerWorker(); } catch (e) { console.warn('app: worker', e); }
    try { wireInstall(); } catch (e) { console.warn('app: install', e); }
    try { wireConnection(); } catch (e) { console.warn('app: connection', e); }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
