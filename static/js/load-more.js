            document.addEventListener('DOMContentLoaded', function () {
                // ---- Appointments Load More ----
                const apptBtn = document.getElementById('appointmentsLoadMoreBtn');
                const apptCursor = document.getElementById('appointmentsCursor');
                const apptTbody = document.querySelector('#appointmentsTable tbody');

                if (apptBtn && apptCursor && apptTbody) {
                    apptBtn.addEventListener('click', function () {
                        const cursor = apptCursor.getAttribute('data-cursor') || '';
                        apptBtn.disabled = true;
                        apptBtn.textContent = 'Loading...';

                        fetch('/admin/appointments_page?cursor=' + encodeURIComponent(cursor))
                            .then(res => res.json())
                            .then(result => {
                                if (!result.success) {
                                    showToast(result.message || 'Failed to load more appointments.');
                                    return;
                                }

                                // Empty-state row, built here rather than server-rendered on
                                // purpose: loadSectionOnce() in app-core.js clears this
                                // whole tbody with innerHTML = '' before the first
                                // request, which would drop a template-provided row
                                // on the floor. Creating it per response keeps it
                                // correct on every lazy-load and Load More pass.
                                // Static markup only -- no patient data is involved.
                                const APPT_COLUMNS = 24;   // 7 visible + 17 hidden
                                const APPT_EMPTY_HTML =
                                    '<tr class="appt-empty-row">' +
                                    '<td colspan="' + APPT_COLUMNS + '">' +
                                    '<div class="appt-empty">' +
                                    '<span class="material-symbols-rounded appt-empty__icon" aria-hidden="true">event_available</span>' +
                                    '<span class="appt-empty__text">No pending appointments right now.</span>' +
                                    '<span class="appt-empty__hint">New booking requests will appear here as soon as they come in.</span>' +
                                    '</div></td></tr>';

                                result.rows.forEach(function (appt) {
                                    const tr = document.createElement('tr');
                                    tr.setAttribute('data-appointment', JSON.stringify(appt));
                                    tr.setAttribute('data-urgency', apptUrgency(appt.UrgencyLevel).key);
                                    tr.innerHTML = `
                            <td>${apptText(appt.FirstName)}</td>
                            ${apptHiddenCells(appt)}
                            ${apptUrgencyCell(appt.UrgencyLevel)}
                            <td class="appt-date-cell" data-raw="${apptAttr(appt.appointment_date)}">${apptText(formatApptDateTime(appt.appointment_date))}</td>
                            <td>${apptText(appt.Service)}</td>
                            <td>
                                <div class="dentist-field">
                                    <input type="text" name="dentist_name" class="dentist-input"
                                        placeholder="Select or type a dentist"
                                        autocomplete="off" autocapitalize="off" spellcheck="false"
                                        role="combobox" aria-autocomplete="list" aria-expanded="false"
                                        aria-controls="dentistMenu" aria-required="true" aria-label="Consulting dentist">
                                    <button type="button" class="dentist-field__toggle" tabindex="-1"
                                        aria-hidden="true" title="Show dentists">
                                        <span class="material-symbols-rounded" aria-hidden="true">arrow_drop_down</span>
                                    </button>
                                </div>
                            </td>
                            <td><span class="badge pending">pending</span></td>
                            <td>
                                <div class="appt-actions">
                                    <button type="button" class="btn-action appt-accept-btn" title="Accept this appointment" aria-label="Accept this appointment" onclick="updateStatus(this.closest('tr'), 'accept')">
                                        <span class="material-symbols-rounded" aria-hidden="true">event_available</span>
                                    </button>
                                    <button type="button" class="btn-action appt-reschedule-btn" title="Reschedule this appointment" aria-label="Reschedule this appointment" onclick="openRescheduleModal(this.closest('tr'))">
                                        <span class="material-symbols-rounded" aria-hidden="true">event_repeat</span>
                                    </button>
                                    <button type="button" class="btn-action appt-decline-btn" title="Decline this appointment" aria-label="Decline this appointment" onclick="updateStatus(this.closest('tr'), 'decline')">
                                        <span class="material-symbols-rounded" aria-hidden="true">event_busy</span>
                                    </button>
                                </div>
                            </td>
                        `;
                                    apptTbody.appendChild(tr);
                                });

                                // Swap in the empty state only when this response left the table
                                // with no real rows. Keyed off tr[data-appointment]
                                // rather than a row count so it cannot be fooled by
                                // anything else in the tbody.
                                const emptyRow = apptTbody.querySelector('.appt-empty-row');
                                if (emptyRow) emptyRow.remove();
                                if (!apptTbody.querySelector('tr[data-appointment]')) {
                                    apptTbody.insertAdjacentHTML('beforeend', APPT_EMPTY_HTML);
                                }

                                if (window.markBlockedAppointments) window.markBlockedAppointments();

                                if (result.next_cursor) {
                                    apptCursor.setAttribute('data-cursor', result.next_cursor);
                                    apptBtn.disabled = false;
                                    apptBtn.textContent = 'Load More';
                                } else {
                                    apptBtn.style.display = 'none';
                                }
                            })
                            .catch(function (err) {
                                console.error('Load more appointments error:', err);
                                showToast('Failed to load more appointments. Please try again.');
                                apptBtn.disabled = false;
                                apptBtn.textContent = 'Load More';
                                // Show a failure state rather than "no appointments":
                                // the table is not empty, the request failed, and the
                                // two should not look the same. Kept distinct from the
                                // success empty state so it cannot be mistaken for one.
                                if (!apptTbody.querySelector('tr[data-appointment]') &&
                                    !apptTbody.querySelector('.appt-empty-row')) {
                                    apptTbody.insertAdjacentHTML('beforeend',
                                        '<tr class="appt-empty-row"><td colspan="' + APPT_COLUMNS + '">' +
                                        '<div class="appt-empty">' +
                                        '<span class="material-symbols-rounded appt-empty__icon" aria-hidden="true">error</span>' +
                                        '<span class="appt-empty__text">Could not load appointments.</span>' +
                                        '<span class="appt-empty__hint">Check your connection and use Load More to try again.</span>' +
                                        '</div></td></tr>');
                                }
                            });
                    });
                }

                // ---- Approved Patients Load More ----
                const weeklyBtn = document.getElementById('weeklyClientsLoadMoreBtn');
                const weeklyCursor = document.getElementById('weeklyClientsCursor');
                const weeklyGrid = document.getElementById('weeklyClientsGrid');

                if (weeklyBtn && weeklyCursor && weeklyGrid) {
                    weeklyBtn.addEventListener('click', function () {
                        const cursor = weeklyCursor.getAttribute('data-cursor') || '';
                        weeklyBtn.disabled = true;
                        weeklyBtn.textContent = 'Loading...';

                        fetch('/admin/approved_page?cursor=' + encodeURIComponent(cursor))
                            .then(res => res.json())
                            .then(result => {
                                if (!result.success) {
                                    showToast(result.message || 'Failed to load more approved patients.');
                                    return;
                                }

                                result.rows.forEach(function (a) {
                                    weeklyGrid.appendChild(buildApprovedCard(a));
                                });

                                if (result.next_cursor) {
                                    weeklyCursor.setAttribute('data-cursor', result.next_cursor);
                                    weeklyBtn.disabled = false;
                                    weeklyBtn.textContent = 'Load More';
                                } else {
                                    weeklyBtn.style.display = 'none';
                                }
                            })
                            .catch(function (err) {
                                console.error('Load more approved patients error:', err);
                                showToast('Failed to load more approved patients. Please try again.');
                                weeklyBtn.disabled = false;
                                weeklyBtn.textContent = 'Load More';
                            });
                    });
                }
            });
