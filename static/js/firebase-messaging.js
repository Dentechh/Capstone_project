// firebase-messaging.js
// Handles FCM push notification setup for patients
// Run this AFTER the patient logs in and is on the dashboard

// Your VAPID Key from Firebase Console > Project Settings > Cloud Messaging > Web Push Certificates
const VAPID_KEY = "BMxCaxDuwgWJZ0-QFplpC59jPkgGpC3iq9r7trSKEmvC9hbbMRM5cm3hSoTJED0kC4luBBvDD6d9k5AE4OouXcg";

// Firebase config ? must match your Firebase project
const firebaseConfig = {
  apiKey: "AIzaSyCpt9dnVFDvDNfnX4jQyfxxtYfnR_duUEE",
  authDomain: "dentech-c2ee0.firebaseapp.com",
  projectId: "dentech-c2ee0",
  storageBucket: "dentech-c2ee0.firebasestorage.app",
  messagingSenderId: "921529543911",
  appId: "1:921529543911:web:08e91a5f6982eb541b0642",
  measurementId: "G-Y3X4RF50Y5"
};

let fcmToken = null;

async function initFirebaseMessaging() {
  try {
    // Load Firebase compat SDK dynamically
    await loadScript("https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js");
    await loadScript("https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js");

    // Initialize Firebase
    if (!firebase.apps || firebase.apps.length === 0) {
      firebase.initializeApp(firebaseConfig);
    }

    // Initialize Messaging
    const messaging = firebase.messaging();

    // Request notification permission
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      console.warn("Notification permission denied");
      return;
    }

    // Check if the browser supports service workers
    if (!("serviceWorker" in navigator)) {
      console.warn("Service Worker not supported");
      return;
    }

    // Get FCM token using VAPID key
    fcmToken = await messaging.getToken({
      vapidKey: VAPID_KEY,
      serviceWorkerRegistration: await navigator.serviceWorker.ready
    });

    if (fcmToken) {
      console.log("FCM Token:", fcmToken);
      await saveFcmToken(fcmToken);
    } else {
      console.warn("No FCM token received");
    }

    // Handle foreground messages
    messaging.onMessage((payload) => {
      const notificationTitle = payload.notification?.title || "Capizonda Dental Clinic";
      const notificationOptions = {
        body: payload.notification?.body || "You have a new notification",
        icon: "/static/img/logo.png",
        badge: "/static/img/logo.png",
        tag: "appointment-notification"
      };
      new Notification(notificationTitle, notificationOptions);
    });

  } catch (error) {
    console.error("FCM initialization error:", error);
  }
}

// Helper: dynamically load a script
function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load script: " + src));
    document.head.appendChild(script);
  });
}

// Send FCM token to Flask server
async function saveFcmToken(token) {
  try {
    const response = await fetch("/save-fcm-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ fcm_token: token })
    });
    if (!response.ok) {
      console.error("Failed to save FCM token:", response.status);
    } else {
      console.log("FCM token saved successfully");
    }
  } catch (error) {
    console.error("Error saving FCM token:", error);
  }
}

// Register service worker and init messaging
if ("serviceWorker" in navigator) {
  navigator.serviceWorker
    .register("/static/firebase-messaging-sw.js")
    .then((registration) => {
      console.log("Service Worker registered:", registration);
      initFirebaseMessaging();
    })
    .catch((error) => {
      console.error("Service Worker registration failed:", error);
    });
}
