/* Patient notification bell.
   Reads /get_clinic_notices (upcoming clinic closures / limited
   availability that the dentist chose to tell patients about) and
   /get_schedule_notifications (the patient's own appointment
   accept / decline / reschedule events), and shows both in a small
   panel under the bell. A red badge counts anything unseen. */
(function () {
    'use strict';

    var STORE_KEY = 'capiSeenNotices';
    var SCHEDULE_STORE_KEY = 'capiSeenScheduleNotices';
    var btn = null, panel = null, badge = null;
    var notices = [], scheduleNotifs = [];
    var failed = false, scheduleFailed = false;

    function readSeen(key) {
        try {
            var v = JSON.parse(localStorage.getItem(key) || '[]');
            return Array.isArray(v) ? v : [];
        } catch (e) { return []; }
    }

    function writeSeen(key, ids) {
        try { localStorage.setItem(key, JSON.stringify(ids.slice(-100))); } catch (e) { /* storage blocked */ }
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

    /* Firestore stores appointment datetimes as "YYYY-MM-DD HH:MM". */
    function fmtDateTime(s) {
        var parts = String(s || '').trim().split(/[T ]+/);
        var date = fmtDate(parts[0] || '', true);
        var time = fmtTime(parts[1] || '');
        if (!date) return s || '';
        return time ? date + ' \u00b7 ' + time : date;
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

    function unseenIn(list, key) {
        var seen = readSeen(key);
        return list.filter(function (n) { return seen.indexOf(n.id) === -1; })
            .map(function (n) { return n.id; });
    }

    function unseenIds() { return unseenIn(notices, STORE_KEY); }
    function unseenScheduleIds() { return unseenIn(scheduleNotifs, SCHEDULE_STORE_KEY); }

    function updateBadge() {
        if (!badge) return;
        var n = unseenIds().length + unseenScheduleIds().length;
        badge.textContent = n > 9 ? '9+' : String(n);
        badge.classList.toggle('show', n > 0);
        if (btn) btn.setAttribute('aria-label', n ? 'Notifications (' + n + ' new)' : 'Notifications');
    }

    var SCHEDULE_ICONS = {
        accepted: 'event_available',
        declined: 'event_busy',
        rescheduled: 'event_repeat'
    };

    var SCHEDULE_TITLES = {
        accepted: 'Appointment Accepted',
        declined: 'Appointment Declined',
        rescheduled: 'Appointment Rescheduled'
    };

    function scheduleMessage(n) {
        var service = (n.service || '').trim() || 'appointment';
        var dentist = (n.dentist_name || '').trim();
        var when = fmtDateTime(n.appointment_date);
        var old = fmtDateTime(n.previous_appointment_date);

        switch (n.type) {
            case 'accepted':
                return 'Your ' + service + (dentist ? ' with ' + dentist : '') +
                    (when ? ' on ' + when : '') + ' has been accepted.';
            case 'declined':
                return 'Your ' + service + (when ? ' on ' + when : '') +
                    ' was declined. Please book another slot.';
            case 'rescheduled':
                return 'Your ' + service + ' was moved' +
                    (old ? ' from ' + old : '') + (when ? ' to ' + when : '') + '.';
            default:
                return 'Your appointment was updated.';
        }
    }

    function renderScheduleItem(n, newIds) {
        var item = el('div', 'notif-item schedule');

        var icon = el('div', 'notif-icon');
        var glyph = el('span', 'material-symbols-rounded', SCHEDULE_ICONS[n.type] || 'event');
        glyph.setAttribute('aria-hidden', 'true');
        icon.appendChild(glyph);

        var body = el('div', 'notif-body');
        var title = el('div', 'notif-title', SCHEDULE_TITLES[n.type] || 'Appointment update');
        if (newIds.indexOf(n.id) !== -1) title.appendChild(el('span', 'notif-new', 'NEW'));
        body.appendChild(title);

        var when = fmtDateTime(n.appointment_date);
        if (when) body.appendChild(el('div', 'notif-when', when));

        body.appendChild(el('div', 'notif-msg', scheduleMessage(n)));

        item.appendChild(icon);
        item.appendChild(body);
        return item;
    }

    function emptyState(icon, text) {
        var wrap = el('div', 'notif-empty');
        var glyph = el('span', 'material-symbols-rounded notif-empty-icon', icon);
        glyph.setAttribute('aria-hidden', 'true');
        wrap.appendChild(glyph);
        wrap.appendChild(el('span', 'notif-empty-text', text));
        return wrap;
    }

    function render(newIds, newScheduleIds) {
        panel.innerHTML = '';

        /* Panel title + how many items are still unseen. */
        var head = el('div', 'notif-panel-head');
        head.appendChild(el('div', 'notif-panel-title', 'Notifications'));
        var unseen = newIds.length + newScheduleIds.length;
        if (unseen > 0) {
            head.appendChild(el('div', 'notif-panel-count', unseen + ' new'));
        }
        panel.appendChild(head);

        /* ---- Schedule updates: what the dentist did to your appointments ---- */
        panel.appendChild(el('div', 'notif-head', 'Schedule updates'));

        if (scheduleFailed) {
            panel.appendChild(emptyState('cloud_off', 'Could not load schedule updates. Please try again later.'));
        } else if (!scheduleNotifs.length) {
            panel.appendChild(emptyState('event_available', 'No schedule updates yet.'));
        } else {
            scheduleNotifs.forEach(function (n) {
                panel.appendChild(renderScheduleItem(n, newScheduleIds));
            });
        }

        /* ---- Clinic notices: closures / limited availability ---- */
        panel.appendChild(el('div', 'notif-head', 'Clinic notices'));

        if (failed) {
            panel.appendChild(emptyState('cloud_off', 'Could not load clinic notices. Please try again later.'));
            return;
        }
        if (!notices.length) {
            panel.appendChild(emptyState('campaign', 'No clinic notices right now.'));
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
        var freshSchedule = unseenScheduleIds();
        render(fresh, freshSchedule);
        panel.classList.add('open');
        btn.setAttribute('aria-expanded', 'true');
        position();

        // Opening the panel counts as seeing everything in it.
        if (fresh.length || freshSchedule.length) {
            var seen = readSeen(STORE_KEY);
            notices.forEach(function (n) { if (seen.indexOf(n.id) === -1) seen.push(n.id); });
            writeSeen(STORE_KEY, seen);

            var seenSchedule = readSeen(SCHEDULE_STORE_KEY);
            scheduleNotifs.forEach(function (n) { if (seenSchedule.indexOf(n.id) === -1) seenSchedule.push(n.id); });
            writeSeen(SCHEDULE_STORE_KEY, seenSchedule);

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
        panel.setAttribute('aria-label', 'Notifications');
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
                writeSeen(STORE_KEY, readSeen(STORE_KEY).filter(function (id) { return ids.indexOf(id) !== -1; }));
                updateBadge();
                if (isOpen()) render(unseenIds(), unseenScheduleIds());
            })
            .catch(function (err) {
                console.error('Clinic notices error:', err);
                failed = true;
                if (isOpen()) render(unseenIds(), unseenScheduleIds());
            });

        fetch('/get_schedule_notifications', { headers: { 'Accept': 'application/json' } })
            .then(function (res) {
                // Guests are not logged in; the bell simply has no
                // schedule updates for them.
                if (res.status === 401) return [];
                return res.json();
            })
            .then(function (data) {
                if (!Array.isArray(data)) throw new Error('bad response');
                scheduleNotifs = data;
                var ids = scheduleNotifs.map(function (n) { return n.id; });
                writeSeen(SCHEDULE_STORE_KEY, readSeen(SCHEDULE_STORE_KEY).filter(function (id) { return ids.indexOf(id) !== -1; }));
                updateBadge();
                if (isOpen()) render(unseenIds(), unseenScheduleIds());
            })
            .catch(function (err) {
                console.error('Schedule notifications error:', err);
                scheduleFailed = true;
                if (isOpen()) render(unseenIds(), unseenScheduleIds());
            });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
