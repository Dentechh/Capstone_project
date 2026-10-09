/* Patient page shell: header interactions for pages that include
   _patient_header.html. Extracted from the inline scripts of
   about.html so the legal pages (privacy policy / terms of
   service) get the same working theme toggle, services dropdown,
   profile dropdown, hamburger, and auth-modal helpers.
   Load AFTER _patient_header.html so the header elements exist. */

document.addEventListener('DOMContentLoaded', function() {
    const dropdownTrigger = document.getElementById('profileDropdownTrigger');
    const dropdownMenu = document.getElementById('profileDropdown');

    if(dropdownTrigger && dropdownMenu) {
        dropdownTrigger.onclick = (e) => {
            e.stopPropagation();
            dropdownMenu.classList.toggle('show');
        };
    }

    window.addEventListener('click', function(e) {
        if(dropdownMenu && dropdownTrigger && !dropdownTrigger.contains(e.target)) {
            dropdownMenu.classList.remove('show');
        }
    });

    const dropBtn = document.getElementById('servicesDropdownBtn');
    const dropMenu = document.getElementById('servicesDropdownMenu');

    // Toggle dropdown on click
    if (dropBtn && dropMenu) {
        dropBtn.addEventListener('click', function(e) {
            e.stopPropagation(); // Prevents the click from reaching the window listener below
            dropMenu.classList.toggle('show');
            this.classList.toggle('active-link');
        });

        // Close the dropdown if the user clicks outside of it
        window.addEventListener('click', function(e) {
            if (!dropMenu.contains(e.target) && !dropBtn.contains(e.target)) {
                dropMenu.classList.remove('show');
                dropBtn.classList.remove('active-link');
            }
        });
    }
});

// Hamburger menu toggle
const hamburger = document.getElementById('hamburger');
const navLinks = document.getElementById('navLinks');

if (hamburger && navLinks) {
    hamburger.addEventListener('click', () => {
        hamburger.classList.toggle('active');
        navLinks.classList.toggle('active');
    });
}

// Theme Toggle Functionality
const themeToggle = document.getElementById('themeToggle');
const body = document.body;

const savedTheme = localStorage.getItem('theme');
if (savedTheme === 'dark') {
    body.classList.add('dark-mode');
}

if (themeToggle) {
    themeToggle.addEventListener('click', () => {
        body.classList.toggle('dark-mode');
        const isDark = body.classList.contains('dark-mode');
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
    });
}

// Auth Modal Functions
function openAuthModal(modalId) {
    document.getElementById(modalId).style.display = "flex";
}

function closeAuthModal(modalId) {
    document.getElementById(modalId).style.display = "none";
}

// Show / hide password fields in the auth modals
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.toggle-password').forEach(button => {
        button.addEventListener('click', () => {
            const wrapper = button.closest('.password-wrapper');
            const input = wrapper.querySelector('input');
            const eyeIcon = button.querySelector('.eye-icon');
            const eyeOffIcon = button.querySelector('.eye-off-icon');

            if (input.type === 'password') {
                input.type = 'text';
                eyeIcon.style.display = 'none';
                eyeOffIcon.style.display = 'block';
            } else {
                input.type = 'password';
                eyeIcon.style.display = 'block';
                eyeOffIcon.style.display = 'none';
            }
        });
    });
});

// Google Sign-In: the gsi client calls this with the signed-in
// credential. Post it to /google-auth like a normal form submit.
function handleCredentialResponse(response) {
    const form = document.createElement("form");
    form.method = "POST";
    form.action = "/google-auth";

    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "token";
    input.value = response.credential;
    form.appendChild(input);

    const csrf = document.createElement("input");
    csrf.type = "hidden";
    csrf.name = "csrf_token";
    csrf.value = document.querySelector('meta[name="csrf-token"]').content;
    form.appendChild(csrf);

    document.body.appendChild(form);
    form.submit();
}

// Attach the CSRF token from <meta name="csrf-token"> to every
// same-origin fetch that mutates state, so Flask-WTF accepts it.
(function () {
    const _fetch = window.fetch;
    window.fetch = function (input, opts) {
        opts = opts || {};
        const url = typeof input === 'string' ? input : ((input && input.url) || '');
        const sameOrigin = url.startsWith('/') || url.startsWith(location.origin);
        const method = (opts.method || (input && input.method) || 'GET').toUpperCase();
        if (sameOrigin && method !== 'GET' && method !== 'HEAD') {
            const meta = document.querySelector('meta[name="csrf-token"]');
            opts.headers = new Headers(opts.headers || {});
            if (meta) opts.headers.set('X-CSRFToken', meta.content);
        }
        return _fetch.call(this, input, opts);
    };
})();
