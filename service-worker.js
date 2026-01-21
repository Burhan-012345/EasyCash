// Update service-worker.js
const CACHE_NAME = 'easycash-v4';
const STATIC_ASSETS = [
  '/',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/manifest.json'
];

// Push notification subscription
let notificationPermissionGranted = false;

// Check for notification permission
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'CHECK_NOTIFICATION_PERMISSION') {
    Notification.requestPermission().then(permission => {
      notificationPermissionGranted = permission === 'granted';
      event.source.postMessage({
        type: 'NOTIFICATION_PERMISSION',
        granted: notificationPermissionGranted
      });
    });
  }
});

// Show notification
function showNotification(title, options) {
  if (notificationPermissionGranted) {
    self.registration.showNotification(title, options);
  }
}

// Install event
self.addEventListener('install', event => {
  console.log('[Service Worker] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[Service Worker] Caching app shell');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate event
self.addEventListener('activate', event => {
  console.log('[Service Worker] Activating...');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('[Service Worker] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      // Request notification permission
      return Notification.requestPermission();
    }).then(permission => {
      notificationPermissionGranted = permission === 'granted';
      return self.clients.claim();
    })
  );
});

// Fetch event
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request);
      })
  );
});

// Push event - handle push notifications
self.addEventListener('push', event => {
  console.log('[Service Worker] Push received');
  
  let data = {};
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data = {
        title: 'EasyCash',
        body: event.data.text()
      };
    }
  }
  
  const options = {
    body: data.body || 'You have a new notification',
    icon: '/static/icon-192.png',
    badge: '/static/icon-192.png',
    tag: data.tag || 'easycash-notification',
    data: data.data || {},
    actions: [
      {
        action: 'view',
        title: 'View'
      },
      {
        action: 'dismiss',
        title: 'Dismiss'
      }
    ]
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title || 'EasyCash', options)
  );
});

// Notification click event
self.addEventListener('notificationclick', event => {
  console.log('[Service Worker] Notification click');
  
  event.notification.close();
  
  if (event.action === 'dismiss') {
    return;
  }
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(clientList => {
        // Check if there's already a window/tab open with the app
        for (const client of clientList) {
          if (client.url.includes('/') && 'focus' in client) {
            return client.focus();
          }
        }
        
        // If no client is open, open a new window
        if (clients.openWindow) {
          return clients.openWindow('/');
        }
      })
  );
});

// Background sync for offline notifications
self.addEventListener('sync', event => {
  if (event.tag === 'sync-notifications') {
    event.waitUntil(
      syncNotifications()
    );
  }
});

async function syncNotifications() {
  // This would sync notifications when back online
  console.log('Syncing notifications...');
}