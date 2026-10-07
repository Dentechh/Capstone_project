(function () {
            const TIME_SLOTS = [
                { value: "09:00", label: "9:00 AM" }, { value: "10:00", label: "10:00 AM" },
                { value: "11:00", label: "11:00 AM" }, { value: "12:00", label: "12:00 PM" },
                { value: "13:00", label: "1:00 PM" }, { value: "14:00", label: "2:00 PM" },
                { value: "15:00", label: "3:00 PM" }, { value: "16:00", label: "4:00 PM" },
                { value: "17:00", label: "5:00 PM" }
            ];

            let blockedMap = {};
            let selectedDate = null;
            let calendarInstance = null;

            let lastDay = { date: null, appts: [], failed: false };
            const SLOT_LABEL = {};
            TIME_SLOTS.forEach(sl => { SLOT_LABEL[sl.value] = sl.label; });

            function esc(t) {
                const d = document.createElement('div');
                d.textContent = t == null ? '' : String(t);
                return d.innerHTML;
            }

            function timeLabel(v) {
                if (SLOT_LABEL[v]) return SLOT_LABEL[v];
                const m = /^(\d{1,2}):(\d{2})$/.exec(v || '');
                if (!m) return v || '';
                let h = Number(m[1]);
                const ap = h >= 12 ? 'PM' : 'AM';
                h = h % 12 || 12;
                return h + ':' + m[2] + ' ' + ap;
            }

            // ---- Block-slot conflict summary (counts only, never a long list of names) ----
            function countLabel(n) {
                return n >= 20 ? '20+' : String(n);
            }

            function apptWord(n) {
                return n === 1 ? 'scheduled appointment' : 'scheduled appointments';
            }

            function conflictMessage(r, fullDay, dateStr) {
                const slots = r.slots || [];
                if (fullDay) {
                    return formatBlockDate(dateStr) + ' already has ' + countLabel(r.total) + ' ' + apptWord(r.total) + '.';
                }
                if (slots.length === 1) {
                    const s0 = slots[0];
                    let msg = timeLabel(s0.time) + ' already has ' + countLabel(s0.count) + ' ' + apptWord(s0.count);
                    if (s0.count === 1 && s0.name) msg += ': ' + s0.name + (s0.accepted ? ' (Accepted)' : ' (Pending)');
                    return msg + '.';
                }
                return 'The selected times already have ' + countLabel(r.total) + ' ' + apptWord(r.total) + '.';
            }

            function conflictDetails(r) {
                const slots = r.slots || [];
                if (slots.length <= 1) return [];
                const MAX_ROWS = 5;
                const rows = slots.slice(0, MAX_ROWS).map(s => [
                    timeLabel(s.time),
                    s.count === 1 && s.name ? s.name : countLabel(s.count) + ' appointments'
                ]);
                if (slots.length > MAX_ROWS) {
                    rows.push(['', '+ ' + (slots.length - MAX_ROWS) + ' more time slots']);
                }
                return rows;
            }

            let scheduleToken = 0;
            async function loadDaySchedule(dateStr) {
                const box = document.getElementById('daySchedule');
                if (!box) return;
                document.getElementById('dayScheduleTitle').textContent = 'Schedule: ' + formatBlockDate(dateStr);
                const token = ++scheduleToken;
                box.innerHTML = '<div class="dc-empty">Loading...</div>';
                let appts = [];
                let failed = false;
                try {
                    const res = await fetch('/admin/day_schedule?date=' + encodeURIComponent(dateStr));
                    const data = await res.json();
                    if (token !== scheduleToken) return;
                    if (data.success) appts = data.appointments || [];
                    else failed = true;
                } catch (err) {
                    if (token !== scheduleToken) return;
                    console.error('Day schedule error:', err);
                    failed = true;
                }
                lastDay = { date: dateStr, appts: appts, failed: failed };
                renderDaySchedule();
            }

            function renderDaySchedule() {
                const box = document.getElementById('daySchedule');
                if (!box || !lastDay.date) return;
                if (lastDay.failed) {
                    box.innerHTML = '<div class="dc-empty">Could not load appointments for this day.</div>';
                    return;
                }

                const info = blockedMap[lastDay.date];
                const isBlocked = t => !!(info && (info.full_day || (info.blocked_times || []).includes(t)));

                const byTime = {};
                lastDay.appts.forEach(a => { (byTime[a.time] = byTime[a.time] || []).push(a); });

                const times = TIME_SLOTS.map(sl => sl.value);
                Object.keys(byTime).forEach(t => { if (!times.includes(t)) times.push(t); });
                times.sort();

                const booked = lastDay.appts.length;
                const blockedCount = times.filter(isBlocked).length;
                let html = '<div class="dc-summary">' + booked + ' appointment' + (booked === 1 ? '' : 's') +
                    ' &middot; ' + (info && info.full_day ? 'Full day blocked' : blockedCount + ' blocked slot' + (blockedCount === 1 ? '' : 's')) + '</div>';

                times.forEach(t => {
                    const list = byTime[t] || [];
                    const blocked = isBlocked(t);
                    if (list.length) {
                        list.forEach(a => {
                            const chip = '<span class="dc-chip ' + (a.status === 'Accepted' ? 'accepted' : 'pending') + '">' + esc(a.status) + '</span>';
                            const warn = blocked ? '<span class="dc-chip blocked">Slot is blocked</span>' : '';
                            const sub = [a.service, formatDentistName(a.dentist)].filter(Boolean).map(esc).join(' &middot; ');
                            const canMove = a.id && a.uid;
                            html += '<div class="dc-row is-booked' + (blocked ? ' is-conflict' : '') + '">' +
                                '<div class="dc-time">' + esc(timeLabel(t)) + '</div>' +
                                '<div class="dc-main"><strong>' + esc(a.patient_name) + chip + warn + '</strong>' +
                                (sub ? '<span class="dc-sub">' + sub + '</span>' : '') + '</div>' +
                                (canMove ? '<div class="dc-actions"><button type="button" class="dc-mini-btn' +
                                    (blocked ? ' is-urgent' : '') + '" data-act="move" data-uid="' + esc(a.uid) +
                                    '" data-id="' + esc(a.id) + '">Reschedule</button></div>' : '') +
                                '</div>';
                        });
                    } else if (blocked) {
                        html += '<div class="dc-row">' +
                            '<div class="dc-time">' + esc(timeLabel(t)) + '</div>' +
                            '<div class="dc-main"><span class="dc-chip blocked" style="margin-left:0">Blocked</span>' +
                            (info.reason ? '<span class="dc-sub">' + esc(info.reason) + '</span>' : '') + '</div></div>';
                    } else {
                        html += '<div class="dc-row">' +
                            '<div class="dc-time">' + esc(timeLabel(t)) + '</div>' +
                            '<div class="dc-main dc-muted">Open</div></div>';
                    }
                });
                box.innerHTML = html;
            }

            function shortDate(iso, withWeekday) {
                const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
                if (!m) return iso || '';
                const opts = withWeekday
                    ? { weekday: 'short', month: 'short', day: 'numeric' }
                    : { month: 'short', day: 'numeric' };
                return new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString('en-US', opts);
            }

            // Days saved together with "Block multiple days" share a range_id and
            // are shown as one row; everything else stays one row per day.
            function groupUpcoming(list) {
                const groups = [];
                const byRange = {};
                list.forEach(i => {
                    if (i.full_day && i.range_id) {
                        if (byRange[i.range_id]) { byRange[i.range_id].items.push(i); return; }
                        const g = { items: [i] };
                        byRange[i.range_id] = g;
                        groups.push(g);
                        return;
                    }
                    groups.push({ items: [i] });
                });
                return groups;
            }

            function renderUpcomingBlocked() {
                const box = document.getElementById('upcomingBlocked');
                if (!box) return;
                const today = toDateStr(new Date());
                const list = Object.values(blockedMap)
                    .filter(i => i.date >= today)
                    .sort((a, b) => (a.date < b.date ? -1 : 1));
                const groups = groupUpcoming(list);
                document.getElementById('upcomingBlockedCount').textContent = groups.length ? String(groups.length) : '';
                if (!groups.length) {
                    box.innerHTML = '<div class="dc-empty">No upcoming blocked days.</div>';
                    return;
                }
                box.innerHTML = groups.map(g => {
                    const i = g.items[0];
                    const last = g.items[g.items.length - 1];
                    const isRange = g.items.length > 1;
                    const label = isRange
                        ? shortDate(i.date) + ' \u2013 ' + shortDate(last.date)
                        : shortDate(i.date, true);
                    const chip = i.full_day
                        ? '<span class="dc-chip blocked" style="margin-left:0">' +
                          (isRange ? 'Full day &middot; ' + g.items.length + ' days' : 'Full day') + '</span>'
                        : '<span class="dc-chip partial" style="margin-left:0">' +
                        esc((i.blocked_times || []).map(timeLabel).join(', ')) + '</span>';
                    const notes =
                        (i.reason ? '<span class="dc-sub">' + esc(i.reason) + '</span>' : '') +
                        (i.patient_message ? '<span class="dc-sub">Patients see: ' + esc(i.patient_message) + '</span>' : '');
                    const unblockBtn = isRange
                        ? '<button type="button" class="dc-mini-btn danger" data-act="unblock-range" data-start="' + esc(i.date) +
                          '" data-end="' + esc(last.date) + '" data-range="' + esc(i.range_id) + '">Unblock all</button>'
                        : '<button type="button" class="dc-mini-btn danger" data-act="unblock" data-date="' + esc(i.date) + '">Unblock</button>';
                    return '<div class="dc-row">' +
                        '<div class="dc-date">' + esc(label) + '</div>' +
                        '<div class="dc-main">' + chip + notes + '</div>' +
                        '<div class="dc-actions">' +
                        '<button type="button" class="dc-mini-btn" data-act="view" data-date="' + esc(i.date) + '">View</button>' +
                        unblockBtn +
                        '</div></div>';
                }).join('');
            }

            async function unblockDate(date) {
                if (!(await showConfirm('Unblock ' + formatBlockDate(date) + '?'))) return;
                const formData = new FormData();
                formData.append('date', date);
                try {
                    const res = await fetch('/admin/unblock_slot', { method: 'POST', body: formData });
                    const result = await res.json();
                    if (result.success) { await loadBlockedSlots(); showToast('Unblocked successfully.'); }
                    else showToast(result.message || 'Failed to unblock.');
                } catch (err) {
                    console.error('Unblock slot error:', err);
                    showToast('Failed to unblock. Please try again.');
                }
            }

            async function unblockRangeDays(start, end, rangeId) {
                const question = start === end
                    ? 'Unblock ' + formatBlockDate(start) + '?'
                    : 'Unblock ' + formatBlockDate(start) + ' to ' + formatBlockDate(end) + '?';
                if (!(await showConfirm(question, { title: 'Unblock days', confirmLabel: 'Unblock' }))) return;
                const formData = new FormData();
                formData.append('start_date', start);
                formData.append('end_date', end);
                if (rangeId) formData.append('range_id', rangeId);
                try {
                    const res = await fetch('/admin/unblock_range', { method: 'POST', body: formData });
                    const result = await res.json();
                    if (result.success) { await loadBlockedSlots(); showToast(result.message || 'Unblocked successfully.'); }
                    else showToast(result.message || 'Failed to unblock.');
                } catch (err) {
                    console.error('Unblock range error:', err);
                    showToast('Failed to unblock. Please try again.');
                }
            }

            
                        /* ---- Closure summary: month picker + yearly chart ---- */
            const closure = { year: null, data: null, chart: null, loaded: false };
            const SHORT_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

            async function loadClosureYear(year) {
                try {
                    const res = await fetch('/admin/closure_summary?year=' + encodeURIComponent(year));
                    const data = await res.json();
                    if (!data.success) throw new Error(data.message || 'failed');
                    closure.year = year;
                    closure.data = data;
                    closure.loaded = true;
                    renderClosureSummary();
                } catch (err) {
                    console.error('Closure summary error:', err);
                    const list = document.getElementById('closureList');
                    if (list) list.innerHTML = '<div class="dc-empty">Could not load the closure summary.</div>';
                }
            }

            // Called after any block/unblock/mark so the numbers stay current.
            function refreshClosureSummary() {
                if (closure.loaded) loadClosureYear(closure.year);
            }

            function selectedClosureMonth() {
                const m = /^(\d{4})-(\d{2})$/.exec(document.getElementById('closureMonth').value || '');
                return m ? { year: +m[1], month: +m[2] } : null;
            }

            function drawClosureChart(months) {
                const canvas = document.getElementById('closureChart');
                if (!canvas) return;
                if (typeof Chart === 'undefined') { canvas.parentNode.style.display = 'none'; return; }
                const closed = months.map(m => m.closed + m.scheduled);
                const partial = months.map(m => m.partial);
                if (closure.chart) {
                    closure.chart.data.datasets[0].data = closed;
                    closure.chart.data.datasets[1].data = partial;
                    closure.chart.update();
                    return;
                }
                closure.chart = new Chart(canvas, {
                    type: 'bar',
                    data: {
                        labels: SHORT_MONTHS,
                        datasets: [
                            { label: 'Closed days', data: closed, backgroundColor: '#ef4444', borderRadius: 4 },
                            { label: 'Partial days', data: partial, backgroundColor: '#f59e0b', borderRadius: 4 }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
                        plugins: { legend: { position: 'bottom' } }
                    }
                });
            }

            function renderClosureSummary() {
                const sel = selectedClosureMonth();
                if (!sel || !closure.data || sel.year !== closure.year) return;
                const months = closure.data.months;
                const cur = months[sel.month - 1];

                document.getElementById('statClosed').textContent = cur.closed;
                document.getElementById('statOpen').textContent = cur.elapsed ? Math.max(0, cur.elapsed - cur.closed) : '\u2013';
                document.getElementById('statPartial').textContent = cur.partial;
                document.getElementById('statScheduled').textContent = cur.scheduled;

                const sum = k => months.reduce((t, m) => t + m[k], 0);
                document.getElementById('closureYearLine').textContent =
                    closure.year + ': ' + sum('closed') + ' closed day' + (sum('closed') === 1 ? '' : 's') +
                    ', ' + sum('partial') + ' partial day' + (sum('partial') === 1 ? '' : 's') +
                    (sum('scheduled') ? ', ' + sum('scheduled') + ' scheduled ahead' : '') + '.';

                drawClosureChart(months);

                const prefix = sel.year + '-' + pad(sel.month);
                const rows = closure.data.entries.filter(e => e.date.indexOf(prefix) === 0);
                const list = document.getElementById('closureList');
                if (!rows.length) {
                    list.innerHTML = '<div class="dc-empty">No closures in ' + MONTH_NAMES[sel.month - 1] + ' ' + sel.year + '.</div>';
                    return;
                }
                // Count full-day closures by reason (same text, ignoring capitals/spacing, counts together).
                const counts = {};
                rows.forEach(e => {
                    if (!e.full_day) return;
                    const label = (e.reason || '').trim() || 'No reason recorded';
                    const key = label.toLowerCase();
                    (counts[key] = counts[key] || { label: label, n: 0 }).n++;
                });
                const reasonList = Object.values(counts).sort((a, b) => b.n - a.n);
                const breakdown = reasonList.length
                    ? '<div class="dc-summary">By reason: ' + reasonList.map(r =>
                        esc(r.label) + ' (' + r.n + ' day' + (r.n === 1 ? '' : 's') + ')').join(' \u00b7 ') + '</div>'
                    : '';

                list.innerHTML = breakdown + rows.map(e => {
                    const chip = e.full_day
                        ? '<span class="dc-chip blocked" style="margin-left:0">Closed' + (e.upcoming ? ' &middot; upcoming' : '') + '</span>'
                        : '<span class="dc-chip partial" style="margin-left:0">' + esc(e.blocked_times.map(timeLabel).join(', ')) + '</span>';
                    const reasonHtml = e.reason
                        ? esc(e.reason)
                        : '<span class="dc-muted">No reason recorded</span>';
                    return '<div class="dc-row"><div class="dc-date">' + esc(shortDate(e.date, true)) +
                        '</div><div class="dc-main"><strong>' + reasonHtml + '</strong><span class="dc-sub">' + chip +
                        (e.past_marked ? ' &middot; marked afterwards' : '') + '</span></div></div>';
                }).join('');
            }

            function initClosureSummary() {
                const monthInput = document.getElementById('closureMonth');
                if (!monthInput) return;
                const now = new Date();
                monthInput.value = now.getFullYear() + '-' + pad(now.getMonth() + 1);

                monthInput.addEventListener('change', function () {
                    const sel = selectedClosureMonth();
                    if (!sel) return;
                    if (sel.year !== closure.year) loadClosureYear(sel.year); else renderClosureSummary();
                });

                // Load the first time the card is really on screen (the section starts hidden).
                const card = document.querySelector('.dc-closures');
                const start = function () {
                    const sel = selectedClosureMonth();
                    if (!closure.loaded && sel) loadClosureYear(sel.year);
                };
                if ('IntersectionObserver' in window && card) {
                    const io = new IntersectionObserver(function (items) {
                        if (items.some(i => i.isIntersecting)) { io.disconnect(); start(); }
                    });
                    io.observe(card);
                } else start();

                /* Mark past days as closed */
                const pFrom = document.getElementById('pastFrom');
                const pTo = document.getElementById('pastTo');
                const pBtn = document.getElementById('pastMarkBtn');
                if (!pFrom || !pTo || !pBtn) return;
                const yest = new Date();
                yest.setDate(yest.getDate() - 1);
                pFrom.max = toDateStr(yest);
                pTo.max = toDateStr(yest);
                pFrom.addEventListener('change', function () {
                    pTo.min = pFrom.value || '';
                    if (pTo.value && pFrom.value && pTo.value < pFrom.value) pTo.value = pFrom.value;
                });

                pBtn.addEventListener('click', async function () {
                    if (!pFrom.value || !pTo.value) { showToast('Pick the first and last day.'); return; }
                    if (pTo.value < pFrom.value) { showToast('The last day is before the first day.'); return; }
                    const q = pFrom.value === pTo.value
                        ? 'Mark ' + formatBlockDate(pFrom.value) + ' as closed?'
                        : 'Mark ' + formatBlockDate(pFrom.value) + ' to ' + formatBlockDate(pTo.value) + ' as closed?';
                    if (!(await showConfirm(q, {
                        title: 'Mark past days as closed',
                        confirmLabel: 'Mark as closed',
                        note: 'This is kept in the closure summary and cannot be undone.'
                    }))) return;

                    const formData = new FormData();
                    formData.append('start_date', pFrom.value);
                    formData.append('end_date', pTo.value);
                    formData.append('reason', document.getElementById('pastReason').value.trim());
                    try {
                        const res = await fetch('/admin/mark_past_closed', { method: 'POST', body: formData });
                        const result = await res.json();
                        if (result.success) {
                            pFrom.value = '';
                            pTo.value = '';
                            document.getElementById('pastReason').value = '';
                            await loadBlockedSlots();
                            showToast(result.message || 'Marked as closed.');
                        } else {
                            showToast(result.message || 'Failed to mark as closed.');
                        }
                    } catch (err) {
                        console.error('Mark past closed error:', err);
                        showToast('Failed to mark as closed. Please try again.');
                    }
                });
            }

            /* Custom month dropdown.
                The native <select> flatpickr renders is hidden by CSS because its
                opened <option> list is drawn with OS chrome that CSS cannot restyle.
                We hide it but keep using it as the source of truth for which months are
                selectable, and drive the calendar through fp.changeMonth().

                scope: the panel the calendar lives in. flatpickr inserts
                .flatpickr-calendar as a SIBLING of the input, so the input's own id
                matches nothing as a descendant selector - the wrapping panel is the
                only reliable root. Both calendars (Doctors Calendar and the
                Reschedule modal) use the same .adm-month-dd markup and CSS, so the
                control is built once here and reused. */
            const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'];

            function buildMonthDropdown(fp, scope) {
                const root = scope || '.doctor-cal-panel';
                const host = document.querySelector(root + ' .flatpickr-current-month');
                if (!host) return;
                const sel = host.querySelector('select.flatpickr-monthDropdown-months');
                if (!sel) return;
                if (host.querySelector('.adm-month-dd')) { fp.syncMonthLabel(); return; }

                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'adm-month-dd';
                btn.setAttribute('aria-haspopup', 'listbox');
                btn.setAttribute('aria-expanded', 'false');
                host.insertBefore(btn, sel);

                const list = document.createElement('div');
                list.className = 'adm-month-dd-list';
                list.setAttribute('role', 'listbox');
                host.appendChild(list);

                // Read the current month off the instance, not the hidden select: the
                // select is not guaranteed to stay in sync when we drive navigation.
                const label = () => MONTH_NAMES[fp.currentMonth] || '';

                function close() {
                    list.classList.remove('is-open');
                    btn.setAttribute('aria-expanded', 'false');
                }

                function open() {
                    if (list.classList.contains('is-open')) { close(); return; }
                    list.innerHTML = '';
                    for (let i = 0; i < sel.options.length; i++) {
                        const opt = sel.options[i];
                        const month = Number(opt.value);
                        const isActive = month === fp.currentMonth;
                        const item = document.createElement('button');
                        item.type = 'button';
                        item.className = 'adm-month-dd-item' + (isActive ? ' is-active' : '');
                        item.setAttribute('role', 'option');
                        if (isActive) item.setAttribute('aria-selected', 'true');
                        item.textContent = opt.text;
                        item.addEventListener('click', function () {
                            const target = Number(this.dataset.month);
                            close();
                            if (target === fp.currentMonth) return;
                            // changeMonth() is a relative offset, so jumpToDate is used
                            // to move to an absolute month.
                            fp.jumpToDate(new Date(fp.currentYear, target, 1));
                            fp.syncMonthLabel();
                        });
                        item.dataset.month = String(month);
                        list.appendChild(item);
                    }
                    list.classList.add('is-open');
                    btn.setAttribute('aria-expanded', 'true');
                }

                btn.addEventListener('click', open);
                btn.addEventListener('keydown', function (e) {
                    if (e.key === 'Escape' && list.classList.contains('is-open')) { close(); btn.focus(); }
                });
                document.addEventListener('click', function (e) {
                    if (!host.contains(e.target)) close();
                });

                fp.syncMonthLabel = function () { btn.textContent = label(); };
                fp.syncMonthLabel();

                // Signal that the custom control is live, which is what allows the CSS
                // to hide the native select. Done last so a failure above leaves the
                // native dropdown in place.
                const card = document.querySelector(root + ' .flatpickr-calendar');
                if (card) card.classList.add('has-custom-month');
            }

            /* Exposed so any other calendar in the admin can adopt the same control.
               The markup (.adm-month-dd / .adm-month-dd-list / .adm-month-dd-item)
               and all of its CSS - including dark mode - are global, so reuse needs
               nothing else. Pass the panel the calendar lives in. */
            window.admBuildMonthDropdown = buildMonthDropdown;
            window.admReloadBlockedSlots = function () { return loadBlockedSlots(); };

            function pad(n) { return n < 10 ? "0" + n : "" + n; }
            function toDateStr(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }

            function buildTimesGrid() {
                const grid = document.getElementById('blockTimesGrid');
                grid.innerHTML = '';
                TIME_SLOTS.forEach(slot => {
                    const label = document.createElement('label');
                    label.className = 'block-time-label';
                    label.innerHTML = `<input type="checkbox" class="block-time-cb calendar-checkbox" value="${slot.value}"> <span>${slot.label}</span>`;
                    grid.appendChild(label);
                });
            }

            async function loadBlockedSlots() {
                try {
                    const res = await fetch('/get_blocked_slots');
                    const data = await res.json();
                    blockedMap = {};
                    data.forEach(item => { blockedMap[item.date] = item; });
                    window.__blockedSlotsMap = blockedMap; // shared with the New Appointment modal

                    /* The New Appointment modal's date picker greys out fully
                       blocked days using this map. flatpickr evaluates its
                       `disable` predicate when the calendar renders, so a month
                       grid built before this fetch would keep showing a date
                       that has since been blocked. Nudge it to rebuild. */
                    if (window.__admApptDatePicker) {
                        const picker = window.__admApptDatePicker;
                        if (typeof picker.redraw === 'function') picker.redraw();
                        else if (typeof picker.update === 'function') picker.update();
                    }
                    renderUpcomingBlocked();
                    refreshClosureSummary();
                    if (window.markBlockedAppointments) window.markBlockedAppointments();
                    if (calendarInstance) {
                        calendarInstance.redraw();
                        // redraw() can rebuild the native month select, so re-sync label
                        if (calendarInstance.syncMonthLabel) calendarInstance.syncMonthLabel();
                    }
                    if (selectedDate) selectDate(selectedDate);
                } catch (err) {
                    console.error('Failed to load blocked slots:', err);
                }
            }

            /* Display-only date format.
            selectedDate deliberately stays in Y-m-d: that is what the
            /admin/block_slot and /admin/unblock_slot endpoints and the blockedMap
               keys expect, so only the heading text is reformatted. */
            function formatBlockDate(iso) {
                const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
                if (!m) return 'Select a date';
                return MONTH_NAMES[Number(m[2]) - 1] + ' ' + m[3] + ', ' + m[1];
            }

            function selectDate(dateStr) {
                selectedDate = dateStr;
                document.getElementById('blockPanelDate').textContent = formatBlockDate(dateStr);
                if (lastDay.date === dateStr) renderDaySchedule(); else loadDaySchedule(dateStr);

                const existing = blockedMap[dateStr];
                const fullDayToggle = document.getElementById('blockFullDayToggle');
                const reasonInput = document.getElementById('blockReasonInput');

                fullDayToggle.checked = !!(existing && existing.full_day);
                reasonInput.value = existing ? (existing.reason || '') : '';
                const patientMsgInput = document.getElementById('blockPatientMessageInput');
                if (patientMsgInput) patientMsgInput.value = existing ? (existing.patient_message || '') : '';

                document.querySelectorAll('.block-time-cb').forEach(cb => {
                    cb.checked = !!(existing && !existing.full_day && existing.blocked_times.includes(cb.value));
                    cb.disabled = fullDayToggle.checked;
                });
            }

            document.addEventListener('DOMContentLoaded', function () {
                buildTimesGrid();

                document.getElementById('daySchedule').addEventListener('click', function (e) {
                    const btn = e.target.closest('button[data-act="move"]');
                    if (!btn || !lastDay.date) return;
                    const a = lastDay.appts.find(x => x.id === btn.getAttribute('data-id') &&
                        x.uid === btn.getAttribute('data-uid'));
                    if (!a || typeof window.openRescheduleModal !== 'function') return;
                    window.openRescheduleModal({
                        uid: a.uid, id: a.id, name: a.patient_name, service: a.service,
                        appointment_date: a.appointment_date, dentist: a.dentist, source: a.source,
                        onDone: function () {
                            // The appointment left this day: reload the schedule and blocked list.
                            lastDay = { date: null, appts: [], failed: false };
                            loadDaySchedule(selectedDate);
                        }
                    });
                });

                document.getElementById('dayScheduleRefresh').addEventListener('click', function () {
                    if (selectedDate) loadDaySchedule(selectedDate);
                });

                document.getElementById('upcomingBlocked').addEventListener('click', function (e) {
                    const btn = e.target.closest('button[data-act]');
                    if (!btn) return;
                    const date = btn.getAttribute('data-date');
                    const act = btn.getAttribute('data-act');
                    if (act === 'view') {
                        if (calendarInstance) calendarInstance.setDate(date, true);
                    } else if (act === 'unblock-range') {
                        unblockRangeDays(btn.getAttribute('data-start'), btn.getAttribute('data-end'),
                            btn.getAttribute('data-range'));
                    } else {
                        unblockDate(date);
                    }
                });

                document.getElementById('blockFullDayToggle').addEventListener('change', function () {
                    document.querySelectorAll('.block-time-cb').forEach(cb => cb.disabled = this.checked);
                });

                calendarInstance = flatpickr('#doctorCalendarPicker', {
                    inline: true,
                    minDate: 'today',
                    maxDate: new Date().fp_incr(365),
                    onChange: function (selectedDates, dateStr) { selectDate(dateStr); },
                    onDayCreate: function (dObj, dStr, fp, dayElem) {
                        const key = toDateStr(dayElem.dateObj);
                        const info = blockedMap[key];
                        if (!info) return;
                        const dot = document.createElement('span');
                        dot.style.cssText = 'position:absolute;bottom:4px;left:50%;transform:translateX(-50%);width:6px;height:6px;border-radius:50%;';
                        dot.style.background = info.full_day ? '#ef4444' : '#f59e0b';
                        dayElem.style.position = 'relative';
                        dayElem.appendChild(dot);
                    },
                    onReady: function (selectedDates, dateStr, fp) {
                        buildMonthDropdown(fp);
                    },
                    onMonthChange: function (selectedDates, dateStr, fp) {
                        if (fp.syncMonthLabel) fp.syncMonthLabel();
                    },
                    onYearChange: function (selectedDates, dateStr, fp) {
                        if (fp.syncMonthLabel) fp.syncMonthLabel();
                    }
                });

                document.getElementById('saveBlockBtn').addEventListener('click', async function () {
                    if (!selectedDate) { showToast('Please select a date first.'); return; }

                    const fullDay = document.getElementById('blockFullDayToggle').checked;
                    const reason = document.getElementById('blockReasonInput').value.trim();
                    const patientMsgEl = document.getElementById('blockPatientMessageInput');
                    const patientMessage = patientMsgEl ? patientMsgEl.value.trim() : '';
                    const checkedTimes = Array.from(document.querySelectorAll('.block-time-cb:checked')).map(cb => cb.value);

                    if (!fullDay && checkedTimes.length === 0) {
                        showToast('Select "Block entire day" or at least one time slot.');
                        return;
                    }

                    const dateToBlock = selectedDate;
                    function postBlock(force) {
                        const formData = new FormData();
                        formData.append('date', dateToBlock);
                        formData.append('full_day', fullDay ? 'true' : 'false');
                        checkedTimes.forEach(t => formData.append('blocked_times[]', t));
                        formData.append('reason', reason);
                        formData.append('patient_message', patientMessage);
                        if (force) formData.append('force', 'true');
                        return fetch('/admin/block_slot', { method: 'POST', body: formData })
                            .then(res => res.json());
                    }

                    try {
                        let result = await postBlock(false);

                        // The day/time already has appointments: summarise, then let the doctor decide.
                        if (result && result.conflict) {
                            const ok = await showConfirm(conflictMessage(result, fullDay, dateToBlock), {
                                title: 'Appointments already booked',
                                confirmLabel: 'Block anyway',
                                note: 'Blocking will not cancel or move these appointments. After saving, use Reschedule in the day schedule below to move them.',
                                details: conflictDetails(result)
                            });
                            if (!ok) return;
                            result = await postBlock(true);
                        }

                        if (result.success) { await loadBlockedSlots(); showToast('Blocked slot saved.'); }
                        else showToast(result.message || 'Failed to save block.');
                    } catch (err) {
                        console.error('Block slot error:', err);
                        showToast('Failed to save block. Please try again.');
                    }
                });

                document.getElementById('unblockBtn').addEventListener('click', async function () {
                    if (!selectedDate) { showToast('Please select a date first.'); return; }
                    if (!(await showConfirm('Unblock ' + selectedDate + '?'))) return;

                    const formData = new FormData();
                    formData.append('date', selectedDate);

                    try {
                        const res = await fetch('/admin/unblock_slot', { method: 'POST', body: formData });
                        const result = await res.json();
                        if (result.success) { await loadBlockedSlots(); selectDate(selectedDate); showToast('Unblocked successfully.'); }
                        else showToast(result.message || 'Failed to unblock.');
                    } catch (err) {
                        console.error('Unblock slot error:', err);
                        showToast('Failed to unblock. Please try again.');
                    }
                });

                /* ---- Block / unblock several whole days at once ---- */
                const rangeFrom = document.getElementById('rangeFrom');
                const rangeTo = document.getElementById('rangeTo');
                if (rangeFrom && rangeTo) {
                    const MAX_RANGE_DAYS = 90;
                                        const summary = document.getElementById('rangeSummary');
                    const todayStr = toDateStr(new Date());
                    rangeFrom.min = todayStr;
                    rangeTo.min = todayStr;

                    function ymdToDate(v) {
                        const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v || '');
                        return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
                    }

                    // Backend weekday numbers: Monday = 0 ... Sunday = 6.
                    function skippedWeekdays() {
                        return Array.from(document.querySelectorAll('#blockRangeCard .dc-range-skip input:checked'))
                            .map(cb => Number(cb.value));
                    }

                    function rangeInfo(maxDays) {
                        const a = ymdToDate(rangeFrom.value);
                        const b = ymdToDate(rangeTo.value);
                        if (!a || !b) return { ok: false, text: 'Pick the first and last day.' };
                        if (b < a) return { ok: false, text: 'The last day is before the first day.' };
                        const span = Math.round((b - a) / 86400000) + 1;
                        if (span > maxDays) return { ok: false, text: 'Please choose ' + maxDays + ' days or fewer at a time.' };
                        const skip = skippedWeekdays();
                        let n = 0;
                        for (let k = 0; k < span; k++) {
                            const d = new Date(a.getFullYear(), a.getMonth(), a.getDate() + k);
                            if (!skip.includes((d.getDay() + 6) % 7)) n++;
                        }
                        if (!n) return { ok: false, text: 'Every day in that range is skipped.' };
                        return {
                            ok: true, days: n, span: span,
                            text: n + ' day' + (n === 1 ? '' : 's') + ' will be blocked' +
                                (n !== span ? ' (' + (span - n) + ' skipped).' : '.')
                        };
                    }

                    function refreshRangeSummary() {
                        const info = rangeInfo(MAX_RANGE_DAYS);
                        summary.textContent = info.text;
                        summary.classList.toggle('is-error', !info.ok && !!(rangeFrom.value && rangeTo.value));
                    }

                    rangeFrom.addEventListener('change', function () {
                        rangeTo.min = rangeFrom.value || todayStr;
                        if (rangeTo.value && rangeFrom.value && rangeTo.value < rangeFrom.value) rangeTo.value = rangeFrom.value;
                        refreshRangeSummary();
                    });
                    rangeTo.addEventListener('change', refreshRangeSummary);
                    document.querySelectorAll('#blockRangeCard .dc-range-skip input')
                        .forEach(cb => cb.addEventListener('change', refreshRangeSummary));

                    function postRange(force) {
                        const formData = new FormData();
                        formData.append('start_date', rangeFrom.value);
                        formData.append('end_date', rangeTo.value);
                        skippedWeekdays().forEach(v => formData.append('skip_weekdays[]', String(v)));
                        formData.append('reason', document.getElementById('rangeReason').value.trim());
                        formData.append('patient_message', document.getElementById('rangeMessage').value.trim());
                        if (force) formData.append('force', 'true');
                        return fetch('/admin/block_range', { method: 'POST', body: formData }).then(res => res.json());
                    }

                    function rangeConflictDetails(r) {
                        const days = r.days || [];
                        const MAX_ROWS = 5;
                        const rows = days.slice(0, MAX_ROWS).map(d => [
                            shortDate(d.date, true),
                            countLabel(d.appointments.length) + ' ' + (d.appointments.length === 1 ? 'appointment' : 'appointments')
                        ]);
                        if (days.length > MAX_ROWS) rows.push(['', '+ ' + (days.length - MAX_ROWS) + ' more days']);
                        return rows;
                    }

                    document.getElementById('rangeBlockBtn').addEventListener('click', async function () {
                        const info = rangeInfo(MAX_RANGE_DAYS);
                        if (!info.ok) { showToast(info.text); return; }
                        const question = 'Block ' + formatBlockDate(rangeFrom.value) + ' to ' +
                            formatBlockDate(rangeTo.value) + '? ' + info.text;
                        if (!(await showConfirm(question, { title: 'Block multiple days', confirmLabel: 'Block days' }))) return;

                        try {
                            let result = await postRange(false);

                            if (result && result.conflict) {
                                const msg = countLabel(result.total) + ' ' + apptWord(result.total) +
                                    ' fall on ' + (result.days || []).length + ' of these days.';
                                const ok = await showConfirm(msg, {
                                    title: 'Appointments already booked',
                                    confirmLabel: 'Block anyway',
                                    note: 'Blocking will not cancel or move these appointments. After saving, open each day and use Reschedule in the day schedule to move them.',
                                    details: rangeConflictDetails(result)
                                });
                                if (!ok) return;
                                result = await postRange(true);
                            }

                            if (result.success) {
                                await loadBlockedSlots();
                                showToast(result.message || 'Days blocked.');
                                rangeFrom.value = '';
                                rangeTo.value = '';
                                document.getElementById('rangeReason').value = '';
                                document.getElementById('rangeMessage').value = '';
                                refreshRangeSummary();
                            } else {
                                showToast(result.message || 'Failed to block these days.');
                            }
                        } catch (err) {
                            console.error('Block range error:', err);
                            showToast('Failed to block these days. Please try again.');
                        }
                    });

                    document.getElementById('rangeUnblockBtn').addEventListener('click', function () {
                        // Unblocking ignores the skip boxes: it reopens every blocked day in the range.
                        if (!rangeFrom.value || !rangeTo.value) { showToast('Pick the first and last day.'); return; }
                        if (rangeTo.value < rangeFrom.value) { showToast('The last day is before the first day.'); return; }
                        unblockRangeDays(rangeFrom.value, rangeTo.value, '');
                    });
                }

                initClosureSummary();
                loadBlockedSlots();
            });
        })();