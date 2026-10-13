/* Runs before module imports; handles missing bundles without a reload loop. */
(function () {
  try {
    if (localStorage.getItem('taskflow:theme') === 'graphite') document.documentElement.dataset.theme = 'graphite';
  } catch (_) {}
  var retryKey = 'taskflow:startup-retry';
  var displayed = false;
  function notice() {
    if (displayed) return;
    displayed = true;
    var panel = document.createElement('div');
    panel.setAttribute('role', 'alert');
    panel.style.cssText = 'position:fixed;bottom:16px;left:16px;right:16px;z-index:9999;padding:20px;border:1px solid #b9b2a6;border-radius:16px;background:#fffdf8;color:#29251f;font:14px system-ui;box-shadow:0 4px 24px #0002';
    var text = document.createElement('p');
    text.textContent = 'Не удалось загрузить интерфейс. Возможно, приложение обновилось или соединение прервалось. Обновите страницу. Несохранённый текст может быть потерян.';
    var button = document.createElement('button');
    button.type = 'button'; button.textContent = 'Обновить страницу';
    button.style.cssText = 'padding:8px 14px;cursor:pointer';
    button.onclick = function () { location.reload(); };
    panel.append(text, button);
    document.body.appendChild(panel);
  }
  function failed() {
    var root = document.getElementById('root');
    // After startup, never discard a user's open form automatically.
    if (root && root.dataset.boot === 'ready') { notice(); return; }
    try {
      var previous = Number(sessionStorage.getItem(retryKey));
      if (!previous || Date.now() - previous > 60000) {
        sessionStorage.setItem(retryKey, String(Date.now()));
        location.reload(); return;
      }
    } catch (_) { /* No storage: no automatic reload. */ }
    if (document.body) notice();
    else document.addEventListener('DOMContentLoaded', notice, { once: true });
  }
  window.addEventListener('vite:preloadError', function (event) { event.preventDefault(); failed(); });
  window.addEventListener('error', function (event) {
    var target = event.target;
    if (target && target.tagName === 'SCRIPT' && target.src && new URL(target.src, location.href).pathname.indexOf('/assets/') === 0) failed();
  }, true);
  window.addEventListener('unhandledrejection', function (event) {
    if (/Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(String(event.reason && event.reason.message || event.reason))) failed();
  });
  window.addEventListener('DOMContentLoaded', function () {
    setTimeout(function () {
      var root = document.getElementById('root');
      if (!root || root.dataset.boot !== 'ready') notice();
    }, 15000);
  }, { once: true });
})();
