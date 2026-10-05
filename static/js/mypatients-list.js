            function buildMyPatientRow(p) {
                const tr = document.createElement('tr');
                tr.setAttribute('data-recent-appointment', p.most_recent_appointment || '');
                const ageDisplay = (p.age === null || p.age === undefined) ? '-' : p.age;
                const birthYearDisplay = p.birthday || '-';
                const sexDisplay = p.sex || '-';
                const civilStatusDisplay = p.civil_status || '-';
                tr.innerHTML = `
            <td data-cell="name">${p.full_name || ''}</td>
            <td>${ageDisplay}</td>
            <td>${birthYearDisplay}</td>
            <td data-cell="sex">${sexDisplay}</td>
            <td data-cell="civil">${civilStatusDisplay}</td>
            <td data-cell="mobile">${p.contact_number || '-'}</td>

        <td>
            <div class="mp-actions">
                <button type="button" class="btn-action accept mp-info-btn" title="Treatment information" aria-label="Treatment information"
                    onclick="openCheckInfoModal('${p.patient_id}', this.closest('tr').querySelector('td').textContent.trim())"><span class="material-symbols-rounded" aria-hidden="true">info</span></button>
                <button type="button" class="btn-action edit-patient-btn" title="Edit patient" aria-label="Edit patient"
                    data-uid="${p.uid}" data-patient-id="${p.patient_id}"
                    data-firstname="${p.first_name}" data-middlename="${p.middle_name}"
                    data-lastname="${p.last_name}" data-contact="${p.contact_number}" data-email="${p.email}"
                    data-sex="${p.sex || ''}" data-civilstatus="${p.civil_status || ''}">
<span class="material-symbols-rounded" aria-hidden="true">edit</span></button>
                <button type="button" class="btn-action delete-patient-btn" title="Remove patient" aria-label="Remove patient"
                    data-uid="${p.uid}" data-patient-id="${p.patient_id}" data-name="${p.full_name}"><span class="material-symbols-rounded" aria-hidden="true">delete</span></button>
            </div>
        </td>
    `;
                return tr;
            }

            function upsertMyPatientRow(uid, fields) {
                const tbody = document.querySelector('#myPatientsTable tbody');
                if (!tbody) return;

                const existingBtn = tbody.querySelector('.edit-patient-btn[data-uid="' + uid + '"]');
                if (existingBtn) {
                    const row = existingBtn.closest('tr');
                    const fullName = [fields.FirstName, fields.MiddleName, fields.LastName].filter(Boolean).join(' ');
                    // Look cells up by name, not position: adding a column must not
                    // silently redirect these writes.
                    const cellBy = name => row.querySelector('td[data-cell="' + name + '"]');
                    const nameCell = cellBy('name');
                    const sexCell = cellBy('sex');
                    const mobileCell = cellBy('mobile');
                    if (nameCell) nameCell.textContent = fullName;
                    if (sexCell) sexCell.textContent = fields.Sex || '-';
                    if (mobileCell) mobileCell.textContent = fields.ContactNumber || '-';
                    existingBtn.setAttribute('data-firstname', fields.FirstName || '');
                    existingBtn.setAttribute('data-middlename', fields.MiddleName || '');
                    existingBtn.setAttribute('data-lastname', fields.LastName || '');
                    existingBtn.setAttribute('data-contact', fields.ContactNumber || '');
                    existingBtn.setAttribute('data-sex', fields.Sex || '');
                    tbody.insertBefore(row, tbody.firstChild);
                    return;
                }

                // This refresh is itself the first page load; stop the lazy loader duplicating it.
                window._lazyLoaded = window._lazyLoaded || {};
                window._lazyLoaded.mypatients = true;

                fetch('/admin/my_patients_page')
                    .then(res => res.json())
                    .then(result => {
                        if (!result.success) return;
                        tbody.innerHTML = '';
                        result.rows.forEach(function (p) { tbody.appendChild(buildMyPatientRow(p)); });

                        // Keep Load More working after a refresh.
                        const cur = document.getElementById('myPatientsCursor');
                        const btn = document.getElementById('myPatientsLoadMoreBtn');
                        if (cur) cur.setAttribute('data-cursor', result.next_cursor || '');
                        if (btn) {
                            btn.disabled = false;
                            btn.textContent = 'Load More';
                            btn.style.display = result.next_cursor ? '' : 'none';
                        }
                    })
                    .catch(function (err) { console.error('Refresh my patients error:', err); });
            }

                /* accepted_at is stored as a UTC ISO string, so it needs the browser to do the
                timezone conversion. Deliberately NOT formatApptDateTime(): that one
                exists to re-render Firestore's "YYYY-MM-DD HH:MM" without ever
                rewriting it, and this value has a different shape and a real offset.
                The raw string stays in data-accepted-at either way, because
               sortWeeklyClientsByDate parses the attribute, not the text. */
            function formatAcceptedAt(raw) {
                const value = String(raw == null ? '' : raw).trim();
                if (!value) return 'Not recorded';

                const when = new Date(value);
                if (isNaN(when.getTime())) return value;

                return when.toLocaleString('en-US', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit'
                });
            }

            function apptFullName(parts) {
                const src = parts || {};
                const joined = [src.FirstName, src.MiddleName, src.LastName]
                    .map(function (part) { return String(part == null ? '' : part).trim(); })
                    .filter(Boolean)
                    .join(' ');
                return joined || String(src.FirstName || '').trim() || 'Unnamed patient';
            }

                /* The assigned-dentist cell. Read-only once a dentist is on the
                appointment; an inline editor only while there is nothing to show,
                so a filled-in card and an edited card end up looking identical. */
            function apptCardDentistValue(name) {
                // Rendered through formatDentistName() so a card built from an older
                // record ("Dr. Capizonda") reads the same as a freshly assigned one.
                return '<span class="appt-card__val appt-card__val--dentist">' + apptText(formatDentistName(name)) + '</span>';
            }

            function apptCardDentistEditor(a) {
                const src = a || {};
                const docId = src.Patient_unq_id || src.id || '';

                return '<span class="appt-dentist">'
                    + '<span class="dentist-field">'
                    + '<input type="text" class="dentist-input" placeholder="Select or type a dentist"'
                    + ' autocomplete="off" autocapitalize="off" spellcheck="false" role="combobox"'
                    + ' aria-autocomplete="list" aria-expanded="false" aria-controls="dentistMenu"'
                    + ' aria-label="Assign a consulting dentist">'
                    + '<button type="button" class="dentist-field__toggle" tabindex="-1" aria-hidden="true"'
                    + ' title="Show dentists">'
                    + '<span class="material-symbols-rounded" aria-hidden="true">arrow_drop_down</span>'
                    + '</button>'
                    + '</span>'
                    + '<button type="button" class="btn-action appt-dentist-save" title="Save dentist"'
                    + ' aria-label="Save dentist"'
                    + ' data-uid="' + apptAttr(src.uid) + '"'
                    + ' data-appointment-id="' + apptAttr(docId) + '"'
                    + ' onclick="assignDentistFromCard(this)">'
                    + '<span class="material-symbols-rounded" aria-hidden="true">save</span>'
                    + '</button>'
                    + '</span>';
            }

            function apptCardDentistCell(a) {
                const assigned = String((a && a.DentistName) || '').trim();
                return assigned ? apptCardDentistValue(assigned) : apptCardDentistEditor(a);
            }

            function apptCardRow(icon, label, valueHtml) {
                return '<div class="appt-card__row">'
                    + '<span class="appt-card__key">'
                    + '<span class="material-symbols-rounded" aria-hidden="true">' + icon + '</span>'
                    + apptText(label)
                    + '</span>'
                    + valueHtml
                    + '</div>';
            }

            /* The scheduled date, shown above Accepted: it is what the visit is
               FOR, whereas Accepted is bookkeeping about when it was confirmed.
               appointment_date keeps its stored "YYYY-MM-DD HH:MM" value - only the
               display is reformatted. Returns '' when there is no date, so the row
               is simply absent rather than showing a placeholder for an accepted
               appointment that predates scheduling. */
            function apptCardAppointmentDateRow(a) {
                const raw = String((a && a.appointment_date) || '').trim();
                if (!raw) return '';
                return apptCardRow(
                    'event',
                    'Appointment date',
                    '<span class="appt-card__val appt-card__val--date">' +
                    apptText(formatApptDateTime(raw)) + '</span>'
                );
            }

                /* Save handler for the "no dentist assigned" editor. Only swaps the
                editor for the read-only name once the server has confirmed, so a
                failed save never leaves the card claiming a dentist it does not
                have. */
            function assignDentistFromCard(btn) {
                const wrap = btn.closest('.appt-dentist');
                const input = wrap ? wrap.querySelector('.dentist-input') : null;
                const name = input ? input.value.trim() : '';

                if (!name) {
                    showToast('Please select or type a dentist.');
                    if (input) input.focus();
                    return;
                }

                const card = btn.closest('.patient-card');
                const body = new FormData();
                body.append('uid', btn.getAttribute('data-uid') || '');
                body.append('appointment_id', btn.getAttribute('data-appointment-id') || '');
                body.append('dentist_name', name);

                btn.disabled = true;

                fetch('/admin/assign_dentist', { method: 'POST', body: body })
                    .then(function (res) {
                        return res.json().catch(function () { return {}; }).then(function (data) {
                            if (!res.ok) {
                                throw new Error(data.message || 'Failed to assign the dentist.');
                            }
                            return data;
                        });
                    })
                    .then(function () {
                        const row = wrap ? wrap.closest('.appt-card__row') : null;
                        if (row) row.innerHTML = apptCardRow('dentistry', 'Assigned dentist', apptCardDentistValue(name));

                        const infoBtn = card ? card.querySelector('.check-profile-btn') : null;
                        if (infoBtn) infoBtn.setAttribute('data-dentist', name);

                        showToast('Dentist assigned.');
                    })
                    .catch(function (err) {
                        console.error('Assign dentist error:', err);
                        showToast(err.message || 'Failed to assign the dentist.');
                        btn.disabled = false;
                    });
            }

            function buildApprovedCard(a) {
                const card = document.createElement('div');

                const fullName = apptFullName(a);
                const urgency = apptUrgency(a.UrgencyLevel);

                // The urgency modifier drives the card's left accent, so a
                // critical booking is findable while scanning the grid.
                card.className = 'patient-card appt-card appt-card--' + urgency.key;

                // filterWeeklyClients and sortWeeklyClients both read data-name,
                // so it carries the full name an admin would recognise -- the
                // first name alone made "Dela Cruz" sort under "Cruz".
                card.setAttribute('data-name', fullName);
                card.setAttribute('data-accepted-at', a.accepted_at || '');

                card.innerHTML = `
        <div class="appt-card__head">
            <div class="p-info">
                <strong class="appt-card__name">${apptText(fullName)}</strong>
                <span class="appt-card__service">${apptText(a.Service || 'General consultation')}</span>
            </div>
            <span class="urg-badge urg-badge--${urgency.key}" title="Urgency level: ${apptAttr(urgency.label)}">
                <span class="urg-badge__dot" aria-hidden="true"></span>
                <span class="urg-badge__label">${apptText(urgency.label)}</span>
            </span>
        </div>

        <div class="appt-card__rows">
            ${apptCardAppointmentDateRow(a)}
            ${apptCardRow('event_available', 'Accepted', '<span class="appt-card__val appt-card__val--date">' + apptText(formatAcceptedAt(a.accepted_at)) + '</span>')}
            ${apptCardRow('dentistry', 'Assigned dentist', apptCardDentistCell(a))}
        </div>

        <div class="appt-card__actions">
            <button type="button" class="btn-action accept check-profile-btn"
                data-name="${apptAttr(a.FirstName || '')}"
                data-Patient_unq_id="${apptAttr(a.Patient_unq_id || '')}"
                data-uid="${apptAttr(a.uid || '')}"
                data-sex="${apptAttr(a.Sex || '')}"
                data-age="${apptAttr(a.Age || 'N/A')}"
                data-lastname="${apptAttr(a.LastName || '')}"
                data-middlename="${apptAttr(a.MiddleName || '')}"
                data-birthday="${apptAttr(a.Birthday || '')}"
                data-nationality="${apptAttr(a.Nationality || '')}"
                data-religion="${apptAttr(a.Religion || '')}"
                data-occupation="${apptAttr(a.Occupation || '')}"
                data-civilstatus="${apptAttr(a.CivilStatus || '')}"
                data-contact="${apptAttr(a.ContactNumber || '')}"
                data-service="${apptAttr(a.Service || '')}"
                data-dentist="${apptAttr(a.DentistName || '')}"
                data-q1="${apptAttr(a.q1 || 'N')}" data-q2="${apptAttr(a.q2 || 'N')}"
                data-q3="${apptAttr(a.q3 || 'N')}" data-q4="${apptAttr(a.q4 || 'N')}"
                data-q5="${apptAttr(a.q5 || 'N')}" data-q6="${apptAttr(a.q6 || 'N')}"
                data-q7="${apptAttr(a.q7 || 'N')}" data-q9="${apptAttr(a.q9 || 'N')}"
                data-q2_spec="${apptAttr(a.q2_spec || '')}" data-q3_spec="${apptAttr(a.q3_spec || '')}"
                data-q4_spec="${apptAttr(a.q4_spec || '')}" data-q5_spec="${apptAttr(a.q5_spec || '')}"
                data-q7_spec="${apptAttr(a.q7_spec || '')}" data-q9_spec="${apptAttr(a.q9_spec || '')}"
                data-w-preg="${apptAttr(a.w_preg || 'N')}" data-w-nurse="${apptAttr(a.w_nurse || 'N')}"
                data-w-pill="${apptAttr(a.w_pill || 'N')}">
                <span class="material-symbols-rounded" aria-hidden="true">fact_check</span>
                <span>Check Info</span>
            </button>
        </div>
    `;
                return card;
            }

            document.addEventListener('DOMContentLoaded', function () {
                const loadMoreBtn = document.getElementById('myPatientsLoadMoreBtn');
                const cursorHolder = document.getElementById('myPatientsCursor');
                const tbody = document.querySelector('#myPatientsTable tbody');

                if (!loadMoreBtn || !cursorHolder || !tbody) return;

                loadMoreBtn.addEventListener('click', function () {
                    const cursor = cursorHolder.getAttribute('data-cursor') || '';
                    loadMoreBtn.disabled = true;
                    loadMoreBtn.textContent = 'Loading...';

                    fetch('/admin/my_patients_page?cursor=' + encodeURIComponent(cursor))
                        .then(res => res.json())
                        .then(result => {
                            if (!result.success) {
                                showToast(result.message || 'Failed to load more patients.');
                                return;
                            }

                            result.rows.forEach(function (p) {
                                tbody.appendChild(buildMyPatientRow(p));
                            });

                            if (result.next_cursor) {
                                cursorHolder.setAttribute('data-cursor', result.next_cursor);
                                loadMoreBtn.disabled = false;
                                loadMoreBtn.textContent = 'Load More';
                            } else {
                                loadMoreBtn.style.display = 'none';
                            }
                        })
                        .catch(function (err) {
                            console.error('Load more patients error:', err);
                            showToast('Failed to load more patients. Please try again.');
                            loadMoreBtn.disabled = false;
                            loadMoreBtn.textContent = 'Load More';
                        });
                });
            });

            // Live name search for the My Patients table (onkeyup in the section markup).
        function filterMyPatients() {
            var input = document.getElementById('myPatientSearch').value.toUpperCase();
            var table = document.getElementById('myPatientsTable');
            var tbody = table.querySelector('tbody');
            var rows = tbody.querySelectorAll('tr');
            rows.forEach(function (row) {
                var nameCell = row.querySelector('td');
                if (nameCell) {
                    var textValue = nameCell.textContent || nameCell.innerText;
                    row.style.display = textValue.toUpperCase().indexOf(input) > -1 ? '' : 'none';
                }
            });
        }
