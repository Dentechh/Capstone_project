/* Settings page.
 *
 * Section 1 - Medicines: the list offered in the Medicine field of the
 * treatment records. The list is kept on the server (Settings/medicines); this
 * file shows it, lets staff add or remove a medicine, and hands the current list
 * to the treatment-record rows so their dropdown always matches it.
 * Removing a medicine never changes a record that was already saved (records
 * keep the medicine as plain text).
 *
 * Section 2 - Dentists: same behaviour for the list offered in the dentist
 * dropdowns (Settings/dentists). The default dentist is always available.
 *
 * Section 3 - Treatments: the services the clinic offers (Settings/treatments).
 *
 * Section 4 - Clinic information: address, phone, email and Facebook link
 * (Settings/clinic_info), shown in the website footers.
 *
 * Section 5 - About page: the dentist section of the public About page
 * (Settings/about_info).
 */
(function () {
    'use strict';

    var section = document.getElementById('section-settings');
    if (!section) return;

    function csrf() {
        var m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.getAttribute('content') : '';
    }
    function toast(message, type) {
        if (typeof window.showToast === 'function') window.showToast(message, type || 'success');
    }
    function el(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text != null) node.textContent = text;
        return node;
    }
    function icon(name) {
        var s = el('span', 'material-symbols-rounded', name);
        s.setAttribute('aria-hidden', 'true');
        return s;
    }

    function post(url, data) {
        var p = new URLSearchParams();
        Object.keys(data).forEach(function (k) { p.append(k, data[k]); });
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': csrf(), 'X-Requested-With': 'fetch' },
            body: p.toString()
        }).then(function (res) {
            return res.json().catch(function () { return { success: false, message: 'Something went wrong.' }; });
        }).catch(function () {
            return { success: false, message: 'Could not reach the server. Please try again.' };
        });
    }

    /* One card = one list. Both cards share this code; the config says which
       elements, which server routes and which dropdown hook belong to it. */
    function setupList(cfg) {
        var form = document.getElementById(cfg.form);
        if (!form) return;
        var input = document.getElementById(cfg.input);
        var addBtn = document.getElementById(cfg.add);
        var errEl = document.getElementById(cfg.err);
        var listEl = document.getElementById(cfg.list);
        var countEl = document.getElementById(cfg.count);
        var items = [];

        function showError(message) {
            errEl.textContent = message || '';
            errEl.hidden = !message;
        }

        /* The list changed (or was just loaded): show it, and give it to the
           dropdowns that use it. */
        function publish(list) {
            items = (list || []).slice();
            if (typeof window[cfg.hook] === 'function') window[cfg.hook](items);
            render();
        }

        function item(name, locked) {
            var li = el('li', 'set-item' + (locked ? ' set-item--locked' : ''));
            var label = el('span', 'set-item__name');
            label.appendChild(icon(locked ? 'lock' : cfg.icon));
            label.appendChild(document.createTextNode(name));
            li.appendChild(label);

            var actions = el('div', 'set-item__actions');
            if (locked) {
                actions.appendChild(el('span', 'set-item__note', 'Always available'));
            } else {
                showRemove(actions, name);
            }
            li.appendChild(actions);
            return li;
        }

        // "Remove" asks once more before anything is deleted.
        function showRemove(actions, name) {
            actions.textContent = '';
            var rm = el('button', 'set-btn set-btn--danger');
            rm.type = 'button';
            rm.appendChild(icon('delete'));
            rm.appendChild(document.createTextNode('Remove'));
            rm.addEventListener('click', function () { showConfirm(actions, name); });
            actions.appendChild(rm);
        }
        function showConfirm(actions, name) {
            actions.textContent = '';
            actions.appendChild(el('span', 'set-item__note', 'Remove it?'));
            var yes = el('button', 'set-btn set-btn--confirm', 'Yes, remove');
            yes.type = 'button';
            var no = el('button', 'set-btn', 'Keep');
            no.type = 'button';
            no.addEventListener('click', function () { showRemove(actions, name); });
            yes.addEventListener('click', function () {
                yes.disabled = true; no.disabled = true;
                post(cfg.url + '/remove', { name: name }).then(function (d) {
                    if (d && d.success) {
                        publish(d[cfg.key]);
                        toast('Removed "' + name + '".');
                    } else {
                        toast((d && d.message) || 'Could not remove it.', 'error');
                        showRemove(actions, name);
                    }
                });
            });
            actions.appendChild(yes);
            actions.appendChild(no);
        }

        function render() {
            countEl.textContent = String(items.length);
            listEl.textContent = '';
            if (cfg.lockedName) listEl.appendChild(item(cfg.lockedName, true));
            items.forEach(function (name) { listEl.appendChild(item(name, false)); });
            if (!items.length) {
                listEl.appendChild(el('li', 'set-empty', cfg.empty));
            }
        }

        function load() {
            return fetch(cfg.url, { credentials: 'same-origin', cache: 'no-store' })
                .then(function (res) { return res.json(); })
                .then(function (d) { if (d && d.success) publish(d[cfg.key]); })
                .catch(function () { /* the built-in list stays in use */ });
        }

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var name = input.value.trim();
            showError('');
            if (!name) { showError(cfg.typeHint); input.focus(); return; }
            addBtn.disabled = true;
            post(cfg.url + '/add', { name: name }).then(function (d) {
                addBtn.disabled = false;
                if (d && d.success) {
                    input.value = '';
                    publish(d[cfg.key]);
                    toast('Added "' + name + '".');
                    input.focus();
                } else {
                    showError((d && d.message) || 'Could not add it.');
                }
            });
        });
        input.addEventListener('input', function () { showError(''); });

        // Re-read the list whenever Settings is opened (another staff member may have changed it).
        if ('MutationObserver' in window) {
            var wasOpen = section.classList.contains('active-section');
            new MutationObserver(function () {
                var open = section.classList.contains('active-section');
                if (open && !wasOpen) load();
                wasOpen = open;
            }).observe(section, { attributes: true, attributeFilter: ['class'] });
        }

        render();
        load();           // also gives the dropdowns the saved list at page load
    }

    setupList({
        form: 'setMedForm', input: 'setMedInput', add: 'setMedAdd', err: 'setMedErr',
        list: 'setMedList', count: 'setMedCount',
        url: '/admin/settings/medicines', key: 'medicines', hook: 'tdSetMedicineOptions',
        icon: 'medication', lockedName: 'None',
        typeHint: 'Type a medicine name.', empty: 'No medicines yet. Add the first one above.'
    });
    setupList({
        form: 'setDenForm', input: 'setDenInput', add: 'setDenAdd', err: 'setDenErr',
        list: 'setDenList', count: 'setDenCount',
        url: '/admin/settings/dentists', key: 'dentists', hook: 'tdSetDentistOptions',
        icon: 'stethoscope', lockedName: 'Dr. Julix Dionne Capizonda',
        typeHint: 'Type a dentist name.', empty: 'No other dentists yet. Add one above.'
    });
    setupList({
        form: 'setTrtForm', input: 'setTrtInput', add: 'setTrtAdd', err: 'setTrtErr',
        list: 'setTrtList', count: 'setTrtCount',
        url: '/admin/settings/treatments', key: 'treatments', hook: 'tdSetTreatmentOptions',
        icon: 'medical_services', lockedName: '',
        typeHint: 'Type a treatment name.', empty: 'No treatments yet. Add the first one above.'
    });
    /* Section 4 - Clinic information: one small form (address, phone, email,
       Facebook link). The server keeps it in Settings/clinic_info and the
       website pages read it, so one save updates every footer. */
    (function setupClinic() {
        var form = document.getElementById('setClinicForm');
        if (!form) return;
        var fields = {
            address: document.getElementById('setClinicAddress'),
            phone: document.getElementById('setClinicPhone'),
            email: document.getElementById('setClinicEmail'),
            facebook: document.getElementById('setClinicFacebook')
        };
        var saveBtn = document.getElementById('setClinicSave');
        var errEl = document.getElementById('setClinicErr');

        function showError(message) {
            errEl.textContent = message || '';
            errEl.hidden = !message;
        }
        function fill(c) {
            Object.keys(fields).forEach(function (k) { fields[k].value = (c && c[k]) || ''; });
        }
        function load() {
            return fetch('/admin/settings/clinic', { credentials: 'same-origin', cache: 'no-store' })
                .then(function (res) { return res.json(); })
                .then(function (d) { if (d && d.success) fill(d.clinic); })
                .catch(function () { /* leave the form as it is */ });
        }

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            showError('');
            var data = {};
            Object.keys(fields).forEach(function (k) { data[k] = fields[k].value.trim(); });
            saveBtn.disabled = true;
            post('/admin/settings/clinic/save', data).then(function (d) {
                saveBtn.disabled = false;
                if (d && d.success) {
                    fill(d.clinic);
                    toast('Clinic information saved.');
                } else {
                    showError((d && d.message) || 'Could not save it.');
                }
            });
        });
        Object.keys(fields).forEach(function (k) {
            fields[k].addEventListener('input', function () { showError(''); });
        });

        if ('MutationObserver' in window) {
            var wasOpen = section.classList.contains('active-section');
            new MutationObserver(function () {
                var open = section.classList.contains('active-section');
                if (open && !wasOpen) load();
                wasOpen = open;
            }).observe(section, { attributes: true, attributeFilter: ['class'] });
        }
        load();
    })();
    /* Section 5 - About page: one form; the server keeps it in
       Settings/about_info and the About page reads it. */
    (function setupAbout() {
        var form = document.getElementById('setAboutForm');
        if (!form) return;
        var fields = {
            dr_name: document.getElementById('setAboutName'),
            dr_title: document.getElementById('setAboutTitle'),
            intro: document.getElementById('setAboutIntro'),
            school: document.getElementById('setAboutSchool'),
            licensed: document.getElementById('setAboutLicensed'),
            association: document.getElementById('setAboutAssoc'),
            technology: document.getElementById('setAboutTech'),
            vision: document.getElementById('setAboutVision'),
            community: document.getElementById('setAboutCommunity')
        };
        var saveBtn = document.getElementById('setAboutSave');
        var errEl = document.getElementById('setAboutErr');

        function showError(message) {
            errEl.textContent = message || '';
            errEl.hidden = !message;
        }
        function fill(a) {
            Object.keys(fields).forEach(function (k) { fields[k].value = (a && a[k]) || ''; });
        }
        function load() {
            return fetch('/admin/settings/about', { credentials: 'same-origin', cache: 'no-store' })
                .then(function (res) { return res.json(); })
                .then(function (d) { if (d && d.success) fill(d.about); })
                .catch(function () { /* leave the form as it is */ });
        }

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            showError('');
            var data = {};
            Object.keys(fields).forEach(function (k) { data[k] = fields[k].value.trim(); });
            saveBtn.disabled = true;
            post('/admin/settings/about/save', data).then(function (d) {
                saveBtn.disabled = false;
                if (d && d.success) {
                    fill(d.about);
                    toast('About page saved.');
                } else {
                    showError((d && d.message) || 'Could not save it.');
                }
            });
        });
        Object.keys(fields).forEach(function (k) {
            fields[k].addEventListener('input', function () { showError(''); });
        });

        if ('MutationObserver' in window) {
            var wasOpen = section.classList.contains('active-section');
            new MutationObserver(function () {
                var open = section.classList.contains('active-section');
                if (open && !wasOpen) load();
                wasOpen = open;
            }).observe(section, { attributes: true, attributeFilter: ['class'] });
        }
        load();
    })();
})();