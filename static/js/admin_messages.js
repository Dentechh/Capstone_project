/* Admin inbox. Mount point: <div id="adminMessages"></div>.
   Call AdminMessages.start() when the Messages section is shown and
   AdminMessages.stop() when it is hidden. Optional sidebar badge: #adminMsgBadge */
(function () {
  var root = document.getElementById('adminMessages');
  if (!root) return;
  function csrfToken() { return (document.querySelector('meta[name="csrf-token"]') || {}).content || ''; }
  var convs = {}, active = null, listSince = '', cursor = '', shown = {}, timer = null, running = false, sending = false;
  var FAST = 4000, SLOW = 30000, delay = FAST;   // adaptive polling
  var MAX_FILE = 10 * 1024 * 1024;               // keep in step with messaging.py
  var ACCEPT = '.jpg,.jpeg,.png,.gif,.webp,.pdf,.docx,.xlsx,image/*,application/pdf';
  var EXT_OK = /\.(jpe?g|png|gif|webp|pdf|docx|xlsx)$/i;
  var pendingFile = null;

  root.innerHTML =
    '<div class="cm-admin">' +
      '<div class="cm-list">' +
        '<div class="cm-searchrow"><input class="cm-search" placeholder="Search conversations..."><button class="cm-new" type="button" title="New message" aria-label="New message"><span class="material-symbols-rounded" aria-hidden="true">edit_square</span></button></div>' +
        '<div class="cm-convs"></div>' +
        '<div class="cm-picker" hidden><div class="cm-pickhead"><b>New message</b><button class="cm-pickx" type="button" aria-label="Close"><span class="material-symbols-rounded" aria-hidden="true">close</span></button></div>' +
        '<input class="cm-pickq" placeholder="Search patient by name or email..."><div class="cm-pickres"></div></div>' +
      '</div>' +
      '<div class="cm-pane"><div class="cm-none">Select a patient to read their messages</div></div>' +
    '</div>';
  var wrap = root.querySelector('.cm-admin'), listEl = root.querySelector('.cm-convs'),
      search = root.querySelector('.cm-search'), pane = root.querySelector('.cm-pane');
  var badge = document.getElementById('adminMsgBadge');

  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  function initials(n) { return (n || '?').split(/\s+/).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase(); }
  function short(iso) {
    if (!iso) return ''; var d = new Date(iso), n = new Date();
    return d.toDateString() === n.toDateString() ? d.toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'})
      : d.toLocaleDateString([], {month: 'short', day: 'numeric'});
  }
  function fmtSize(n) {
    n = Number(n) || 0;
    return n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
  }
  function buildAttachment(att, onLoad) {
    var a = document.createElement('a');
    a.href = att.url; a.rel = 'noopener';
    if (att.kind === 'image') {
      a.target = '_blank'; a.className = 'cm-att-imglink';
      var img = document.createElement('img');
      img.className = 'cm-att-img'; img.src = att.url; img.alt = att.name || 'Photo'; img.loading = 'lazy';
      img.addEventListener('load', onLoad || function () {});
      a.appendChild(img);
    } else {
      a.className = 'cm-att-file'; a.setAttribute('download', att.name || '');
      var ic = document.createElement('span'); ic.className = 'material-symbols-rounded'; ic.setAttribute('aria-hidden', 'true'); ic.textContent = 'description';
      var meta = document.createElement('span'); meta.className = 'cm-att-meta';
      var nm = document.createElement('b'); nm.textContent = att.name || 'File';
      var sz = document.createElement('small'); sz.textContent = fmtSize(att.size);
      meta.appendChild(nm); meta.appendChild(sz); a.appendChild(ic); a.appendChild(meta);
    }
    return a;
  }
  function get(url) { return fetch(url, {headers: {'X-Requested-With': 'fetch'}}).then(function (r) { return r.ok ? r.json() : null; }); }
  function pollBadge() { return get('/admin/messages/conversations?badge=1').then(function (d) { if (d) setBadge(d.unread_total); }); }
  function setBadge(n) { if (!badge || n == null) return; badge.textContent = n > 99 ? '99+' : n; badge.hidden = !n; }

  function post(url, fields) {
    var fd = new FormData(); Object.keys(fields).forEach(function (k) { fd.append(k, fields[k]); });
    return fetch(url, {method: 'POST', body: fd, headers: {'X-CSRFToken': csrfToken()}}).then(function (r) { return r.json(); });
  }
  function updateBadge() {
    setBadge(Object.keys(convs).reduce(function (n, k) { return n + (convs[k].unread || 0); }, 0));
  }
  function applyBlock(blocked, canBlock) {
    var btn = pane.querySelector('.cm-blk'), sub = pane.querySelector('.cm-sub');
    if (!btn) return;
    btn.hidden = !canBlock;
    btn.dataset.blocked = blocked ? '1' : '0';
    btn.title = btn.ariaLabel = blocked ? 'Unblock account' : 'Block account';
    btn.querySelector('.material-symbols-rounded').textContent = blocked ? 'lock_open' : 'block';
    if (sub) sub.textContent = blocked ? 'Patient · Blocked' : 'Patient';
  }
  function renderList() {
    var q = search.value.trim().toLowerCase();
    var items = Object.keys(convs).map(function (k) { return convs[k]; })
      .filter(function (c) { return !q || (c.name || '').toLowerCase().indexOf(q) > -1; })
      .sort(function (a, b) { return a.last_message_at < b.last_message_at ? 1 : -1; });
    listEl.innerHTML = items.length ? items.map(function (c) {
      return '<div class="cm-conv' + (c.uid === active ? ' active' : '') + (c.unread ? ' unread' : '') + '" data-uid="' + esc(c.uid) + '">' +
        '<div class="cm-av">' + esc(initials(c.name)) + '</div><div class="cm-meta"><div class="cm-top"><span class="cm-name">' + esc(c.name) +
        '</span><span class="cm-when">' + short(c.last_message_at) + '</span></div><div class="cm-prev">' +
        (c.last_sender === 'admin' ? 'You: ' : '') + esc(c.last_message) + '</div></div>' +
        (c.unread ? '<div class="cm-dot" title="Mark as read">' + (c.unread > 99 ? '99+' : c.unread) + '</div>' : '') + '</div>';
    }).join('') : '<div class="cm-empty">No conversations yet</div>';
  }

  function loadList() {
    return get('/admin/messages/conversations' + (listSince ? '?since=' + encodeURIComponent(listSince) : '')).then(function (d) {
      if (!d || !d.conversations) return 0;
      d.conversations.forEach(function (c) {
        if (c.uid === active) c.unread = 0;       // thread is open, so it's being read
        convs[c.uid] = c;
        if (c.last_message_at > listSince) listSince = c.last_message_at;
      });
      renderList();
      setBadge(Object.keys(convs).reduce(function (n, k) { return n + (convs[k].unread || 0); }, 0));
      return d.conversations.length;
    });
  }

  function attachScroll() {
    var scrollBtn = pane.querySelector('.cm-scroll-btn');
    var box = pane.querySelector('.cm-msgs');
    if (box && scrollBtn) {
      box.addEventListener('scroll', function () {
        var nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
        scrollBtn.classList.toggle('show', !nearBottom && box.scrollHeight > box.clientHeight);
      });
      scrollBtn.addEventListener('click', function () { box.scrollTop = box.scrollHeight; });
    }
    var emojiBtn = pane.querySelector('.cm-emoji-btn');
    var emojiPicker = pane.querySelector('.cm-emoji-picker');
    var ta = pane.querySelector('textarea');
    if (emojiPicker && emojiBtn && ta) {
      var EMOJIS = ['😀','😁','😂','🤣','😊','😍','😘','😜','😎','🤔','👍','👎','👏','🙏','❤️','💙','💚','💛','🔥','✨','🎉','😭','😅','😇','🤝','😬','😴','🤯','💯','✅','❌','⭐','🌟','🦷','💬'];
      EMOJIS.forEach(function (e) {
        var b = document.createElement('button'); b.type = 'button'; b.textContent = e;
        b.addEventListener('click', function () { ta.value += e; ta.focus(); ta.dispatchEvent(new Event('input')); });
        emojiPicker.appendChild(b);
      });
      emojiBtn.addEventListener('click', function (ev) { ev.stopPropagation(); emojiPicker.classList.toggle('open'); });
      document.addEventListener('click', function (e) {
        if (!e.target.closest('.cm-emoji-picker') && !e.target.closest('.cm-emoji-btn')) emojiPicker.classList.remove('open');
      });
    }
  }

  function openThread(uid, extra) {
    delay = FAST; active = uid; cursor = ''; shown = {};
    var c = convs[uid] || {name: (extra && extra.name) || 'Patient'}; c.unread = 0;
    wrap.classList.add('chat-open'); renderList();
    pane.innerHTML =
      '<div class="cm-head"><button class="cm-back" aria-label="Back"><span class="material-symbols-rounded" aria-hidden="true">arrow_back</span></button><div class="cm-av">' + esc(initials(c.name)) + '</div><div><b>' + esc(c.name) + '</b><small class="cm-sub">Patient</small></div>' +
      '<div class="cm-tools">' +
      '<button class="cm-del cm-unread" type="button" title="Mark as unread" aria-label="Mark as unread"><span class="material-symbols-rounded" aria-hidden="true">mark_email_unread</span></button>' +
      '<button class="cm-del cm-blk" type="button" title="Block account" aria-label="Block account" hidden><span class="material-symbols-rounded" aria-hidden="true">block</span></button>' +
      '<button class="cm-del cm-rm" type="button" title="Delete conversation" aria-label="Delete conversation"><span class="material-symbols-rounded" aria-hidden="true">delete</span></button>' +
      '</div></div>' +
      '<div class="cm-msgs"><div class="cm-empty">No messages yet. Say hello!</div><button class="cm-scroll-btn" type="button" aria-label="Scroll to bottom">↓</button></div>' +
      '<div class="cm-emoji-picker"></div>' +
      '<div class="cm-attach-preview" hidden></div>' +
      '<form class="cm-form"><input type="file" class="cm-file" hidden accept="' + ACCEPT + '">' +
      '<button type="button" class="cm-attach-btn" aria-label="Attach a photo or document" title="Attach a photo or document"><span class="material-symbols-rounded" aria-hidden="true">attach_file</span></button>' +
      '<button type="button" class="cm-emoji-btn" aria-label="Emoji" title="Emoji">😊</button><textarea rows="1" maxlength="1000" placeholder="Reply to ' + esc(c.name) + '..."></textarea>' +
      '<button type="submit" aria-label="Send"><span class="material-symbols-rounded" aria-hidden="true">send</span></button></form>';
    attachScroll();
    var form = pane.querySelector('form'), ta = pane.querySelector('textarea');
    var brandNew = !convs[uid];
    if (brandNew) { pane.querySelector('.cm-unread').hidden = true; pane.querySelector('.cm-rm').hidden = true; }
    pane.querySelector('.cm-unread').onclick = function () {
      post('/admin/messages/mark', {uid: uid, unread: '1'}).then(function (d) {
        if (!d.success) { alert(d.message || 'Could not update.'); return; }
        convs[uid].unread = Math.max(convs[uid].unread || 0, 1);
        active = null; wrap.classList.remove('chat-open');
        pane.innerHTML = '<div class="cm-none">Marked as unread</div>';
        renderList(); updateBadge();
      }).catch(function () { alert('Could not update.'); });
    };
    pane.querySelector('.cm-blk').onclick = function () {
      var blocked = this.dataset.blocked === '1', self = this;
      var q = blocked ? 'Unblock ' + c.name + '? They will be able to log in and send messages again.'
                      : 'Block ' + c.name + '? They will not be able to log in or send messages.';
      if (!confirm(q)) return;
      post('/admin/toggle_user_block', {uid: uid, disabled: blocked ? 'false' : 'true'}).then(function (d) {
        if (!d.success) { alert(d.message || 'Could not update the account.'); return; }
        applyBlock(!blocked, true);
        if (typeof showToast === 'function') showToast(d.message || (blocked ? 'Account unblocked' : 'Account blocked'), 'success', 3000);
      }).catch(function () { alert('Could not update the account.'); });
    };
    pane.querySelector('.cm-rm').onclick = function () {
      if (!confirm('Delete this whole conversation with ' + c.name + '? This cannot be undone.')) return;
      var fd = new FormData(); fd.append('uid', uid);
      fetch('/admin/messages/delete', {method: 'POST', body: fd, headers: {'X-CSRFToken': csrfToken()}})
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.success) { alert(d.message || 'Could not delete.'); return; }
          delete convs[uid]; active = null; wrap.classList.remove('chat-open');
          pane.innerHTML = '<div class="cm-none">Conversation deleted</div>';
          renderList();
          setBadge(Object.keys(convs).reduce(function (n, k) { return n + (convs[k].unread || 0); }, 0));
          if (typeof showToast === 'function') showToast('Conversation deleted', 'success', 3000);
        })
        .catch(function () { alert('Could not delete.'); });
    };
    pane.querySelector('.cm-back').onclick = function () { wrap.classList.remove('chat-open'); active = null; renderList(); };
    ta.addEventListener('input', function () { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 90) + 'px'; });
    ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });

    // ---- attachments: pick a file, show a removable preview, send with the message ----
    var fileInput = pane.querySelector('.cm-file'), preview = pane.querySelector('.cm-attach-preview');
    pendingFile = null;
    function clearPending() { pendingFile = null; fileInput.value = ''; preview.hidden = true; preview.textContent = ''; }
    function showPending() {
      preview.textContent = '';
      var chip = document.createElement('div'); chip.className = 'cm-prev-chip';
      var isImg = /^image\//.test(pendingFile.type);
      if (isImg) {
        var im = document.createElement('img'); im.alt = ''; im.src = URL.createObjectURL(pendingFile);
        im.addEventListener('load', function () { URL.revokeObjectURL(im.src); });
        chip.appendChild(im);
      } else {
        var ic = document.createElement('span'); ic.className = 'material-symbols-rounded'; ic.setAttribute('aria-hidden', 'true'); ic.textContent = 'description';
        chip.appendChild(ic);
      }
      var info = document.createElement('span'); info.className = 'cm-prev-name'; info.textContent = pendingFile.name + ' · ' + fmtSize(pendingFile.size);
      var x = document.createElement('button'); x.type = 'button'; x.className = 'cm-prev-x'; x.setAttribute('aria-label', 'Remove attachment');
      x.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true">close</span>';
      x.addEventListener('click', clearPending);
      chip.appendChild(info); chip.appendChild(x); preview.appendChild(chip); preview.hidden = false;
    }
    pane.querySelector('.cm-attach-btn').addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', function () {
      var f = fileInput.files && fileInput.files[0]; if (!f) return;
      if (!EXT_OK.test(f.name)) { alert('Only photos (JPG, PNG, GIF, WebP), PDF, Word (.docx) and Excel (.xlsx) files are allowed.'); clearPending(); return; }
      if (f.size > MAX_FILE) { alert('That file is larger than 10 MB.'); clearPending(); return; }
      pendingFile = f; showPending(); ta.focus();
    });

    form.addEventListener('submit', function (e) {
      e.preventDefault(); var text = ta.value.trim(), file = pendingFile; if ((!text && !file) || sending) return; sending = true;
      var fd = new FormData(); fd.append('uid', uid); fd.append('text', text);
      if (file) fd.append('file', file);
      if (!convs[uid]) fd.append('new', '1');
      fetch('/admin/messages/send', {method: 'POST', body: fd, headers: {'X-CSRFToken': csrfToken()}})
        .then(function (r) { return r.json(); })
        .then(function (d) { if (d.success) { ta.value = ''; ta.style.height = 'auto'; clearPending(); delay = FAST; return loadThread(); } alert(d.message || 'Could not send.'); })
        .catch(function () { alert('Could not send.'); })
        .then(function () {
          sending = false; ta.focus();
          loadList().then(function () {
            if (convs[uid] && active === uid) {
              var u = pane.querySelector('.cm-unread'), r = pane.querySelector('.cm-rm');
              if (u) u.hidden = false; if (r) r.hidden = false;
            }
          });
        });
    });
    loadThread(true).then(function () { ta.focus(); loadList(); });
  }

  function loadThread(first) {
    if (!active) return Promise.resolve(0);
    var uid = active;
    return get('/admin/messages/thread/' + encodeURIComponent(uid) + '?mark_read=1' + (cursor ? '&after=' + encodeURIComponent(cursor) : ''))
      .then(function (d) {
        if (!d || !d.messages || uid !== active) return 0;
        if (typeof d.blocked === 'boolean') applyBlock(d.blocked, d.can_block);
        var box = pane.querySelector('.cm-msgs'); if (!box) return 0;
        var emptyEl = box.querySelector('.cm-empty');
        if (emptyEl && d.messages.length) emptyEl.remove();
        var fresh = 0;
        var near = first || box.scrollHeight - box.scrollTop - box.clientHeight < 80;
        d.messages.forEach(function (m) {
          if (shown[m.id]) return; shown[m.id] = 1; fresh++;
          var day = new Date(m.created_at).toLocaleDateString([], {weekday: 'long', month: 'long', day: 'numeric'});
          if (box.dataset.day !== day) { var dd = document.createElement('div'); dd.className = 'cm-day'; dd.textContent = day; box.appendChild(dd); box.dataset.day = day; }
          var row = document.createElement('div'); row.className = 'cm-row ' + (m.sender === 'admin' ? 'me' : 'them');
          var b = document.createElement('div'); b.className = 'cm-bubble';
          if (m.attachment) {
            b.classList.add('has-att');
            b.appendChild(buildAttachment(m.attachment, function () { if (near) box.scrollTop = box.scrollHeight; }));
          }
          if (m.text) {
            var tx = document.createElement('div'); tx.className = 'cm-text'; tx.textContent = m.text; b.appendChild(tx);
            var copy = document.createElement('button'); copy.className = 'cm-copy'; copy.type = 'button'; copy.setAttribute('aria-label', 'Copy message');
            copy.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true">content_copy</span>';
            copy.addEventListener('click', function () {
              if (navigator.clipboard) navigator.clipboard.writeText(m.text).then(function () {
                copy.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true">check</span>';
                setTimeout(function () { copy.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true">content_copy</span>'; }, 1200);
              });
            });
            b.appendChild(copy);
          }
          var t = document.createElement('div'); t.className = 'cm-time';
          t.textContent = new Date(m.created_at).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}) + (m.sender === 'admin' && m.staff_name ? ' · ' + m.staff_name : '');
          row.appendChild(b); row.appendChild(t); box.appendChild(row); cursor = m.created_at;
        });
        if (near) box.scrollTop = box.scrollHeight;
        var scrollBtn = pane.querySelector('.cm-scroll-btn');
        if (scrollBtn && box) {
          var nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
          scrollBtn.classList.toggle('show', !nearBottom && box.scrollHeight > box.clientHeight);
        }
        return fresh;
      });
  }

  function tick() {
    if (!running) return;
    var visible = root.offsetParent !== null && !document.hidden;
    if (!visible) return next();
    Promise.all([loadList(), loadThread()]).then(function (r) {
      var activity = (r[0] || 0) + (r[1] || 0);
      delay = activity ? FAST : Math.min(Math.round(delay * 1.5), SLOW);   // quiet -> slow down
      next();
    }, next);
  }
  function next() { clearTimeout(timer); if (running) timer = setTimeout(tick, delay); }

  // ---- "New message": pick a patient who hasn't written yet ----
  var picker = root.querySelector('.cm-picker'), pickQ = root.querySelector('.cm-pickq'),
      pickRes = root.querySelector('.cm-pickres'), pickTimer = null;
  function closePicker() { picker.hidden = true; pickQ.value = ''; pickRes.innerHTML = ''; }
  function searchPatients() {
    get('/admin/messages/patients?q=' + encodeURIComponent(pickQ.value.trim())).then(function (d) {
      if (!d || !d.patients) { pickRes.innerHTML = '<div class="cm-empty">Could not load patients</div>'; return; }
      pickRes.innerHTML = d.patients.length ? d.patients.map(function (p) {
        return '<div class="cm-conv" data-uid="' + esc(p.uid) + '" data-name="' + esc(p.name) + '">' +
          '<div class="cm-av">' + esc(initials(p.name)) + '</div><div class="cm-meta"><div class="cm-name">' + esc(p.name) +
          '</div><div class="cm-prev">' + esc(p.email) + '</div></div></div>';
      }).join('') : '<div class="cm-empty">No matching patients</div>';
    });
  }
  root.querySelector('.cm-new').addEventListener('click', function () {
    picker.hidden = false; pickQ.focus(); searchPatients();
  });
  root.querySelector('.cm-pickx').addEventListener('click', closePicker);
  pickQ.addEventListener('input', function () { clearTimeout(pickTimer); pickTimer = setTimeout(searchPatients, 250); });
  pickRes.addEventListener('click', function (e) {
    var el = e.target.closest('.cm-conv'); if (!el) return;
    var uid = el.dataset.uid, name = el.dataset.name;
    closePicker();
    openThread(uid, {name: name});
  });

  listEl.addEventListener('click', function (e) {
    var el = e.target.closest('.cm-conv'); if (!el) return;
    var uid = el.dataset.uid;
    if (e.target.closest('.cm-dot')) {           // red count = "mark as read" without opening
      post('/admin/messages/mark', {uid: uid, unread: '0'}).then(function (d) {
        if (d.success && convs[uid]) { convs[uid].unread = 0; renderList(); updateBadge(); }
      });
      return;
    }
    openThread(uid);
  });
  search.addEventListener('input', renderList);

  window.AdminMessages = {
    start: function () { if (running) return; running = true; delay = FAST; loadList().then(next, next); },
    stop: function () { running = false; clearTimeout(timer); },
    refreshBadge: pollBadge
  };
  // keep the sidebar badge fresh even while the Messages tab is closed (slow poll)
  setInterval(function () { if (!running && !document.hidden) pollBadge(); }, 60000);
  pollBadge();
})();