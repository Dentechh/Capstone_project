            /* ---- Appointment request tab: shared helpers ---- */

            /* Display-only. Firestore stores "YYYY-MM-DD HH:MM" because that string is
            what order_by, the cursor pagination and the blocked-slot lookups compare
            against, so it must never be rewritten -- only rendered differently. */
            function formatApptDateTime(raw) {
                const value = String(raw == null ? '' : raw).trim();
                if (!value) return '';

                const match = value.match(
                    /^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2}))?/
                );
                if (!match) return value;

                const months = ['January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'];
                const monthName = months[Number(match[2]) - 1];
                if (!monthName) return value;

                const datePart = monthName + ' ' + Number(match[3]) + ', ' + match[1];
                if (match[4] === undefined) return datePart;

                /* Stored hours are 24-hour ("13:00"), so the meridiem has to be
                   derived and the hour converted. The picker offers real PM slots
                   (12:00 PM to 5:00 PM), so appending "AM" unconditionally would
                   print "13:00AM" for a 1:00 PM appointment. */
                const hour24 = Number(match[4]);
                const meridiem = hour24 >= 12 ? 'PM' : 'AM';
                let hour12 = hour24 % 12;
                if (hour12 === 0) hour12 = 12;
                const hours = String(hour12).padStart(2, '0');

                return datePart + ' - ' + hours + ':' + match[5] + meridiem;
            }

            /* One entry for now. Add more names here and every Consulting Dentist box in
               the table (server-rendered and loaded on demand) picks them up. */
            const APPOINTMENT_DENTIST_OPTIONS = ['Dr. Julix Dionne Capizonda'];

            /* The one name we display for this practitioner. Records saved before
               the rename carry the short form, so every read of a stored dentist
               name has to go through formatDentistName() or the same dentist shows
               up under two spellings on one screen. */
            const CANONICAL_DENTIST_NAME = 'Dr. Julix Dionne Capizonda';

            /* Every stored spelling that means this practitioner, lower-cased with
               whitespace collapsed. Mirrors normalize_dentist_name() in main.py
               exactly - the two must agree, because the server's double-booking
               check and this file's reschedule check both compare names for
               equality. Keep the list, and the Python one, in step. */
            const DENTIST_NAME_ALIASES = [
                'capizonda',
                'dr capizonda',
                'dr. capizonda',
                'julix dionne capizonda',
                'dr julix dionne capizonda',
                'dr. julix dionne capizonda'
            ];

            function normalizeDentistCase(value) {
                const raw = value == null ? '' : String(value);
                return raw.toLowerCase().replace(/\s+/g, ' ').trim();
            }

            /* Display form of a stored dentist name. Display only - never write the
               result back to the database, and never use it for equality checks,
               because old records legitimately hold the short form. */
            function formatDentistName(value) {
                const raw = value == null ? '' : String(value).trim();
                if (!raw) return '';
                return DENTIST_NAME_ALIASES.indexOf(normalizeDentistCase(raw)) !== -1
                    ? CANONICAL_DENTIST_NAME
                    : raw;
            }

            /* Identity key for "is this the same dentist?". Both spellings collapse
               to "capizonda", which is what the double-booking checks need: the
               server (normalize_dentist_name) and reschedule.js both compare names
               for equality, and a plain case-fold would stop matching old records
               the moment a new one is saved under the full name. */
            function dentistIdentityKey(value) {
                const normalized = normalizeDentistCase(value);
                if (!normalized) return '';
                if (DENTIST_NAME_ALIASES.indexOf(normalized) !== -1) return 'capizonda';
                // Any other dentist: drop the honorific so "Dr. Smith" and "Smith"
                // agree, and leave the rest untouched.
                return normalized.replace(/^dr\.?\s+/, '').trim();
            }

            /* Matching is against the name plus these generic words, so someone who types
            "dentist" or "dr" still finds the list instead of an empty popup. Typing
            anything else is unaffected: the input is never overwritten by a match. */
            const APPOINTMENT_DENTIST_KEYWORDS = ' dr doctor dentist';

            function dentistMatches(query) {
                const needle = String(query || '').trim().toLowerCase();
                if (!needle) return APPOINTMENT_DENTIST_OPTIONS.slice();

                return APPOINTMENT_DENTIST_OPTIONS.filter(function (name) {
                    return (name + APPOINTMENT_DENTIST_KEYWORDS).toLowerCase().indexOf(needle) !== -1;
                });
            }

            /* ---- Required Consulting Dentist ----
               An appointment is never accepted or created without a dentist, so
               both the Accept button and the New Appointment submit funnel
               through here. Returns true when the box already holds a name;
               otherwise it flags the field and returns false for the caller to
               abort on.

               The modal copy of the field deliberately has no `required`
               attribute: it sits on step 1 while step 2 submits, and a hidden
               required control makes the browser block the submit with an
               undismissable console error instead of a message the admin can
               act on. Same reason the appointment date is checked by hand. */
            function clearDentistInputError(input) {
                if (!input) return;
                input.classList.remove('dentist-input--invalid');
                input.removeAttribute('aria-invalid');
            }

            function requireDentistInput(input) {
                if (input && String(input.value || '').trim()) {
                    clearDentistInputError(input);
                    return true;
                }

                if (input) {
                    input.classList.add('dentist-input--invalid');
                    input.setAttribute('aria-invalid', 'true');
                    if (typeof closeDentistMenu === 'function') closeDentistMenu();
                    input.focus();
                }

                return false;
            }

            /* Clears the flag on the first keystroke, so a red box is never left
               sitting on a field the admin is already filling in. Delegated, so
               the rows built by "Load More" are covered without re-binding. */
            document.addEventListener('input', function (e) {
                const el = e.target;
                if (el && el.classList && el.classList.contains('dentist-input')) {
                    clearDentistInputError(el);
                }
            });

            /* Rewrites the server-rendered cells that carry the raw stored value. */
            function formatApptDateCells(root) {
                (root || document).querySelectorAll('.appt-date-cell[data-raw]').forEach(function (cell) {
                    cell.textContent = formatApptDateTime(cell.getAttribute('data-raw'));
                });
            }

            /* Local escapers so these helpers never depend on load order between the
               separate <script> blocks in this template. */
            function apptText(value) {
                const div = document.createElement('div');
                div.appendChild(document.createTextNode(String(value == null ? '' : value)));
                return div.innerHTML;
            }

            function apptAttr(value) {
                return apptText(value).replace(/"/g, '&quot;');
            }

            /* The header carries 17 hidden columns before "Urgency Level". A row built in
            JS has to emit the same 24 cells or every value after the patient name
            shifts one column left of its heading. */
            const APPOINTMENT_HIDDEN_FIELDS = ['uid', 'id', 'MiddleName', 'LastName',
                'HouseNo', 'Street', 'Brgy', 'Municipality', 'Province', 'ContactNumber',
                'Nationality', 'Religion', 'Age', 'Sex', 'Birthday', 'Occupation',
                'CivilStatus'];

            function apptHiddenCells(appt) {
                return APPOINTMENT_HIDDEN_FIELDS.map(function (field) {
                    return '<td style="display:none;">' + apptText(appt[field]) + '</td>';
                }).join('');
            }

            /* ---- Urgency severity ----
            Mirrors the Jinja whitelist above so a server-rendered row and a
            "Load More" row are styled identically. Only the whitelisted key ever
           reaches a class name or attribute; the raw value is display text. */
            const APPOINTMENT_URGENCY_KEYS = {
                emergency: 'emergency',
                urgent: 'urgent',
                normal: 'normal'
            };

            function apptUrgency(raw) {
                const text = String(raw == null ? '' : raw).trim();
                const key = APPOINTMENT_URGENCY_KEYS[text.toLowerCase()] || 'unset';
                return {
                    key: key,
                    label: text || 'Unspecified'
                };
            }

            function apptUrgencyCell(raw) {
                const urgency = apptUrgency(raw);
                return '<td data-cell="urgency">'
                    + '<span class="urg-badge urg-badge--' + urgency.key + '" title="Urgency level: ' + apptAttr(urgency.label) + '">'
                    + '<span class="urg-badge__dot" aria-hidden="true"></span>'
                    + '<span class="urg-badge__label">' + apptText(urgency.label) + '</span>'
                    + '</span></td>';
            }

            /* ---- Consulting Dentist combobox ----
                A native <datalist> cannot be styled, so this is a real listbox popup.
                The table sets overflow:hidden and the panel sets overflow-x:auto, either
                of which would clip an in-cell menu, so the popup is a single shared
                <ul> portalled to <body> and positioned with fixed coordinates.
                All interaction is delegated from document, so rows added later by
               "Load More" work with no extra wiring. */
            const DENTIST_MENU_ID = 'dentistMenu';
            const DENTIST_MENU_GAP = 6;
            const DENTIST_MENU_MAX_HEIGHT = 220;

            let dentistMenuEl = null;
            let dentistOpenInput = null;

            function getDentistMenu() {
                if (dentistMenuEl && dentistMenuEl.isConnected) return dentistMenuEl;

                dentistMenuEl = document.createElement('ul');
                dentistMenuEl.id = DENTIST_MENU_ID;
                dentistMenuEl.className = 'dentist-menu';
                dentistMenuEl.setAttribute('role', 'listbox');
                dentistMenuEl.hidden = true;
                document.body.appendChild(dentistMenuEl);
                return dentistMenuEl;
            }

            function setDentistToggleOpen(input, isOpen) {
                const field = input && input.closest ? input.closest('.dentist-field') : null;
                const toggle = field ? field.querySelector('.dentist-field__toggle') : null;
                if (toggle) toggle.classList.toggle('is-open', isOpen);
            }

            /* The popup is portalled to <body>, so it needs a different stacking level
               depending on what opened it: .modal sits at z-index 99999 and the modal
               box clips its own overflow. */
            function setDentistMenuContext(input) {
                const menu = getDentistMenu();
                menu.classList.toggle('is-over-modal',
                    !!(input && input.closest && input.closest('#newApptModal')));
            }

            function closeDentistMenu() {
                if (dentistMenuEl) {
                    dentistMenuEl.hidden = true;
                    dentistMenuEl.classList.remove('is-over-modal');
                }
                if (dentistOpenInput) {
                    dentistOpenInput.setAttribute('aria-expanded', 'false');
                    dentistOpenInput.removeAttribute('aria-activedescendant');
                    setDentistToggleOpen(dentistOpenInput, false);
                    dentistOpenInput = null;
                }
            }

            function positionDentistMenu(input) {
                const menu = getDentistMenu();
                const rect = input.getBoundingClientRect();
                const spaceBelow = window.innerHeight - rect.bottom;
                const placeAbove = spaceBelow < DENTIST_MENU_MAX_HEIGHT && rect.top > spaceBelow;
                const available = placeAbove ? rect.top : spaceBelow;

                menu.style.left = rect.left + 'px';
                menu.style.width = rect.width + 'px';
                menu.style.maxHeight = Math.max(96, Math.min(DENTIST_MENU_MAX_HEIGHT, available - DENTIST_MENU_GAP - 12)) + 'px';

                if (placeAbove) {
                    menu.style.top = 'auto';
                    menu.style.bottom = (window.innerHeight - rect.top + DENTIST_MENU_GAP) + 'px';
                    menu.classList.add('is-above');
                } else {
                    menu.style.bottom = 'auto';
                    menu.style.top = (rect.bottom + DENTIST_MENU_GAP) + 'px';
                    menu.classList.remove('is-above');
                }
            }

            function openDentistMenu(input) {
                /* Always start from a clean slate: only one popup and one chevron can be
                   open, and any previously highlighted option is stale after a re-filter. */
                closeDentistMenu();

                const menu = getDentistMenu();
                const matches = dentistMatches(input.value);

                /* An empty list still opens, so typing a name that is not on the list
                   never looks broken -- the field stays a plain free-text input. */
                menu.innerHTML = matches.length
                    ? matches.map(function (name, index) {
                        return '<li class="dentist-menu__option" role="option" id="dentistOpt-' + index + '" data-value="' + apptAttr(name) + '">'
                            + '<span class="dentist-menu__name">' + apptText(name) + '</span>'
                            + '<span class="material-symbols-rounded dentist-menu__tick" aria-hidden="true">check</span>'
                            + '</li>';
                    }).join('')
                    : '<li class="dentist-menu__empty">No matching dentist &mdash; your text will be used</li>';

                menu.hidden = false;
                menu.classList.remove('has-active');
                dentistOpenInput = input;
                input.setAttribute('aria-expanded', 'true');
                input.removeAttribute('aria-activedescendant');
                setDentistToggleOpen(input, true);
                setDentistMenuContext(input);
                positionDentistMenu(input);
            }

            function setActiveDentistOption(input, direction) {
                const menu = getDentistMenu();
                const options = Array.prototype.slice.call(
                    menu.querySelectorAll('.dentist-menu__option')
                );
                if (!options.length) return;

                let index = options.findIndex(function (el) {
                    return el.classList.contains('is-active');
                });

                if (index === -1) {
                    index = direction === 'up' ? options.length - 1 : 0;
                } else {
                    index = direction === 'up'
                        ? (index - 1 + options.length) % options.length
                        : (index + 1) % options.length;
                }

                options.forEach(function (el, i) {
                    el.classList.toggle('is-active', i === index);
                    el.setAttribute('aria-selected', i === index ? 'true' : 'false');
                });

                const active = options[index];
                menu.classList.add('has-active');
                input.setAttribute('aria-activedescendant', active.id);
                active.scrollIntoView({ block: 'nearest' });
            }

            function commitActiveDentistOption(input) {
                const active = getDentistMenu().querySelector('.dentist-menu__option.is-active');
                if (!active) return false;
                input.value = active.getAttribute('data-value') || '';
                closeDentistMenu();
                return true;
            }

            function selectDentistOption(input, option) {
                input.value = option.getAttribute('data-value') || '';
                closeDentistMenu();
                input.focus();
            }

            function isDentistTarget(target, selector) {
                return !!(target && target.closest && target.closest(selector));
            }

            document.addEventListener('click', function (event) {
                const target = event.target;
                if (!target || !target.closest) return;

                if (isDentistTarget(target, '.dentist-menu__option')) {
                    const option = target.closest('.dentist-menu__option');
                    if (dentistOpenInput) selectDentistOption(dentistOpenInput, option);
                    return;
                }

                if (isDentistTarget(target, '.dentist-field__toggle')) {
                    const input = target.closest('.dentist-field').querySelector('.dentist-input');
                    if (dentistOpenInput === input) {
                        closeDentistMenu();
                    } else if (input) {
                        openDentistMenu(input);
                    }
                    event.preventDefault();
                    return;
                }

                if (!isDentistTarget(target, '.dentist-field') && !isDentistTarget(target, '#' + DENTIST_MENU_ID)) {
                    closeDentistMenu();
                }
            });

            document.addEventListener('input', function (event) {
                if (!isDentistTarget(event.target, '.dentist-input')) return;
                openDentistMenu(event.target.closest('.dentist-input'));
            });

            document.addEventListener('keydown', function (event) {
                if (!isDentistTarget(event.target, '.dentist-input')) return;

                const input = event.target.closest('.dentist-input');
                const menuOpen = dentistOpenInput === input && !getDentistMenu().hidden;

                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                    event.preventDefault();
                    if (!menuOpen) {
                        openDentistMenu(input);
                        return;
                    }
                    setActiveDentistOption(input, event.key === 'ArrowUp' ? 'up' : 'down');
                    return;
                }

                if (event.key === 'Enter') {
                    if (menuOpen && commitActiveDentistOption(input)) event.preventDefault();
                    return;
                }

                if (event.key === 'Escape') {
                    if (menuOpen) {
                        event.preventDefault();
                        closeDentistMenu();
                    }
                }
            });

            /* A fixed-position popup cannot follow its anchor once the page moves. */
            window.addEventListener('resize', closeDentistMenu);
            window.addEventListener('scroll', closeDentistMenu, true);

            document.addEventListener('DOMContentLoaded', function () {
                formatApptDateCells();
            });
