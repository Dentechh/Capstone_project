/* Patient notification bell.
   Reads /get_clinic_notices (upcoming clinic closures / limited availability
   that the dentist chose to tell patients about) and shows them in a small
   panel under the bell. A red badge counts notices the patient has not seen. */
(function () {
    'use strict';

    var STORE_KEY = 'capiSeenNotices';
    var btn = null, panel = null, badge = null;
    var notices = [], failed = false;

    function readSeen() {
        try {
            var v = JSON.parse(localStorage.getItem(STORE_KEY) || '[]');
            return Array.isArray(v) ? v : [];
        } catch (e) { return []; }
    }

    function writeSeen(ids) {
        try { localStorage.setItem(STORE_KEY, JSON.stringify(ids.slice(-100))); } catch (e) { /* storage blocked */ }
    }

    function parseYmd(s) {
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || '');
        return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
    }

    function fmtDate(s, withWeekday) {
        var d = parseYmd(s);
        if (!d) return s || '';
        var opts = { month: 'short', day: 'numeric' };
        if (withWeekday) opts.weekday = 'short';
        if (d.getFullYear() !== new Date().getFullYear()) opts.year = 'numeric';
        return d.toLocaleDateString('en-US', opts);
    }

    function fmtTime(v) {
        var m = /^(\d{1,2}):(\d{2})$/.exec(v || '');
        if (!m) return v || '';
        var h = Number(m[1]);
        var ap = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        return h + ':' + m[2] + ' ' + ap;
    }

    function whenLabel(n) {
        if (n.start === n.end) return fmtDate(n.start, true);
        return fmtDate(n.start) + ' \u2013 ' + fmtDate(n.end);
    }

    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text != null) e.textContent = text;
        return e;
    }

    function unseenIds() {
        var seen = readSeen();
        return notices.filter(function (n) { return seen.indexOf(n.id) === -1; })
            .map(function (n) { return n.id; });
    }

    function updateBadge() {
        if (!badge) return;
        var n = unseenIds().length;
        badge.textContent = n > 9 ? '9+' : String(n);
        badge.classList.toggle('show', n > 0);
        if (btn) btn.setAttribute('aria-label', n ? 'Notifications (' + n + ' new)' : 'Notifications');
    }

    function render(newIds) {
        panel.innerHTML = '';
        panel.appendChild(el('div', 'notif-head', 'Clinic notices'));

        if (failed) {
            panel.appendChild(el('div', 'notif-empty', 'Could not load notices. Please try again later.'));
            return;
        }
        if (!notices.length) {
            panel.appendChild(el('div', 'notif-empty', 'No clinic notices right now.'));
            return;
        }

        notices.forEach(function (n) {
            var closed = n.type === 'closed';
            var item = el('div', 'notif-item ' + (closed ? 'closed' : 'partial'));

            var icon = el('div', 'notif-icon');
            var glyph = el('span', 'material-symbols-rounded', closed ? 'event_busy' : 'schedule');
            glyph.setAttribute('aria-hidden', 'true');
            icon.appendChild(glyph);

            var body = el('div', 'notif-body');
            var title = el('div', 'notif-title', closed ? 'Clinic closed' : 'Limited availability');
            if (newIds.indexOf(n.id) !== -1) title.appendChild(el('span', 'notif-new', 'NEW'));
            body.appendChild(title);

            var when = whenLabel(n);
            if (!closed && n.times && n.times.length) {
                when += ' \u00b7 ' + n.times.map(fmtTime).join(', ') + ' unavailable';
            }
            body.appendChild(el('div', 'notif-when', when));

            var msg = (n.message || '').trim();
            if (!msg) msg = closed ? 'Appointments are not available on these dates.' : 'Some appointment times are not available.';
            body.appendChild(el('div', 'notif-msg', msg));

            item.appendChild(icon);
            item.appendChild(body);
            panel.appendChild(item);
        });
    }

    function position() {
        if (!btn || !panel) return;
        var r = btn.getBoundingClientRect();
        var w = panel.offsetWidth || 360;
        var left = Math.min(Math.max(8, r.right - w), window.innerWidth - w - 8);
        panel.style.top = Math.round(r.bottom + 8) + 'px';
        panel.style.left = Math.round(left) + 'px';
    }

    function isOpen() { return panel.classList.contains('open'); }

    function close() {
        panel.classList.remove('open');
        btn.setAttribute('aria-expanded', 'false');
    }

    function open() {
        var fresh = unseenIds();
        render(fresh);
        panel.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
        position();

        // Opening the panel counts as seeing everything in it.
        if (fresh.length) {
            var seen = readSeen();
            notices.forEach(function (n) { if (seen.indexOf(n.id) === -1) seen.push(n.id); });
            writeSeen(seen);
            updateBadge();
        }
    }

    function init() {
        btn = document.getElementById('notificationBtn');
        if (!btn) return;

        badge = el('span', 'notif-badge');
        badge.setAttribute('aria-hidden', 'true');
        btn.appendChild(badge);

        panel = el('div', 'notif-panel');
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'Clinic notices');
        document.body.appendChild(panel);

        btn.setAttribute('aria-haspopup', 'dialog');
        btn.setAttribute('aria-expanded', 'false');

        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            if (isOpen()) close(); else open();
        });
        document.addEventListener('click', function (e) {
            if (isOpen() && !panel.contains(e.target) && !btn.contains(e.target)) close();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && isOpen()) { close(); btn.focus(); }
        });
        window.addEventListener('resize', function () { if (isOpen()) position(); });
        window.addEventListener('scroll', function () { if (isOpen()) position(); }, { passive: true });

        fetch('/get_clinic_notices', { headers: { 'Accept': 'application/json' } })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!Array.isArray(data)) throw new Error('bad response');
                notices = data;
                // Forget notices that no longer exist so the stored list stays small.
                var ids = notices.map(function (n) { return n.id; });
                writeSeen(readSeen().filter(function (id) { return ids.indexOf(id) !== -1; }));
                updateBadge();
                if (isOpen()) render([]);
            })
            .catch(function (err) {
                console.error('Clinic notices error:', err);
                failed = true;
                if (isOpen()) render([]);
            });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();