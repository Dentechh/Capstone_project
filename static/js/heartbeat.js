(function () {
    'use strict';

    var HEARTBEAT_INTERVAL_MS = 10000; // 10 seconds
    var heartbeatTimer = null;

    // True once the server has accepted a heartbeat on this page, i.e. the
    // visitor really was signed in. Visitors who never signed in get a 401
    // on every heartbeat, and must NOT be redirected.
    var wasSignedIn = false;

    function sendHeartbeat() {
        fetch('/api/heartbeat', {
            method: 'POST',
            credentials: 'same-origin',
            keepalive: true,
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        }).then(function (res) {
            if (res.ok) {
                wasSignedIn = true;
            } else if (res.status === 401) {
                stopHeartbeat();
                if (wasSignedIn) {
                    window.location.replace('/');
                }
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

    // Tell the server right away when the tab/page is closed, so the admin
    // sees Offline immediately instead of waiting for the window to expire.
    // If the person is just navigating to another page, the next page's
    // heartbeat flips them straight back to Online.
    function sayGoodbye() {
        if (!wasSignedIn || !navigator.sendBeacon) return;
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (!meta || !meta.content) return;
        var fd = new FormData();
        fd.append('csrf_token', meta.content);
        navigator.sendBeacon('/api/offline', fd);
    }

    document.addEventListener('DOMContentLoaded', startHeartbeat);

    // Browsers slow timers in background tabs. Ping the moment the tab is
    // visible again so the status is correct immediately.
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && heartbeatTimer) sendHeartbeat();
    });

    window.addEventListener('pagehide', sayGoodbye);

    window.Heartbeat = {
        start: startHeartbeat,
        stop: stopHeartbeat
    };
})();