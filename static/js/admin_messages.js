    /* Admin inbox. Mount point: <div id="adminMessages"></div>.
    Call AdminMessages.start() when the Messages section is shown and
    AdminMessages.stop() when it is hidden. Optional sidebar badge: #adminMsgBadge */
    (function () {
    var root = document.getElementById('adminMessages');
    if (!root) return;
    function csrfToken() { return (document.querySelector('meta[name="csrf-token"]') || {}).content || ''; }
    var convs = {}, active = null, listSince = '', cursor = '', shown = {}, timer = null, running = false, sending = false;
    var FAST = 4000, SLOW = 30000, delay = FAST;   // adaptive polling

    root.innerHTML =
        '<div class="cm-admin">' +
        '<div class="cm-list"><input class="cm-search" placeholder="Search patients..."><div class="cm-convs"></div></div>' +
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

    function openThread(uid) {
        delay = FAST; active = uid; cursor = ''; shown = {};
        var c = convs[uid] || {name: 'Patient'}; c.unread = 0;
        wrap.classList.add('chat-open'); renderList();
        pane.innerHTML =
        '<div class="cm-head"><button class="cm-back" aria-label="Back">&larr;</button><div class="cm-av">' + esc(initials(c.name)) + '</div><div><b>' + esc(c.name) + '</b><small class="cm-sub">Patient</small></div>' +
        '<div class="cm-tools">' +
        '<button class="cm-del cm-unread" type="button" title="Mark as unread" aria-label="Mark as unread"><span class="material-symbols-rounded" aria-hidden="true">mark_email_unread</span></button>' +
        '<button class="cm-del cm-blk" type="button" title="Block account" aria-label="Block account" hidden><span class="material-symbols-rounded" aria-hidden="true">block</span></button>' +
        '<button class="cm-del cm-rm" type="button" title="Delete conversation" aria-label="Delete conversation"><span class="material-symbols-rounded" aria-hidden="true">delete</span></button>' +
        '</div></div>' +
        '<div class="cm-msgs"></div>' +
        '<form class="cm-form"><textarea rows="1" maxlength="1000" placeholder="Reply to ' + esc(c.name) + '..."></textarea>' +
        '<button type="submit" aria-label="Send"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/></svg></button></form>';
        var form = pane.querySelector('form'), ta = pane.querySelector('textarea');
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
        form.addEventListener('submit', function (e) {
        e.preventDefault(); var text = ta.value.trim(); if (!text || sending) return; sending = true;
        var fd = new FormData(); fd.append('uid', uid); fd.append('text', text);
        fetch('/admin/messages/send', {method: 'POST', body: fd, headers: {'X-CSRFToken': csrfToken()}})
            .then(function (r) { return r.json(); })
            .then(function (d) { if (d.success) { ta.value = ''; ta.style.height = 'auto'; delay = FAST; return loadThread(); } alert(d.message || 'Could not send.'); })
            .catch(function () { alert('Could not send.'); })
            .then(function () { sending = false; ta.focus(); loadList(); });
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
            var fresh = 0;
            var near = first || box.scrollHeight - box.scrollTop - box.clientHeight < 80;
            d.messages.forEach(function (m) {
            if (shown[m.id]) return; shown[m.id] = 1; fresh++;
            var day = new Date(m.created_at).toLocaleDateString([], {weekday: 'long', month: 'long', day: 'numeric'});
            if (box.dataset.day !== day) { var dd = document.createElement('div'); dd.className = 'cm-day'; dd.textContent = day; box.appendChild(dd); box.dataset.day = day; }
            var row = document.createElement('div'); row.className = 'cm-row ' + (m.sender === 'admin' ? 'me' : 'them');
            var b = document.createElement('div'); b.className = 'cm-bubble'; b.textContent = m.text;
            var t = document.createElement('div'); t.className = 'cm-time';
            t.textContent = new Date(m.created_at).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}) + (m.sender === 'admin' && m.staff_name ? ' · ' + m.staff_name : '');
            row.appendChild(b); row.appendChild(t); box.appendChild(row); cursor = m.created_at;
            });
            if (near) box.scrollTop = box.scrollHeight;
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