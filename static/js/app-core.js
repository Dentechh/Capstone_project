function showSection(sectionId) {
            document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
            const activeNav = document.getElementById('nav-' + sectionId);
            if (activeNav) activeNav.classList.add('active');

            document.querySelectorAll('.content-section').forEach(section => {
                section.classList.remove('active-section');
            });

            const target = document.getElementById('section-' + sectionId);
            if (target) target.classList.add('active-section');

            const titles = {
                'dashboard': 'Dashboard Overview',
                'financialreports': 'Financial Reports',
                'doctorscalendar': 'Doctors Calendar',
                'appointments': 'Appointment Requests',
                'WeeklyClients': 'My Weekly Patients',
                'records': 'Patient Database',
                'patientdashboard': 'Patient Dashboard',
                'mypatients': 'My Patients',
                'usermanagement': 'User Management',
            };
            document.getElementById('page-title').innerText = titles[sectionId] || 'Admin Panel';

            // Lazy-load the four big lists the first time their tab is opened,
            // so opening the dashboard itself doesn't read them from Firestore.
            loadSectionOnce(sectionId);

            // Unpaid Procedures table: refetch each time Financial Reports is
            // opened so it reflects payments taken since. The server answers
            // from its cache, so this is cheap.
            if (sectionId === 'financialreports' && typeof loadUnpaidProcedures === 'function') {
                loadUnpaidProcedures();
            }
        }

        // section id -> [load-more button, cursor holder, container to clear]
        const LAZY_SECTIONS = {
            appointments: ['appointmentsLoadMoreBtn', 'appointmentsCursor', '#appointmentsTable tbody'],
            WeeklyClients: ['weeklyClientsLoadMoreBtn', 'weeklyClientsCursor', '#weeklyClientsGrid'],
            mypatients: ['myPatientsLoadMoreBtn', 'myPatientsCursor', '#myPatientsTable tbody'],
            usermanagement: ['userMgmtLoadMoreBtn', 'userMgmtCursor', '#userManagementTable tbody']
        };
        window._lazyLoaded = window._lazyLoaded || {};

        function loadSectionOnce(sectionId) {
            const cfg = LAZY_SECTIONS[sectionId];
            if (!cfg || window._lazyLoaded[sectionId]) return;
            const btn = document.getElementById(cfg[0]);
            const cursor = document.getElementById(cfg[1]);
            const container = document.querySelector(cfg[2]);
            if (!btn || !cursor || !container) return;

            window._lazyLoaded[sectionId] = true;
            container.innerHTML = '';            // drop anything inserted locally before the first load
            cursor.setAttribute('data-cursor', '');   // empty cursor = first page
            btn.style.display = '';
            btn.click();                         // reuses the existing Load More handler
        }

        function openPatientDashboard(
            name,
            lastname,
            uid,
            birthday,
            sex,
            age,
            middlename,
            nationality,
            religion,
            occupation,
            civilstatus,
            contact,
            service,
            Patient_unq_id,
            q1,
            q2,
            q3,
            q4,
            q5,
            q6,
            q7,
            q9,
            q2_spec,
            q3_spec,
            q4_spec,
            q5_spec,
            q7_spec,
            q9_spec,
            w_preg,
            w_nurse,
            w_pill
        ) {

            var pdFullName = (name || 'Unknown') + " " + (lastname || '');

            document.getElementById('pd-name').innerText = pdFullName;
            // The "Account No" wording now lives in the markup, so #pd-id holds only
            // the uid. Anything that reads it must not expect the old prefixed string.
            document.getElementById('pd-id').innerText = uid || '';

            // Avatar: show initials straight away, then upgrade to the uploaded
            // picture if this account has one. A patient with no account document,
            // or one that never chose a picture, keeps the default avatar.
            renderPatientAvatar(pdFullName, uid);

            // Never default a missing Sex to a real gender value -- showing an
            // unknown patient's sex as "Female" is wrong data, not a placeholder.
            document.getElementById('pd-gender').innerText = sex || 'Not set';
            document.getElementById('pd-age').innerText = age || 'N/A';
            syncWomensHealthVisibility(sex);

            document.getElementById('pd-disp-fullname').innerText =
                (name || 'Unknown') + " " + (lastname || '');
            document.getElementById('pd-disp-middlename').innerText = middlename || 'Unknown';
            document.getElementById('pd-disp-birthday').innerText = birthday || 'Unknown';

            document.getElementById('pd-disp-nationality').innerText = nationality || 'Unknown';
            document.getElementById('pd-disp-religion').innerText = religion || 'Unknown';
            document.getElementById('pd-disp-occupation').innerText = occupation || 'Unknown';
            document.getElementById('pd-disp-civilstatus').innerText = civilstatus || 'Unknown';

            document.getElementById('pd-disp-contact').innerText = contact || 'Unknown';
            document.getElementById('pd-disp-service').innerText = service || 'Unknown';

            document.getElementById('pd-disp-Patient_unq_id').innerText = Patient_unq_id || 'Unknown';
            document.getElementById('td-Patient_unq_id').innerText = Patient_unq_id || 'Unknown';
            document.getElementById('td-history-uid').innerText = uid || 'Unknown';
            // 🧠 IMPORTANT: store correct patient record ID globally
            window.currentPatientId = Patient_unq_id;
            window.currentPatientUid = uid;

            // Blood type - hardcoded
            var pdBloodEl = document.getElementById('pd-blood');
            if (pdBloodEl) pdBloodEl.innerText = 'O+';

            // Medical History
            setCheckbox('q1-check', q1);
            setCheckbox('q2-check', q2);
            setCheckbox('q3-check', q3);
            setCheckbox('q4-check', q4);
            setCheckbox('q5-check', q5);
            setCheckbox('q6-check', q6);
            setCheckbox('q7-check', q7);
            setCheckbox('q9-check', q9);

            setSpec('q2-spec', q2_spec);
            setSpec('q3-spec', q3_spec);
            setSpec('q4-spec', q4_spec);
            setSpec('q5-spec', q5_spec);
            setSpec('q7-spec', q7_spec);
            setSpec('q9-spec', q9_spec);

            // Women's Health
            setCheckbox('w-preg-check', w_preg);
            setCheckbox('w-nurse-check', w_nurse);
            setCheckbox('w-pill-check', w_pill);

            // Show nav link (flex, not block: the .nav-item class
            // centers icon + label with flexbox, and an inline
            // display value overrides it)
            var navLink = document.getElementById('nav-patientdashboard');
            if (navLink) navLink.style.display = 'flex';

            showSection('patientdashboard');

            // Show treatment section
            var tdSection = document.getElementById('td-treatment-section');
            if (tdSection) tdSection.style.display = 'block';

            // ✅ FIX: always use Patient_unq_id, NOT uid
            loadTreatmentNotes(Patient_unq_id);

            // Load Visit History
            fetch(`/get_patient/${uid}`)
                .then(res => res.json())
                .then(data => {

                    // Sex can be missing on the button that opened this dashboard: it comes
                    // from the Approve record, and older records predate that field. The
                    // account keeps the latest accepted value, which get_patient now exposes
                    // as "sex", so use it as the fallback. Women's Health visibility has to
                    // follow the resolved value, not the earlier possibly-empty one.
                    var fetchedSex = (data && data.sex ? String(data.sex) : '').trim();
                    if (fetchedSex && !(sex || '').trim()) {
                        document.getElementById('pd-gender').innerText = fetchedSex;
                        syncWomensHealthVisibility(fetchedSex);
                    }

                    const history = document.getElementById("pd-visit-history");
                    history.innerHTML = "";

                    const procedures = data.Done_procedure || [];
                    setVisitCount(procedures.length);

                    if (procedures.length === 0) {

                        renderVisitHistoryEmpty(history, 'event_busy', 'No visit history found.');
                        return;
                    }

                    window.currentProcedures = procedures;

                    procedures.forEach(function (p, index) {

                        history.innerHTML += `
        <tr>
            <td>${formatDentistName(p.dentist)}</td>
            <td class="pd-visits__chart">
                <button type="button" class="pd-icon-btn"
                    onclick="openChartViewModal(${index})"
                    title="View dental chart"
                    aria-label="View dental chart for visit ${index + 1}">
                    <span class="material-symbols-rounded" aria-hidden="true">visibility</span>
                </button>
            </td>
            <td>${p.date || ""}</td>
            <td>${p.procedure || ""}</td>
            <td class="pd-visits__fee">₱${p.paid || 0}</td>
            <td>${formatApptDateTime(p.next_appointment) || ""}</td>
        </tr>
    `;

                    });
                })
                .catch(function () {
                    renderVisitHistoryEmpty(
                        document.getElementById("pd-visit-history"),
                        'error',
                        'Could not load visit history. Please try again.'
                    );
                    setVisitCount(null);
                });
        }

        /**
         * Empty/error row for the Visit History table.
         *
         * All three states (nothing selected, no visits, load failed) go through here
         * so they look the same instead of being a bare centred sentence.
         */
        function renderVisitHistoryEmpty(tbody, icon, message) {
            if (!tbody) return;
            // Static strings only -- no patient data is interpolated into markup.
            tbody.innerHTML =
                '<tr><td colspan="6">' +
                '<div class="pd-empty">' +
                '<span class="material-symbols-rounded pd-empty__icon" aria-hidden="true">' + icon + '</span>' +
                '<span class="pd-empty__text">' + message + '</span>' +
                '</div>' +
                '</td></tr>';
        }

        /**
         * Visit count badge in the Visit History panel header.
         *
         * null clears it back to hidden, which is what a failed load should show --
         * "0 visits" would claim the patient has no history, and we do not know that.
         */
        function setVisitCount(count) {
            var badge = document.getElementById('pd-visits-count');
            if (!badge) return;
            if (count === null || count === undefined) {
                badge.hidden = true;
                badge.textContent = '';
                return;
            }
            badge.textContent = count === 1 ? '1 visit' : count + ' visits';
            badge.hidden = count === 0;
        }


        /**
         * Avatar for the Patient Dashboard header.
         *
         * Starts on the initials badge (always available, never waits on the
         * network), then asks the server for the patient's uploaded picture and
         * swaps it in only if one exists. An account with no picture, a missing
         * account document, a failed request, or a broken image URL all keep the
         * initials badge, so the header is never left blank or broken.
         */
        function renderPatientAvatar(fullName, uid) {
            var img = document.getElementById('pd-avatar-img');
            var initialsEl = document.getElementById('pd-avatar-initials');

            var initials = (fullName || '').trim().split(/\s+/)
                .filter(Boolean)
                .slice(0, 2)
                .map(function (part) { return part.charAt(0); })
                .join('')
                .toUpperCase();

            if (initialsEl) initialsEl.textContent = initials || '?';

            if (!img) return;

            img.style.display = 'none';
            img.onerror = function () {
                img.style.display = 'none';
            };

            if (!uid) return;

            fetch('/admin/patient_avatar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ uid: uid })
            })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data && data.profile_pic) {
                        img.src = data.profile_pic;
                        img.style.display = 'block';
                    }
                })
                .catch(function () { /* keep the initials badge */ });
        }




        function setCheckbox(id, value) {
            var el = document.getElementById(id);
            if (el) {
                var span = el.querySelector('.pd-check__value') || el.querySelector('span');
                if (span) {
                    var yes = (value === 'Y' || value === 'Yes' || value === 'yes');
                    span.innerText = yes ? 'Yes' : 'No';
                    // State comes from these classes now; the inline colour is
                    // cleared so it can't keep overriding them.
                    span.classList.toggle('is-yes', yes);
                    span.classList.toggle('is-no', !yes);
                    span.style.color = '';
                }
            }
        }

        /**
         * Hide the Women's Health block for a male patient.
         *
         * Those questions (pregnant / nursing / birth control) can't apply to a male
         * patient, so showing them just adds noise. Anything that is not explicitly
         * Male -- Female, blank, or an unexpected value -- keeps the block visible,
         * because a section we can't prove is irrelevant may still hold real answers.
         */
        function syncWomensHealthVisibility(sex) {
            var block = document.getElementById('pd-womens-block');
            if (!block) return;
            var isMale = /^(m|male)$/i.test((sex || '').trim());
            block.hidden = isMale;
            block.style.display = isMale ? 'none' : '';
        }

        function setSpec(id, value) {
            var el = document.getElementById(id);
            if (el) {
                el.innerText = value ? '(' + value + ')' : '';
            }
        }

        function filterPatients() {
            var input = document.getElementById('patientSearch').value.toUpperCase();
            var table = document.getElementById('recordsTable');
            var tr = table.getElementsByTagName('tr');
            for (var i = 1; i < tr.length; i++) {
                var td = tr[i].getElementsByTagName('td')[1];
                if (td) {
                    var textValue = td.textContent || td.innerText;
                    tr[i].style.display = textValue.toUpperCase().indexOf(input) > -1 ? '' : 'none';
                }
            }
        }

        // Sort buttons now contain an icon plus a label, so write the
        // label into its own span. textContent would delete the icon.
        function setFilterSortLabel(btn, label) {
            var el = btn.querySelector('.filter-btn__label');
            if (el) {
                el.textContent = label;
                return;
            }
            btn.textContent = label;
        }

        function sortMyPatients() {
            var table = document.getElementById('myPatientsTable');
            var tbody = table.querySelector('tbody');
            var rows = Array.from(tbody.querySelectorAll('tr'));
            var sortBtn = document.getElementById('sortMyPatientsBtn');
            var isAsc = sortBtn.getAttribute('data-sort') !== 'asc';
            sortBtn.setAttribute('data-sort', isAsc ? 'asc' : 'desc');
            setFilterSortLabel(sortBtn, isAsc ? 'A-Z' : 'Z-A');
            rows.sort(function (a, b) {
                var aName = a.querySelector('td') ? a.querySelector('td').textContent.toLowerCase() : '';
                var bName = b.querySelector('td') ? b.querySelector('td').textContent.toLowerCase() : '';
                if (aName < bName) return isAsc ? -1 : 1;
                if (aName > bName) return isAsc ? 1 : -1;
                return 0;
            });
            rows.forEach(function (row) {
                tbody.appendChild(row);
            });
        }

        function sortMyPatientsByDate() {
            var table = document.getElementById('myPatientsTable');
            var tbody = table.querySelector('tbody');
            var rows = Array.from(tbody.querySelectorAll('tr'));
            var sortBtn = document.getElementById('sortMyPatientsDateBtn');
            var isNewest = sortBtn.getAttribute('data-sort') !== 'asc';
            sortBtn.setAttribute('data-sort', isNewest ? 'asc' : 'desc');
            setFilterSortLabel(sortBtn, isNewest ? 'Newest' : 'Oldest');
            rows.sort(function (a, b) {
                var aVal = a.getAttribute('data-recent-appointment');
                var bVal = b.getAttribute('data-recent-appointment');
                var aDate = aVal ? new Date(aVal) : new Date(0);
                var bDate = bVal ? new Date(bVal) : new Date(0);
                if (isNewest) {
                    return bDate - aDate;
                } else {
                    return aDate - bDate;
                }
            });
            rows.forEach(function (row) {
                tbody.appendChild(row);
            });
        }

        function filterWeeklyClients() {
            var input = document.getElementById('weeklyClientSearch').value.toUpperCase();
            var grid = document.getElementById('weeklyClientsGrid');
            var cards = grid.querySelectorAll('.patient-card');
            cards.forEach(function (card) {
                var name = card.getAttribute('data-name') || '';
                var text = card.textContent || '';
                card.style.display = text.toUpperCase().indexOf(input) > -1 ? '' : 'none';
            });
        }

        function sortWeeklyClients() {
            var grid = document.getElementById('weeklyClientsGrid');
            var cards = Array.from(grid.querySelectorAll('.patient-card'));
            var sortBtn = document.getElementById('sortWeeklyClientsBtn');
            var isAsc = sortBtn.getAttribute('data-sort') !== 'asc';
            sortBtn.setAttribute('data-sort', isAsc ? 'asc' : 'desc');
            setFilterSortLabel(sortBtn, isAsc ? 'A-Z' : 'Z-A');
            cards.sort(function (a, b) {
                var aName = (a.getAttribute('data-name') || '').toLowerCase();
                var bName = (b.getAttribute('data-name') || '').toLowerCase();
                if (aName < bName) return isAsc ? -1 : 1;
                if (aName > bName) return isAsc ? 1 : -1;
                return 0;
            });
            cards.forEach(function (card) {
                grid.appendChild(card);
            });
        }

        function sortWeeklyClientsByDate() {
            var grid = document.getElementById('weeklyClientsGrid');
            var cards = Array.from(grid.querySelectorAll('.patient-card'));
            var sortBtn = document.getElementById('sortWeeklyClientsDateBtn');
            var isNewest = sortBtn.getAttribute('data-sort') !== 'asc';
            sortBtn.setAttribute('data-sort', isNewest ? 'asc' : 'desc');
            setFilterSortLabel(sortBtn, isNewest ? 'Newest' : 'Oldest');
            cards.sort(function (a, b) {
                var aDate = new Date(a.getAttribute('data-accepted-at') || '');
                var bDate = new Date(b.getAttribute('data-accepted-at') || '');
                if (isNewest) {
                    return bDate - aDate;
                } else {
                    return aDate - bDate;
                }
            });
            cards.forEach(function (card) {
                grid.appendChild(card);
            });
        }

        document.addEventListener('click', function (e) {
            var btn = e.target.closest('.check-profile-btn');
            if (!btn) return;

            openPatientDashboard(
                btn.getAttribute('data-name'),
                btn.getAttribute('data-lastname'),
                btn.getAttribute('data-uid'),
                btn.getAttribute('data-birthday'),
                btn.getAttribute('data-sex'),
                btn.getAttribute('data-age'),
                btn.getAttribute('data-middlename'),
                btn.getAttribute('data-nationality'),
                btn.getAttribute('data-religion'),
                btn.getAttribute('data-occupation'),
                btn.getAttribute('data-civilstatus'),
                btn.getAttribute('data-contact'),
                btn.getAttribute('data-service'),
                btn.getAttribute('data-Patient_unq_id'),
                btn.getAttribute('data-q1'),
                btn.getAttribute('data-q2'),
                btn.getAttribute('data-q3'),
                btn.getAttribute('data-q4'),
                btn.getAttribute('data-q5'),
                btn.getAttribute('data-q6'),
                btn.getAttribute('data-q7'),
                btn.getAttribute('data-q9'),
                btn.getAttribute('data-q2_spec'),
                btn.getAttribute('data-q3_spec'),
                btn.getAttribute('data-q4_spec'),
                btn.getAttribute('data-q5_spec'),
                btn.getAttribute('data-q7_spec'),
                btn.getAttribute('data-q9_spec'),
                btn.getAttribute('data-w-preg'),
                btn.getAttribute('data-w-nurse'),
                btn.getAttribute('data-w-pill')
            );
        });

        var saveBtn = document.getElementById('td-save-btn');
        var addBtn = document.getElementById('td-add-row-btn');
        if (addBtn) addBtn.addEventListener('click', addTreatmentRow);

        // Delete a Treatment Records row. Delegated from the tbody so it covers
        // the placeholder row in the markup and every row appendRow() builds,
        // now and in the future, without per-row wiring.
        //
        // Nothing tracks rows by index -- saveTreatmentNotes() and the FormData
        // submit both walk the live <tr> list -- so removing the element is the
        // whole delete. What matters is tearing down what those rows own first:
        // each enhanced <select> can have its option panel portalled to <body>,
        // and each date field owns a flatpickr calendar also appended to <body>.
        // Dropping the <tr> alone would orphan both on the page.
        (function wireTreatmentRowDelete() {
            var tbody = document.querySelector('#td-treatment-table tbody');
            if (!tbody) return;

            tbody.addEventListener('click', function (e) {
                var btn = e.target.closest('[data-td-delete-row]');
                if (!btn) return;
                var row = btn.closest('tr');
                if (!row) return;

                // The panel reads "one row per treatment", so keep at least one:
                // deleting the last row would leave an empty tbody, and both
                // save paths plus the empty-state handling assume rows exist.
                var rows = tbody.querySelectorAll('tr');
                if (rows.length <= 1) {
                    showToast('At least one treatment row is required.');
                    return;
                }

                doDeleteTreatmentRow(row);
            });
        })();

        // Removes one row and releases the body-level nodes it owned. Split out
        // so it can be called from the click handler and, if ever needed, from
        // elsewhere without duplicating the cleanup.
        function doDeleteTreatmentRow(row) {
            // Undo the .adm-select wrappers first: their panels live on <body>
            // while open and would otherwise outlive the row.
            if (typeof window.admDestroySelects === 'function') {
                window.admDestroySelects(row);
            }

            // flatpickr appends its calendar to <body> and only removes it on
            // destroy(), so the instance has to be told.
            row.querySelectorAll('input.adm-date-native').forEach(function (input) {
                if (input._flatpickr && typeof input._flatpickr.destroy === 'function') {
                    input._flatpickr.destroy();
                }
            });

            row.remove();
        }

        // The placeholder row that ships in the markup needs the same
        // listboxes and date pickers before any patient is opened.
        refreshTreatmentControls(document.querySelector('#td-treatment-table tbody'));

        // The shared .adm-select component exports itself from a LATER
        // script block, so on this first pass it is still undefined and the
        // dropdowns stay native selects. Retry once the whole document has
        // run. enhanceSelectsIn() is idempotent, so doing it twice is safe.
        window.addEventListener('load', function () {
            refreshTreatmentControls(document.querySelector('#td-treatment-table tbody'));
        });

        initUnifiedGrid('grid-upper', 10, 'checkbox', 'input');
        initUnifiedGrid('grid-perm-upper', 16, 'checkbox', 'input');
        initUnifiedGrid('grid-perm-lower', 16, 'input', 'checkbox');
        initUnifiedGrid('grid-lower', 10, 'input', 'checkbox');

        var render = function (rowId, nums) {
            var row = document.getElementById(rowId);
            if (row) nums.forEach(function (n) { row.innerHTML += createToothSVG(n); });
        };

        render('teeth-temp-top', [55, 54, 53, 52, 51, 61, 62, 63, 64, 65]);
        render('teeth-perm-top', [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]);
        render('teeth-perm-bottom', [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]);
        render('teeth-temp-bottom', [85, 84, 83, 82, 81, 71, 72, 73, 74, 75]);


        var currentTool = 'healthy';
        var lastClickedTooth = null;

        // Mirrored on window because initUnifiedGrid() lives in a different
        // scope and needs to know which tool is armed before it lets a status
        // cell receive a check mark. The body class lets CSS show that the
        // cells are only markable while Check is selected.
        window.currentChartTool = currentTool;
        document.body.classList.remove('tool-check-active');

        function setTool(el) {
            document.querySelectorAll('.tool').forEach(function (t) {
                t.classList.remove('active');
                t.setAttribute('aria-pressed', 'false');
            });
            el.classList.add('active');
            el.setAttribute('aria-pressed', 'true');
            currentTool = el.getAttribute('data-tool');
            window.currentChartTool = currentTool;
            document.body.classList.toggle('tool-check-active', currentTool === 'check');
        }

        function createToothSVG(id) {
            return '<div class="tooth-unit" id="tooth-' + id + '">' +
                '<span class="tooth-label">' + id + '</span>' +
                '<svg class="tooth-svg" viewBox="0 0 100 100" onclick="handleToothAction(\'' + id + '\')">' +
                '<path class="segment" d="M50,50 L12,12 A54,54 0 0,1 88,12 Z" onclick="paintSegment(event)" />' +
                '<path class="segment" d="M50,50 L88,12 A54,54 0 0,1 88,88 Z" onclick="paintSegment(event)" />' +
                '<path class="segment" d="M50,50 L88,88 A54,54 0 0,1 12,88 Z" onclick="paintSegment(event)" />' +
                '<path class="segment" d="M50,50 L12,88 A54,54 0 0,1 12,12 Z" onclick="paintSegment(event)" />' +
                '<circle class="segment" cx="50" cy="50" r="23" onclick="paintSegment(event)" />' +
                '<line class="mark-line" x1="50" y1="5" x2="50" y2="95" stroke-width="8" style="display:none; pointer-events:none;" />' +
                '<g class="mark-x" style="display:none; pointer-events:none; stroke:#ff4d4d; stroke-width:8;">' +
                '<line x1="20" y1="20" x2="80" y2="80" />' +
                '<line x1="80" y1="20" x2="20" y2="80" />' +
                '</g>' +
                '</svg>' +
                '</div>';
        }

        function paintSegment(e) {
            if (currentTool === 'caries' || currentTool === 'filling') {
                e.stopPropagation();
                e.target.style.fill = (currentTool === 'caries') ? '#ff4d4d' : '#156699';
            }
        }

        function handleToothAction(id) {
            var tooth = document.getElementById('tooth-' + id);
            var markX = tooth.querySelector('.mark-x');
            var markLine = tooth.querySelector('.mark-line');

            if (currentTool === 'healthy') {
                tooth.querySelectorAll('.segment').forEach(function (s) { s.style.fill = '#ffffff'; });
                markX.style.display = 'none';
                markLine.style.display = 'none';
            } else if (currentTool === 'extraction') {
                markX.style.display = (markX.style.display === 'block') ? 'none' : 'block';
            } else if (currentTool === 'crown') {
                // Crown: full shade red
                tooth.querySelectorAll('.segment').forEach(function (s) { s.style.fill = '#ff4d4d'; });
                markX.style.display = 'none';
                markLine.style.display = 'none';
            } else if (currentTool === 'rootcanal') {
                // Root Canal: full shade blue
                tooth.querySelectorAll('.segment').forEach(function (s) { s.style.fill = '#156699'; });
                markX.style.display = 'none';
                markLine.style.display = 'none';
            } else if (currentTool === 'missing') {
                // Missing Tooth: full shade black
                tooth.querySelectorAll('.segment').forEach(function (s) { s.style.fill = '#000000'; });
                markX.style.display = 'none';
                markLine.style.display = 'none';
            }
        }

        function applyModalChoice(color) {
            var tooth = document.getElementById('tooth-' + lastClickedTooth);
            if (currentTool === 'crown') {
                tooth.querySelectorAll('.segment').forEach(function (s) { s.style.fill = color; });
            } else if (currentTool === 'rootcanal') {
                var line = tooth.querySelector('.mark-line');
                line.setAttribute('stroke', color);
                line.style.display = 'block';
            }
            closeModal();
        }

        // Wipe every mark this chart can hold: tooth segment fills, the
        // extraction X and root-canal line, the status text inputs, and the
        // Check tick boxes. Confirmed first, since a mis-click would discard
        // a chart the dentist filled in by hand.
        //
        // This is a view-level reset only. The chart is not persisted on its
        // own -- what gets saved is the Treatment Records table below it
        // (saveTreatmentNotes), which this deliberately leaves untouched, so
        // clearing the picture cannot silently wipe the patient's history.
        function clearDentalChart() {
            var chart = document.querySelector('#section-chart .dental-chart')
                || document.querySelector('.dental-chart');
            if (!chart) return;

            // Nothing to do if the chart is already blank. The mark checks compare
            // against the pristine values a fresh tooth is built with, so a chart
            // that has already been cleared is correctly seen as empty.
            var painted = chart.querySelectorAll('.segment[style*="fill"]');
            var xsShown = chart.querySelectorAll('.mark-x[style*="block"]');
            var linesShown = chart.querySelectorAll('.mark-line[style*="block"]');
            var typed = Array.prototype.some.call(chart.querySelectorAll('.grid-input'), function (i) { return i.value !== ''; });
            var ticked = Array.prototype.some.call(chart.querySelectorAll('.grid-checkbox'), function (c) { return c.checked; });
            if (!painted.length && !xsShown.length && !linesShown.length && !typed && !ticked) {
                showToast('The chart is already clear.');
                return;
            }

            var doClear = function () {
                // Tooth markings. Removing the inline fill is what puts each
                // segment back to its stylesheet colour, which is the same
                // blank state the Healthy tool produces.
                chart.querySelectorAll('.tooth-unit .segment').forEach(function (s) { s.style.removeProperty('fill'); });

                // Extraction X and the root-canal line are toggled with an INLINE
                // display, and .mark-x carries an inline stroke. There is no CSS
                // rule for either, so clearing must put the pristine inline
                // values back rather than drop the properties: removing
                // display leaves the SVG default (inline), which shows the X on
                // every tooth and makes the first click look like a no-op, and
                // removing stroke drops it to none so the X paints invisibly.
                // The root-canal colour is a presentation ATTRIBUTE (set in
                // applyModalChoice), so it needs removeAttribute as well.
                chart.querySelectorAll('.mark-x').forEach(function (m) {
                    m.style.display = 'none';
                    m.style.stroke = '#ff4d4d';
                });
                chart.querySelectorAll('.mark-line').forEach(function (m) {
                    m.style.display = 'none';
                    m.removeAttribute('stroke');
                });

                // Status rows: free text and Check tick boxes.
                chart.querySelectorAll('.grid-input').forEach(function (i) { i.value = ''; });
                chart.querySelectorAll('.grid-checkbox').forEach(function (c) { c.checked = false; });

                // Drop the tooth the palette was last armed against so a later
                // palette click cannot repaint a tooth the dentist just cleared.
                lastClickedTooth = null;

                showToast('Chart cleared.', 'success');
            };

            // showConfirm() lives in a later script block, so on first paint it
            // may not be defined yet; fall back to clearing directly rather than
            // doing nothing.
            if (typeof showConfirm === 'function') {
                showConfirm('Clear all tooth markings, status text and checks on this chart?', {
                    title: 'Clear the chart?',
                    note: 'Treatment records are not affected.',
                    confirmLabel: 'Yes, clear it',
                    danger: true
                }).then(function (ok) { if (ok) doClear(); });
            } else {
                doClear();
            }
        }

        function closeModal() { document.getElementById('tool-modal').style.display = 'none'; }

        function saveTreatmentNotes() {
            // Key must match what loadTreatmentNotes() is called with in
            // openPatientDashboard -- that is Patient_unq_id, not the
            // account uid shown in the header, so use the stored value
            // rather than re-parsing the header text.
            var uid = window.currentPatientId
                || (document.getElementById('pd-id')?.textContent || '').trim();
            if (!uid) return;
            var rows = [];
            var rowEls = document.querySelectorAll('#td-treatment-table tbody tr');
            rowEls.forEach(function (tr) {
                rows.push({
                    date: tr.querySelector('.td-date') ? tr.querySelector('.td-date').value.trim() : '',
                    tooth: tr.querySelector('.td-tooth') ? tr.querySelector('.td-tooth').value.trim() : '',
                    procedure: tr.querySelector('.td-procedure') ? tr.querySelector('.td-procedure').value.trim() : '',
                    dentist: tr.querySelector('.td-dentist') ? tr.querySelector('.td-dentist').value.trim() : '',
                    valueOfWork: tr.querySelector('.td-value') ? tr.querySelector('.td-value').value.trim() : '',
                    amountPaid: tr.querySelector('.td-paid') ? tr.querySelector('.td-paid').value.trim() : '',
                    balance: tr.querySelector('.td-balance') ? tr.querySelector('.td-balance').value.trim() : '',
                    nextAppt: tr.querySelector('.td-next-appt') ? tr.querySelector('.td-next-appt').value.trim() : ''
                });
            });
            var storage = JSON.parse(localStorage.getItem('td_notes') || '{}');
            storage[uid] = rows;
            localStorage.setItem('td_notes', JSON.stringify(storage));
            var msg = document.getElementById('td-save-msg');
            if (msg) { msg.style.display = 'block'; msg.innerText = 'Treatment records saved!'; setTimeout(function () { msg.style.display = 'none'; }, 2000); }
        }

        function loadTreatmentNotes(uid) {
            var storage = JSON.parse(localStorage.getItem('td_notes') || '{}');
            var rows = storage[uid] || [];
            var tableBody = document.querySelector('#td-treatment-table tbody');
            if (!tableBody) return;
            // Drop the enhanced wrappers first: their option panels can be
            // portalled to <body>, and a row wiped with innerHTML would
            // otherwise leave one orphaned on the page.
            if (typeof window.admDestroySelects === 'function') {
                window.admDestroySelects(tableBody);
            }
            tableBody.innerHTML = '';
            if (rows.length === 0) {
                appendRow({ date: '', tooth: '', procedure: '', dentist: '', valueOfWork: '', amountPaid: '', balance: '', nextAppt: '' });
            } else {
                rows.forEach(function (r) { appendRow(r); });
            }
            refreshTreatmentControls(tableBody);
        }

        /**
         * Gives the Treatment Records rows the same controls the My Patients
         * treatment modal uses:
         *   - the shared .adm-select listbox, so the option panel is a real
         *     styled list rather than an OS-drawn popup;
         *   - flatpickr, so both date fields share one themed calendar.
         * Both helpers are idempotent, so this is safe to call after every
         * rebuild of the tbody and after Add Row appends a row.
         */
        function refreshTreatmentControls(tbody) {
            if (!tbody) return;

            if (typeof window.admEnhanceSelects === 'function') {
                // allowFlip: the table scrolls horizontally, so a panel near
                // the bottom of the viewport should open upwards.
                window.admEnhanceSelects(tbody, '.td-records__scroll', true);
            }

            initTreatmentDatePickers(tbody);
        }

        /**
         * flatpickr keeps the original input (and its value) in place and
         * inserts a visible alt input in front of it, so saveTreatmentNotes(),
         * the FormData submit and the validation all keep reading the same
         * element they always did. The calendar is appended to <body> because
         * .td-records__scroll clips anything overflowing the table.
         *
         * The Next Appointment column is the one field that carries a time
         * as well as a date: it feeds the patient's "next visit" suggestion,
         * which stores "YYYY-MM-DD HH:MM" -- the same shape appointment_date
         * uses everywhere else. The visit Date column stays date-only.
         */
        function initTreatmentDatePickers(scope) {
            if (typeof flatpickr !== 'function') return;
            var root = scope || document;
            root.querySelectorAll('input.adm-date-native').forEach(function (input) {
                if (input._flatpickr) return;
                var withTime = input.classList.contains('td-next-appt');
                var opts = {
                    enableTime: withTime,
                    dateFormat: withTime ? 'Y-m-d H:i' : 'Y-m-d',
                    altInput: true,
                    altFormat: withTime ? 'M j, Y - h:i K' : 'M j, Y',
                    altInputClass: withTime ? 'adm-date-alt adm-next-appt-alt' : 'adm-date-alt',
                    className: 'adm-datepicker',
                    allowInput: false,
                    monthSelectorType: 'static',
                    minuteIncrement: withTime ? 30 : 1,
                    appendTo: document.body
                };
                // A next appointment cannot be in the past, so every
                // day before today is greyed out in the calendar.
                if (withTime) opts.minDate = 'today';
                flatpickr(input, opts);
                // The visible control is flatpickr's alt input, so the real
                // input must not keep `required` or validation would block on
                // a field the user cannot even see.
                input.style.display = 'none';
                input.removeAttribute('required');
            });
        }

        function appendRow(data) {
            var tableBody = document.querySelector('#td-treatment-table tbody');
            if (!tableBody) return;

            var tr = document.createElement('tr');

            tr.innerHTML =
                '<td><input type="date" class="td-date adm-date-native" value="' + escHtml(data.date || '') + '"></td>' +

                '<td><input type="text" class="td-tooth" value="' + escHtml(data.tooth || '') + '" placeholder="e.g. 18"></td>' +

                '<td>' +
                '<select class="td-procedure">' +
                '<option value="" disabled' + (!data.procedure ? ' selected' : '') + '>Select Procedure</option>' +
                '<option value="Dental Consultation"' + (data.procedure === "Dental Consultation" ? " selected" : "") + '>Dental Consultation</option>' +
                '<option value="Oral Prophylaxis (Cleaning)"' + (data.procedure === "Oral Prophylaxis (Cleaning)" ? " selected" : "") + '>Oral Prophylaxis (Cleaning)</option>' +
                '<option value="Tooth Restoration (Pasta)"' + (data.procedure === "Tooth Restoration (Pasta)" ? " selected" : "") + '>Tooth Restoration (Pasta)</option>' +
                '<option value="Tooth Extraction (Gabot)"' + (data.procedure === "Tooth Extraction (Gabot)" ? " selected" : "") + '>Tooth Extraction (Gabot)</option>' +
                '<option value="Dentures (Pustiso)"' + (data.procedure === "Dentures (Pustiso)" ? " selected" : "") + '>Dentures (Pustiso)</option>' +
                '<option value="Crowns and Bridges"' + (data.procedure === "Crowns and Bridges" ? " selected" : "") + '>Crowns and Bridges</option>' +
                '<option value="Teeth Whitening"' + (data.procedure === "Teeth Whitening" ? " selected" : "") + '>Teeth Whitening</option>' +
                '<option value="Fluoride Treatment"' + (data.procedure === "Fluoride Treatment" ? " selected" : "") + '>Fluoride Treatment</option>' +
                '<option value="Pit and Fissure Sealant"' + (data.procedure === "Pit and Fissure Sealant" ? " selected" : "") + '>Pit and Fissure Sealant</option>' +
                '<option value="Wisdom Teeth Removal"' + (data.procedure === "Wisdom Teeth Removal" ? " selected" : "") + '>Wisdom Teeth Removal</option>' +
                '<option value="Root Canal Treatment"' + (data.procedure === "Root Canal Treatment" ? " selected" : "") + '>Root Canal Treatment</option>' +
                '<option value="Periapical Xray"' + (data.procedure === "Periapical Xray" ? " selected" : "") + '>Periapical Xray</option>' +
                '<option value="Orthodontic Braces"' + (data.procedure === "Orthodontic Braces" ? " selected" : "") + '>Orthodontic Braces</option>' +
                '<option value="Other"' + (data.procedure === "Other" ? " selected" : "") + '>Other</option>' +
                '</select>' +
                '</td>' +

                /* Same Consulting Dentist combobox as the Appointments table, driven by the
                   same delegated handlers keyed on .dentist-field / .dentist-input,
                   so no extra wiring is needed here. The td-dentist class stays
                   on the input: that is what saveTreatmentNotes(), the
                   FormData submit and the row validation all read. */
                '<td>' +
                '<div class="dentist-field">' +
                /* Loaded value goes through formatDentistName() so treatment rows saved
                   under the old short name still read as the full name. */
                '<input type="text" class="dentist-input td-dentist" value="' + escHtml(formatDentistName(data.dentist)) + '" placeholder="Select or type a dentist"' +
                ' autocomplete="off" autocapitalize="off" spellcheck="false"' +
                ' role="combobox" aria-autocomplete="list" aria-expanded="false"' +
                ' aria-controls="dentistMenu" aria-label="Treating dentist">' +
                '<button type="button" class="dentist-field__toggle" tabindex="-1" aria-hidden="true" title="Show dentists">' +
                '<span class="material-symbols-rounded" aria-hidden="true">arrow_drop_down</span>' +
                '</button>' +
                '</div>' +
                '</td>' +

                '<td><input type="number" class="td-value" value="' + escHtml(data.valueOfWork || '') + '" placeholder="0.00" step="0.01"></td>' +

                '<td><input type="number" class="td-paid" value="' + escHtml(data.amountPaid || '') + '" placeholder="0.00" step="0.01"></td>' +

                '<td><input type="text" class="td-balance" value="' + escHtml(data.balance || '') + '" placeholder="Balance" readonly></td>' +

                '<td><input type="text" class="td-next-appt adm-date-native" value="' + escHtml(data.nextAppt || '') + '" placeholder="Select date &amp; time" autocomplete="off"></td>' +

                '<td>' +
                '<select class="td-medicine">' +
                '<option value="">Select Medicine</option>' +
                '<option value="None"' + (data.medicine === "None" ? " selected" : "") + '>None</option>' +
                '<option value="Mefenamic Acid"' + (data.medicine === "Mefenamic Acid" ? " selected" : "") + '>Mefenamic Acid</option>' +
                '<option value="Tranexamic Acid"' + (data.medicine === "Tranexamic Acid" ? " selected" : "") + '>Tranexamic Acid</option>' +
                '<option value="Amoxicillin"' + (data.medicine === "Amoxicillin" ? " selected" : "") + '>Amoxicillin</option>' +
                '<option value="Co- amoxiclav"' + (data.medicine === "Co- amoxiclav" ? " selected" : "") + '>Co- amoxiclav</option>' +
                '<option value="Other"' + (data.medicine === "Other" ? " selected" : "") + '>Other</option>' +
                '</select>' +
                '</td>' +

                '<td>' +
                '<select class="td-status">' +
                '<option value="Not Paid"' + ((data.status || "Not Paid") === "Not Paid" ? " selected" : "") + '>Not Paid</option>' +
                '<option value="Paid"' + (data.status === "Paid" ? " selected" : "") + '>Paid</option>' +
                '</select>' +
                '</td>' +

                /* Row actions. The delete control is handled by ONE delegated
                   listener on the tbody (see below), so a row built here needs
                   no per-row wiring. */
                '<td class="td-row-actions">' +
                '<button type="button" class="td-delete-row" data-td-delete-row title="Delete this treatment row" aria-label="Delete this treatment row">' +
                '<span class="material-symbols-rounded" aria-hidden="true">delete</span>' +
                '</button>' +
                '</td>';

            tableBody.appendChild(tr);
        }

        function addTreatmentRow() {
            appendRow({
                date: '',
                tooth: '',
                procedure: '',
                dentist: '',
                valueOfWork: '',
                amountPaid: '',
                balance: '',
                nextAppt: '',
                medicine: '',
                status: 'Not Paid'
            });
            // Give the new row the same listboxes and date pickers as the
            // rows already on screen.
            refreshTreatmentControls(document.querySelector('#td-treatment-table tbody'));
        }

        function escHtml(s) {
            var d = document.createElement('div');
            d.appendChild(document.createTextNode(s));
            return d.innerHTML;
        }

        // Ask before declining. Declining deletes the request document on the
        // server and immediately emails the patient, so a mis-click cannot be
        // taken back from this screen. Reuses the shared danger confirm, which
        // already focuses Cancel rather than the destructive button and refuses
        // to close on a stray backdrop click.
        function confirmDeclineAppointment(a) {
            const name = [a.FirstName, a.MiddleName, a.LastName]
                .filter(Boolean).join(' ') || 'this patient';

            const details = [['Patient', name]];
            if (a.Service) details.push(['Service', a.Service]);
            if (a.appointment_date) {
                details.push([
                    'Appointment',
                    typeof formatApptDateTime === 'function'
                        ? formatApptDateTime(a.appointment_date)
                        : a.appointment_date
                ]);
            }

            // If the confirm dialog is unavailable for any reason, still allow
            // the action rather than leaving the admin unable to decline at all.
            if (typeof showConfirm !== 'function') return Promise.resolve(true);

            return showConfirm(
                'Decline the appointment request for ' + name + '?',
                {
                    title: 'Decline appointment request?',
                    details: details,
                    note: 'The request is removed and the patient is emailed ' +
                        'that it was declined. This cannot be undone from here.',
                    confirmLabel: 'Yes, decline it',
                    icon: 'block',
                    danger: true
                }
            );
        }

        // Update status function for accepting/declining appointments
        function updateStatus(rowElement, action) {
            // Get appointment data from the data-appointment attribute
            const appointmentData = JSON.parse(rowElement.getAttribute('data-appointment'));
            if (!appointmentData) {
                console.error('No appointment data found');
                return;
            }

            // Get the dentist name from the input field in the Consulting Dentist column
            const dentistInput = rowElement.querySelector('.dentist-input');
            const dentist_name = dentistInput ? dentistInput.value.trim() : '';

            // Accepting commits the appointment to a dentist, so the name has to
            // be there first. Declining still works without one - nothing gets
            // assigned, so there is nothing to fill in.
            if (action === 'accept' && !requireDentistInput(dentistInput)) {
                showToast('Please select or type the consulting dentist before accepting.');
                return;
            }

            if (action === 'decline') {
                confirmDeclineAppointment(appointmentData).then(function (ok) {
                    if (ok) commitStatus(rowElement, action, appointmentData, dentist_name);
                });
                return;
            }

            commitStatus(rowElement, action, appointmentData, dentist_name);
        }

        // The request that actually talks to the server. Kept separate so the
        // decline path can be gated behind the confirmation without duplicating
        // any of the accept logic.
        function commitStatus(rowElement, action, appointmentData, dentist_name) {

            // Prepare data object
            const data = {
                user_id: appointmentData.uid,
                appointment_id: appointmentData.id,
                firstname: appointmentData.FirstName,
                middlename: appointmentData.MiddleName,
                lastname: appointmentData.LastName,
                houseno: appointmentData.HouseNo,
                street: appointmentData.Street,
                brgy: appointmentData.Brgy,
                municipality: appointmentData.Municipality,
                province: appointmentData.Province,
                contactnumber: appointmentData.ContactNumber,
                nationality: appointmentData.Nationality,
                religion: appointmentData.Religion,
                age: appointmentData.Age,
                sex: appointmentData.Sex,
                birthday: appointmentData.Birthday,
                occupation: appointmentData.Occupation,
                civilstatus: appointmentData.CivilStatus,
                service: appointmentData.Service,
                dentist_name: dentist_name,
                q1: appointmentData.q1 || '',
                q2: appointmentData.q2 || '',
                q3: appointmentData.q3 || '',
                q4: appointmentData.q4 || '',
                q5: appointmentData.q5 || '',
                q6: appointmentData.q6 || '',
                q7: appointmentData.q7 || '',
                q9: appointmentData.q9 || '',
                q2_spec: appointmentData.q2_spec || '',
                q3_spec: appointmentData.q3_spec || '',
                q4_spec: appointmentData.q4_spec || '',
                q5_spec: appointmentData.q5_spec || '',
                q7_spec: appointmentData.q7_spec || '',
                q9_spec: appointmentData.q9_spec || '',
                w_preg: appointmentData.w_preg || '',
                w_nurse: appointmentData.w_nurse || '',
                w_pill: appointmentData.w_pill || ''
            };

            // Create a FormData object to send all the required data
            const formData = new FormData();
            for (const [key, value] of Object.entries(data)) {
                formData.append(key, value);
            }
            formData.append('action', action);

            // Send the data to the /approve endpoint using fetch
            fetch('/approve', {
                method: 'POST',
                body: formData
            })
                .then(response => {
                    if (response.ok) {
                        return response.json().then(result => ({ ok: true, result: result }));
                    }
                    return response.json()
                        .catch(() => ({}))
                        .then(result => {
                            throw new Error(
                                result.message ||
                                ('Failed to ' + action + ' appointment')
                            );
                        });
                })
                .then(function (payload) {
                    const result = payload.result;

                    if (action === 'accept') {
                        showToast('Appointment accepted successfully!');

                        if (rowElement) {
                            rowElement.remove();
                        }

                        if (result && result.patient) {
                            const grid = document.getElementById('weeklyClientsGrid');
                            if (grid) {
                                grid.insertBefore(buildApprovedCard(result.patient), grid.firstChild);
                            }
                            upsertMyPatientRow(result.patient.uid, result.patient);
                        }

                        showSection('mypatients');

                    } else {
                        showToast('Appointment declined successfully!');

                        if (rowElement) {
                            rowElement.remove();
                        }
                    }
                })
                .catch(error => {
                    console.error('Error:', error);

                    showToast(error.message || (
                        'Failed to ' +
                        action +
                        ' appointment. Please try again.'
                    ));
                });
        }

        // Show section based on hash on page load
        window.onload = function () {
            var hash = window.location.hash.substring(1); // removes '#'
            if (hash) {
                showSection(hash);
            }
        };

        function initUnifiedGrid(id, cols, topType, bottomType) {
            var grid = document.getElementById(id);
            if (!grid) return;
            // Defensive default, so a cell is never markable merely because
            // the chart init has not published the current tool yet.
            if (typeof window.currentChartTool !== 'string') {
                window.currentChartTool = 'healthy';
            }
            grid.innerHTML = '';
            for (var i = 0; i < cols; i++) {
                var topBox = document.createElement('div');
                topBox.className = 'grid-box';
                if (topType === 'input') {
                    // No placeholder: an empty cell should read as "not
                    // recorded yet", not as sample data.
                    topBox.innerHTML = '<input type="text" class="grid-input" aria-label="Upper status">';
                } else {
                    // grid-box--mark carries the empty "markable" tint, so the
                    // input itself can be pure tick with no box of its own.
                    topBox.className = 'grid-box grid-box--mark';
                    topBox.innerHTML = '<input type="checkbox" class="grid-checkbox" aria-label="Upper status marked">';
                    guardCheckboxForCheckTool(topBox);
                }

                var bottomBox = document.createElement('div');
                bottomBox.className = 'grid-box';
                if (bottomType === 'input') {
                    bottomBox.innerHTML = '<input type="text" class="grid-input" aria-label="Lower status">';
                } else {
                    bottomBox.className = 'grid-box grid-box--mark';
                    bottomBox.innerHTML = '<input type="checkbox" class="grid-checkbox" aria-label="Lower status marked">';
                    guardCheckboxForCheckTool(bottomBox);
                }

                grid.appendChild(topBox);
                grid.appendChild(bottomBox);
            }
        }

        /**
         * A status cell may only receive its check mark while the Check tool
         * is armed. Under any other tool the click is reverted, so a mark on
         * the chart always came from the Check action and nothing else.
         * The input keeps its own checked state, so anything reading or
         * saving the grid later is unaffected.
         */
        function guardCheckboxForCheckTool(box) {
            var cb = box.querySelector('.grid-checkbox');
            if (!cb) return;
            // Belt and braces: if the chart init that publishes
            // window.currentChartTool has not run for some reason, fall back
            // to reading the active tool straight off the palette, and treat
            // "can't tell" as not-armed rather than silently allowing a mark.
            function armedTool() {
                if (typeof window.currentChartTool === 'string') {
                    return window.currentChartTool;
                }
                var active = document.querySelector('.tool.active');
                return active ? active.getAttribute('data-tool') : null;
            }
            cb.addEventListener('click', function (e) {
                if (armedTool() !== 'check') {
                    e.preventDefault();
                }
            });
        }

        // Theme Toggle
        var themeToggle = document.getElementById('themeToggle');
        var body = document.body;
        var savedTheme = localStorage.getItem('theme');
        if (savedTheme === 'dark') {
            body.classList.add('dark-mode');
        }

        /* Keeps the toggle's accessible name and state honest. Without it the
           button announced nothing at all (no aria-label) and its title stayed
           "Toggle Dark Mode" even in dark mode, so a screen-reader user was
           never told which theme they were in or what the control would do. */
        function syncThemeToggleState() {
            var toggle = document.getElementById('themeToggle');
            if (!toggle) return;
            var isDark = body.classList.contains('dark-mode');
            var label = isDark ? 'Switch to light mode' : 'Switch to dark mode';
            toggle.setAttribute('aria-label', label);
            toggle.setAttribute('title', label);
            toggle.setAttribute('aria-pressed', isDark ? 'true' : 'false');
        }

        syncThemeToggleState();

        if (themeToggle) themeToggle.addEventListener('click', function () {
            body.classList.toggle('dark-mode');
            var isDark = body.classList.contains('dark-mode');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            syncThemeToggleState();
            // Rebuild income chart with theme-appropriate colors
            if (typeof incomeChartInstance !== 'undefined' && incomeChartInstance) {
                var activePeriod = 'weekly';
                var activeBtn = document.querySelector('.period-btn.active');
                if (activeBtn && activeBtn.dataset.period) {
                    activePeriod = activeBtn.dataset.period;
                }
                loadFinancialChart(activePeriod);
            }
            // Rebuild procedure charts with theme-appropriate colors
            if (typeof procCountChartInstance !== 'undefined') {
                var procPeriod = 'overall';
                var procBtn = document.querySelector('.proc-period-btn.active');
                if (procBtn && procBtn.dataset.period) {
                    procPeriod = procBtn.dataset.period;
                }
                loadProcedureCharts(procPeriod);
            }
            // Rebuild the Doctors Calendar closure chart with
            // theme-appropriate colors (hook exposed by block-dates.js)
            if (typeof window.admRebuildClosureChart === 'function') {
                window.admRebuildClosureChart();
            }
            // Rebuild dashboard charts with theme-appropriate colors
            if (typeof dashboardDonutInstance !== 'undefined' && dashboardDonutInstance) {
                rebuildDashboardCharts();
            }
        });