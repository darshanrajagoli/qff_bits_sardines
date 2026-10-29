// SwapPrint page script. Injected once into the app page by streamlit_app.py (it runs in the page itself, not in a
// component frame, so it survives reruns). Four small jobs:
//   1. double-click / double-tap a picture -> that picture's own Streamlit full-screen button
//   2. in-text tab links [2 · Tamper](#go-tamper) -> switch to that tab and scroll to its top
//   3. sidebar Light / Dark buttons (#theme-light, #theme-dark) -> Streamlit's own theme switch in the ⋮ menu
//   4. mark <html data-sp-mode="light|dark"> from the page's real background, so app/pixel.css picks its colours
(() => {
  const doc = document;

  // 1. full screen
  const toggleFullscreen = (t) => {
    const frame = t && t.closest ? t.closest('[data-testid="stFullScreenFrame"]') : null;
    if (!frame || !frame.querySelector('[data-testid="stImage"]')) return false;
    const b = frame.querySelector('[data-testid="stBaseButton-elementToolbar"][aria-label*="ullscreen"]');
    if (b) { b.click(); return true; }
    return false;
  };
  doc.addEventListener('dblclick', (e) => { if (toggleFullscreen(e.target)) e.preventDefault(); });
  let lastTap = 0;
  doc.addEventListener('touchend', (e) => {
    const now = Date.now();
    if (now - lastTap < 320 && toggleFullscreen(e.target)) { e.preventDefault(); lastTap = 0; } else { lastTap = now; }
  }, {passive: false});

  // 2. tab links
  const TABS = {start: 'start here', fingerprint: 'fingerprint', tamper: 'tamper', verify: 'verify',
                how: 'how it works', results: 'results'};
  const goTab = (slug) => {
    const want = TABS[slug];
    const tab = [...doc.querySelectorAll('[role="tab"]')].find((t) => t.innerText.toLowerCase().includes(want));
    if (!tab) return false;
    tab.click();
    const main = doc.querySelector('[data-testid="stMain"]') || doc.querySelector('.stMain');
    setTimeout(() => (main ? main.scrollTo({top: 0, behavior: 'smooth'}) : tab.scrollIntoView()), 50);
    return true;
  };

  // 3. theme buttons drive Streamlit's own switch (keeps the session and its edits)
  const pickTheme = (name) => {
    const item = () => doc.querySelector('[data-testid="stMainMenuItem-theme-' + name + '"]');
    const close = () => doc.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
    if (item()) { item().click(); setTimeout(close, 60); return; }
    const btn = doc.querySelector('[data-testid="stMainMenuButton"]') ||
                doc.querySelector('[data-testid="stMainMenu"] button');
    if (!btn) return;
    btn.click();
    let tries = 0;
    const timer = setInterval(() => {
      const it = item();
      if (it || ++tries > 40) {
        clearInterval(timer);
        if (it) { it.click(); setTimeout(close, 60); }
      }
    }, 25);
  };

  doc.addEventListener('click', (e) => {
    const a = e.target && e.target.closest ? e.target.closest('a[href*="#go-"], a[href="#theme-light"], a[href="#theme-dark"]') : null;
    if (!a) return;
    const href = a.getAttribute('href');
    if (href.startsWith('#theme-')) {
      e.preventDefault(); e.stopPropagation();
      pickTheme(href.endsWith('light') ? 'Light' : 'Dark');
    } else if (goTab(href.split('#go-')[1])) {
      e.preventDefault(); e.stopPropagation();
    }
  }, true);

  // 4. light or dark, read from the actual page background
  const sync = () => {
    const el = doc.querySelector('.stApp');
    if (!el) return;
    const m = getComputedStyle(el).backgroundColor.match(/\d+/g);
    if (!m) return;
    const lum = (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255;
    const mode = lum > 0.5 ? 'light' : 'dark';
    if (doc.documentElement.dataset.spMode !== mode) doc.documentElement.dataset.spMode = mode;
  };
  sync();
  setInterval(sync, 300);
})();
