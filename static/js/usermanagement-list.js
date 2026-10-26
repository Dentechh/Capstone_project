document.addEventListener('DOMContentLoaded', function () {
    const tbody = document.querySelector('#userManagementTable tbody');
    const pagination = document.getElementById('userMgmtPagination');
    const prevBtn = document.getElementById('userMgmtPrevBtn');
    const nextBtn = document.getElementById('userMgmtNextBtn');
    const numbersEl = document.getElementById('userMgmtPageNumbers');
    const infoEl = document.getElementById('userMgmtPageInfo');

    if (!tbody) return;

    const state = { page: 1, pageSize: 30, total: 0, totalPages: 1 };

    function buildRow(a) {
        const tr = document.createElement('tr');
        const isDisabled = !!a.disabled;
        const isOnline = !!a.is_online;
        if (isDisabled) tr.style.opacity = '0.6';
        tr.innerHTML = `
            <td data-cell="name">${a.display_name || a.full_name || ''}${isDisabled ? ' <span class="status-badge blocked">Blocked</span>' : ''}</td>
            <td data-cell="mobile">${a.contact_number || '-'}</td>
            <td>${a.email || '-'}</td>
            <td data-cell="status">
                ${isOnline ? '<span class="status-badge online">Online</span>' : '<span class="status-badge offline">Offline</span>'}
            </td>
            <td>
                <div class="mp-actions">
                    <button type="button" class="btn-action block-user-btn" title="${isDisabled ? 'Unblock account' : 'Block account'}" aria-label="${isDisabled ? 'Unblock account' : 'Block account'}"
                        data-uid="${a.uid}" data-name="${a.display_name || a.full_name}" data-disabled="${isDisabled ? 'true' : 'false'}"><span class="material-symbols-rounded" aria-hidden="true">${isDisabled ? 'lock_open' : 'block'}</span></button>
                    <button type="button" class="btn-action edit-patient-btn" title="Edit patient" aria-label="Edit patient"
                        data-uid="${a.uid}" data-patient-id="${a.patient_id}"
                        data-firstname="${a.first_name}" data-middlename="${a.middle_name}"
                        data-lastname="${a.last_name}" data-contact="${a.contact_number}" data-email="${a.email}" data-sex="${a.sex || ''}" data-civilstatus="${a.CivilStatus || ''}"><span class="material-symbols-rounded" aria-hidden="true">edit</span></button>
                    <button type="button" class="btn-action delete-patient-btn" title="Delete account" aria-label="Delete account"
                        data-uid="${a.uid}" data-patient-id="${a.patient_id}" data-name="${a.display_name || a.full_name}"><span class="material-symbols-rounded" aria-hidden="true">delete</span></button>
                </div>
            </td>
        `;
        return tr;
    }

    function renderPagination() {
        if (prevBtn) {
            prevBtn.disabled = state.page <= 1;
            prevBtn.style.display = state.page <= 1 ? 'none' : '';
        }
        if (nextBtn) {
            nextBtn.disabled = state.page >= state.totalPages;
            nextBtn.style.display = state.page >= state.totalPages ? 'none' : '';
        }
        if (infoEl) infoEl.textContent = 'Page ' + state.page + ' of ' + state.totalPages + ' (' + state.total + ' accounts)';
        if (!numbersEl) return;
        numbersEl.innerHTML = '';
        const total = state.totalPages;
        const current = state.page;
        const pages = [];
        if (total <= 7) {
            for (let i = 1; i <= total; i++) pages.push(i);
        } else {
            pages.push(1);
            if (current > 3) pages.push('...');
            for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) pages.push(i);
            if (current < total - 2) pages.push('...');
            pages.push(total);
        }
        pages.forEach(function (p) {
            if (p === '...') {
                const span = document.createElement('span');
                span.textContent = '\u2026';
                numbersEl.appendChild(span);
                return;
            }
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn-action filter-btn';
            btn.textContent = p;
            if (p === current) btn.disabled = true;
            btn.addEventListener('click', function () { loadPage(p); });
            numbersEl.appendChild(btn);
        });
    }

    function loadPage(page) {
        if (page) state.page = parseInt(page, 10) || state.page;
        if (state.page < 1) state.page = 1;
        fetch('/admin/user_management_page?page=' + encodeURIComponent(state.page) + '&page_size=' + encodeURIComponent(state.pageSize))
            .then(res => res.json())
            .then(result => {
                if (!result.success) {
                    if (typeof showToast === 'function') showToast(result.message || 'Failed to load accounts.');
                    return;
                }
                tbody.innerHTML = '';
                (result.rows || []).forEach(function (a) {
                    tbody.appendChild(buildRow(a));
                });
                state.page = result.page || state.page;
                state.pageSize = result.page_size || state.pageSize;
                state.total = (typeof result.total === 'number') ? result.total : state.total;
                state.totalPages = result.total_pages || state.totalPages;
                if (state.totalPages < 1) state.totalPages = 1;
                if (state.page > state.totalPages) state.page = state.totalPages;
                renderPagination();
                if (state.page === 1 && typeof sortUserManagement === 'function') {
                    // keep sort state
                }
            })
            .catch(function (err) {
                console.error('Load accounts error:', err);
                if (typeof showToast === 'function') showToast('Failed to load accounts. Please try again.');
            });
    }

    if (prevBtn) prevBtn.addEventListener('click', function () { if (state.page > 1) loadPage(state.page - 1); });
    if (nextBtn) nextBtn.addEventListener('click', function () { if (state.page < state.totalPages) loadPage(state.page + 1); });

    // Live name search (onkeyup in markup).
    window.filterUserManagement = function () {
        var terms = (document.getElementById('userMgmtSearch').value || '').toUpperCase().split(/[\s,]+/).filter(Boolean);
        var rows = tbody.querySelectorAll('tr');
        rows.forEach(function (row) {
            var nameCell = row.querySelector('td[data-cell="name"]');
            if (nameCell) {
                var textValue = nameCell.textContent || nameCell.innerText;
                var upper = textValue.toUpperCase();
                row.style.display = terms.every(function (t) { return upper.indexOf(t) > -1; }) ? '' : 'none';
            }
        });
    };

    window.sortUserManagement = function (forceAsc) {
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
        rows.forEach(function (row) { tbody.appendChild(row); });
    };

    // initial load
    loadPage(1);
});
