/* ===========================================================================
 * lms/visitors.js
 * ===========================================================================
 *
 * A reader counter for a site that cannot count.
 *
 * GitHub Pages serves files and runs none of our code, so there is nowhere to
 * keep a tally. This asks a third party counter, which holds integers and
 * nothing else, to increment and report two numbers:
 *
 *     total      every page of the book, both languages
 *     thisPage   the chapter being read
 *
 * Three rules shape the implementation.
 *
 *   It never blocks the page. The badge is appended when the numbers arrive,
 *   which is after the chapter has rendered, and if they never arrive the
 *   badge never appears.
 *
 *   It counts once per browser per configurable window. A reader reloading a
 *   chapter while working through a script is one reader.
 *
 *   It sends nothing about the reader. Two URLs are requested; no identifier,
 *   referrer payload, or analytics beacon goes with them. What the counter
 *   learns is that somebody, somewhere, opened a page.
 *
 * Loaded by lms.js, which owns the feature switch.
 * =========================================================================== */

(function () {
  'use strict';

  var CFG = (window.LMS_CONFIG || {});
  var VC = CFG.visitors || {};
  var LANG = (document.documentElement.lang || 'en').slice(0, 2) === 'id' ? 'id' : 'en';

  var T = {
    en: { readers: 'readers', views: 'views on this page', counting: 'counting' },
    id: { readers: 'pembaca', views: 'kunjungan halaman ini', counting: 'menghitung' }
  }[LANG];

  /* ------------------------------------------------------------------ */
  /* Keys                                                                */
  /* ------------------------------------------------------------------ */

  // A counter name may only contain letters, digits, dashes and underscores,
  // so the page path is flattened into one.
  function pageKey() {
    var path = (location.pathname || '')
      .replace(/\/$/, '/index')
      .replace(/\.html?$/, '');
    var parts = path.split('/').filter(Boolean);
    var tail = parts.slice(-2).join('-') || 'index';
    return tail.replace(/[^A-Za-z0-9_-]/g, '-').slice(0, 60).toLowerCase();
  }

  var NS = (VC.namespace || 'book').replace(/[^A-Za-z0-9_-]/g, '-');
  var TOTAL_KEY = 'total';
  var PAGE_KEY = 'p-' + pageKey();

  /* ------------------------------------------------------------------ */
  /* Deduplication                                                       */
  /* ------------------------------------------------------------------ */

  // localStorage can throw outright in a browser with site data blocked,
  // which is a reason to skip counting, never a reason to fail.
  function shouldIncrement(key) {
    var hours = typeof VC.dedupeHours === 'number' ? VC.dedupeHours : 12;
    if (hours <= 0) return true;
    try {
      var k = 'lms:seen:' + NS + ':' + key;
      var last = parseInt(localStorage.getItem(k) || '0', 10);
      if (Date.now() - last < hours * 3600 * 1000) return false;
      localStorage.setItem(k, String(Date.now()));
      return true;
    } catch (e) {
      return true;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Provider                                                            */
  /* ------------------------------------------------------------------ */

  // counterapi.dev, v1. No account, no key, CORS open.
  //   .../v1/<namespace>/<key>/up  increment and return
  //   .../v1/<namespace>/<key>/    read without incrementing
  // The shape of the reply has varied across their versions, so every
  // plausible field is checked rather than the one documented today.
  function counterapi(key, increment) {
    var base = 'https://api.counterapi.dev/v1/' + encodeURIComponent(NS) +
               '/' + encodeURIComponent(key) + '/';
    return fetch(base + (increment ? 'up' : ''), {
      method: 'GET',
      mode: 'cors',
      cache: 'no-store',
      referrerPolicy: 'no-referrer'
    })
      .then(function (r) {
        if (!r.ok) throw new Error('counter ' + r.status);
        return r.json();
      })
      .then(function (j) {
        var n = j && (j.count != null ? j.count
                    : j.value != null ? j.value
                    : j.data && j.data.up_count != null ? j.data.up_count
                    : j.data && j.data.count);
        if (typeof n !== 'number') throw new Error('counter: unrecognised reply');
        return n;
      });
  }

  var PROVIDERS = { counterapi: counterapi };

  /* ------------------------------------------------------------------ */
  /* Badge                                                               */
  /* ------------------------------------------------------------------ */

  function fmt(n) {
    // 1234 -> "1,234"; 12345 -> "12.3k". Long numbers in a footer badge read
    // as noise rather than as information.
    if (n >= 10000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function paint(total, page) {
    var host = document.querySelector('#lms-visitors') ||
               document.querySelector('main') ||
               document.body;

    var badge = document.createElement('div');
    badge.className = 'lms-visitors';
    badge.setAttribute('role', 'status');

    var bits = [];
    if (typeof total === 'number') {
      bits.push('<span class="lms-vis-item"><strong>' + fmt(total) + '</strong> ' + T.readers + '</span>');
    }
    if (typeof page === 'number') {
      bits.push('<span class="lms-vis-item"><strong>' + fmt(page) + '</strong> ' + T.views + '</span>');
    }
    if (!bits.length) return;

    badge.innerHTML = '<span class="lms-vis-dot" aria-hidden="true"></span>' + bits.join('<span class="lms-vis-sep">·</span>');

    if (host.id === 'lms-visitors') {
      host.replaceWith(badge);
    } else {
      host.appendChild(badge);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Start                                                               */
  /* ------------------------------------------------------------------ */

  function start() {
    if (VC.enabled === false) return;
    var provider = PROVIDERS[VC.provider || 'counterapi'];
    if (!provider) return;
    if (typeof fetch !== 'function') return;

    var inc = shouldIncrement('page');

    // Both counters are asked at once, and the badge shows whichever answer
    // arrives. A failure on one does not hide the other.
    Promise.all([
      provider(TOTAL_KEY, inc).catch(function () { return null; }),
      provider(PAGE_KEY, inc).catch(function () { return null; })
    ]).then(function (r) {
      if (r[0] == null && r[1] == null) return;   // counter unreachable: stay silent
      paint(r[0], r[1]);
    }).catch(function (err) {
      console.warn('visitor counter unavailable:', err);
    });
  }

  window.LMS_VISITORS = { start: start };

  // The landing page has no lms.js, so it starts the counter itself by
  // setting this flag before loading the script.
  if (window.LMS_VISITORS_AUTOSTART) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', start);
    } else {
      start();
    }
  }
})();
