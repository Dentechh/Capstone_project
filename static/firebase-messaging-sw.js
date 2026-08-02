// firebase-messaging-sw.js
// Required for FCM push notifications
// Uses Firebase compat SDK (importScripts) for maximum browser compatibility

importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js");

const firebaseConfig = {
  apiKey: "AIzaSyCpt9dnVFDvDNfnX4jQyfxxtYfnR_duUEE",
  authDomain: "dentech-c2ee0.firebaseapp.com",
  projectId: "dentech-c2ee0",
  storageBucket: "dentech-c2ee0.firebasestorage.app",
  messagingSenderId: "921529543911",
  appId: "1:921529543911:web:08e91a5f6982eb541b0642",
  measurementId: "G-Y3X4RF50Y5"
};

firebase.initializeApp(firebaseConfig);
const messaging = firebase.messaging();

// Handle background messages (when app is closed/minimized)
messaging.onBackgroundMessage((payload) => {
  const notificationTitle = payload.notification?.title || "Capizonda Dental Clinic";
  const notificationOptions = {
    body: payload.notification?.body || "You have a new notification",
    icon: "/static/img/logo.png",
    badge: "/static/img/logo.png",
    tag: "appointment-notification",
    data: {
      url: "/patient-profile"
    }
  };

  self.registration.showNotification(notificationTitle, notificationOptions);
});

// Handle notification clicks
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification?.data?.url || "/patient-profile";
  event.waitUntil(
    clients.matchAll({ type: "window" }).then((clientList) => {
      for (const client of clientList) {
        if (client.url === url && "focus" in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});