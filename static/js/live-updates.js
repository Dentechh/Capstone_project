/* Live updates for the admin panel.
 *
 * Patients submit appointments, reschedules and change requests on their own
 * device; the admin page used to learn about them only after a full reload.
 * This asks the server a tiny question every 30 seconds ("how many pending
 * appointments / open change requests are there?") and, only when an answer
 * changes, refreshes just the part that is affected:
 *   - pending appointments  -> the Appointments list (this section only)
 *   - change requests       -> the Reminders change-request view and badge
 * It pauses while the browser tab is hidden and never touches the rest of the
 * page, so nothing you are working on is reloaded.
 */
(function () {
    'use strict';

    var INTERVAL_MS = 30000;
    var last = null;
    var inFlight = false;

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

    function poll() {
        if (inFlight || document.visibilityState !== 'visible') return;
        inFlight = true;
        fetch('/admin/live_state', { credentials: 'same-origin', cache: 'no-store' })
            .then(function (res) { if (!res.ok) throw new Error(String(res.status)); return res.json(); })
            .then(function (d) {
                if (!d || !d.success) return;
                var now = { appointments: d.appointments, change_requests: d.change_requests };
                if (last) onChange(last, now);   // the first answer is only the baseline
                last = now;
            })
            .catch(function () { /* offline or session ended: try again next time */ })
            .then(function () { inFlight = false; });
    }

    // A new patient message: the Messages script raises this when its unread count grows.
    document.addEventListener('admin:message', function () {
        if (activeSection() !== 'messages') notify('New message from a patient.');
        announce('messages', null);
    });

    setInterval(poll, INTERVAL_MS);
    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') poll();   // catch up when you come back to the tab
    });
    setTimeout(poll, 2000);
})();