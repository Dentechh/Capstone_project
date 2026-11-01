/* Reminders section: follow-up visits from the treatment records, for
   patients with and without an account. Talks to /admin/reminders/*. */
(function () {
    'use strict';
    var section = document.getElementById('section-reminders');
    if (!section) return;

    var PAGE = 25;
    var MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var ACTIVE = { awaiting: 1, contacted: 1, needs_review: 1 };
    var BOOKED = { booked: 1, auto_booked: 1, accepted: 1, rescheduled: 1 };
    var CLOSED = { rejected: 1, expired: 1, cancelled: 1 };

    var $ = function (id) { return document.getElementById(id); };
    var body = $('remBody'), emptyEl = $('remEmpty'), moreBtn = $('remMore');
    var searchEl = $('remSearch'), procEl = $('remProcedure'), acctEl = $('remAccount'), rangeEl = $('remRange');
    var markAll = $('remMarkAll'), tabsEl = $('remTabs'), badge = $('adminRemindersBadge');

    var rows = [], tab = 'all', shown = PAGE, loadedOnce = false;

    /* ---------- helpers ---------- */
    function csrf() {
        var m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.content : '';
    }
    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text != null) e.textContent = text;
        return e;
    }
    function icon(name) {
        var s = el('span', 'material-symbols-rounded', name);
        s.setAttribute('aria-hidden', 'true');
        return s;
    }
    function toast(msg, type) {
        if (typeof window.showToast === 'function') window.showToast(msg, type || 'success', 4000);
        else window.alert(msg);
    }
    function todayStr() {
        var d = new Date();
        return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
    }
    function fmt(raw) {
        var m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?/.exec(String(raw || ''));
        if (!m) return String(raw || '');
        var out = MONTHS[+m[2] - 1] + ' ' + (+m[3]) + ', ' + m[1];
        if (m[4] !== undefined) {
            var h = +m[4];
            out += ' \u00b7 ' + ((h % 12) || 12) + ':' + m[5] + ' ' + (h >= 12 ? 'PM' : 'AM');
        }
        return out;
    }
    function post(url, data) {
        var p = new URLSearchParams();
        Object.keys(data).forEach(function (k) { p.append(k, data[k]); });
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': csrf(), 'X-Requested-With': 'fetch' },
            body: p.toString()
        }).then(function (res) { return res.json().catch(function () { return { success: false, message: 'Something went wrong.' }; }); });
    }
    function isActive(r) { return !!ACTIVE[r.status]; }
    function isOverdue(r) { return isActive(r) && r.appointment_date && r.appointment_date < todayStr(); }
    function category(r, t) {
        switch (t) {
            case 'call': return (!r.has_account && r.status === 'awaiting') || r.status === 'needs_review';
            case 'wait': return (r.has_account && r.status === 'awaiting') || r.status === 'contacted';
            case 'overdue': return isOverdue(r);
            case 'booked': return !!BOOKED[r.status];
            case 'closed': return !!CLOSED[r.status];
            default: return true;
        }
    }

    /* ---------- status text ---------- */
    function describe(r) {
        var left = r.days_left;
        var leftTxt = left === null || left === undefined ? '' : (left <= 1 ? ' \u2013 last day' : ' \u2013 ' + left + ' days left');
        switch (r.status) {
            case 'awaiting':
                if (r.managed_by_patient) return { cls: 'wait', text: 'Awaiting patient response' + leftTxt, detail: 'If there is no reply, it is booked automatically.' };
                if (!r.has_account) return { cls: 'wait', text: 'Needs a call' + leftTxt, detail: 'If nobody books it, it is booked automatically.' };
                return { cls: 'wait', text: 'Suggested in the patient\u2019s schedule', detail: 'You can also call the patient and book it here.' };
            case 'contacted':
                return { cls: 'info', text: 'Contacted' + leftTxt, detail: 'If nobody books it, it is booked automatically.' };
            case 'accepted':
                return { cls: 'info', text: 'Patient accepted ' + fmt(r.chosen_appointment_date), detail: 'Waiting in Appointments for you to accept.' };
            case 'rescheduled':
                return { cls: 'info', text: 'Patient asked to move it to ' + fmt(r.chosen_appointment_date), detail: 'Waiting in Appointments for your approval.' };
            case 'booked':
                return { cls: 'ok', text: 'Booked for ' + fmt(r.chosen_appointment_date), detail: '' };
            case 'auto_booked':
                return { cls: 'ok', text: 'Booked automatically for ' + fmt(r.chosen_appointment_date),
                    detail: r.has_account ? 'The patient did not reply in time.' : 'Not confirmed with the patient yet. Please call to confirm.' };
            case 'rejected':
                return { cls: 'bad', text: 'Rejected by patient', detail: r.reason ? 'Reason: ' + r.reason : 'No reason given.' };
            case 'expired':
                return { cls: 'bad', text: 'Expired without a reply', detail: 'The due date passed before it was booked.' };
            case 'cancelled':
                return { cls: 'bad', text: 'Cancelled', detail: '' };
            case 'needs_review':
                return { cls: 'bad', text: 'Could not book automatically', detail: 'No saved patient details. Please book it manually.' };
            default:
                return { cls: 'info', text: r.status || '', detail: '' };
        }
    }

    /* ---------- filtering / rendering ---------- */
    function baseFiltered() {
        var q = searchEl.value.trim().toLowerCase();
        var proc = procEl.value, acct = acctEl.value, range = parseInt(rangeEl.value, 10) || 0;
        var limit = '';
        if (range) {
            var d = new Date(); d.setDate(d.getDate() + range);
            limit = d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
        }
        return rows.filter(function (r) {
            if (q && (r.patient_name + ' ' + r.procedure).toLowerCase().indexOf(q) === -1) return false;
            if (proc && r.procedure !== proc) return false;
            if (acct === 'yes' && !r.has_account) return false;
            if (acct === 'no' && r.has_account) return false;
            if (limit && !(r.appointment_date <= limit)) return false;
            return true;
        });
    }
    function rank(r) { return isActive(r) ? 0 : (BOOKED[r.status] ? 1 : 2); }
    function sortRows(list) {
        return list.slice().sort(function (a, b) {
            var ra = rank(a), rb = rank(b);
            if (ra !== rb) return ra - rb;
            if (ra === 0) return a.appointment_date < b.appointment_date ? -1 : a.appointment_date > b.appointment_date ? 1 : 0;
            return a.appointment_date < b.appointment_date ? 1 : a.appointment_date > b.appointment_date ? -1 : 0;
        });
    }

    function fillProcedures() {
        var cur = procEl.value;
        var names = {};
        rows.forEach(function (r) { if (r.procedure) names[r.procedure] = 1; });
        procEl.innerHTML = '';
        var all = el('option', null, 'All procedures'); all.value = '';
        procEl.appendChild(all);
        Object.keys(names).sort().forEach(function (n) {
            var o = el('option', null, n); o.value = n; procEl.appendChild(o);
        });
        procEl.value = names[cur] ? cur : '';
    }

    // Copy text to the clipboard (works on desktops that cannot open tel:/sms: links).
    function copyText(value, okMsg) {
        function fallback() {
            var ta = document.createElement('textarea');
            ta.value = value; ta.setAttribute('readonly', '');
            ta.style.position = 'fixed'; ta.style.opacity = '0';
            document.body.appendChild(ta); ta.select();
            var ok = false;
            try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
            document.body.removeChild(ta);
            toast(ok ? okMsg : 'Could not copy. Please select and copy it manually.', ok ? 'success' : 'error');
        }
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(value).then(function () { toast(okMsg); }, fallback);
        } else {
            fallback();
        }
    }

    function mailLink(r) {
        var subject = 'Follow-up reminder: ' + r.procedure;
        var body = 'Hello ' + r.patient_name + ',\n\nThis is Capizonda Dental Clinic. Your ' + r.procedure +
            ' follow-up is due on ' + fmt(r.appointment_date) + '. Please reply to confirm your schedule.\n\nThank you!';
        var a = el('a', 'rem-link rem-link--mail');
        a.href = 'mailto:' + r.email + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body);
        a.title = r.email;
        a.appendChild(icon('mail'));
        a.appendChild(el('span', 'rem-mail__txt', r.email));
        return a;
    }

    function contactCell(r) {
        var td = el('td'); td.setAttribute('data-cell', 'contact');
        var wrap = el('div', 'rem-contact');
        if (r.contact_number) {
            wrap.appendChild(el('span', 'rem-contact__num', r.contact_number));
            var tel = r.contact_number.replace(/[^0-9+]/g, '');
            var msg = 'Hello ' + r.patient_name + ', this is Capizonda Dental Clinic. Your ' + r.procedure +
                ' follow-up is due on ' + fmt(r.appointment_date) + '. Please reply to confirm your schedule. Thank you!';
            var row = el('div', 'rem-contact__row');
            var call = el('a', 'rem-link'); call.href = 'tel:' + tel;
            call.appendChild(icon('call')); call.appendChild(document.createTextNode('Call'));
            var text = el('a', 'rem-link'); text.href = 'sms:' + tel + '?&body=' + encodeURIComponent(msg);
            text.appendChild(icon('sms')); text.appendChild(document.createTextNode('Text'));
            var copyNum = el('button', 'rem-link rem-link--icon'); copyNum.type = 'button';
            copyNum.title = 'Copy number'; copyNum.setAttribute('aria-label', 'Copy number');
            copyNum.appendChild(icon('content_copy'));
            copyNum.addEventListener('click', function () { copyText(r.contact_number, 'Number copied.'); });
            var copyMsg = el('button', 'rem-link rem-link--icon'); copyMsg.type = 'button';
            copyMsg.title = 'Copy message'; copyMsg.setAttribute('aria-label', 'Copy message');
            copyMsg.appendChild(icon('copy_all'));
            copyMsg.addEventListener('click', function () { copyText(msg, 'Message copied.'); });
            row.appendChild(call); row.appendChild(text);
            row.appendChild(copyNum); row.appendChild(copyMsg);
            wrap.appendChild(row);
            if (r.email) wrap.appendChild(mailLink(r));
        } else {
            if (r.email) {
                wrap.appendChild(mailLink(r));
            } else {
                wrap.appendChild(el('span', 'rem-muted', 'No contact number yet'));
            }
            var add = el('button', 'rem-link'); add.type = 'button';
            add.appendChild(icon('add_call')); add.appendChild(document.createTextNode('Add number'));
            add.addEventListener('click', function () { openNumber(r); });
            wrap.appendChild(add);
        }
        td.appendChild(wrap);
        return td;
    }

    function actionCell(r) {
        var td = el('td'); td.setAttribute('data-cell', 'action');
        var box = el('div', 'rem-actions');
        function btn(label, cls, fn) {
            var b = el('button', 'btn-action ' + (cls || ''), label); b.type = 'button';
            b.addEventListener('click', fn); box.appendChild(b);
        }
        if (isActive(r) && !r.managed_by_patient) {
            if (r.status === 'awaiting') btn('Mark contacted', '', function () { act('/admin/reminders/contacted', { id: r.id }, 'Marked as contacted.'); });
            btn('Book', 'accept', function () { openBook(r); });
            btn('Cancel', 'delete', function () {
                askConfirm('The ' + r.procedure + ' follow-up for ' + r.patient_name + ' (due ' + fmt(r.appointment_date) +
                    ') will be removed from the list.').then(function (yes) {
                    if (yes) act('/admin/reminders/cancel', { id: r.id }, 'Reminder cancelled.');
                });
            });
        }
        if (r.unseen) {
            btn('Mark as read', '', function () {
                if (r.managed_by_patient) act('/admin/braces_proposals/seen', { uid: r.uid }, null);
                else act('/admin/reminders/seen', { id: r.id }, null);
            });
        }
        td.appendChild(box);
        return td;
    }

    function render() {
        var base = baseFiltered();
        ['all', 'call', 'wait', 'overdue', 'booked', 'closed'].forEach(function (t) {
            var n = base.filter(function (r) { return category(r, t); }).length;
            var s = tabsEl.querySelector('[data-n="' + t + '"]');
            if (s) s.textContent = String(n);
        });
        var list = sortRows(base.filter(function (r) { return category(r, tab); }));
        body.innerHTML = '';
        list.slice(0, shown).forEach(function (r) {
            var tr = el('tr', r.unseen ? 'is-unseen' : '');
            var name = el('td'); name.setAttribute('data-cell', 'patient');
            name.appendChild(el('span', 'rem-name', r.patient_name));
            name.appendChild(el('span', 'rem-acct rem-acct--' + (r.has_account ? 'yes' : 'no'), r.has_account ? 'Has account' : 'No account'));
            tr.appendChild(name);

            var proc = el('td'); proc.setAttribute('data-cell', 'procedure');
            proc.appendChild(el('span', 'rem-proc', r.procedure));
            if (r.dentist) proc.appendChild(el('span', 'rem-detail', r.dentist));
            tr.appendChild(proc);

            var due = el('td'); due.setAttribute('data-cell', 'due');
            var dueTxt = fmt(r.appointment_date + (r.appointment_time ? ' ' + r.appointment_time : ''));
            due.appendChild(el('span', isOverdue(r) ? 'rem-due--overdue' : '', dueTxt));
            if (isOverdue(r)) due.appendChild(el('span', 'rem-detail', 'Overdue'));
            tr.appendChild(due);

            var d = describe(r);
            var st = el('td'); st.setAttribute('data-cell', 'status');
            st.appendChild(el('span', 'rem-pill rem-pill--' + d.cls, d.text));
            if (d.detail) st.appendChild(el('span', 'rem-detail', d.detail));
            tr.appendChild(st);

            tr.appendChild(contactCell(r));
            tr.appendChild(actionCell(r));
            body.appendChild(tr);
        });
        emptyEl.hidden = list.length !== 0;
        moreBtn.hidden = list.length <= shown;
        var unseenCount = rows.filter(function (r) { return r.unseen; }).length;
        markAll.hidden = unseenCount === 0;
    }

    /* ---------- data ---------- */
    function setBadge(n) {
        if (!badge) return;
        badge.hidden = !n;
        badge.textContent = n > 9 ? '9+' : String(n || '');
    }
    function refreshBadge() {
        return fetch('/admin/reminders/count', { credentials: 'same-origin' })
            .then(function (res) { return res.json(); })
            .then(function (d) { if (d && d.success) setBadge(d.count || 0); })
            .catch(function () { /* badge is best-effort */ });
    }
    function load() {
        return fetch('/admin/reminders', { credentials: 'same-origin' })
            .then(function (res) { return res.json(); })
            .then(function (d) {
                if (!d || !d.success) { toast((d && d.message) || 'Could not load reminders.', 'error'); return; }
                rows = d.rows || [];
                loadedOnce = true;
                fillProcedures();
                render();
                refreshBadge();
            })
            .catch(function (e) { console.error('Reminders failed to load:', e); });
    }
    function act(url, data, okMsg) {
        return post(url, data).then(function (d) {
            if (d && d.success) { if (okMsg) toast(okMsg); }
            else toast((d && d.message) || 'Something went wrong.', 'error');
            return load();
        });
    }


    /* ---------- confirm dialog (replaces the browser's own confirm box) ---------- */
    var confDlg = $('remConfirmDialog'), confResolve = null;
    function askConfirm(message) {
        $('remConfirmMsg').textContent = message;
        confDlg.showModal();
        return new Promise(function (resolve) { confResolve = resolve; });
    }
    function closeConfirm(answer) {
        if (confDlg.open) confDlg.close();
        if (confResolve) { var f = confResolve; confResolve = null; f(answer); }
    }
    $('remConfirmYes').addEventListener('click', function () { closeConfirm(true); });
    $('remConfirmNo').addEventListener('click', function () { closeConfirm(false); });
    confDlg.addEventListener('cancel', function () { closeConfirm(false); });   // Esc key
    confDlg.addEventListener('click', function (e) { if (e.target === confDlg) closeConfirm(false); });

    /* ---------- book dialog ---------- */
    var bookDlg = $('remBookDialog'), bookDate = $('remBookDate'), bookTime = $('remBookTime');
    var bookErr = $('remBookErr'), bookSave = $('remBookSave'), bookRow = null;

    function bookError(msg) { bookErr.textContent = msg || ''; bookErr.hidden = !msg; }
    function loadTimes(preferred) {
        bookTime.innerHTML = ''; bookSave.disabled = true; bookError('');
        if (!bookDate.value) return;
        fetch('/admin/reminders/open_times?date=' + encodeURIComponent(bookDate.value) +
              '&dentist=' + encodeURIComponent(bookRow.dentist || ''), { credentials: 'same-origin' })
            .then(function (res) { return res.json(); })
            .then(function (d) {
                if (!d || !d.success) { bookError((d && d.message) || 'Could not load open times.'); return; }
                if (!d.times.length) { bookError('No open times on this day. Pick another date.'); return; }
                d.times.forEach(function (t) {
                    var h = +t.slice(0, 2);
                    var o = el('option', null, ((h % 12) || 12) + ':' + t.slice(3) + ' ' + (h >= 12 ? 'PM' : 'AM'));
                    o.value = t; bookTime.appendChild(o);
                });
                if (preferred && d.times.indexOf(preferred) !== -1) bookTime.value = preferred;
                bookSave.disabled = false;
            })
            .catch(function () { bookError('Could not load open times.'); });
    }
    function openBook(r) {
        bookRow = r;
        $('remBookTitle').textContent = 'Book ' + r.procedure;
        $('remBookSub').textContent = r.patient_name + ' \u00b7 due ' + fmt(r.appointment_date) + (r.dentist ? ' \u00b7 ' + r.dentist : '');
        var t = todayStr();
        var start = r.appointment_date >= t ? r.appointment_date : t;
        initPicker();
        if (bookFp) bookFp.setDate(start, false);
        else { bookDate.min = t; bookDate.value = start; }
        loadTimes(r.appointment_time);
        bookDlg.showModal();
    }
    // Calendar picker (flatpickr, already on this page): shows "Dec 1, 2026" so the
    // day and month can never be misread, whatever the computer's region setting is.
    var bookFp = null;
    function initPicker() {
        if (bookFp || !window.flatpickr) return;
        bookFp = window.flatpickr(bookDate, {
            dateFormat: 'Y-m-d', altInput: true, altFormat: 'F j, Y', altInputClass: '',
            minDate: 'today', disableMobile: true, static: true, allowInput: false,
            onChange: function () { loadTimes(bookRow && bookRow.appointment_time); }
        });
    }
    bookDate.addEventListener('change', function () { if (!bookFp) loadTimes(bookRow && bookRow.appointment_time); });
    $('remBookCancel').addEventListener('click', function () { bookDlg.close(); });
    bookSave.addEventListener('click', function () {
        if (!bookRow || !bookDate.value || !bookTime.value) return;
        bookSave.disabled = true;
        post('/admin/reminders/book', { id: bookRow.id, date: bookDate.value, time: bookTime.value }).then(function (d) {
            if (d && d.success) {
                bookDlg.close();
                toast('Follow-up booked for ' + fmt(d.chosen) + '.');
                load();
            } else {
                bookError((d && d.message) || 'Could not book this visit.');
                bookSave.disabled = false;
            }
        });
    });

    /* ---------- add number dialog ---------- */
    var numDlg = $('remNumberDialog'), numInput = $('remNumberInput'), numErr = $('remNumberErr'), numRow = null;
    function openNumber(r) {
        numRow = r; numInput.value = ''; numErr.hidden = true;
        $('remNumberSub').textContent = r.patient_name + '. This is also saved to My Patients.';
        numDlg.showModal(); numInput.focus();
    }
    $('remNumberCancel').addEventListener('click', function () { numDlg.close(); });
    $('remNumberSave').addEventListener('click', function () {
        if (!numRow) return;
        post('/admin/reminders/contact_number', { uid: numRow.uid, patient_id: numRow.patient_id, number: numInput.value }).then(function (d) {
            if (d && d.success) { numDlg.close(); toast('Contact number saved.'); load(); }
            else { numErr.textContent = (d && d.message) || 'Could not save the number.'; numErr.hidden = false; }
        });
    });


    // Page heading: set it to "Reminders" whenever this section opens.
    function setPageTitle() {
        var heads = document.querySelectorAll('.main-content h1, .main-content h2, .main-content .page-title');
        for (var i = 0; i < heads.length; i++) {
            if (heads[i].closest('.content-section') || heads[i].closest('dialog')) continue;
            var nodes = [];
            var w = document.createTreeWalker(heads[i], NodeFilter.SHOW_TEXT);
            while (w.nextNode()) if (w.currentNode.nodeValue.trim()) nodes.push(w.currentNode);
            if (nodes.length) { nodes[nodes.length - 1].nodeValue = 'Reminders'; return; }
        }
    }

    /* ---------- wiring ---------- */
    tabsEl.addEventListener('click', function (e) {
        var b = e.target.closest('.rem-tab'); if (!b) return;
        tab = b.getAttribute('data-tab'); shown = PAGE;
        Array.prototype.forEach.call(tabsEl.querySelectorAll('.rem-tab'), function (x) { x.classList.toggle('is-active', x === b); });
        render();
    });
    [procEl, acctEl, rangeEl].forEach(function (c) { c.addEventListener('change', function () { shown = PAGE; render(); }); });
    var t = null;
    searchEl.addEventListener('input', function () { clearTimeout(t); t = setTimeout(function () { shown = PAGE; render(); }, 150); });
    moreBtn.addEventListener('click', function () { shown += PAGE; render(); });
    markAll.addEventListener('click', function () {
        Promise.all([post('/admin/reminders/seen', { id: 'all' }), post('/admin/braces_proposals/seen', { uid: 'all' })]).then(load);
    });

    // Reload each time the section is opened.
    if ('MutationObserver' in window) {
        var wasOpen = section.classList.contains('active-section');
        new MutationObserver(function () {
            var open = section.classList.contains('active-section');
            if (open && !wasOpen) { load(); setPageTitle(); setTimeout(setPageTitle, 60); setTimeout(setPageTitle, 250); }
            wasOpen = open;
        }).observe(section, { attributes: true, attributeFilter: ['class'] });
        if (wasOpen) { load(); setPageTitle(); }
    }

    // Sidebar badge: once now, then every 2 minutes while the tab is visible.
    refreshBadge();
    setInterval(function () { if (document.visibilityState === 'visible') refreshBadge(); }, 120000);
    window.loadReminders = load;
})();