/* One shared dentist list for every dentist dropdown on the site.
 *
 * The list comes from Settings -> Dentists (public read-only route
 * /api/dentists, so the patient pages can use it too). This file:
 *   - keeps the list in window.CLINIC_DENTISTS (default dentist first),
 *   - fills every <select class="dentist-select"> that is a plain dentist
 *     picker (the admin booking modal and the Appointments table),
 *   - tells other scripts when the list changes via the "clinic-dentists"
 *     event on document, and via window.clinicDentistsOnChange(fn).
 * The treatment-record rows (.td-dentist) are handled by app-core.js.
 */
(function () {
    'use strict';

    var DEFAULT = 'Dr. Julix Dionne Capizonda';
    var listeners = [];
    window.CLINIC_DENTISTS = [DEFAULT];

    function fillSelect(sel) {
        if (sel.classList.contains('td-dentist')) return;
        var cur = sel.value;
        var names = window.CLINIC_DENTISTS.slice();
        // A dentist already chosen/saved that is no longer listed must still show.
        if (cur && names.indexOf(cur) === -1) names.push(cur);
        var same = sel.options.length === names.length &&
            names.every(function (n, i) { return sel.options[i].value === n; });
        if (same) return;                     // avoids a needless rebuild loop
        sel.textContent = '';
        names.forEach(function (n) {
            var o = document.createElement('option');
            o.value = n;
            o.textContent = n;
            if (n === (cur || names[0])) o.selected = true;
            sel.appendChild(o);
        });
    }
    function fillAll(root) {
        (root || document).querySelectorAll('select.dentist-select').forEach(fillSelect);
    }

    function setList(extra) {
        var out = [DEFAULT];
        (extra || []).forEach(function (n) {
            if (typeof n === 'string' && n && out.indexOf(n) === -1) out.push(n);
        });
        window.CLINIC_DENTISTS = out;
        fillAll();
        listeners.forEach(function (fn) { try { fn(out.slice()); } catch (e) { /* ignore */ } });
        document.dispatchEvent(new CustomEvent('clinic-dentists', { detail: out.slice() }));
    }

    window.clinicDentistsSet = setList;        // used by Settings after an add/remove
    window.clinicDentistsOnChange = function (fn) {
        listeners.push(fn);
        fn(window.CLINIC_DENTISTS.slice());
    };

    function load() {
        fetch('/api/dentists', { credentials: 'same-origin', cache: 'no-store' })
            .then(function (r) { return r.json(); })
            .then(function (d) { if (d && d.success) setList(d.dentists); })
            .catch(function () { /* the default dentist stays */ });
    }

    // Rows added later (Load More, re-rendered tables) get the list too.
    if ('MutationObserver' in window) {
        new MutationObserver(function (muts) {
            for (var i = 0; i < muts.length; i++) {
                var added = muts[i].addedNodes;
                for (var j = 0; j < added.length; j++) {
                    var n = added[j];
                    if (n.nodeType !== 1) continue;
                    if (n.matches && n.matches('select.dentist-select')) fillSelect(n);
                    else if (n.querySelectorAll) fillAll(n);
                }
            }
        }).observe(document.documentElement, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', load);
    else load();
})();