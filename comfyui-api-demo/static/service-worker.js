// 缓存版本号，每次修改内容时更新
const CACHE_VERSION = 'v1';
const CACHE_NAME = `ai-image-generator-${CACHE_VERSION}`;

// 需要缓存的资源
const CACHE_ASSETS = [
  '/',
  '/index.html',
  '/style.css',
  '/script.js',
  '/favicon.png',
  '/icon-192.png',
  '/icon-512.png',
  '/manifest.json'
];

// 安装 Service Worker 并缓存基本资源
self.addEventListener('install', event => {
  console.log('Service Worker 安装中...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('缓存资源中...');
        return cache.addAll(CACHE_ASSETS);
      })
      .then(() => {
        console.log('资源缓存完成');
        return self.skipWaiting();
      })
  );
});

// 激活时，清理旧缓存
self.addEventListener('activate', event => {
  console.log('Service Worker 已激活');
  
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('删除旧缓存:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 处理网络请求
self.addEventListener('fetch', event => {
  // 不处理API请求，让其直接走网络
  if (event.request.url.includes('/api/') || 
      event.request.url.includes('/generate') || 
      event.request.url.includes('/result')) {
    return;
  }
  
  event.respondWith(
    // 尝试从缓存中获取
    caches.match(event.request)
      .then(cachedResponse => {
        // 如果缓存中存在，直接返回缓存
        if (cachedResponse) {
          return cachedResponse;
        }
        
        // 否则请求网络
        return fetch(event.request)
          .then(response => {
            // 检查是否是有效响应
            if (!response || response.status !== 200 || response.type !== 'basic') {
              return response;
            }
            
            // 克隆响应，因为响应流只能被读取一次
            const responseToCache = response.clone();
            
            // 将响应存入缓存
            caches.open(CACHE_NAME)
              .then(cache => {
                cache.put(event.request, responseToCache);
              });
              
            return response;
          })
          .catch(error => {
            console.log('Fetch 失败:', error);
            // 网络请求失败，返回离线页面
            if (event.request.mode === 'navigate') {
              return caches.match('/');
            }
            
            return new Response('网络连接异常', {
              status: 503,
              statusText: 'Service Unavailable',
              headers: new Headers({
                'Content-Type': 'text/plain'
              })
            });
          });
      })
  );
});

// 处理推送通知
self.addEventListener('push', event => {
  const data = event.data.json();
  
  const options = {
    body: data.body,
    icon: 'icon-192.png',
    badge: 'icon-192.png',
    vibrate: [100, 50, 100]
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// 处理通知点击
self.addEventListener('notificationclick', event => {
  event.notification.close();
  
  event.waitUntil(
    clients.openWindow('/')
  );
}); 