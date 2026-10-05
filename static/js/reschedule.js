        /* ---- Reschedule a pending appointment around the Doctors Calendar blocks ---- */
        (function () {
            const SLOTS = [
                { v: '09:00', l: '9:00 AM' }, { v: '10:00', l: '10:00 AM' }, { v: '11:00', l: '11:00 AM' },
                { v: '12:00', l: '12:00 PM' }, { v: '13:00', l: '1:00 PM' }, { v: '14:00', l: '2:00 PM' },
                { v: '15:00', l: '3:00 PM' }, { v: '16:00', l: '4:00 PM' }, { v: '17:00', l: '5:00 PM' }
            ];
            const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];
            const NOTE = { open: 'Open', blocked: 'Blocked', taken: 'Booked', current: 'Current', past: 'Passed' };

            let fp = null, curRow = null, curAppt = null, curDentist = '', curSource = 'pending', curOnDone = null;
            let chosenDate = '', chosenTime = '';
            let blockedMap = {}, dayAppts = [], dayToken = 0, busy = false;

            const $ = id => document.getElementById(id);
            const pad = n => (n < 10 ? '0' + n : '' + n);
            const toStr = d => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
            const todayStr = () => toStr(new Date());

            function esc(t) {
                const d = document.createElement('div');
                d.textContent = t == null ? '' : String(t);
                return d.innerHTML;
            }

            function labelFor(time) {
                const s = SLOTS.find(x => x.v === time);
                return s ? s.l : time;
            }

            function prettyDate(iso) {
                const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
                return m ? MONTHS[Number(m[2]) - 1] + ' ' + Number(m[3]) + ', ' + m[1] : iso;
            }

            function parseRaw(raw) {
                const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{1,2}):(\d{2})/.exec(String(raw || '').trim());
                return m ? { date: m[1], time: pad(Number(m[2])) + ':' + m[3] } : null;
            }

            /* Same normalisation the server uses for dentist names.
               Delegates to the shared dentistIdentityKey() so this "same dentist?"
               test agrees with the server's double-booking check: records saved
               before the rename read "Dr. Capizonda" and new ones read
               "Dr. Julix Dionne Capizonda", and a plain case-fold would treat
               those as two different people and let the same slot be booked
               twice. Falls back to the old behaviour if the helper is absent. */
            const normName = n => (typeof dentistIdentityKey === 'function')
                ? dentistIdentityKey(n)
                : String(n || '').trim().toLowerCase().split(/\s+/).join(' ');

            function isBlocked(date, time) {
                const info = blockedMap[date];
                return !!(info && (info.full_day || (info.blocked_times || []).includes(time)));
            }

            /* Flag pending requests that sit in a slot the dentist has since blocked. */
            window.markBlockedAppointments = function () {
                const map = window.__blockedSlotsMap || {};
                document.querySelectorAll('#appointmentsTable tbody tr').forEach(function (tr) {
                    const cell = tr.querySelector('.appt-date-cell');
                    if (!cell) return;
                    const old = cell.querySelector('.appt-blocked-chip');
                    if (old) old.remove();
                    tr.classList.remove('appt-row--blocked');

                    const when = parseRaw(cell.getAttribute('data-raw'));
                    const info = when && map[when.date];
                    if (!info) return;
                    if (info.full_day || (info.blocked_times || []).includes(when.time)) {
                        const chip = document.createElement('span');
                        chip.className = 'appt-blocked-chip';
                        chip.textContent = 'Blocked - reschedule';
                        chip.title = info.reason ? 'Dentist unavailable: ' + info.reason : 'Dentist unavailable at this time';
                        cell.appendChild(chip);
                        tr.classList.add('appt-row--blocked');
                    }
                });
            };

            async function loadBlocked() {
                try {
                    const res = await fetch('/get_blocked_slots');
                    const data = await res.json();
                    if (Array.isArray(data)) {
                        blockedMap = {};
                        data.forEach(i => { blockedMap[i.date] = i; });
                        return;
                    }
                } catch (err) {
                    console.error('Reschedule: blocked slots failed', err);
                }
                blockedMap = Object.assign({}, window.__blockedSlotsMap || {});
            }

            function slotState(time) {
                const info = blockedMap[chosenDate];
                if (info && (info.full_day || (info.blocked_times || []).includes(time))) {
                    return { state: 'blocked', title: info.reason || 'Dentist unavailable' };
                }
                const cur = curAppt && parseRaw(curAppt.appointment_date);
                if (cur && cur.date === chosenDate && cur.time === time) return { state: 'current' };

                if (chosenDate === todayStr()) {
                    const now = new Date();
                    const parts = time.split(':').map(Number);
                    if (parts[0] * 60 + parts[1] <= now.getHours() * 60 + now.getMinutes()) return { state: 'past' };
                }
                if (curDentist && dayAppts.some(a => a.status === 'Accepted' && a.time === time &&
                    normName(a.dentist) === normName(curDentist))) {
                    return { state: 'taken', title: 'Already booked for this dentist' };
                }
                return { state: 'open' };
            }

            function renderSlots() {
                const grid = $('rsSlotGrid');
                if (!chosenDate) {
                    grid.innerHTML = '<div class="rs-hint">Choose a date on the calendar to see the open times.</div>';
                    return;
                }
                if (chosenTime && slotState(chosenTime).state !== 'open') chosenTime = '';

                grid.innerHTML = SLOTS.map(function (s) {
                    const st = slotState(s.v);
                    const selected = chosenTime === s.v;
                    return '<button type="button" class="rs-slot is-' + st.state + (selected ? ' is-selected' : '') + '"' +
                        ' data-time="' + s.v + '"' + (st.state === 'open' ? '' : ' disabled') +
                        (st.title ? ' title="' + esc(st.title) + '"' : '') + '>' +
                        '<span class="rs-slot-time">' + esc(s.l) + '</span>' +
                        '<span class="rs-slot-note">' + (selected ? 'Selected' : NOTE[st.state]) + '</span></button>';
                }).join('');
            }

            function updateSummary() {
                const box = $('rsSummary');
                const btn = $('rsConfirmBtn');
                if (chosenDate && chosenTime) {
                    box.textContent = 'New schedule: ' + prettyDate(chosenDate) + ' \u00b7 ' + labelFor(chosenTime);
                    box.classList.add('is-ready');
                    btn.disabled = busy;
                } else {
                    box.textContent = chosenDate ? 'Pick one of the open times.' : 'Select a new date and time.';
                    box.classList.remove('is-ready');
                    btn.disabled = true;
                }
            }

            async function loadDay(date) {
                const token = ++dayToken;
                $('rsSlotGrid').innerHTML = '<div class="rs-hint">Loading...</div>';
                let appts = [];
                try {
                    const res = await fetch('/admin/day_schedule?date=' + encodeURIComponent(date));
                    const data = await res.json();
                    if (data.success) appts = data.appointments || [];
                } catch (err) {
                    console.error('Reschedule: day schedule failed', err);
                }
                if (token !== dayToken) return;
                dayAppts = appts;
                renderSlots();
            }

            function buildCalendar() {
                if (fp) { fp.destroy(); fp = null; }
                fp = flatpickr('#rsCalendar', {
                    inline: true,
                    minDate: 'today',
                    maxDate: new Date().fp_incr(365),
                    disable: [function (d) {
                        const info = blockedMap[toStr(d)];
                        return !!(info && info.full_day);
                    }],
                    onDayCreate: function (dObj, dStr, inst, dayElem) {
                        const info = blockedMap[toStr(dayElem.dateObj)];
                        if (info && !info.full_day) dayElem.classList.add('rs-partial');
                    },
                    onChange: function (dates, dateStr) {
                        chosenDate = dateStr;
                        chosenTime = '';
                        $('rsSlotsTitle').textContent = prettyDate(dateStr);
                        updateSummary();
                        loadDay(dateStr);
                    }
                });

                /* Swap flatpickr's native month <select> for the admin's shared
                   .adm-month-dd listbox. The native control's opened <option>
                   list is OS-drawn and cannot be styled, so it would show a
                   default grey dropdown inside this calendar's navy header.
                   Guarded: if block-dates.js ever fails to load, the native
                   select simply stays visible and usable. */
                if (typeof window.admBuildMonthDropdown === 'function') {
                    try {
                        window.admBuildMonthDropdown(fp, '#rescheduleModal .rs-cal');
                    } catch (err) {
                        console.warn('Reschedule: month dropdown unavailable:', err);
                    }
                }
            }

            function closeModal() {
                $('rescheduleModal').style.display = 'none';
                document.removeEventListener('keydown', onKey);
                if (fp) { fp.destroy(); fp = null; }
                curRow = curAppt = curOnDone = null;
            }

            function onKey(e) { if (e.key === 'Escape' && !busy) closeModal(); }

            /* Accepts either a row of the Appointments table (pending request) or a plain
               object from the Doctors Calendar day schedule:
               { uid, id, name, service, appointment_date, dentist, source, onDone } */
            window.openRescheduleModal = async function (target) {
                let appt = null;
                curRow = null;
                curOnDone = null;
                curSource = 'pending';

                if (target && typeof target.getAttribute === 'function') {
                    try { appt = JSON.parse(target.getAttribute('data-appointment')); } catch (err) { /* handled below */ }
                    curRow = target;
                    const dentistInput = target.querySelector('.dentist-input');
                    curDentist = dentistInput ? dentistInput.value.trim() : '';
                } else if (target && target.uid && target.id) {
                    appt = {
                        uid: target.uid, id: target.id, Service: target.service || '',
                        appointment_date: target.appointment_date || '', __name: target.name || ''
                    };
                    curDentist = target.dentist || '';
                    curSource = target.source === 'accepted' ? 'accepted' : 'pending';
                    curOnDone = typeof target.onDone === 'function' ? target.onDone : null;
                }
                if (!appt) { showToast('Could not read this appointment.'); return; }

                curAppt = appt;
                chosenDate = '';
                chosenTime = '';
                dayAppts = [];

                $('rsPatient').textContent = (appt.__name || [appt.FirstName, appt.LastName].filter(Boolean).join(' ')) +
                    (appt.Service ? ' \u00b7 ' + appt.Service : '');
                $('rsCurrent').textContent = 'Loading...';
                $('rsSlotsTitle').textContent = 'Pick a new date';
                renderSlots();
                updateSummary();
                $('rescheduleModal').style.display = 'flex';
                document.addEventListener('keydown', onKey);

                await loadBlocked();
                if (curAppt !== appt) return; // closed while loading

                const cur = parseRaw(appt.appointment_date);
                let html = 'Currently scheduled: ' + (cur ? esc(prettyDate(cur.date) + ' \u00b7 ' + labelFor(cur.time)) : 'not set');
                if (cur && isBlocked(cur.date, cur.time)) {
                    const info = blockedMap[cur.date] || {};
                    html += '<span class="rs-flag">Blocked' + (info.reason ? ': ' + esc(info.reason) : '') + '</span>';
                }
                $('rsCurrent').innerHTML = html;
                buildCalendar();
            };

            function applyToRow(newDt) {
                if (!curRow) return; // opened from the Doctors Calendar: its onDone refreshes the view
                curAppt.appointment_date = newDt;
                curRow.setAttribute('data-appointment', JSON.stringify(curAppt));
                const cell = curRow.querySelector('.appt-date-cell');
                if (cell) {
                    cell.setAttribute('data-raw', newDt);
                    cell.textContent = formatApptDateTime(newDt);
                }
                // The blocked map is refreshed from the server, then rows re-flagged.
                window.__blockedSlotsMap = Object.assign({}, blockedMap);
                window.markBlockedAppointments();
            }

