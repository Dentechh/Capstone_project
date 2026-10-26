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
    var notices = [], scheduleNotifs = [], archivedSchedule = [], archivedClinicNotices = [];
    var failed = false, scheduleFailed = false, archivedFailed = false, clinicArchivedFailed = false;
    var showArchived = false;

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

    function activeSchedule() { return scheduleNotifs.filter(function (n) { return !n.archived; }); }
    function archivedList() { return archivedSchedule.length ? archivedSchedule : scheduleNotifs.filter(function (n) { return n.archived; }); }

    function isUnread(n) { return n.read === false; }

    function unseenIds() { return unseenIn(notices, STORE_KEY); }
    function unseenScheduleIds() {
        return activeSchedule().filter(isUnread).map(function (n) { return n.id; });
    }

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

    function postJson(url, body) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(body || {})
        }).then(function (res) { return res.json().catch(function () { return {}; }); });
    }

    function renderScheduleItem(n, newIds) {
        var item = el('div', 'notif-item schedule');

        var icon = el('div', 'notif-icon');
        var glyph = el('span', 'material-symbols-rounded', SCHEDULE_ICONS[n.type] || 'event');
        glyph.setAttribute('aria-hidden', 'true');
        icon.appendChild(glyph);

        var body = el('div', 'notif-body');
        var title = el('div', 'notif-title', SCHEDULE_TITLES[n.type] || 'Appointment update');
        if (newIds.indexOf(n.id) !== -1 || isUnread(n)) title.appendChild(el('span', 'notif-new', 'NEW'));
        body.appendChild(title);

        var when = fmtDateTime(n.appointment_date);
        if (when) body.appendChild(el('div', 'notif-when', when));

        body.appendChild(el('div', 'notif-msg', scheduleMessage(n)));

        item.appendChild(icon);
        item.appendChild(body);

        // action buttons
        var actions = el('div', 'notif-actions');
        if (n.archived) {
            var restoreBtn = el('button', 'notif-action-btn', '');
            restoreBtn.type = 'button';
            restoreBtn.title = 'Restore';
            restoreBtn.setAttribute('aria-label', 'Restore notification');
            restoreBtn.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true">unarchive</span>';
            restoreBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                postJson('/unarchive_schedule_notification', { id: n.id }).then(function () {
                    n.archived = false;
                    // move in lists
                    archivedSchedule = archivedSchedule.filter(function (x) { return x.id !== n.id; });
                    if (scheduleNotifs.indexOf(n) === -1) scheduleNotifs.push(n);
                    render(unseenIds(), unseenScheduleIds());
                    updateBadge();
                });
            });
            actions.appendChild(restoreBtn);
        } else {
            var archiveBtn = el('button', 'notif-action-btn', '');
            archiveBtn.type = 'button';
            archiveBtn.title = 'Archive';
            archiveBtn.setAttribute('aria-label', 'Archive notification');
            archiveBtn.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true">archive</span>';
            archiveBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                postJson('/archive_schedule_notification', { id: n.id }).then(function () {
                    n.archived = true;
                    n.read = true;
                    archivedSchedule.push(n);
                    scheduleNotifs = scheduleNotifs.filter(function (x) { return x.id !== n.id; });
                    render(unseenIds(), unseenScheduleIds());
                    updateBadge();
                });
            });
            actions.appendChild(archiveBtn);
        }
        var delBtn = el('button', 'notif-action-btn notif-action-btn--danger', '');
        delBtn.type = 'button';
        delBtn.title = 'Delete';
        delBtn.setAttribute('aria-label', 'Delete notification');
        delBtn.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true">delete</span>';
        delBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            postJson('/delete_schedule_notification', { id: n.id }).then(function () {
                scheduleNotifs = scheduleNotifs.filter(function (x) { return x.id !== n.id; });
                archivedSchedule = archivedSchedule.filter(function (x) { return x.id !== n.id; });
                render(unseenIds(), unseenScheduleIds());
                updateBadge();
            });
        });
        actions.appendChild(delBtn);

        item.appendChild(actions);
        return item;
    }

    function renderClinicItem(n, archived) {
        var closed = n.type === 'closed';
        var item = el('div', 'notif-item ' + (closed ? 'closed' : 'partial'));

        var icon = el('div', 'notif-icon');
        var glyph = el('span', 'material-symbols-rounded', closed ? 'event_busy' : 'schedule');
        glyph.setAttribute('aria-hidden', 'true');
        icon.appendChild(glyph);

        var body = el('div', 'notif-body');
        var title = el('div', 'notif-title', closed ? 'Clinic closed' : 'Limited availability');
        if (!archived && unseenIds().indexOf(n.id) !== -1) title.appendChild(el('span', 'notif-new', 'NEW'));
        body.appendChild(title);

        var when = whenLabel(n);
        if (!closed && n.times && n.times.length) {
            when += ' \\u00b7 ' + n.times.map(fmtTime).join(', ') + ' unavailable';
        }
        body.appendChild(el('div', 'notif-when', when));

        var msg = (n.message || '').trim();
        if (!msg) msg = closed ? 'Appointments are not available on these dates.' : 'Some appointment times are not available.';
        body.appendChild(el('div', 'notif-msg', msg));

        item.appendChild(icon);
        item.appendChild(body);

        var actions = el('div', 'notif-actions');
        if (archived) {
            var restoreBtn = el('button', 'notif-action-btn', '');
            restoreBtn.type = 'button';
            restoreBtn.title = 'Restore';
            restoreBtn.setAttribute('aria-label', 'Restore notice');
            restoreBtn.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true">unarchive</span>';
            restoreBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                postJson('/unarchive_clinic_notice', { id: n.id }).then(function () {
                    archivedClinicNotices = archivedClinicNotices.filter(function (x) { return x.id !== n.id; });
                    if (notices.indexOf(n) === -1) notices.push(n);
                    render(unseenIds(), unseenScheduleIds());
                });
            });
            actions.appendChild(restoreBtn);
        } else {
            var archiveBtn = el('button', 'notif-action-btn', '');
            archiveBtn.type = 'button';
            archiveBtn.title = 'Archive';
            archiveBtn.setAttribute('aria-label', 'Archive notice');
            archiveBtn.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true">archive</span>';
            archiveBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                postJson('/archive_clinic_notice', { id: n.id }).then(function () {
                    notices = notices.filter(function (x) { return x.id !== n.id; });
                    if (archivedClinicNotices.indexOf(n) === -1) archivedClinicNotices.push(n);
                    // mark as seen so badge doesn't count archived notices
                    var seen = readSeen(STORE_KEY);
                    if (seen.indexOf(n.id) === -1) seen.push(n.id);
                    writeSeen(STORE_KEY, seen);
                    render(unseenIds(), unseenScheduleIds());
                    updateBadge();
                });
            });
            actions.appendChild(archiveBtn);
        }
        item.appendChild(actions);

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
        var schHead = el('div', 'notif-section-head');
        schHead.appendChild(el('div', 'notif-head', showArchived ? 'Archived schedule updates' : 'Schedule updates'));

        var toggle = el('button', 'notif-toggle', showArchived ? 'Show active' : 'Show archive');
        toggle.type = 'button';
        toggle.addEventListener('click', function (e) {
            e.stopPropagation();
            showArchived = !showArchived;
            var fetches = [];
            if (showArchived) {
                if (!archivedSchedule.length) {
                    fetches.push(fetch('/get_schedule_notifications?archived=1', { headers: { 'Accept': 'application/json' } })
                        .then(function (res) { return res.json(); })
                        .then(function (data) { if (Array.isArray(data)) archivedSchedule = data; archivedFailed = false; })
                        .catch(function () { archivedFailed = true; }));
                }
                if (!archivedClinicNotices.length) {
                    fetches.push(fetch('/get_clinic_notices?archived=1', { headers: { 'Accept': 'application/json' } })
                        .then(function (res) { return res.json(); })
                        .then(function (data) { if (Array.isArray(data)) archivedClinicNotices = data; clinicArchivedFailed = false; })
                        .catch(function () { clinicArchivedFailed = true; }));
                }
            }
            if (fetches.length) {
                Promise.all(fetches).then(function () { render(unseenIds(), unseenScheduleIds()); });
            } else {
                render(unseenIds(), unseenScheduleIds());
            }
        });
        schHead.appendChild(toggle);
        panel.appendChild(schHead);

        if (showArchived) {
            if (archivedFailed) {
                panel.appendChild(emptyState('cloud_off', 'Could not load archived updates.'));
            } else if (!archivedList().length) {
                panel.appendChild(emptyState('archive', 'No archived updates.'));
            } else {
                archivedList().forEach(function (n) {
                    panel.appendChild(renderScheduleItem(n, []));
                });
            }
        } else {
            if (scheduleFailed) {
                panel.appendChild(emptyState('cloud_off', 'Could not load schedule updates. Please try again later.'));
            } else {
                var list = activeSchedule();
                if (!list.length) {
                    panel.appendChild(emptyState('event_available', 'No schedule updates yet.'));
                } else {
                    list.forEach(function (n) {
                        panel.appendChild(renderScheduleItem(n, newScheduleIds));
                    });
                }
            }
        }

        /* ---- Clinic notices: closures / limited availability ---- */
        panel.appendChild(el('div', 'notif-head', showArchived ? 'Archived clinic notices' : 'Clinic notices'));

        var clinicList = showArchived ? archivedClinicNotices : notices;
        if (showArchived) {
            if (clinicArchivedFailed) {
                panel.appendChild(emptyState('cloud_off', 'Could not load archived notices.'));
            } else if (!clinicList.length) {
                panel.appendChild(emptyState('archive', 'No archived notices.'));
            } else {
                clinicList.forEach(function (n) { panel.appendChild(renderClinicItem(n, true)); });
            }
        } else {
            if (failed) {
                panel.appendChild(emptyState('cloud_off', 'Could not load clinic notices. Please try again later.'));
            } else if (!clinicList.length) {
                panel.appendChild(emptyState('campaign', 'No clinic notices right now.'));
            } else {
                clinicList.forEach(function (n) { panel.appendChild(renderClinicItem(n, false)); });
            }
        }
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

        // Mark all active schedule notifications as read on the server so
        // the "new" state persists across logins.
        var unreadActive = activeSchedule().filter(isUnread).map(function (n) { return n.id; });
        if (unreadActive.length) {
            postJson('/mark_schedule_notifications_read', { ids: unreadActive }).then(function () {
                scheduleNotifs.forEach(function (n) { if (!n.archived) n.read = true; });
                updateBadge();
                if (isOpen()) render(unseenIds(), unseenScheduleIds());
            });
        }

        // Opening the panel counts as seeing clinic notices (localStorage).
        if (fresh.length) {
            var seen = readSeen(STORE_KEY);
            notices.forEach(function (n) { if (seen.indexOf(n.id) === -1) seen.push(n.id); });
            writeSeen(STORE_KEY, seen);
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
                if (res.status === 401) return [];
                return res.json();
            })
            .then(function (data) {
                if (!Array.isArray(data)) throw new Error('bad response');
                scheduleNotifs = data;
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
