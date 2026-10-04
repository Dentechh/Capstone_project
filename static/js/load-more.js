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
