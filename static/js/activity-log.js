/* Activity Log (admin). Read-only list of what the admin / dentist did.
   Data comes from GET /admin/activity_log, which returns whole days (one
   Firestore read per day), so every filter below runs in the browser and
   costs nothing. Loads the first time the card is on screen. */
(function () {
    'use strict';

    var CATEGORY_LABELS = {
        patients: 'Patients',
        billing: 'Billing',
        appointments: 'Appointments',
        calendar: 'Calendar',
        security: 'Sign-in'
    };

    var state = {
        entries: [],
        seen: {},
        nextEnd: null,
        hasMore: false,
        loading: false,
        loaded: false,
        oldest: '',
        newest: '',
        category: 'all',
        admin: 'all',
        retentionDays: 365
    };

    function $(id) { return document.getElementById(id); }

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text !== undefined && text !== null) n.textContent = text;
        return n;
    }

    function manilaDay(iso) {
        try {
            return new Date(iso).toLocaleDateString('en-CA', { timeZone: 'Asia/Manila' });
        } catch (e) { return String(iso).slice(0, 10); }
    }

    function manilaTime(iso) {
        try {
            return new Date(iso).toLocaleTimeString('en-US', {
                timeZone: 'Asia/Manila', hour: 'numeric', minute: '2-digit'
            });
        } catch (e) { return ''; }
    }

    function prettyDay(ymd) {
        var p = String(ymd).split('-');
        if (p.length !== 3) return ymd;
        var d = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2]));
        return d.toLocaleDateString('en-US', {
            timeZone: 'UTC', weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
        });
    }

    var ROLE_LABELS = { developer: 'Developer', dentist: 'Dentist', admin: 'Admin' };

    function roleOf(e) {
        return ROLE_LABELS[e.actor_role] ? e.actor_role : 'admin';
    }

    function staffName(e) {
        return e.actor_name || e.actor_email || 'Unknown';
    }

    function setStatus(text) {
        var s = $('activityStatus');
        if (s) s.textContent = text || '';
    }

    function setBody(message) {
        var body = $('activityTableBody');
        if (!body) return;
        body.textContent = '';
        var tr = el('tr');
        var td = el('td', 'unpaid-empty', message);
        td.colSpan = 5;
        tr.appendChild(td);
        body.appendChild(tr);
    }

    function filtered() {
        var q = (($('activitySearch') || {}).value || '').trim().toLowerCase();
        return state.entries.filter(function (e) {
            if (state.category !== 'all' && e.category !== state.category) return false;
            if (state.admin !== 'all' && staffName(e) !== state.admin) return false;
            if (q) {
                var hay = [e.target, e.detail, e.action, staffName(e)].join(' ').toLowerCase();
                if (hay.indexOf(q) === -1) return false;
            }
            return true;
        });
    }

    function fillAdminSelect() {
        var menu = $('activityAdminMenu');
        if (!menu) return;
        var names = {};
        var roles = {};
        state.entries.forEach(function (e) {
            var n = staffName(e);
            names[n] = true;
            roles[n] = roleOf(e);
        });
        var list = Object.keys(names).sort();
        menu.textContent = '';
        appendAdminOption(menu, 'all', 'All staff', 'admin');
        list.forEach(function (n) {
            appendAdminOption(menu, n, n + ' (' + (ROLE_LABELS[roles[n]] || roles[n]) + ')', roles[n]);
        });
        if (state.admin !== 'all' && list.indexOf(state.admin) === -1) state.admin = 'all';
        updateAdminLabel();
        highlightAdminOption();
    }

    function appendAdminOption(menu, val, text, role) {
        var b = el('button', 'activity-select__option', text);
        b.type = 'button';
        b.setAttribute('role', 'option');
        b.setAttribute('data-value', val);
        b.setAttribute('data-role', role || 'admin');
        b.onclick = function () {
            setActivityAdmin(val);
            closeActivityAdminMenu();
        };
        menu.appendChild(b);
    }

    function updateAdminLabel() {
        var label = $('activityAdminLabel');
        if (!label) return;
        label.textContent = state.admin === 'all' ? 'All staff' : state.admin;
    }

    function highlightAdminOption() {
        var menu = $('activityAdminMenu');
        if (!menu) return;
        Array.prototype.forEach.call(menu.querySelectorAll('.activity-select__option'), function (b) {
            var v = b.getAttribute('data-value');
            b.classList.toggle('is-selected', v === state.admin);
            b.setAttribute('aria-selected', v === state.admin ? 'true' : 'false');
        });
    }

    function positionMenu(menu, btn) {
        if (!menu || !btn) return;
        var rect = btn.getBoundingClientRect();
        menu.style.position = 'fixed';
        menu.style.top = (rect.bottom + 6) + 'px';
        menu.style.left = rect.left + 'px';
        menu.style.width = rect.width + 'px';
        menu.style.right = 'auto';
    }

    function toggleActivityAdminMenu() {
        var menu = $('activityAdminMenu');
        var btn = $('activityAdminBtn');
        if (!menu || !btn) return;
        var open = menu.hasAttribute('hidden');
        if (open) {
            closeActivityRangeMenu();
            positionMenu(menu, btn);
            menu.removeAttribute('hidden');
            btn.setAttribute('aria-expanded', 'true');
        } else {
            menu.setAttribute('hidden', '');
            btn.setAttribute('aria-expanded', 'false');
        }
    }

    function closeActivityAdminMenu() {
        var menu = $('activityAdminMenu');
        var btn = $('activityAdminBtn');
        if (menu) menu.setAttribute('hidden', '');
        if (btn) btn.setAttribute('aria-expanded', 'false');
    }

    function setActivityRangeLabel(text) {
        var label = $('activityRangeLabel');
        if (label) label.textContent = text;
    }

    function highlightRangeOption() {
        var menu = $('activityRangeMenu');
        var preset = $('activityRangePreset');
        if (!menu || !preset) return;
        var val = preset.value;
        Array.prototype.forEach.call(menu.querySelectorAll('.activity-select__option'), function (b) {
            var v = b.getAttribute('data-value');
            b.classList.toggle('is-selected', v === val);
            b.setAttribute('aria-selected', v === val ? 'true' : 'false');
        });
    }

    function toggleActivityRangeMenu() {
        var menu = $('activityRangeMenu');
        var btn = $('activityRangeBtn');
        if (!menu || !btn) return;
        var open = menu.hasAttribute('hidden');
        if (open) {
            closeActivityAdminMenu();
            positionMenu(menu, btn);
            menu.removeAttribute('hidden');
            btn.setAttribute('aria-expanded', 'true');
        } else {
            menu.setAttribute('hidden', '');
            btn.setAttribute('aria-expanded', 'false');
        }
    }

    function closeActivityRangeMenu() {
        var menu = $('activityRangeMenu');
        var btn = $('activityRangeBtn');
        if (menu) menu.setAttribute('hidden', '');
        if (btn) btn.setAttribute('aria-expanded', 'false');
    }

    function renderActivityLog() {
        var body = $('activityTableBody');
        if (!body) return;
        var rows = filtered();
        var more = $('activityMoreBtn');
        if (more) more.style.display = state.hasMore ? '' : 'none';

        if (!state.loaded) return;
        if (!rows.length) {
            setBody(state.entries.length
                ? 'No activity matches these filters.'
                : 'No activity recorded in this period.');
        } else {
            body.textContent = '';
            var lastDay = '';
            rows.forEach(function (e) {
                var day = manilaDay(e.ts);
                if (day !== lastDay) {
                    lastDay = day;
                    var dr = el('tr', 'act-day');
                    var dc = el('td', '', prettyDay(day));
                    dc.colSpan = 5;
                    dr.appendChild(dc);
                    body.appendChild(dr);
                }
                var tr = el('tr');
                tr.appendChild(el('td', 'act-time', manilaTime(e.ts)));
                var tdS = el('td', 'act-staff', staffName(e));
                tdS.appendChild(el('span', 'role-badge role-' + roleOf(e), ROLE_LABELS[roleOf(e)]));
                tr.appendChild(tdS);
                var tdA = el('td');
                tdA.appendChild(el('span', 'act-badge cat-' + e.category, CATEGORY_LABELS[e.category] || e.category));
                tdA.appendChild(document.createTextNode(e.action));
                tr.appendChild(tdA);
                tr.appendChild(el('td', '', e.target || '\u2014'));
                tr.appendChild(el('td', 'act-detail', e.detail || ''));
                body.appendChild(tr);
            });
        }

        var span = state.oldest && state.newest
            ? ' from ' + prettyDay(state.oldest) + ' to ' + prettyDay(state.newest)
            : '';
        setStatus('Showing ' + rows.length + ' of ' + state.entries.length + ' entries' + span +
            (state.hasMore ? '' : ' (the log goes back ' + state.retentionDays + ' days).'));
    }

    function addDays(ymd, n) {
        var p = ymd.split('-');
        var d = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2] + n));
        return d.toISOString().slice(0, 10);
    }

    function daysBetween(a, b) {
        var pa = a.split('-'), pb = b.split('-');
        return Math.round((Date.UTC(+pb[0], +pb[1] - 1, +pb[2]) - Date.UTC(+pa[0], +pa[1] - 1, +pa[2])) / 86400000);
    }

    // reset=true starts over (first load / new date range); false appends older days.
    function load(reset, end, days) {
        if (state.loading) return;
        state.loading = true;
        if (reset) {
            state.entries = [];
            state.seen = {};
            state.loaded = false;
            state.oldest = '';
            state.newest = '';
            setBody('Loading...');
            setStatus('');
        }
        var params = new URLSearchParams();
        var useEnd = reset ? end : state.nextEnd;
        if (useEnd) params.set('end', useEnd);
        params.set('days', String(days || 14));

        var moreBtn = $('activityMoreBtn');
        if (moreBtn) moreBtn.disabled = true;

        fetch('/admin/activity_log?' + params.toString(), {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (r) { return r.json().catch(function () { return {}; }); })
            .then(function (data) {
                if (!data || data.success !== true) {
                    throw new Error((data && data.message) || 'Could not load the activity log.');
                }
                (data.entries || []).forEach(function (e) {
                    if (e.id && state.seen[e.id]) return;
                    if (e.id) state.seen[e.id] = true;
                    state.entries.push(e);
                });
                state.entries.sort(function (a, b) { return a.ts < b.ts ? 1 : (a.ts > b.ts ? -1 : 0); });
                state.nextEnd = data.next_end || null;
                state.hasMore = !!data.has_more;
                state.retentionDays = data.retention_days || state.retentionDays;
                if (!state.newest || data.range_end > state.newest) state.newest = data.range_end;
                if (!state.oldest || data.range_start < state.oldest) state.oldest = data.range_start;
                state.loaded = true;
                if (reset) state.loadedAt = Date.now();
                fillAdminSelect();
                renderActivityLog();
            })
            .catch(function (err) {
                if (reset || !state.loaded) setBody((err && err.message) || 'Could not load the activity log.');
                else setStatus((err && err.message) || 'Could not load more.');
                state.loaded = state.loaded || false;
            })
            .then(function () {
                state.loading = false;
                if (moreBtn) moreBtn.disabled = false;
            });
    }

    function loadActivityLog(reset) {
        load(!!reset, undefined, 14);
    }

    function setActivityCategory(cat) {
        state.category = cat || 'all';
        document.querySelectorAll('#activityCategoryGroup .unpaid-filter-btn').forEach(function (b) {
            b.classList.toggle('active', b.getAttribute('data-cat') === state.category);
        });
        renderActivityLog();
    }

    function setActivityAdmin(name) {
        state.admin = name || 'all';
        updateAdminLabel();
        highlightAdminOption();
        renderActivityLog();
    }

    function applyActivityRange() {
        var from = ($('activityFrom') || {}).value;
        var to = ($('activityTo') || {}).value;
        if (!from && !to) { resetActivityRange(); return; }
        if (!to) to = from;
        if (!from) from = to;
        if (from > to) { var t = from; from = to; to = t; }
        var span = daysBetween(from, to) + 1;
        if (span > 62) {
            from = addDays(to, -61);
            span = 62;
            $('activityFrom').value = from;
        }
        load(true, to, span);
    }

    function resetActivityRange() {
        if ($('activityFrom')) $('activityFrom').value = '';
        if ($('activityTo')) $('activityTo').value = '';
        load(true, undefined, 14);
    }

    /* ---- PDF (what is currently shown, after the filters) ---- */
    function pdfSafe(text) {
        return String(text == null ? '' : text)
            .replace(/\u20b1/g, 'PHP ')
            .replace(/\u00b7/g, '-')
            .replace(/[^\x20-\x7E\xA0-\xFF]/g, '?');
    }

    function downloadActivityLogPDF() {
        var rows = filtered();
        if (!rows.length) {
            if (typeof showToast === 'function') showToast('There is no activity to download.', 'error', 3500);
            return;
        }
        if (!window.jspdf || !window.jspdf.jsPDF) {
            if (typeof showToast === 'function') showToast('PDF tools are still loading. Try again in a moment.', 'error', 3500);
            return;
        }
        var jsPDF = window.jspdf.jsPDF;
        var pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
        var W = pdf.internal.pageSize.getWidth();
        var H = pdf.internal.pageSize.getHeight();
        var M = 12;
        var cols = [
            { t: 'When', x: M, w: 34 },
            { t: 'Staff', x: M + 34, w: 38 },
            { t: 'Action', x: M + 72, w: 62 },
            { t: 'Patient', x: M + 134, w: 40 },
            { t: 'Details', x: M + 174, w: W - M * 2 - 174 }
        ];
        var y = M;

        function header() {
            pdf.setFont('helvetica', 'bold');
            pdf.setFontSize(9);
            pdf.setFillColor(13, 71, 161);
            pdf.rect(M, y - 4.5, W - M * 2, 7, 'F');
            pdf.setTextColor(255, 255, 255);
            cols.forEach(function (c) { pdf.text(c.t, c.x + 1.5, y); });
            pdf.setTextColor(30, 30, 30);
            y += 7;
        }

        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(15);
        pdf.setTextColor(13, 71, 161);
        pdf.text('Capizonda Dental Clinic - Activity Log', M, y + 2);
        y += 9;
        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(9);
        pdf.setTextColor(84, 110, 122);
        var info = [];
        if (state.category !== 'all') info.push('Type: ' + (CATEGORY_LABELS[state.category] || state.category));
        if (state.admin !== 'all') info.push('Staff: ' + state.admin);
        var q = (($('activitySearch') || {}).value || '').trim();
        if (q) info.push('Search: "' + q + '"');
        if (state.oldest && state.newest) info.push(state.oldest + ' to ' + state.newest);
        info.push('Generated ' + new Date().toLocaleString('en-US', { timeZone: 'Asia/Manila' }));
        pdf.text(pdfSafe(info.join('   |   ')), M, y);
        y += 8;
        header();

        pdf.setFontSize(8.5);
        rows.forEach(function (e) {
            var when = manilaDay(e.ts) + ' ' + manilaTime(e.ts);
            var cells = [
                when,
                staffName(e) + ' (' + ROLE_LABELS[roleOf(e)] + ')',
                (CATEGORY_LABELS[e.category] || e.category) + ': ' + e.action,
                e.target || '-',
                e.detail || ''
            ].map(function (txt, i) {
                return pdf.splitTextToSize(pdfSafe(txt), cols[i].w - 3);
            });
            var lines = Math.max.apply(null, cells.map(function (c) { return c.length; }));
            var h = lines * 4 + 2.5;
            if (y + h > H - M) {
                pdf.addPage();
                y = M;
                header();
                pdf.setFontSize(8.5);
            }
            pdf.setFont('helvetica', 'normal');
            pdf.setTextColor(30, 30, 30);
            cells.forEach(function (c, i) { pdf.text(c, cols[i].x + 1.5, y); });
            pdf.setDrawColor(225, 230, 235);
            pdf.line(M, y + h - 3.6, W - M, y + h - 3.6);
            y += h;
        });

        pdf.save('activity-log-' + new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Manila' }) + '.pdf');
    }

    // Called each time the section is opened. The first open is handled by the
    // observer below; later opens refresh the default view if it is over a
    // minute old. A custom date range is left alone.
    function activityLogOpened() {
        if (!state.loaded || state.loading) return;
        var custom = (($('activityFrom') || {}).value || ($('activityTo') || {}).value);
        if (custom) return;
        if (Date.now() - (state.loadedAt || 0) < 60000) return;
        loadActivityLog(true);
    }

    function todayYMD() {
        return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Manila' });
    }

    function addDaysYMD(ymd, n) {
        var p = ymd.split('-');
        var d = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2] + n));
        return d.toISOString().slice(0, 10);
    }

    function applyActivityPreset(val) {
        var from = $('activityFrom');
        var to = $('activityTo');
        var preset = $('activityRangePreset');
        if (!from || !to) return;
        val = val || (preset ? preset.value : '14');
        if (val === 'custom') {
            setActivityRangeLabel('Custom');
            return;
        }
        var labels = { '7': 'Last 7 days', '14': 'Last 14 days', '30': 'Last 30 days', '60': 'Last 60 days', '90': 'Last 90 days', 'month': 'This month' };
        setActivityRangeLabel(labels[val] || val);
        var t = todayYMD();
        if (val === 'month') {
            var p = t.split('-');
            from.value = p[0] + '-' + p[1] + '-01';
            to.value = t;
        } else {
            var n = parseInt(val, 10);
            if (isNaN(n) || n < 1) n = 14;
            from.value = addDaysYMD(t, -(n - 1));
            to.value = t;
        }
        if (preset) preset.value = val;
        highlightRangeOption();
        applyActivityRange();
    }

    function onActivityDateChange() {
        var preset = $('activityRangePreset');
        if (preset) preset.value = 'custom';
        setActivityRangeLabel('Custom');
        highlightRangeOption();
    }

    function resetActivityRange() {
        if ($('activityFrom')) $('activityFrom').value = '';
        if ($('activityTo')) $('activityTo').value = '';
        var preset = $('activityRangePreset');
        if (preset) preset.value = '14';
        setActivityRangeLabel('Last 14 days');
        highlightRangeOption();
        load(true, undefined, 14);
    }
    function initActivityDatePickers() {
        if (typeof flatpickr !== 'function') return;
        ['activityFrom', 'activityTo'].forEach(function (id) {
            var input = $(id);
            if (!input || input._flatpickr) return;
            flatpickr(input, {
                dateFormat: 'Y-m-d',
                allowInput: true,
                clickOpens: true,
                disableMobile: true,
                onChange: function () { onActivityDateChange(); }
            });
        });
    }

    window.loadActivityLog = loadActivityLog;
    window.activityLogOpened = activityLogOpened;
    window.renderActivityLog = renderActivityLog;
    window.setActivityCategory = setActivityCategory;
    window.setActivityAdmin = setActivityAdmin;
    window.applyActivityRange = applyActivityRange;
    window.applyActivityPreset = applyActivityPreset;
    window.resetActivityRange = resetActivityRange;
    window.toggleActivityAdminMenu = toggleActivityAdminMenu;
    window.closeActivityAdminMenu = closeActivityAdminMenu;
    window.toggleActivityRangeMenu = toggleActivityRangeMenu;
    window.closeActivityRangeMenu = closeActivityRangeMenu;
    window.onActivityDateChange = onActivityDateChange;
    window.downloadActivityLogPDF = downloadActivityLogPDF;

    // First load when the card is really on screen (the section starts hidden).
    document.addEventListener('DOMContentLoaded', function () {
        initActivityDatePickers();
        document.addEventListener('click', function (e) {
            var adminWrap = $('activityAdminWrap');
            var rangeWrap = $('activityRangeWrap');
            if (adminWrap && !adminWrap.contains(e.target)) closeActivityAdminMenu();
            if (rangeWrap && !rangeWrap.contains(e.target)) closeActivityRangeMenu();
        });
        window.addEventListener('scroll', function () {
            closeActivityAdminMenu();
            closeActivityRangeMenu();
        }, true);
        var card = $('activityLogCard');
        if (!card) return;
        var start = function () { if (!state.loaded && !state.loading) loadActivityLog(true); };
        if ('IntersectionObserver' in window) {
            var io = new IntersectionObserver(function (items) {
                if (items.some(function (i) { return i.isIntersecting; })) { io.disconnect(); start(); }
            });
            io.observe(card);
        } else {
            start();
        }
    });
})();