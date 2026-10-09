        (function () {
            var icons = { success: '\u2713', error: '\u2715', warning: '!', info: 'i' };

            function classifyToast(message) {
                var m = String(message == null ? '' : message).trim();
                if (/successfully|welcome back|logged out|account created/i.test(m)) return 'success';
                if (/(email|verification).*sent|sent.*(email|inbox)/i.test(m)) return 'success';
                if (/fail|error|not found|unauthorized|invalid|unavailable|missing|could not|do not match|passwords/i.test(m)) return 'error';
                if (/^please\b/i.test(m) || /select/i.test(m) || /too many requests/i.test(m)) return 'warning';
                return 'info';
            }

            window.showToast = function (message, type, duration) {
                type = type || classifyToast(message);
                duration = duration || 4500;

                var container = document.getElementById('toast-container');
                if (!container) return;

                var toast = document.createElement('div');
                toast.className = 'toast ' + type;

                var icon = document.createElement('div');
                icon.className = 'toast-icon';
                icon.textContent = icons[type] || icons.info;

                var msg = document.createElement('div');
                msg.className = 'toast-message';
                msg.textContent = message;

                var closeBtn = document.createElement('button');
                closeBtn.className = 'toast-close';
                closeBtn.type = 'button';
                closeBtn.setAttribute('aria-label', 'Close');
                closeBtn.innerHTML = '&times;';

                var progress = document.createElement('div');
                progress.className = 'toast-progress';
                progress.style.animationDuration = duration + 'ms';

                toast.appendChild(icon);
                toast.appendChild(msg);
                toast.appendChild(closeBtn);
                toast.appendChild(progress);
                container.appendChild(toast);

                requestAnimationFrame(function () {
                    toast.classList.add('show');
                });

                var removed = false;
                function remove() {
                    if (removed) return;
                    removed = true;
                    toast.classList.remove('show');
                    toast.classList.add('hide');
                    setTimeout(function () { toast.remove(); }, 250);
                }

                var timer = setTimeout(remove, duration);
                closeBtn.addEventListener('click', function () {
                    clearTimeout(timer);
                    remove();
                });
            };

            /* Park a toast to be shown on the NEXT page, then navigate.
               Register and login flows redirect right after a success,
               which would tear down a toast before it could be read.
               sessionStorage survives the navigation in the same tab,
               so the message is handed across and painted afterwards.
               Same component and design as showToast() - only the
               delivery point moves. */
            var PENDING_KEY = 'patientPendingToast';

            window.showToastAfterReload = function (message, type, url) {
                try {
                    sessionStorage.setItem(PENDING_KEY, JSON.stringify({
                        message: String(message),
                        type: type || classifyToast(message)
                    }));
                } catch (err) {
                    // Storage unavailable (private mode, quota). Still
                    // navigate, just without the confirmation - never
                    // block the navigation itself.
                }
                setTimeout(function () {
                    window.location.href = url || '/';
                }, 700);
            };

            // Show anything parked by showToastAfterReload(), exactly once.
            (function flushPendingToast() {
                document.addEventListener('DOMContentLoaded', function () {
                    var raw = null;
                    try {
                        raw = sessionStorage.getItem(PENDING_KEY);
                        // Cleared before showing so a later navigation
                        // cannot repeat it.
                        sessionStorage.removeItem(PENDING_KEY);
                    } catch (err) {
                        return;
                    }
                    if (!raw) return;
                    var data = null;
                    try { data = JSON.parse(raw); } catch (err) { return; }
                    if (!data || !data.message) return;
                    window.showToast(data.message, data.type || 'success');
                });
            })();

            /* Server-rendered flash boxes (.flash-box) are
               routed through the same showToast() component,
               so alerts that travel through a redirect - logout,
               login, booking, payment - share one design, one
               position and one animation with the alerts created
               in the page. The markup only carries the message
               and a flash-<category> class. */
            function enhanceFlashBoxInPlace(box, type) {
                var icon = document.createElement('div');
                icon.className = 'toast-icon';
                icon.textContent = icons[type] || icons.info;
                box.insertBefore(icon, box.firstChild);

                var closeBtn = document.createElement('button');
                closeBtn.className = 'toast-close';
                closeBtn.type = 'button';
                closeBtn.setAttribute('aria-label', 'Close');
                closeBtn.innerHTML = '&times;';
                box.appendChild(closeBtn);

                var duration = 5000;
                var progress = document.createElement('div');
                progress.className = 'toast-progress';
                progress.style.animationDuration = duration + 'ms';
                box.appendChild(progress);

                var removed = false;
                function remove() {
                    if (removed) return;
                    removed = true;
                    box.style.transition = 'opacity 0.3s ease';
                    box.style.opacity = '0';
                    setTimeout(function () { box.remove(); }, 300);
                }

                var timer = setTimeout(remove, duration);
                closeBtn.addEventListener('click', function () {
                    clearTimeout(timer);
                    remove();
                });
            }

            function enhanceFlashBoxes() {
                var container = document.getElementById('toast-container');
                var boxes = document.querySelectorAll('.flash-box');
                for (var i = 0; i < boxes.length; i++) {
                    var box = boxes[i];
                    if (box.dataset.enhanced) continue;
                    box.dataset.enhanced = '1';

                    var type = 'info';
                    if (box.classList.contains('flash-success')) type = 'success';
                    else if (box.classList.contains('flash-error')) type = 'error';
                    else if (box.classList.contains('flash-warning')) type = 'warning';

                    if (container) {
                        // Same component as every other alert.
                        window.showToast(box.textContent, type, 5000);
                        box.remove();
                    } else {
                        // No toast container in this template -
                        // enhance the box in place so the message
                        // is never lost.
                        enhanceFlashBoxInPlace(box, type);
                    }
                }

                var flashContainer = document.getElementById('flash-container');
                if (flashContainer && !flashContainer.children.length) {
                    flashContainer.remove();
                }
            }

            /* Flash messages travel from the server as a JS
               array (window.__patientFlashes) instead of
               rendered boxes, so no server-rendered alert box
               ever appears - the toast is the only alert.
               Shown straight away when the array is already
               set (the inline script runs before this file),
               and again on DOMContentLoaded for templates that
               load this file in the head. 
               Also supports data attribute pattern for templates
               that avoid inline JS (to avoid linter warnings). */
            var flashesShown = false;

            function showPatientFlashes() {
                if (flashesShown) return;
                
                // Try window.__patientFlashes first (legacy pattern)
                var flashes = window.__patientFlashes;
                
                // Fallback: read from data attribute (new pattern)
                if (!flashes || !flashes.length) {
                    var dataEl = document.getElementById('patient-flashes-data');
                    if (dataEl) {
                        try {
                            flashes = JSON.parse(dataEl.getAttribute('data-flashes') || '[]');
                        } catch (e) {
                            flashes = [];
                        }
                    }
                }
                
                if (!flashes || !flashes.length) return;
                flashesShown = true;
                for (var i = 0; i < flashes.length; i++) {
                    var f = flashes[i];
                    if (!f) continue;
                    // Flashes arrive either as {category, message} objects
                    // or as ["category", "message"] arrays - Jinja's tojson
                    // serializes (category, message) tuples as arrays.
                    var category = f.category !== undefined ? f.category : f[0];
                    var message = f.message !== undefined ? f.message : f[1];
                    var type = 'info';
                    if (category === 'success') type = 'success';
                    else if (category === 'error') type = 'error';
                    else if (category === 'warning') type = 'warning';
                    window.showToast(message, type, 5000);
                }
            }

            showPatientFlashes();

            document.addEventListener('DOMContentLoaded', function () {
                showPatientFlashes();
                enhanceFlashBoxes();
            });
        })();
