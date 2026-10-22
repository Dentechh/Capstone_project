            document.addEventListener('DOMContentLoaded', function () {
                const loadMoreBtn = document.getElementById('userMgmtLoadMoreBtn');
                const cursorHolder = document.getElementById('userMgmtCursor');
                const tbody = document.querySelector('#userManagementTable tbody');

                if (!loadMoreBtn || !cursorHolder || !tbody) return;

                loadMoreBtn.addEventListener('click', function () {
                    const cursor = cursorHolder.getAttribute('data-cursor') || '';
                    const isFirstPage = (cursor === '');
                    loadMoreBtn.disabled = true;
                    loadMoreBtn.textContent = 'Loading...';

                    fetch('/admin/manageable_accounts_page?cursor=' + encodeURIComponent(cursor))
                        .then(res => res.json())
                        .then(result => {
                            if (!result.success) {
                                showToast(result.message || 'Failed to load more accounts.');
                                return;
                            }

                            result.rows.forEach(function (a) {
                                const tr = document.createElement('tr');
                                const isDisabled = !!a.disabled;
                                const isOnline = !!a.is_online;
                                if (isDisabled) tr.style.opacity = '0.6';
                                tr.innerHTML = `
                        <td data-cell="name">${a.full_name || ''}${isDisabled ? ' <span class="status-badge blocked">Blocked</span>' : ''}</td>
                            <td data-cell="mobile">${a.contact_number || '-'}</td>

                        <td>${a.email || '-'}</td>
                        <td data-cell="status">
                            ${isOnline ? '<span class="status-badge online">Online</span>' : '<span class="status-badge offline">Offline</span>'}
                        </td>
                        <td>
                            <div class="mp-actions">
                                <button type="button" class="btn-action block-user-btn" title="${isDisabled ? 'Unblock account' : 'Block account'}" aria-label="${isDisabled ? 'Unblock account' : 'Block account'}"
                                    data-uid="${a.uid}" data-name="${a.full_name}" data-disabled="${isDisabled ? 'true' : 'false'}"><span class="material-symbols-rounded" aria-hidden="true">${isDisabled ? 'lock_open' : 'block'}</span></button>
                                <button type="button" class="btn-action edit-patient-btn" title="Edit patient" aria-label="Edit patient"
                                    data-uid="${a.uid}" data-patient-id="${a.patient_id}"
                                    data-firstname="${a.first_name}" data-middlename="${a.middle_name}"
                                    data-lastname="${a.last_name}" data-contact="${a.contact_number}" data-email="${a.email}" data-sex="${a.sex || ''}" data-civilstatus="${a.CivilStatus || ''}"><span class="material-symbols-rounded" aria-hidden="true">edit</span></button>
                                <button type="button" class="btn-action delete-patient-btn" title="Delete account" aria-label="Delete account"
                                    data-uid="${a.uid}" data-patient-id="${a.patient_id}" data-name="${a.full_name}"><span class="material-symbols-rounded" aria-hidden="true">delete</span></button>
                            </div>
                        </td>
                    `;
                                tbody.appendChild(tr);
                            });

                            if (isFirstPage && typeof sortUserManagement === 'function') {
                                sortUserManagement(true);
                            }

                            if (result.next_cursor) {
                                cursorHolder.setAttribute('data-cursor', result.next_cursor);
                                loadMoreBtn.disabled = false;
                                loadMoreBtn.textContent = 'Load More';
                            } else {
                                loadMoreBtn.style.display = 'none';
                            }
                        })
                        .catch(function (err) {
                            console.error('Load more accounts error:', err);
                            showToast('Failed to load more accounts. Please try again.');
                            loadMoreBtn.disabled = false;
                            loadMoreBtn.textContent = 'Load More';
                        });
                });
            });

            // Live name search for the User Management table (onkeyup in the section markup).
        function filterUserManagement() {
            var terms = document.getElementById('userMgmtSearch').value.toUpperCase().split(/[\s,]+/).filter(Boolean);
            var table = document.getElementById('userManagementTable');
            var tbody = table.querySelector('tbody');
            var rows = tbody.querySelectorAll('tr');
            rows.forEach(function (row) {
                var nameCell = row.querySelector('td[data-cell="name"]');
                if (nameCell) {
                    var textValue = nameCell.textContent || nameCell.innerText;
                    var upper = textValue.toUpperCase();
                    row.style.display = terms.every(function (t) { return upper.indexOf(t) > -1; }) ? '' : 'none';
                }
            });
        }

        function sortUserManagement(forceAsc) {
            var table = document.getElementById('userManagementTable');
            var tbody = table.querySelector('tbody');
            var rows = Array.from(tbody.querySelectorAll('tr'));
            var sortBtn = document.getElementById('sortUserMgmtBtn');
            var isAsc;
            if (forceAsc === true) isAsc = true;
            else if (forceAsc === false) isAsc = false;
            else isAsc = sortBtn.getAttribute('data-sort') !== 'asc';
            sortBtn.setAttribute('data-sort', isAsc ? 'asc' : 'desc');
            var label = sortBtn.querySelector('.filter-btn__label');
            if (label) label.textContent = isAsc ? 'A-Z' : 'Z-A';
            rows.sort(function (a, b) {
                var aCell = a.querySelector('td[data-cell="name"]');
                var bCell = b.querySelector('td[data-cell="name"]');
                var aName = aCell ? aCell.textContent.toLowerCase() : '';
                var bName = bCell ? bCell.textContent.toLowerCase() : '';
                if (aName < bName) return isAsc ? -1 : 1;
                if (aName > bName) return isAsc ? 1 : -1;
                return 0;
            });
            rows.forEach(function (row) {
                tbody.appendChild(row);
            });
        }
