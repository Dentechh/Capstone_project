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
                            const sub = [a.service, a.dentist].filter(Boolean).map(esc).join(' &middot; ');
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

            function renderUpcomingBlocked() {
                const box = document.getElementById('upcomingBlocked');
                if (!box) return;
                const today = toDateStr(new Date());
                const list = Object.values(blockedMap)
                    .filter(i => i.date >= today)
                    .sort((a, b) => (a.date < b.date ? -1 : 1));
                document.getElementById('upcomingBlockedCount').textContent = list.length ? String(list.length) : '';
                if (!list.length) {
                    box.innerHTML = '<div class="dc-empty">No upcoming blocked days.</div>';
                    return;
                }
                box.innerHTML = list.map(i => {
                    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(i.date);
                    const label = m ? new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString('en-US',
                        { weekday: 'short', month: 'short', day: 'numeric' }) : i.date;
                    const chip = i.full_day
                        ? '<span class="dc-chip blocked" style="margin-left:0">Full day</span>'
                        : '<span class="dc-chip partial" style="margin-left:0">' +
                        esc((i.blocked_times || []).map(timeLabel).join(', ')) + '</span>';
                    return '<div class="dc-row">' +
                        '<div class="dc-date">' + esc(label) + '</div>' +
                        '<div class="dc-main">' + chip +
                        (i.reason ? '<span class="dc-sub">' + esc(i.reason) + '</span>' : '') + '</div>' +
                        '<div class="dc-actions">' +
                        '<button type="button" class="dc-mini-btn" data-act="view" data-date="' + esc(i.date) + '">View</button>' +
                        '<button type="button" class="dc-mini-btn danger" data-act="unblock" data-date="' + esc(i.date) + '">Unblock</button>' +
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

            /* Custom month dropdown.
               The native <select> flatpickr renders is hidden by CSS because its
               opened <option> list is drawn with OS chrome that CSS cannot restyle.
               We hide it but keep using it as the source of truth for which months are
               selectable, and drive the calendar through fp.changeMonth(). */
            const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'];

            function buildMonthDropdown(fp) {
                // Scope via .doctor-cal-panel, NOT #doctorCalendarPicker: the calendar
                // is a sibling of the picker, so a descendant selector matches nothing.
                const host = document.querySelector('.doctor-cal-panel .flatpickr-current-month');
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
                const card = document.querySelector('.doctor-cal-panel .flatpickr-calendar');
                if (card) card.classList.add('has-custom-month');
            }

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
                    renderUpcomingBlocked();
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
                    if (btn.getAttribute('data-act') === 'view') {
                        if (calendarInstance) calendarInstance.setDate(date, true);
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

                loadBlockedSlots();
            });
        })();
