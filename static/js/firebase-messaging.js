// firebase-messaging.js
// Handles FCM push notification setup for patients
// Run this AFTER the patient logs in and is on the dashboard

// Your VAPID Key from Firebase Console > Project Settings > Cloud Messaging > Web Push Certificates
const VAPID_KEY = "BMxCaxDuwgWJZ0-QFplpC59jPkgGpC3iq9r7trSKEmvC9hbbMRM5cm3hSoTJED0kC4luBBvDD6d9k5AE4OouXcg";

// Firebase config — must match your Firebase project
const firebaseConfig = {
  apiKey: "AIzaSyCpt9dnVFDvDNfnX4jQyfxxtYfnR_duUEE",
  authDomain: "dentech-c2ee0.firebaseapp.com",
  projectId: "dentech-c2ee0",
  storageBucket: "dentech-c2ee0.firebasestorage.app",
  messagingSenderId: "921529543911",
  appId: "1:921529543911:web:08e91a5f6982eb541b0642",
  measurementId: "G-Y3X4RF50Y5"
};

// Firebase App
let fcmApp = null;
let fcmMessaging = null;
let fcmToken = null;

async function initFirebaseMessaging() {
  // Import Firebase dynamically
  const { initializeApp } = await import(
    "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js"
  );
  const {
    getMessaging,
    getToken,
    onMessage
  } = await import(
    "https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging.js"
  );

  // Initialize Firebase (only once)
  if (!fcmApp) {
    fcmApp = initializeApp(firebaseConfig, "fcm-app");
  }

  // Initialize Messaging
  if (!fcmMessaging) {
    fcmMessaging = getMessaging(fcmApp);
  }

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

  // Get or register the FCM token
  fcmToken = await getToken(fcmMessaging, {
    vapidKey: VAPID_KEY,
    serviceWorkerRegistration: await navigator.serviceWorker.ready
  });

  if (fcmToken) {
    console.log("FCM Token:", fcmToken);
    // Send token to Flask server
    await saveFcmToken(fcmToken);
  } else {
    console.warn("No FCM token received");
  }

  // Handle foreground messages
  onMessage(fcmMessaging, (payload) => {
    const notificationTitle =
      payload.notification?.title || "Capizonda Dental Clinic";
    const notificationOptions = {
      body: payload.notification?.body || "You have a new notification",
      icon: "/static/img/logo.png",
      badge: "/static/img/logo.png",
      tag: "appointment-notification"
    };
    new Notification(notificationTitle, notificationOptions);
  });
}

// Send FCM token to Flask server for storage in Firestore
async function saveFcmToken(token) {
  try {
    const response = await fetch("/save-fcm-token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
  // Register the service worker
  navigator.serviceWorker
    .register("/static/firebase-messaging-sw.js")
    .then((registration) => {
      console.log("Service Worker registered:", registration);
      // Initialize messaging after SW is ready
      initFirebaseMessaging();
    })
    .catch((error) => {
      console.error("Service Worker registration failed:", error);
    });
}
