        (function () {
            var icons = { success: '\u2713', error: '\u2715', warning: '!' };

            function classifyToast(message) {
                var m = String(message == null ? '' : message).trim();
                if (/successfully/i.test(m) || m === 'Blocked slot saved.') return 'success';
                if (/fail|error|not found|unauthorized|invalid|unavailable|missing|could not/i.test(m)) return 'error';
                if (/^please\b/i.test(m) || /select/i.test(m) || /do not match/i.test(m)) return 'warning';
                return 'error';
            }

            window.showToast = function (message, type, duration) {
                type = type || classifyToast(message);
                duration = duration || 4500;

                var container = document.getElementById('toastContainer');
                if (!container) return;

                var toast = document.createElement('div');
                toast.className = 'toast ' + type;

                var icon = document.createElement('div');
                icon.className = 'toast-icon';
                icon.textContent = icons[type] || icons.error;

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
        })();
