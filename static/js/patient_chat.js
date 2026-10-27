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
    var MAX_FILE = 10 * 1024 * 1024;               // keep in step with messaging.py
    var ACCEPT = '.jpg,.jpeg,.png,.gif,.webp,.pdf,.docx,.xlsx,image/*,application/pdf';
    var EXT_OK = /\.(jpe?g|png|gif|webp|pdf|docx|xlsx)$/i;
    var pendingFile = null;
    var cursor = '', open = false, timer = null, sending = false, shown = {};
    var FAST = 3000, SLOW = 30000, CLOSED = 60000, delay = FAST;   // adaptive polling

    var panel = document.createElement('div');
    panel.className = 'cm-panel';
    panel.innerHTML =
        '<div class="cm-head"><div class="cm-av"><span class="material-symbols-rounded" aria-hidden="true">dentistry</span></div><div><b>Dr. Capizonda</b><small>Capizonda Dental Clinic</small></div>' +
        '<button class="cm-x" aria-label="Close"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button></div>' +
        '<div class="cm-msgs"><div class="cm-empty">Say hello! Send a message and the dentist will reply here.</div><button class="cm-scroll-btn" type="button" aria-label="Scroll to bottom">↓</button></div>' +
        '<div class="cm-note">Not for emergencies. Please call the clinic for urgent concerns.</div>' +
        '<div class="cm-emoji-picker"></div>' +
        '<div class="cm-attach-preview" hidden></div>' +
        '<form class="cm-form"><input type="file" class="cm-file" hidden accept="' + ACCEPT + '">' +
        '<button type="button" class="cm-attach-btn" aria-label="Attach a photo or document" title="Attach a photo or document"><span class="material-symbols-rounded" aria-hidden="true">attach_file</span></button>' +
        '<button type="button" class="cm-emoji-btn" aria-label="Emoji" title="Emoji"><span class="material-symbols-rounded" aria-hidden="true">sentiment_satisfied</span></button><textarea rows="1" maxlength="1000" placeholder="Type a message..."></textarea>' +
        '<button type="submit" aria-label="Send"><span class="material-symbols-rounded" aria-hidden="true">send</span></button></form>';
    document.body.appendChild(panel);

    var box = panel.querySelector('.cm-msgs'), form = panel.querySelector('form'),
        ta = panel.querySelector('textarea'), sendBtn = form.querySelector('button[type="submit"]');
    var scrollBtn = panel.querySelector('.cm-scroll-btn');
    var fileInput = panel.querySelector('.cm-file'), preview = panel.querySelector('.cm-attach-preview');

    box.addEventListener('scroll', function () {
        var nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
        scrollBtn.classList.toggle('show', !nearBottom && box.scrollHeight > box.clientHeight);
    });
    scrollBtn.addEventListener('click', function () { box.scrollTop = box.scrollHeight; });

    var emojiBtn = panel.querySelector('.cm-emoji-btn');
    var emojiPicker = panel.querySelector('.cm-emoji-picker');
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

    function fmtTime(iso) { return new Date(iso).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit'}); }
    function fmtDay(iso) { return new Date(iso).toLocaleDateString([], {weekday: 'long', month: 'long', day: 'numeric'}); }
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
        var b = document.createElement('div'); b.className = 'cm-bubble';
        if (m.attachment) {
            b.classList.add('has-att');
            b.appendChild(buildAttachment(m.attachment, function () { if (nearBottom) box.scrollTop = box.scrollHeight; }));
        }
        if (m.text) {
            var tx = document.createElement('div'); tx.className = 'cm-text'; tx.textContent = m.text; b.appendChild(tx);   // textContent = safe
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

    function clearPending() { pendingFile = null; fileInput.value = ''; preview.hidden = true; preview.textContent = ''; }
    function showPending() {
        preview.textContent = '';
        var chip = document.createElement('div'); chip.className = 'cm-prev-chip';
        if (/^image\//.test(pendingFile.type)) {
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
    panel.querySelector('.cm-attach-btn').addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', function () {
        var f = fileInput.files && fileInput.files[0]; if (!f) return;
        if (!EXT_OK.test(f.name)) { alert('Only photos (JPG, PNG, GIF, WebP), PDF, Word (.docx) and Excel (.xlsx) files are allowed.'); clearPending(); return; }
        if (f.size > MAX_FILE) { alert('That file is larger than 10 MB.'); clearPending(); return; }
        pendingFile = f; showPending(); ta.focus();
    });

    form.addEventListener('submit', function (e) {
        e.preventDefault();
        var text = ta.value.trim(), file = pendingFile; if ((!text && !file) || sending) return;
        sending = true; sendBtn.disabled = true;
        var fd = new FormData(); fd.append('text', text);
        if (file) fd.append('file', file);
        fetch('/messages/send', {method: 'POST', body: fd, headers: {'X-CSRFToken': csrfToken()}})
        .then(function (r) { return r.json(); })
        .then(function (d) {
            if (d.success) { ta.value = ''; ta.style.height = 'auto'; clearPending(); delay = FAST; return loadThread(); }
            alert(d.message || 'Could not send.');
        })
        .catch(function () { alert('Could not send. Please check your connection.'); })
        .then(function () { sending = false; sendBtn.disabled = false; ta.focus(); });
    });

    pollBadge(); schedule();
})();