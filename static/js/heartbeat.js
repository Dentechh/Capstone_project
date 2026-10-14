(function () {
    'use strict';

    var HEARTBEAT_INTERVAL_MS = 15000; // 15 seconds
    var heartbeatTimer = null;

    function sendHeartbeat() {
        fetch('/api/heartbeat', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        }).catch(function (err) {
            console.debug('Heartbeat failed:', err);
        });
    }

    function startHeartbeat() {
        if (heartbeatTimer) return;
        sendHeartbeat();
        heartbeatTimer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);
    }

    function stopHeartbeat() {
        if (heartbeatTimer) {
            clearInterval(heartbeatTimer);
            heartbeatTimer = null;
        }
    }

    // Start heartbeat when the page loads if user is logged in
    // We detect this by checking for a session cookie or a data attribute
    document.addEventListener('DOMContentLoaded', function () {
        // Check if there's a user session by looking for common indicators
        // The session cookie is HttpOnly so we can't read it directly, but we can
        // check for elements that only exist when logged in, or try the heartbeat
        // and it will fail with 401 if not logged in (which is fine).
        startHeartbeat();
    });

    // Stop heartbeat on page unload
    window.addEventListener('beforeunload', stopHeartbeat);

    // Expose for manual control if needed
    window.Heartbeat = {
        start: startHeartbeat,
        stop: stopHeartbeat
    };
})();