async function submit() {
            if (busy || !chosenDate || !chosenTime || !curAppt) return;
            busy = true;
            const btn = $('rsConfirmBtn');
            const btnLabel = $('rsConfirmLabel');
            btn.disabled = true;
            // The label span, NOT btn.textContent: the button now carries a
            // Material Symbol alongside the text, and assigning textContent
            // would delete the icon node.
            if (btnLabel) btnLabel.textContent = 'Saving...';
            btn.classList.add('is-busy');

                const fd = new FormData();
                fd.append('user_id', curAppt.uid);
                fd.append('appointment_id', curAppt.id);
                fd.append('new_date', chosenDate);
                fd.append('new_time', chosenTime);
                fd.append('dentist_name', curDentist);
                fd.append('source', curSource);

                let done = false;
                try {
                    const res = await fetch('/admin/reschedule_appointment', { method: 'POST', body: fd });
                    const result = await res.json().catch(() => ({}));
                    if (res.ok && result.success) {
                        applyToRow(result.appointment_date);
                        if (curOnDone) curOnDone(result.appointment_date);
                        showToast(result.email_on_file
                            ? 'Appointment rescheduled. The patient was notified by email.'
                            : 'Appointment rescheduled. No email is on file for this patient.');
                        done = true;
                    } else {
                        showToast(result.message || 'Failed to reschedule.');
                        if (res.status === 409) {
                            await loadBlocked();
                            loadDay(chosenDate);
                        }
                    }
                } catch (err) {
                    console.error('Reschedule error:', err);
                    showToast('Failed to reschedule. Please try again.');
                } finally {
                    busy = false;
                    if (btnLabel) btnLabel.textContent = 'Reschedule';
                    btn.classList.remove('is-busy');
                    if (done) closeModal(); else updateSummary();
                }
            }

            document.addEventListener('DOMContentLoaded', function () {
                $('rsCloseBtn').addEventListener('click', closeModal);
                $('rsCancelBtn').addEventListener('click', closeModal);
                $('rsConfirmBtn').addEventListener('click', submit);
                $('rsSlotGrid').addEventListener('click', function (e) {
                    const b = e.target.closest('.rs-slot.is-open');
                    if (!b) return;
                    chosenTime = b.getAttribute('data-time');
                    renderSlots();
                    updateSummary();
                });
            });
        })();
