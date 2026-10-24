/* Patient chat panel. Needs a #msgBtn button (with optional #msgBadge span). */
(function () {
    var btn = document.getElementById('msgBtn');
    if (!btn) return;
    var badge = document.getElementById('msgBadge');
    function csrfToken() {
        var m = document.querySelector('meta[name="csrf-token"]');
        if (m && m.content) return m.content;
        var i = document.querySelector('input[name="csrf_token"]');
        return i ? i.value : '';
    }
    var cursor = '', open = false, timer = null, sending = false, shown = {};
    var FAST = 3000, SLOW = 30000, CLOSED = 60000, delay = FAST;   // adaptive polling

    var panel = document.createElement('div');
    panel.className = 'cm-panel';
    panel.innerHTML =
        '<div class="cm-head"><div class="cm-av">🦷</div><div><b>Dr. Capizonda</b><small>Capizonda Dental Clinic</small></div>' +
        '<button class="cm-x" aria-label="Close">&times;</button></div>' +
        '<div class="cm-msgs"><div class="cm-empty">Say hello! Send a message and the dentist will reply here.</div></div>' +
        '<div class="cm-note">Not for emergencies. Please call the clinic for urgent concerns.</div>' +
        '<form class="cm-form"><textarea rows="1" maxlength="1000" placeholder="Type a message..."></textarea>' +
        '<button type="submit" aria-label="Send"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/></svg></button></form>';
    document.body.appendChild(panel);

    var box = panel.querySelector('.cm-msgs'), form = panel.querySelector('form'),
        ta = panel.querySelector('textarea'), sendBtn = form.querySelector('button');

    function fmtTime(iso) { return new Date(iso).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}); }
    function fmtDay(iso) { return new Date(iso).toLocaleDateString([], {weekday: 'long', month: 'long', day: 'numeric'}); }
    function setBadge(n) { if (!badge) return; badge.textContent = n > 9 ? '9+' : n; badge.hidden = !n; }

    function render(msgs) {
        var fresh = 0;
        if (!msgs.length) return 0;
        var empty = box.querySelector('.cm-empty'); if (empty) empty.remove();
        var nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
        msgs.forEach(function (m) {
        if (shown[m.id]) return; shown[m.id] = 1; fresh++;
        var day = fmtDay(m.created_at);
        if (box.dataset.day !== day) {
            var d = document.createElement('div'); d.className = 'cm-day'; d.textContent = day; box.appendChild(d);
            box.dataset.day = day;
        }
        var row = document.createElement('div'); row.className = 'cm-row ' + (m.sender === 'patient' ? 'me' : 'them');
        var b = document.createElement('div'); b.className = 'cm-bubble'; b.textContent = m.text;   // textContent = safe
        var t = document.createElement('div'); t.className = 'cm-time'; t.textContent = fmtTime(m.created_at);
        row.appendChild(b); row.appendChild(t); box.appendChild(row);
        cursor = m.created_at;
        });
        if (nearBottom || !box.dataset.init) { box.scrollTop = box.scrollHeight; box.dataset.init = 1; }
        return fresh;
    }

    function get(url) { return fetch(url, {headers: {'X-Requested-With': 'fetch'}}).then(function (r) { return r.ok ? r.json() : null; }); }

    function loadThread() {
        return get('/messages/thread?mark_read=1' + (cursor ? '&after=' + encodeURIComponent(cursor) : ''))
        .then(function (d) {
            if (!d || !d.messages) return 0;
            var n = render(d.messages);
            if (n) setBadge(0);
            return n;
        });
    }
    function pollBadge() { get('/messages/unread').then(function (d) { if (d) setBadge(d.unread || 0); }); }

    // Open: check every 3s, but back off toward 30s while nothing arrives.
    // Any new message (or sending one) snaps it back to 3s. Closed: once a minute.
    function schedule() {
        clearTimeout(timer);
        timer = setTimeout(function () {
        if (document.hidden) return schedule();
        if (open) {
            loadThread().then(function (n) {
            delay = n ? FAST : Math.min(Math.round(delay * 1.5), SLOW);
            schedule();
            }, schedule);
        } else {
            Promise.resolve(pollBadge()).then(schedule, schedule);
        }
        }, open ? delay : CLOSED);
    }

    function toggle(force) {
        open = typeof force === 'boolean' ? force : !open;
        delay = FAST;
        if (open) {
        var h = document.querySelector('.top-header'), top = h ? h.getBoundingClientRect().bottom + 8 : 78;
        panel.style.top = Math.max(top, 8) + 'px';
        }
        panel.classList.toggle('open', open);
        if (open) { loadThread().then(function () { box.scrollTop = box.scrollHeight; }); ta.focus(); }
        schedule();
    }

    // Capture phase on document: our click is handled first and never reaches any
    // other script that might also be listening on .notification-btn buttons.
    document.addEventListener('click', function (e) {
        if (e.target.closest && e.target.closest('#msgBtn')) { e.preventDefault(); e.stopPropagation(); toggle(); }
    }, true);
    panel.querySelector('.cm-x').addEventListener('click', function () { toggle(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && open) toggle(false); });

    ta.addEventListener('input', function () { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 90) + 'px'; });
    ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        var text = ta.value.trim(); if (!text || sending) return;
        sending = true; sendBtn.disabled = true;
        var fd = new FormData(); fd.append('text', text);
        fetch('/messages/send', {method: 'POST', body: fd, headers: {'X-CSRFToken': csrfToken()}})
        .then(function (r) { return r.json(); })
        .then(function (d) {
            if (d.success) { ta.value = ''; ta.style.height = 'auto'; delay = FAST; return loadThread(); }
            alert(d.message || 'Could not send.');
        })
        .catch(function () { alert('Could not send. Please check your connection.'); })
        .then(function () { sending = false; sendBtn.disabled = false; ta.focus(); });
    });

    pollBadge(); schedule();
})();