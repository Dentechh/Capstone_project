/* Live updates for the admin panel.
 *
 * Patients submit appointments, reschedules and change requests on their own
 * device. This asks the server one tiny question ("how many pending
 * appointments / open change requests are there?") and, only when the answer
 * changes, refreshes just the affected part: the Appointments list, or the
 * Reminders change-request view and badge.
 *
 * It is deliberately gentle on the server and on Firestore reads:
 *   - checks once a minute (not every few seconds);
 *   - pauses while the browser tab is hidden;
 *   - pauses after 10 minutes without any mouse or keyboard activity, so a tab
 *     left open overnight costs nothing, and resumes the moment you are back;
 *   - slows itself down (up to 5 minutes) whenever the server is slow or fails.
 *
 * To switch it off for testing, run this in the browser console and reload:
 *     localStorage.setItem('adminLive', 'off')
 * and to switch it back on:  localStorage.removeItem('adminLive')
 */
(function () {
    'use strict';

    try { if (localStorage.getItem('adminLive') === 'off') return; } catch (e) { /* storage blocked: carry on */ }

    var BASE_MS = 60000;           // normal gap between checks
    var MAX_MS = 300000;           // longest gap when the server is struggling
    var SLOW_MS = 4000;            // an answer slower than this counts as "struggling"
    var IDLE_MS = 10 * 60 * 1000;  // stop checking after this long without activity

    var delay = BASE_MS;
    var last = null;
    var inFlight = false;
    var timer = null;
    var lastActivity = Date.now();

    function activeSection() {
        var s = document.querySelector('.content-section.active-section');
        return s ? s.id.replace(/^section-/, '') : '';
    }

    function notify(message) {
        if (typeof window.showToast === 'function') window.showToast(message, 'success');
    }

    // Do not swap a list underneath someone who is in the middle of using it.
    function userIsBusyIn(selector) {
        var a = document.activeElement;
        if (a && a.closest && a.closest(selector)) return true;
        return !!document.querySelector('dialog[open], [aria-modal="true"]:not([hidden])');
    }

    function refreshAppointments() {
        // Whatever happens now, the list is stale: reload it next time it is opened.
        if (window._lazyLoaded) window._lazyLoaded.appointments = false;
        if (activeSection() !== 'appointments') return;
        if (userIsBusyIn('#appointmentsTable')) {
            setTimeout(refreshAppointments, 4000);
            return;
        }
        if (typeof loadSectionOnce === 'function') loadSectionOnce('appointments');
    }

    function changed(a, b) {
        return typeof a === 'number' && typeof b === 'number' && a !== b;
    }

    function announce(what, counts) {
        // Lets any other part of the page hook in without editing this file.
        try {
            document.dispatchEvent(new CustomEvent('admin:live', { detail: { what: what, counts: counts } }));
        } catch (e) { /* old browser: nothing to announce to */ }
    }

    function onChange(prev, now) {
        if (changed(prev.appointments, now.appointments)) {
            if (now.appointments > prev.appointments) {
                notify('New appointment request received.');
                refreshAppointments();
            } else if (window._lazyLoaded) {
                window._lazyLoaded.appointments = false;   // list is stale; reload on next visit
            }
            announce('appointments', now);
        }
        if (changed(prev.change_requests, now.change_requests)) {
            if (now.change_requests > prev.change_requests) notify('A patient sent a change request.');
            if (window.RemindersLive) window.RemindersLive.refresh();
            announce('change_requests', now);
        }
    }

    function isIdle() { return Date.now() - lastActivity > IDLE_MS; }

    function schedule(ms) {
        clearTimeout(timer);
        timer = setTimeout(poll, ms);
    }

    function poll() {
        // Paused while hidden or idle; activity / returning to the tab restarts it.
        if (document.visibilityState !== 'visible' || isIdle()) return;
        if (inFlight) { schedule(delay); return; }

        inFlight = true;
        var started = Date.now();
        fetch('/admin/live_state', { credentials: 'same-origin', cache: 'no-store' })
            .then(function (res) { if (!res.ok) throw new Error(String(res.status)); return res.json(); })
            .then(function (d) {
                var slow = Date.now() - started > SLOW_MS;
                delay = slow ? Math.min(delay * 2, MAX_MS) : BASE_MS;
                if (!d || !d.success) return;
                var now = { appointments: d.appointments, change_requests: d.change_requests };
                if (last) onChange(last, now);   // the first answer is only the baseline
                last = now;
            })
            .catch(function () {
                delay = Math.min(delay * 2, MAX_MS);   // offline, session ended or server busy: back off
            })
            .then(function () {
                inFlight = false;
                schedule(delay);
            });
    }

    // A new patient message: the Messages script raises this when its unread count grows.
    document.addEventListener('admin:message', function () {
        if (activeSection() !== 'messages') notify('New message from a patient.');
        announce('messages', null);
    });

    function onActivity() {
        var wasIdle = isIdle();
        lastActivity = Date.now();
        if (wasIdle) schedule(1000);                  // welcome back: catch up quickly
    }
    ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'].forEach(function (ev) {
        window.addEventListener(ev, onActivity, { passive: true });
    });
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') schedule(500);
    });

    schedule(5000);
})();