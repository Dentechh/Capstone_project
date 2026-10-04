            const CONFIRM_ICON_QUESTION = '<circle cx="12" cy="12" r="10"></circle><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"></path><path d="M12 17h.01"></path>';
            const CONFIRM_ICON_TRASH = '<polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path>';

            // Shared confirmation dialog. opts:
            //   title        - heading text
            //   note         - extra warning line (own tinted strip)
            //   details      - [[label, value], ...] rendered as a summary list
            //   confirmLabel - override the confirm button's label
            //   danger       - red icon + red confirm button
            //   icon         - 'question' (default) | 'trash'
            // Only `message` is required, so the existing callers keep working unchanged.
            function showConfirm(message, opts) {
                opts = opts || {};
                return new Promise(function (resolve) {
                    const modal = document.getElementById('confirmModal');
                    const titleEl = document.getElementById('confirmModalTitle');
                    const msgEl = document.getElementById('confirmModalMessage');
                    const noteEl = document.getElementById('confirmModalNote');
                    const listEl = document.getElementById('confirmModalDetails');
                    const iconEl = document.getElementById('confirmModalIcon');
                    const okBtn = document.getElementById('confirmModalOkBtn');
                    const cancelBtn = document.getElementById('confirmModalCancelBtn');

                    if (!modal || !msgEl || !okBtn || !cancelBtn) {
                        resolve(false);
                        return;
                    }

                    const danger = !!opts.danger;

                    titleEl.textContent = opts.title || (danger ? 'Are you sure?' : 'Please confirm');
                    msgEl.textContent = message;
                    okBtn.textContent = opts.confirmLabel || (danger ? 'Yes, delete' : 'Confirm');

                    // Colour comes from CSS via a data attribute; setting it inline here
                    // used to fight the stylesheet.
                    modal.setAttribute('data-variant', danger ? 'danger' : 'default');

                    if (iconEl) {
                        iconEl.innerHTML = (opts.icon === 'trash' || danger)
                            ? CONFIRM_ICON_TRASH
                            : CONFIRM_ICON_QUESTION;
                    }

                    if (noteEl) {
                        noteEl.textContent = opts.note || '';
                        noteEl.hidden = !opts.note;
                    }

                    if (listEl) {
                        listEl.textContent = '';
                        const details = opts.details || [];
                        details.forEach(function (pair) {
                            const li = document.createElement('li');
                            const key = document.createElement('span');
                            key.className = 'ci-danger-key';
                            key.textContent = pair[0];
                            const val = document.createElement('span');
                            val.className = 'ci-danger-value';
                            val.textContent = pair[1];
                            li.appendChild(key);
                            li.appendChild(val);
                            listEl.appendChild(li);
                        });
                        listEl.hidden = details.length === 0;
                    }

                    modal.style.display = 'flex';

                    function cleanup(result) {
                        modal.style.display = 'none';
                        okBtn.removeEventListener('click', onOk);
                        cancelBtn.removeEventListener('click', onCancel);
                        document.removeEventListener('keydown', onKey);
                        resolve(result);
                    }
                    function onOk() { cleanup(true); }
                    function onCancel() { cleanup(false); }
                    // No backdrop-to-close: a stray click outside this dialog must not
                    // dismiss a destructive confirmation. Cancel or Escape instead.
                    function onKey(e) { if (e.key === 'Escape') cleanup(false); }

                    okBtn.addEventListener('click', onOk);
                    cancelBtn.addEventListener('click', onCancel);
                    document.addEventListener('keydown', onKey);
                    // Focus Cancel, not the destructive action.
                    cancelBtn.focus();
                });
            }

            function openEditPatientModal(uid, patientId, firstname, middlename, lastname, contact, email, sex, civilStatus) {
                document.getElementById('editPatientUid').value = uid || '';
                document.getElementById('editPatientPatientId').value = patientId || '';
                document.getElementById('editFirstName').value = firstname || '';
                document.getElementById('editMiddleName').value = middlename || '';
                document.getElementById('editLastName').value = lastname || '';
                document.getElementById('editContactNumber').value = contact || '';
                document.getElementById('editEmail').value = email || '';
                document.getElementById('editSex').value = sex || '';
                document.getElementById('editCivilStatus').value = civilStatus || '';

                // Setting .value does not fire "change", so the custom listboxes would
                // not move their tick marks. Nothing else listens to these selects.
                ['editSex', 'editCivilStatus'].forEach(function (id) {
                    const field = document.getElementById(id);
                    if (field) {
                        field.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                });

                const fullName = [firstname, middlename, lastname].filter(Boolean).join(' ');
                const subtitle = document.getElementById('editPatientSubtitle');
                if (subtitle) {
                    const bits = [];
                    if (fullName) bits.push(fullName);
                    if (patientId) bits.push('Patient ID: ' + patientId);
                    subtitle.textContent = bits.join('   ·   ');
                }

                const modal = document.getElementById('editPatientModal');
                modal.style.display = 'flex';

                // No backdrop-to-close: clicking outside used to discard the form.
                // Use Cancel, the X, or Escape.
                document.addEventListener('keydown', function onEsc(e) {
                    if (e.key !== 'Escape') return;
                    if (document.getElementById('editPatientModal').style.display === 'flex') {
                        closeEditPatientModal();
                    }
                    document.removeEventListener('keydown', onEsc);
                });

                const firstNameField = document.getElementById('editFirstName');
                if (firstNameField) firstNameField.focus();
            }

            function closeEditPatientModal() {
                document.getElementById('editPatientModal').style.display = 'none';
            }

            document.addEventListener('DOMContentLoaded', function () {

                document.addEventListener('click', async function (e) {
                    const editBtn = e.target.closest('.edit-patient-btn');
                    if (editBtn) {
                        openEditPatientModal(
                            editBtn.getAttribute('data-uid'),
                            editBtn.getAttribute('data-patient-id'),
                            editBtn.getAttribute('data-firstname'),
                            editBtn.getAttribute('data-middlename'),
                            editBtn.getAttribute('data-lastname'),
                            editBtn.getAttribute('data-contact'),
                            editBtn.getAttribute('data-email'),
                            editBtn.getAttribute('data-sex'),
                            editBtn.getAttribute('data-civilstatus')
                        );
                        return;
                    }

                    const blockBtn = e.target.closest('.block-user-btn');
                    if (blockBtn) {
                        const uid = blockBtn.getAttribute('data-uid');
                        const name = blockBtn.getAttribute('data-name') || 'this account';
                        const isCurrentlyDisabled = blockBtn.getAttribute('data-disabled') === 'true';
                        const nextDisabled = !isCurrentlyDisabled;

                        const confirmMsg = nextDisabled
                            ? 'Block ' + name + '? They will not be able to log in until you unblock them.'
                            : 'Unblock ' + name + '? They will be able to log in again.';

                        if (!(await showConfirm(confirmMsg))) {
                            return;
                        }

                        const formData = new FormData();
                        formData.append('uid', uid);
                        formData.append('disabled', nextDisabled ? 'true' : 'false');

                        fetch('/admin/toggle_user_block', {
                            method: 'POST',
                            body: formData
                        })
                            .then(res => res.json())
                            .then(result => {
                                if (result.success) {
                                    const nowDisabled = !!result.disabled;
                                    blockBtn.setAttribute('data-disabled', nowDisabled ? 'true' : 'false');

                                    // The button is icon-only, so swap the glyph and the
                                    // tooltip instead of writing text -- setting textContent
                                    // here would delete the icon span.
                                    const icon = blockBtn.querySelector('.material-symbols-rounded');
                                    if (icon) icon.textContent = nowDisabled ? 'lock_open' : 'block';
                                    blockBtn.title = nowDisabled ? 'Unblock account' : 'Block account';
                                    blockBtn.setAttribute('aria-label',
                                        nowDisabled ? 'Unblock account' : 'Block account');

                                    const row = blockBtn.closest('tr');
                                    row.style.opacity = nowDisabled ? '0.6' : '1';

                                    const nameCell = row.querySelector('td');
                                    const existingBadge = nameCell.querySelector('.status-badge');
                                    if (result.disabled && !existingBadge) {
                                        nameCell.insertAdjacentHTML('beforeend', ' <span class="status-badge blocked">Blocked</span>');
                                    } else if (!result.disabled && existingBadge) {
                                        existingBadge.remove();
                                    }
                                } else {
                                    showToast(result.message || 'Failed to update account status.');
                                }
                            })
                            .catch(function (err) {
                                console.error('Toggle block error:', err);
                                showToast('Failed to update account status. Please try again.');
                            });
                        return;
                    }

                    const delBtn = e.target.closest('.delete-patient-btn');
                    if (delBtn) {
                        const uid = delBtn.getAttribute('data-uid');
                        const patientId = delBtn.getAttribute('data-patient-id');
                        const name = delBtn.getAttribute('data-name') || 'this patient';

                        const confirmed = await showConfirm(
                            'This removes the account along with its booking history and '
                            + 'treatment records.',
                            {
                                danger: true,
                                title: 'Delete this patient?',
                                confirmLabel: 'Delete patient',
                                icon: 'trash',
                                note: 'This cannot be undone.',
                                details: [
                                    ['Patient', name],
                                    ['Patient ID', patientId || '—']
                                ]
                            }
                        );
                        if (!confirmed) {
                            return;
                        }

                        const formData = new FormData();
                        formData.append('uid', uid);
                        formData.append('patient_id', patientId);

                        fetch('/admin/delete_patient', {
                            method: 'POST',
                            body: formData
                        })
                            .then(res => res.json())
                            .then(result => {
                                if (result.success) {
                                    delBtn.closest('tr').remove();
                                    if (result.message && result.message !== 'Patient deleted successfully') {
                                        showToast(result.message);
                                    }
                                } else {
                                    showToast(result.message || 'Failed to delete patient.');
                                }
                            })
                            .catch(function (err) {
                                console.error('Delete patient error:', err);
                                showToast('Failed to delete patient. Please try again.');
                            });
                    }
                });

                const editPatientForm = document.getElementById('editPatientForm');
                if (editPatientForm) {
                    editPatientForm.addEventListener('submit', function (e) {
                        e.preventDefault();

                        const formData = new FormData(editPatientForm);

                        // admin_dashboard.html — inside editPatientForm submit handler
                        fetch('/admin/update_patient', {
                            method: 'POST',
                            body: formData
                        })
                            .then(res => res.json())
                            .then(result => {
                                if (result.success) {
                                    showToast('Patient updated successfully.');

                                    const uid = formData.get('uid');
                                    const firstName = formData.get('first_name') || '';
                                    const middleName = formData.get('middle_name') || '';
                                    const lastName = formData.get('last_name') || '';
                                    const contact = formData.get('contact_number') || '';
                                    const email = formData.get('email') || '';
                                    const sex = formData.get('sex') || '';
                                    const civilStatus = formData.get('civil_status') || '';
                                    const fullName = [firstName, middleName, lastName].filter(Boolean).join(' ');

                                    const editBtn = document.querySelector('.edit-patient-btn[data-uid="' + uid + '"]');
                                    if (editBtn) {
                                        const row = editBtn.closest('tr');
                                        if (row) {
                                            // By name, not position - see the note on the
                                            // other in-place row refresh.
                                            const cellBy = name => row.querySelector('td[data-cell="' + name + '"]');
                                            const nameCell = cellBy('name');
                                            const sexCell = cellBy('sex');
                                            const civilCell = cellBy('civil');
                                            const mobileCell = cellBy('mobile');
                                            if (nameCell) nameCell.textContent = fullName;
                                            if (sexCell) sexCell.textContent = sex || '-';
                                            if (civilCell) civilCell.textContent = civilStatus || '-';
                                            if (mobileCell) mobileCell.textContent = contact;
                                            const delBtn = row.querySelector('.delete-patient-btn');
                                            if (delBtn) delBtn.setAttribute('data-name', fullName);
                                        }
                                        editBtn.setAttribute('data-firstname', firstName);
                                        editBtn.setAttribute('data-middlename', middleName);
                                        editBtn.setAttribute('data-lastname', lastName);
                                        editBtn.setAttribute('data-contact', contact);
                                        editBtn.setAttribute('data-email', email);
                                        editBtn.setAttribute('data-sex', sex);
                                        editBtn.setAttribute('data-civilstatus', civilStatus);
                                    }

                                    closeEditPatientModal();
                                } else {
                                    showToast(result.message || 'Failed to update patient.');
                                }
                            })
                            .catch(function (err) {
                                console.error('Update patient error:', err);
                                showToast('Failed to update patient. Please try again.');
                            });
                    });
                }
            });

            (function () {
                const firstNameInput = document.getElementById('admFirstName');
                const lastNameInput = document.getElementById('admLastName');
                const middleNameInput = document.getElementById('admMiddleName');
                const birthdayInput = document.getElementById('admBirthday');
                const warningBox = document.getElementById('admDuplicateWarning');
                const dupNameSpan = document.getElementById('admDupName');
                const useDupBtn = document.getElementById('admUseDupBtn');
                const dismissDupBtn = document.getElementById('admDismissDupBtn');

                if (!firstNameInput || !lastNameInput) return;

                let lastMatch = null;
                let debounceTimer = null;

                async function checkDuplicate() {
                    const first = firstNameInput.value.trim();
                    const last = lastNameInput.value.trim();

                    if (first.length < 2 || last.length < 2) {
                        warningBox.style.display = 'none';
                        lastMatch = null;
                        return;
                    }

                    const payload = {
                        first_name: first,
                        last_name: last,
                        middle_name: middleNameInput ? middleNameInput.value.trim() : '',
                        birthday: birthdayInput ? birthdayInput.value.trim() : ''
                    };

                    try {
                        const res = await fetch('/admin/check_duplicate_patient', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload)
                        });
                        const result = await res.json();

                        if (result.match) {
                            lastMatch = result;
                            dupNameSpan.textContent = [result.first_name, result.middle_name, result.last_name].filter(Boolean).join(' ');
                            warningBox.style.display = 'block';
                        } else {
                            lastMatch = null;
                            warningBox.style.display = 'none';
                        }
                    } catch (err) {
                        console.error('Duplicate check failed:', err);
                    }
                }

                function debouncedCheck() {
                    clearTimeout(debounceTimer);
                    debounceTimer = setTimeout(checkDuplicate, 500);
                }

                [firstNameInput, lastNameInput, middleNameInput, birthdayInput].forEach(el => {
                    if (el) el.addEventListener('blur', debouncedCheck);
                });

                dismissDupBtn.addEventListener('click', () => {
                    warningBox.style.display = 'none';
                    lastMatch = null;
                });

                useDupBtn.addEventListener('click', () => {
                    if (!lastMatch) return;

                    document.querySelector('input[name="patientMode"][value="existing"]').checked = true;
                    togglePatientMode();

                    const searchInput = document.getElementById('admPatientSearch');
                    const select = document.getElementById('admPatientSelect');
                    const uidField = document.getElementById('admPatientUid');

                    searchInput.value = dupNameSpan.textContent;
                    searchInput.dispatchEvent(new Event('input'));

                    setTimeout(() => {
                        for (const opt of select.options) {
                            if (opt.value === lastMatch.patient_id) {
                                select.value = lastMatch.patient_id;
                                uidField.value = opt.dataset.accountUid || '';
                                break;
                            }
                        }
                    }, 500);

                    warningBox.style.display = 'none';
                });
            })();
