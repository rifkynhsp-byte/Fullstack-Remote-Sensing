/* ===========================================================================
 * lms/lms.js
 * ===========================================================================
 *
 * A small learning platform bolted onto a static Quarto book.
 *
 * Design constraint that shapes everything below: GitHub Pages serves static
 * files and runs no code of ours. So the storage layer is an interface with
 * two implementations, chosen at load time.
 *
 *     LocalStore     browser localStorage, no account, no network
 *     RemoteStore    Supabase, real accounts, syncs across devices
 *
 * Everything above the storage layer, quizzes, progress, notes, the question
 * widget, the dashboard, is written against that interface and does not know
 * or care which one is active.
 *
 * No build step, no bundler, no framework. One file, loaded after the body.
 * =========================================================================== */

(function () {
  'use strict';

  var CFG = window.LMS_CONFIG || {};
  var FEATURES = CFG.features || {};
  var LANG = (document.documentElement.lang || 'en').slice(0, 2) === 'id' ? 'id' : 'en';

  /* ---------------------------------------------------------------------- */
  /* Strings                                                                 */
  /* ---------------------------------------------------------------------- */

  var T = {
    en: {
      signIn: 'Sign in', signOut: 'Sign out', signedInAs: 'Signed in as',
      setName: 'Set your name', yourName: 'Your name',
      emailLabel: 'Email address',
      magicLinkSent: 'Check your inbox. The sign in link is valid for one hour.',
      signInBlurb: 'Sign in with a link sent to your email. No password to remember.',
      localBlurb: 'Your progress is saved in this browser only. Adding a name just personalises the page.',
      save: 'Save', cancel: 'Cancel', send: 'Send', close: 'Close',
      markComplete: 'Mark this chapter complete',
      completed: 'Chapter complete',
      progress: 'Course progress',
      chaptersDone: 'chapters complete',
      quizTitle: 'Knowledge check',
      checkAnswer: 'Check answer', tryAgain: 'Try again', nextQ: 'Next question',
      correct: 'Correct', notQuite: 'Not quite',
      quizDone: 'Knowledge check complete',
      yourScore: 'You scored',
      retake: 'Retake',
      notes: 'My notes for this chapter',
      notesPlaceholder: 'Anything you want to remember. Saved automatically, visible only to you.',
      notesSaved: 'Saved',
      ask: 'Ask a question',
      askTitle: 'Ask the instructor',
      askBlurb: 'Your question is sent with the chapter you are reading, so there is no need to explain where you are.',
      askPlaceholder: 'What is unclear? Paste an error message if you have one.',
      askContext: 'About',
      askSent: 'Sent. You will get a reply by email.',
      askMailto: 'Your email client will open with the question ready to send.',
      questionRequired: 'Please write your question first.',
      emailRequired: 'Please enter your email so a reply can reach you.',
      dashTitle: 'Your progress',
      dashEmpty: 'Nothing recorded yet. Progress appears here as you work through the chapters.',
      dashQuizzes: 'Knowledge checks',
      dashNotes: 'Your notes',
      dashQuestions: 'Your questions',
      noQuestions: 'You have not asked anything yet.',
      awaiting: 'Awaiting reply',
      answered: 'Answered',
      export: 'Export my data', reset: 'Reset my progress',
      resetConfirm: 'This deletes your progress, quiz scores and notes on this device. Continue?',
      localMode: 'Local mode',
      accountMode: 'Account mode',
      instructorOnly: 'This page is for the instructor.',
      inbox: 'Question inbox', markAnswered: 'Mark answered', noInbox: 'No questions yet.'
    },
    id: {
      signIn: 'Masuk', signOut: 'Keluar', signedInAs: 'Masuk sebagai',
      setName: 'Isi nama Anda', yourName: 'Nama Anda',
      emailLabel: 'Alamat email',
      magicLinkSent: 'Periksa kotak masuk Anda. Tautan masuk berlaku satu jam.',
      signInBlurb: 'Masuk dengan tautan yang dikirim ke email Anda. Tidak ada kata sandi yang perlu diingat.',
      localBlurb: 'Kemajuan Anda hanya tersimpan di peramban ini. Mengisi nama sekadar mempersonalisasi halaman.',
      save: 'Simpan', cancel: 'Batal', send: 'Kirim', close: 'Tutup',
      markComplete: 'Tandai bab ini selesai',
      completed: 'Bab selesai',
      progress: 'Kemajuan kursus',
      chaptersDone: 'bab selesai',
      quizTitle: 'Uji pemahaman',
      checkAnswer: 'Periksa jawaban', tryAgain: 'Coba lagi', nextQ: 'Pertanyaan berikutnya',
      correct: 'Benar', notQuite: 'Belum tepat',
      quizDone: 'Uji pemahaman selesai',
      yourScore: 'Skor Anda',
      retake: 'Ulangi',
      notes: 'Catatan saya untuk bab ini',
      notesPlaceholder: 'Apa pun yang ingin Anda ingat. Tersimpan otomatis, hanya Anda yang melihat.',
      notesSaved: 'Tersimpan',
      ask: 'Ajukan pertanyaan',
      askTitle: 'Bertanya kepada pengajar',
      askBlurb: 'Pertanyaan Anda dikirim beserta bab yang sedang dibaca, jadi tidak perlu menjelaskan posisi Anda.',
      askPlaceholder: 'Bagian mana yang belum jelas? Tempel pesan galat bila ada.',
      askContext: 'Tentang',
      askSent: 'Terkirim. Balasan akan dikirim lewat email.',
      askMailto: 'Aplikasi email Anda akan terbuka dengan pertanyaan yang siap dikirim.',
      questionRequired: 'Tuliskan pertanyaan Anda terlebih dahulu.',
      emailRequired: 'Isi email Anda agar balasan dapat sampai.',
      dashTitle: 'Kemajuan Anda',
      dashEmpty: 'Belum ada yang tercatat. Kemajuan muncul di sini seiring Anda mengerjakan bab.',
      dashQuizzes: 'Uji pemahaman',
      dashNotes: 'Catatan Anda',
      dashQuestions: 'Pertanyaan Anda',
      noQuestions: 'Anda belum mengajukan pertanyaan.',
      awaiting: 'Menunggu balasan',
      answered: 'Sudah dijawab',
      export: 'Ekspor data saya', reset: 'Atur ulang kemajuan',
      resetConfirm: 'Ini menghapus kemajuan, skor dan catatan Anda di perangkat ini. Lanjutkan?',
      localMode: 'Mode lokal',
      accountMode: 'Mode akun',
      instructorOnly: 'Halaman ini untuk pengajar.',
      inbox: 'Kotak masuk pertanyaan', markAnswered: 'Tandai terjawab', noInbox: 'Belum ada pertanyaan.'
    }
  }[LANG];

  /* ---------------------------------------------------------------------- */
  /* Small helpers                                                           */
  /* ---------------------------------------------------------------------- */

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      if (k === 'class') node.className = attrs[k];
      else if (k === 'html') node.innerHTML = attrs[k];
      else if (k === 'text') node.textContent = attrs[k];
      else if (k.indexOf('on') === 0) node.addEventListener(k.slice(2), attrs[k]);
      else node.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments, self = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(self, args); }, ms);
    };
  }

  // A stable identifier for the current page, used as the key for progress,
  // notes and quiz results. Derived from the URL rather than the title,
  // because titles get edited and URLs mostly do not.
  function pageId() {
    var path = location.pathname.replace(/\/index\.html?$/, '/').replace(/\.html?$/, '');
    var parts = path.split('/').filter(Boolean);
    return parts.slice(-2).join('/') || 'index';
  }

  function pageTitle() {
    var h1 = document.querySelector('h1.title, header h1, main h1');
    return (h1 ? h1.textContent : document.title).trim();
  }

  // Is this a chapter, or a support page like the dashboard? Progress and
  // notes only make sense on chapters.
  function isChapter() {
    var id = pageId();
    return /\/\d{2}-/.test('/' + id) || /\/appendix-/.test('/' + id);
  }

  /* ---------------------------------------------------------------------- */
  /* Storage layer                                                           */
  /* ---------------------------------------------------------------------- */

  var NS = 'lms:' + (CFG.courseId || 'course') + ':';

  var LocalStore = {
    mode: 'local',
    user: null,

    init: function () {
      var raw = localStorage.getItem(NS + 'user');
      this.user = raw ? JSON.parse(raw) : null;
      return Promise.resolve();
    },
    signIn: function (profile) {
      this.user = { name: profile.name || '', email: profile.email || '', local: true };
      localStorage.setItem(NS + 'user', JSON.stringify(this.user));
      return Promise.resolve(this.user);
    },
    signOut: function () {
      this.user = null;
      localStorage.removeItem(NS + 'user');
      return Promise.resolve();
    },
    get: function (bucket) {
      var raw = localStorage.getItem(NS + bucket);
      return Promise.resolve(raw ? JSON.parse(raw) : {});
    },
    set: function (bucket, key, value) {
      var raw = localStorage.getItem(NS + bucket);
      var obj = raw ? JSON.parse(raw) : {};
      obj[key] = value;
      localStorage.setItem(NS + bucket, JSON.stringify(obj));
      return Promise.resolve(obj);
    },
    listQuestions: function () {
      var raw = localStorage.getItem(NS + 'questions');
      return Promise.resolve(raw ? JSON.parse(raw) : []);
    },
    addQuestion: function (q) {
      var raw = localStorage.getItem(NS + 'questions');
      var list = raw ? JSON.parse(raw) : [];
      list.unshift(q);
      localStorage.setItem(NS + 'questions', JSON.stringify(list));
      return Promise.resolve(q);
    },
    clear: function () {
      Object.keys(localStorage)
        .filter(function (k) { return k.indexOf(NS) === 0; })
        .forEach(function (k) { localStorage.removeItem(k); });
      return Promise.resolve();
    }
  };

  var RemoteStore = {
    mode: 'account',
    user: null,
    sb: null,
    cache: {},

    init: function () {
      var self = this;
      return loadScript('https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js')
        .then(function () {
          self.sb = window.supabase.createClient(CFG.supabaseUrl, CFG.supabaseAnonKey);
          return self.sb.auth.getSession();
        })
        .then(function (res) {
          var session = res.data && res.data.session;
          self.user = session ? {
            id: session.user.id,
            email: session.user.email,
            name: (session.user.user_metadata || {}).name || ''
          } : null;
          self.sb.auth.onAuthStateChange(function () { location.reload(); });
          return self.user ? self.preload() : null;
        });
    },

    // One round trip on page load rather than one per widget.
    preload: function () {
      var self = this;
      return self.sb.from('lms_state')
        .select('bucket,key,value')
        .eq('course_id', CFG.courseId)
        .then(function (res) {
          self.cache = {};
          (res.data || []).forEach(function (row) {
            self.cache[row.bucket] = self.cache[row.bucket] || {};
            self.cache[row.bucket][row.key] = row.value;
          });
        });
    },

    signIn: function (profile) {
      return this.sb.auth.signInWithOtp({
        email: profile.email,
        options: {
          emailRedirectTo: location.href,
          data: { name: profile.name || '' }
        }
      }).then(function (res) {
        if (res.error) throw res.error;
        return { pending: true };
      });
    },

    signOut: function () {
      return this.sb.auth.signOut().then(function () { location.reload(); });
    },

    get: function (bucket) {
      return Promise.resolve(this.cache[bucket] || {});
    },

    set: function (bucket, key, value) {
      var self = this;
      self.cache[bucket] = self.cache[bucket] || {};
      self.cache[bucket][key] = value;
      if (!self.user) return Promise.resolve(self.cache[bucket]);
      return self.sb.from('lms_state').upsert({
        user_id: self.user.id,
        course_id: CFG.courseId,
        bucket: bucket,
        key: key,
        value: value,
        updated_at: new Date().toISOString()
      }, { onConflict: 'user_id,course_id,bucket,key' })
        .then(function () { return self.cache[bucket]; });
    },

    listQuestions: function (all) {
      var q = this.sb.from('lms_questions')
        .select('*')
        .eq('course_id', CFG.courseId)
        .order('created_at', { ascending: false });
      return q.then(function (res) { return res.data || []; });
    },

    addQuestion: function (question) {
      var self = this;
      return self.sb.from('lms_questions').insert({
        course_id: CFG.courseId,
        user_id: self.user ? self.user.id : null,
        asker_email: question.email,
        asker_name: question.name || '',
        page_id: question.pageId,
        page_title: question.pageTitle,
        page_url: question.url,
        lang: LANG,
        body: question.body
      }).then(function (res) {
        if (res.error) throw res.error;
        return question;
      });
    },

    answerQuestion: function (id, answer) {
      return this.sb.from('lms_questions')
        .update({ answer: answer, answered_at: new Date().toISOString() })
        .eq('id', id);
    },

    clear: function () {
      var self = this;
      if (!self.user) return Promise.resolve();
      return self.sb.from('lms_state').delete()
        .eq('user_id', self.user.id).eq('course_id', CFG.courseId)
        .then(function () { self.cache = {}; });
    }
  };

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error('Failed to load ' + src)); };
      document.head.appendChild(s);
    });
  }

  var Store = (CFG.supabaseUrl && CFG.supabaseAnonKey) ? RemoteStore : LocalStore;

  /* ---------------------------------------------------------------------- */
  /* Modal                                                                   */
  /* ---------------------------------------------------------------------- */

  function modal(title, bodyNode, actions) {
    var overlay = el('div', { class: 'lms-overlay' });
    var box = el('div', { class: 'lms-modal', role: 'dialog', 'aria-modal': 'true' }, [
      el('div', { class: 'lms-modal-head' }, [
        el('h3', { text: title }),
        el('button', { class: 'lms-x', 'aria-label': T.close, text: '\u00d7', onclick: close })
      ]),
      el('div', { class: 'lms-modal-body' }, [bodyNode]),
      el('div', { class: 'lms-modal-foot' }, (actions || []).map(function (a) {
        return el('button', {
          class: 'lms-btn' + (a.primary ? ' lms-btn-primary' : ''),
          text: a.label,
          onclick: function () { a.onClick(close); }
        });
      }))
    ]);
    overlay.appendChild(box);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
    document.addEventListener('keydown', esc);
    document.body.appendChild(overlay);
    var focusable = box.querySelector('input, textarea, button');
    if (focusable) focusable.focus();

    function esc(e) { if (e.key === 'Escape') close(); }
    function close() {
      document.removeEventListener('keydown', esc);
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
    return { close: close, body: box.querySelector('.lms-modal-body') };
  }

  function toast(message) {
    var t = el('div', { class: 'lms-toast', text: message });
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add('lms-toast-out'); }, 2600);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 3200);
  }

  /* ---------------------------------------------------------------------- */
  /* Account bar                                                             */
  /* ---------------------------------------------------------------------- */

  function renderAccountBar() {
    var host = document.querySelector('.navbar .navbar-nav.ms-auto') ||
               document.querySelector('#quarto-header nav') ||
               document.body;

    var wrap = el('div', { class: 'lms-account' });

    function paint() {
      wrap.innerHTML = '';
      if (Store.user) {
        var label = Store.user.name || Store.user.email || 'reader';
        wrap.appendChild(el('span', { class: 'lms-user', title: T.signedInAs + ' ' + label },
          [el('span', { class: 'lms-avatar', text: label.slice(0, 1).toUpperCase() }),
           el('span', { class: 'lms-user-name', text: label })]));
        wrap.appendChild(el('button', { class: 'lms-link', text: T.signOut, onclick: function () {
          Store.signOut().then(function () { location.reload(); });
        }}));
      } else {
        wrap.appendChild(el('button', {
          class: 'lms-btn lms-btn-small lms-btn-primary',
          text: Store.mode === 'account' ? T.signIn : T.setName,
          onclick: openSignIn
        }));
      }
    }

    function openSignIn() {
      var nameInput = el('input', { class: 'lms-input', type: 'text', placeholder: T.yourName });
      var emailInput = el('input', { class: 'lms-input', type: 'email', placeholder: T.emailLabel });
      var body = el('div', {}, [
        el('p', { class: 'lms-muted', text: Store.mode === 'account' ? T.signInBlurb : T.localBlurb }),
        el('label', { class: 'lms-label', text: T.yourName }), nameInput,
        el('label', { class: 'lms-label', text: T.emailLabel }), emailInput
      ]);

      var m = modal(Store.mode === 'account' ? T.signIn : T.setName, body, [
        { label: T.cancel, onClick: function (close) { close(); } },
        { label: Store.mode === 'account' ? T.signIn : T.save, primary: true, onClick: function (close) {
            if (Store.mode === 'account' && !emailInput.value.trim()) {
              return toast(T.emailRequired);
            }
            Store.signIn({ name: nameInput.value.trim(), email: emailInput.value.trim() })
              .then(function (res) {
                close();
                if (res && res.pending) toast(T.magicLinkSent);
                else { paint(); location.reload(); }
              })
              .catch(function (err) { toast(err.message || 'Sign in failed'); });
          }}
      ]);
      return m;
    }

    paint();
    host.appendChild(wrap);
  }

  /* ---------------------------------------------------------------------- */
  /* Reading progress bar                                                    */
  /* ---------------------------------------------------------------------- */

  function renderReadingBar() {
    var bar = el('div', { class: 'lms-reading' }, [el('span')]);
    document.body.appendChild(bar);
    var fill = bar.firstChild;
    function update() {
      var h = document.documentElement.scrollHeight - window.innerHeight;
      var pct = h > 0 ? Math.min(100, (window.scrollY / h) * 100) : 0;
      fill.style.width = pct.toFixed(1) + '%';
    }
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    update();
  }

  /* ---------------------------------------------------------------------- */
  /* Chapter completion                                                      */
  /* ---------------------------------------------------------------------- */

  function renderCompletion(progress) {
    var id = pageId();
    var done = !!progress[id];

    var button = el('button', {
      class: 'lms-complete' + (done ? ' is-done' : ''),
      onclick: function () {
        done = !done;
        Store.set('progress', id, done ? { done: true, at: new Date().toISOString() } : null)
          .then(function () { paint(); updateSidebarBadges(); });
      }
    });

    function paint() {
      button.className = 'lms-complete' + (done ? ' is-done' : '');
      button.innerHTML = '';
      button.appendChild(el('span', { class: 'lms-check', text: done ? '\u2713' : '' }));
      button.appendChild(el('span', { text: done ? T.completed : T.markComplete }));
    }
    paint();

    var main = document.querySelector('main#quarto-document-content') ||
               document.querySelector('main') || document.body;
    main.appendChild(el('div', { class: 'lms-complete-wrap' }, [button]));
  }

  // Tick the sidebar entries the reader has finished, and show a course wide
  // percentage above the table of contents.
  function updateSidebarBadges() {
    Store.get('progress').then(function (progress) {
      var links = Array.prototype.slice.call(
        document.querySelectorAll('#quarto-sidebar a.sidebar-item-text, #quarto-sidebar .sidebar-item a'));
      var total = 0, done = 0;

      links.forEach(function (a) {
        var href = a.getAttribute('href');
        if (!href || href.indexOf('#') === 0) return;
        var key = href.replace(/\.html?$/, '').replace(/^\.\//, '');
        if (!/\d{2}-/.test(key) && !/appendix-/.test(key)) return;
        var langDir = location.pathname.split('/').filter(Boolean).slice(-2, -1)[0] || LANG;
        var id = langDir + '/' + key.split('/').pop();
        total++;
        var old = a.querySelector('.lms-tick');
        if (old) old.remove();
        if (progress[id] && progress[id].done) {
          done++;
          a.appendChild(el('span', { class: 'lms-tick', text: '\u2713' }));
        }
      });

      var host = document.querySelector('#quarto-sidebar .sidebar-menu-container') ||
                 document.querySelector('#quarto-sidebar');
      if (!host || !total) return;
      var existing = document.querySelector('.lms-course-progress');
      if (existing) existing.remove();
      var pct = Math.round((done / total) * 100);
      host.parentNode.insertBefore(el('div', { class: 'lms-course-progress' }, [
        el('div', { class: 'lms-cp-label' }, [
          el('span', { text: T.progress }),
          el('strong', { text: pct + '%' })
        ]),
        el('div', { class: 'lms-cp-track' }, [
          el('span', { style: 'width:' + pct + '%' })
        ]),
        el('div', { class: 'lms-cp-count', text: done + ' / ' + total + ' ' + T.chaptersDone })
      ]), host);
    });
  }

  /* ---------------------------------------------------------------------- */
  /* Quizzes                                                                 */
  /* ---------------------------------------------------------------------- */
  /*
   * Authored in a chapter as a raw HTML block:
   *
   *   <script type="application/json" class="lms-quiz">
   *   { "id": "ch02-signatures",
   *     "questions": [
   *       { "q": "...", "options": ["...", "..."], "answer": 1,
   *         "why": "explanation shown after answering" }
   *     ] }
   *   </script>
   *
   * Feedback is per question and immediate, and the explanation shows whether
   * the reader was right or wrong. A quiz that only reports a score at the end
   * teaches nothing.
   */

  function renderQuizzes(results) {
    var blocks = document.querySelectorAll('script.lms-quiz');
    Array.prototype.forEach.call(blocks, function (block) {
      var spec;
      try { spec = JSON.parse(block.textContent); }
      catch (e) { console.warn('LMS: malformed quiz JSON', e); return; }

      var key = pageId() + ':' + spec.id;
      var saved = results[key] || null;
      var index = 0;
      var score = 0;

      var host = el('section', { class: 'lms-quiz-card' });
      block.parentNode.insertBefore(host, block);

      function paintQuestion() {
        var q = spec.questions[index];
        host.innerHTML = '';
        host.appendChild(el('div', { class: 'lms-quiz-head' }, [
          el('span', { class: 'lms-quiz-tag', text: T.quizTitle }),
          el('span', { class: 'lms-quiz-count',
                       text: (index + 1) + ' / ' + spec.questions.length })
        ]));
        host.appendChild(el('p', { class: 'lms-quiz-q', text: q.q }));

        var chosen = null;
        var optionNodes = q.options.map(function (opt, i) {
          var node = el('button', {
            class: 'lms-option', text: opt,
            onclick: function () {
              if (chosen !== null) return;
              chosen = i;
              optionNodes.forEach(function (n) { n.classList.add('is-locked'); });
              var right = i === q.answer;
              node.classList.add(right ? 'is-right' : 'is-wrong');
              if (!right) optionNodes[q.answer].classList.add('is-right');
              if (right) score++;
              feedback.className = 'lms-feedback ' + (right ? 'is-right' : 'is-wrong');
              feedback.innerHTML = '';
              feedback.appendChild(el('strong', { text: right ? T.correct : T.notQuite }));
              if (q.why) feedback.appendChild(el('span', { text: ' ' + q.why }));
              next.style.display = 'inline-flex';
            }
          });
          return node;
        });

        var list = el('div', { class: 'lms-options' }, optionNodes);
        var feedback = el('div', { class: 'lms-feedback' });
        var next = el('button', {
          class: 'lms-btn lms-btn-primary lms-next',
          style: 'display:none',
          text: index + 1 < spec.questions.length ? T.nextQ : T.quizDone,
          onclick: function () {
            index++;
            if (index < spec.questions.length) paintQuestion();
            else finish();
          }
        });

        host.appendChild(list);
        host.appendChild(feedback);
        host.appendChild(next);
      }

      function finish() {
        var pct = Math.round((score / spec.questions.length) * 100);
        Store.set('quiz', key, {
          score: score, total: spec.questions.length, pct: pct,
          at: new Date().toISOString(), title: pageTitle()
        });
        paintResult({ score: score, total: spec.questions.length, pct: pct });
      }

      function paintResult(r) {
        host.innerHTML = '';
        host.classList.add('is-done');
        host.appendChild(el('div', { class: 'lms-quiz-head' }, [
          el('span', { class: 'lms-quiz-tag', text: T.quizDone })
        ]));
        host.appendChild(el('p', { class: 'lms-quiz-score',
          text: T.yourScore + ' ' + r.score + ' / ' + r.total + ' (' + r.pct + '%)' }));
        host.appendChild(el('button', {
          class: 'lms-btn lms-btn-small', text: T.retake,
          onclick: function () { index = 0; score = 0; host.classList.remove('is-done'); paintQuestion(); }
        }));
      }

      if (saved) paintResult(saved); else paintQuestion();
    });
  }

  /* ---------------------------------------------------------------------- */
  /* Per chapter notes                                                       */
  /* ---------------------------------------------------------------------- */

  function renderNotes(notes) {
    var id = pageId();
    var area = el('textarea', {
      class: 'lms-notes-area', rows: '6', placeholder: T.notesPlaceholder
    });
    area.value = (notes[id] && notes[id].body) || '';

    var status = el('span', { class: 'lms-notes-status' });
    var save = debounce(function () {
      Store.set('notes', id, { body: area.value, at: new Date().toISOString(), title: pageTitle() })
        .then(function () {
          status.textContent = T.notesSaved;
          setTimeout(function () { status.textContent = ''; }, 1500);
        });
    }, 700);
    area.addEventListener('input', save);

    var details = el('details', { class: 'lms-notes' }, [
      el('summary', {}, [el('span', { text: T.notes }), status]),
      area
    ]);
    if (area.value) details.setAttribute('open', '');

    var main = document.querySelector('main#quarto-document-content') ||
               document.querySelector('main') || document.body;
    main.appendChild(details);
  }

  /* ---------------------------------------------------------------------- */
  /* Ask a question                                                          */
  /* ---------------------------------------------------------------------- */

  function renderAskButton() {
    var fab = el('button', {
      class: 'lms-fab', title: T.ask, onclick: openAsk
    }, [el('span', { class: 'lms-fab-icon', text: '?' }),
        el('span', { class: 'lms-fab-label', text: T.ask })]);
    document.body.appendChild(fab);
  }

  function openAsk() {
    var user = Store.user || {};
    var nameInput = el('input', { class: 'lms-input', type: 'text',
      placeholder: T.yourName, value: user.name || '' });
    var emailInput = el('input', { class: 'lms-input', type: 'email',
      placeholder: T.emailLabel, value: user.email || '' });
    var bodyInput = el('textarea', { class: 'lms-input lms-textarea', rows: '6',
      placeholder: T.askPlaceholder });

    var body = el('div', {}, [
      el('p', { class: 'lms-muted', text: T.askBlurb }),
      el('div', { class: 'lms-context' }, [
        el('span', { class: 'lms-context-tag', text: T.askContext }),
        el('span', { text: pageTitle() })
      ]),
      el('label', { class: 'lms-label', text: T.yourName }), nameInput,
      el('label', { class: 'lms-label', text: T.emailLabel }), emailInput,
      el('label', { class: 'lms-label', text: T.askTitle }), bodyInput
    ]);

    modal(T.askTitle, body, [
      { label: T.cancel, onClick: function (close) { close(); } },
      { label: T.send, primary: true, onClick: function (close) {
          var text = bodyInput.value.trim();
          if (!text) return toast(T.questionRequired);
          if (!emailInput.value.trim()) return toast(T.emailRequired);

          var question = {
            name: nameInput.value.trim(),
            email: emailInput.value.trim(),
            body: text,
            pageId: pageId(),
            pageTitle: pageTitle(),
            url: location.href,
            at: new Date().toISOString(),
            status: 'open'
          };

          submitQuestion(question)
            .then(function (via) {
              Store.addQuestion(question);
              close();
              toast(via === 'mailto' ? T.askMailto : T.askSent);
            })
            .catch(function (err) { toast(err.message || 'Could not send'); });
        }}
    ]);
  }

  // Three delivery routes, tried in order of how good the experience is.
  function submitQuestion(q) {
    if (Store.mode === 'account' && Store.addQuestion !== LocalStore.addQuestion) {
      return RemoteStore.addQuestion(q).then(function () { return 'supabase'; });
    }
    if (CFG.formspreeEndpoint) {
      return fetch(CFG.formspreeEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({
          name: q.name, email: q.email, _subject: '[' + CFG.courseId + '] ' + q.pageTitle,
          chapter: q.pageTitle, url: q.url, message: q.body
        })
      }).then(function (r) {
        if (!r.ok) throw new Error('Form submission failed');
        return 'formspree';
      });
    }
    var subject = '[' + (CFG.courseId || 'course') + '] ' + q.pageTitle;
    var lines = [
      q.body, '', '---',
      'Chapter: ' + q.pageTitle,
      'Page: ' + q.url,
      'From: ' + (q.name || '(no name)') + ' <' + q.email + '>'
    ].join('\n');
    window.location.href = 'mailto:' + CFG.instructorEmail +
      '?subject=' + encodeURIComponent(subject) +
      '&body=' + encodeURIComponent(lines);
    return Promise.resolve('mailto');
  }

  /* ---------------------------------------------------------------------- */
  /* Dashboard                                                               */
  /* ---------------------------------------------------------------------- */

  function renderDashboard(host) {
    Promise.all([
      Store.get('progress'), Store.get('quiz'), Store.get('notes'), Store.listQuestions()
    ]).then(function (r) {
      var progress = r[0], quiz = r[1], notes = r[2], questions = r[3];
      host.innerHTML = '';

      var doneKeys = Object.keys(progress).filter(function (k) { return progress[k] && progress[k].done; });
      var quizKeys = Object.keys(quiz);
      var noteKeys = Object.keys(notes).filter(function (k) { return notes[k] && notes[k].body; });

      if (!doneKeys.length && !quizKeys.length && !noteKeys.length && !questions.length) {
        host.appendChild(el('p', { class: 'lms-muted', text: T.dashEmpty }));
      }

      // Headline numbers
      var avg = quizKeys.length
        ? Math.round(quizKeys.reduce(function (a, k) { return a + quiz[k].pct; }, 0) / quizKeys.length)
        : null;

      host.appendChild(el('div', { class: 'lms-stats' }, [
        stat(doneKeys.length, T.chaptersDone),
        stat(quizKeys.length, T.dashQuizzes),
        avg === null ? null : stat(avg + '%', T.yourScore),
        stat(questions.length, T.dashQuestions)
      ]));

      // Quiz table
      if (quizKeys.length) {
        host.appendChild(el('h2', { text: T.dashQuizzes }));
        var rows = quizKeys.map(function (k) {
          return el('tr', {}, [
            el('td', { text: quiz[k].title || k }),
            el('td', { text: quiz[k].score + ' / ' + quiz[k].total }),
            el('td', {}, [el('span', {
              class: 'lms-pill ' + (quiz[k].pct >= 70 ? 'is-good' : 'is-weak'),
              text: quiz[k].pct + '%'
            })])
          ]);
        });
        host.appendChild(el('table', { class: 'lms-table' }, [el('tbody', {}, rows)]));
      }

      // Notes
      if (noteKeys.length) {
        host.appendChild(el('h2', { text: T.dashNotes }));
        noteKeys.forEach(function (k) {
          host.appendChild(el('div', { class: 'lms-note-card' }, [
            el('h4', { text: notes[k].title || k }),
            el('p', { text: notes[k].body })
          ]));
        });
      }

      // Questions
      host.appendChild(el('h2', { text: T.dashQuestions }));
      if (!questions.length) {
        host.appendChild(el('p', { class: 'lms-muted', text: T.noQuestions }));
      } else {
        questions.forEach(function (q) {
          host.appendChild(el('div', { class: 'lms-note-card' }, [
            el('h4', { text: q.page_title || q.pageTitle || '' }),
            el('p', { text: q.body }),
            el('span', {
              class: 'lms-pill ' + (q.answer ? 'is-good' : 'is-weak'),
              text: q.answer ? T.answered : T.awaiting
            }),
            q.answer ? el('blockquote', { text: q.answer }) : null
          ]));
        });
      }

      // Data controls
      host.appendChild(el('div', { class: 'lms-data-actions' }, [
        el('button', { class: 'lms-btn lms-btn-small', text: T.export, onclick: function () {
          var blob = new Blob([JSON.stringify({ progress: progress, quiz: quiz, notes: notes }, null, 2)],
            { type: 'application/json' });
          var a = el('a', { href: URL.createObjectURL(blob), download: 'my-progress.json' });
          document.body.appendChild(a); a.click(); a.remove();
        }}),
        el('button', { class: 'lms-btn lms-btn-small lms-btn-danger', text: T.reset, onclick: function () {
          if (confirm(T.resetConfirm)) Store.clear().then(function () { location.reload(); });
        }})
      ]));
    });

    function stat(value, label) {
      return el('div', { class: 'lms-stat' }, [
        el('span', { class: 'lms-stat-n', text: String(value) }),
        el('span', { class: 'lms-stat-l', text: label })
      ]);
    }
  }

  /* ---------------------------------------------------------------------- */
  /* Instructor inbox                                                        */
  /* ---------------------------------------------------------------------- */

  function renderInstructor(host) {
    if (Store.mode !== 'account') {
      host.appendChild(el('p', { class: 'lms-muted', html:
        'Account mode is not configured, so questions arrive by email at <strong>' +
        CFG.instructorEmail + '</strong> rather than in this inbox. ' +
        'See <code>lms/README-lms.md</code> to enable accounts.' }));
      return;
    }
    if (!Store.user || Store.user.email !== CFG.instructorEmail) {
      host.appendChild(el('p', { class: 'lms-muted', text: T.instructorOnly }));
      return;
    }

    RemoteStore.listQuestions(true).then(function (list) {
      host.innerHTML = '';
      if (!list.length) return host.appendChild(el('p', { class: 'lms-muted', text: T.noInbox }));

      list.forEach(function (q) {
        var reply = el('textarea', { class: 'lms-input lms-textarea', rows: '3',
          placeholder: 'Reply', value: q.answer || '' });
        host.appendChild(el('div', { class: 'lms-note-card' }, [
          el('h4', { text: q.page_title }),
          el('p', { class: 'lms-muted', text: (q.asker_name || '') + ' <' + q.asker_email + '> \u00b7 ' +
            new Date(q.created_at).toLocaleString() }),
          el('p', { text: q.body }),
          reply,
          el('button', { class: 'lms-btn lms-btn-small lms-btn-primary', text: T.markAnswered,
            onclick: function () {
              RemoteStore.answerQuestion(q.id, reply.value).then(function () { toast(T.answered); });
            }})
        ]));
      });
    });
  }

  /* ---------------------------------------------------------------------- */
  /* Boot                                                                    */
  /* ---------------------------------------------------------------------- */

  function boot() {
    Store.init().then(function () {
      renderAccountBar();

      if (FEATURES.reading !== false) renderReadingBar();

      var dash = document.getElementById('lms-dashboard');
      if (dash) renderDashboard(dash);

      var inbox = document.getElementById('lms-instructor');
      if (inbox) renderInstructor(inbox);

      if (FEATURES.quizzes !== false) {
        Store.get('quiz').then(renderQuizzes);
      }

      if (isChapter()) {
        if (FEATURES.progress !== false) {
          Store.get('progress').then(function (p) {
            renderCompletion(p);
            updateSidebarBadges();
          });
        }
        if (FEATURES.notes !== false) {
          Store.get('notes').then(renderNotes);
        }
      } else if (FEATURES.progress !== false) {
        updateSidebarBadges();
      }

      if (FEATURES.questions !== false) renderAskButton();
    }).catch(function (err) {
      // A failure here must never take the book down with it. The chapter is
      // the product; the platform around it is an enhancement.
      console.warn('LMS failed to start, continuing without it:', err);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
