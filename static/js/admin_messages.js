    /* Admin inbox. Mount point: <div id="adminMessages"></div>.
    Call AdminMessages.start() when the Messages section is shown and
    AdminMessages.stop() when it is hidden. Optional sidebar badge: #adminMsgBadge */
    (function () {
    var root = document.getElementById('adminMessages');
    if (!root) return;
    function csrfToken() { return (document.querySelector('meta[name="csrf-token"]') || {}).content || ''; }
    var convs = {}, active = null, listSince = '', cursor = '', shown = {}, timer = null, running = false, sending = false;

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
            (c.unread ? '<div class="cm-dot">' + (c.unread > 99 ? '99+' : c.unread) + '</div>' : '') + '</div>';
        }).join('') : '<div class="cm-empty">No conversations yet</div>';
    }

    function loadList() {
        return get('/admin/messages/conversations' + (listSince ? '?since=' + encodeURIComponent(listSince) : '')).then(function (d) {
        if (!d || !d.conversations) return;
        d.conversations.forEach(function (c) {
            if (c.uid === active) c.unread = 0;       // thread is open, so it's being read
            convs[c.uid] = c;
            if (c.last_message_at > listSince) listSince = c.last_message_at;
        });
        renderList(); setBadge(d.unread_total);
        });
    }

    function openThread(uid) {
        active = uid; cursor = ''; shown = {};
        var c = convs[uid] || {name: 'Patient'}; c.unread = 0;
        wrap.classList.add('chat-open'); renderList();
        pane.innerHTML =
        '<div class="cm-head"><button class="cm-back" aria-label="Back">&larr;</button><div class="cm-av">' + esc(initials(c.name)) + '</div><div><b>' + esc(c.name) + '</b><small>Patient</small></div></div>' +
        '<div class="cm-msgs"></div>' +
        '<form class="cm-form"><textarea rows="1" maxlength="1000" placeholder="Reply to ' + esc(c.name) + '..."></textarea>' +
        '<button type="submit" aria-label="Send"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/></svg></button></form>';
        var form = pane.querySelector('form'), ta = pane.querySelector('textarea');
        pane.querySelector('.cm-back').onclick = function () { wrap.classList.remove('chat-open'); active = null; renderList(); };
        ta.addEventListener('input', function () { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 90) + 'px'; });
        ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
        form.addEventListener('submit', function (e) {
        e.preventDefault(); var text = ta.value.trim(); if (!text || sending) return; sending = true;
        var fd = new FormData(); fd.append('uid', uid); fd.append('text', text);
        fetch('/admin/messages/send', {method: 'POST', body: fd, headers: {'X-CSRFToken': csrfToken()}})
            .then(function (r) { return r.json(); })
            .then(function (d) { if (d.success) { ta.value = ''; ta.style.height = 'auto'; return loadThread(); } alert(d.message || 'Could not send.'); })
            .catch(function () { alert('Could not send.'); })
            .then(function () { sending = false; ta.focus(); loadList(); });
        });
        loadThread(true).then(function () { ta.focus(); loadList(); });
    }

    function loadThread(first) {
        if (!active) return Promise.resolve();
        var uid = active;
        return get('/admin/messages/thread/' + encodeURIComponent(uid) + '?mark_read=1' + (cursor ? '&after=' + encodeURIComponent(cursor) : ''))
        .then(function (d) {
            if (!d || !d.messages || uid !== active) return;
            var box = pane.querySelector('.cm-msgs'); if (!box) return;
            var near = first || box.scrollHeight - box.scrollTop - box.clientHeight < 80;
            d.messages.forEach(function (m) {
            if (shown[m.id]) return; shown[m.id] = 1;
            var day = new Date(m.created_at).toLocaleDateString([], {weekday: 'long', month: 'long', day: 'numeric'});
            if (box.dataset.day !== day) { var dd = document.createElement('div'); dd.className = 'cm-day'; dd.textContent = day; box.appendChild(dd); box.dataset.day = day; }
            var row = document.createElement('div'); row.className = 'cm-row ' + (m.sender === 'admin' ? 'me' : 'them');
            var b = document.createElement('div'); b.className = 'cm-bubble'; b.textContent = m.text;
            var t = document.createElement('div'); t.className = 'cm-time';
            t.textContent = new Date(m.created_at).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}) + (m.sender === 'admin' && m.staff_name ? ' · ' + m.staff_name : '');
            row.appendChild(b); row.appendChild(t); box.appendChild(row); cursor = m.created_at;
            });
            if (near) box.scrollTop = box.scrollHeight;
        });
    }

    function tick() {
        if (!running) return;
        var visible = root.offsetParent !== null && !document.hidden;
        (visible ? Promise.all([loadList(), loadThread()]) : Promise.resolve()).then(next, next);
    }
    function next() { clearTimeout(timer); if (running) timer = setTimeout(tick, 4000); }

    listEl.addEventListener('click', function (e) { var el = e.target.closest('.cm-conv'); if (el) openThread(el.dataset.uid); });
    search.addEventListener('input', renderList);

    window.AdminMessages = {
        start: function () { if (running) return; running = true; loadList().then(next, next); },
        stop: function () { running = false; clearTimeout(timer); },
        refreshBadge: pollBadge
    };
    // keep the sidebar badge fresh even while the Messages tab is closed (slow poll)
    setInterval(function () { if (!running && !document.hidden) pollBadge(); }, 60000);
    pollBadge();
})();