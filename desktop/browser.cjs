const { WebContentsView, session, shell } = require('electron');
function webURL(value) {
  const u = new URL(String(value));
  if (u.protocol !== 'https:' || u.username || u.password)
    throw Error('Enter an HTTPS web address without embedded credentials.');
  return u.href;
}
function createBrowser(getWindow) {
  let view = null,
    error = '',
    target = '',
    sessionReady = false;
  function state() {
    const wc = view?.webContents;
    return {
      open: !!view,
      url: wc?.getURL() || target,
      title: wc?.getTitle() || 'GOTEET browser',
      loading: wc?.isLoading() || false,
      back: wc?.navigationHistory.canGoBack() || false,
      forward: wc?.navigationHistory.canGoForward() || false,
      error,
    };
  }
  function emit() {
    const win = getWindow();
    if (win && !win.isDestroyed()) win.webContents.send('browser-state', state());
  }
  function close() {
    if (view) {
      getWindow()?.contentView.removeChildView(view);
      view.webContents.close();
      view = null;
    }
    error = '';
    target = '';
    emit();
  }
  function ensure() {
    if (view) return;
    const isolated = session.fromPartition('persist:goteet-browser');
    isolated.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
    isolated.setPermissionCheckHandler(() => false);
    if (!sessionReady)
      isolated.on('will-download', (event) => {
        event.preventDefault();
        error = 'Use Open externally to download this file in your browser.';
        emit();
      });
    sessionReady = true;
    view = new WebContentsView({
      webPreferences: {
        partition: 'persist:goteet-browser',
        sandbox: true,
        contextIsolation: true,
        nodeIntegration: false,
        webSecurity: true,
        allowRunningInsecureContent: false,
      },
    });
    getWindow().contentView.addChildView(view);
    view.setBounds({ x: 0, y: 0, width: 0, height: 0 });
    const wc = view.webContents;
    const guard = (event, url) => {
      try {
        webURL(url);
      } catch {
        event.preventDefault();
        error = 'This navigation is not an HTTPS web page.';
        emit();
      }
    };
    wc.on('will-navigate', guard);
    wc.on('will-redirect', guard);
    wc.setWindowOpenHandler(({ url }) => {
      try {
        open(url);
      } catch (e) {
        error = e.message;
        emit();
      }
      return { action: 'deny' };
    });
    for (const name of [
      'did-start-loading',
      'did-stop-loading',
      'did-navigate',
      'did-navigate-in-page',
      'page-title-updated',
    ])
      wc.on(name, emit);
    wc.on('did-fail-load', (_event, code, description, _url, isMainFrame) => {
      if (isMainFrame && code !== -3) {
        error = description;
        emit();
      }
    });
  }
  async function open(url) {
    target = webURL(url);
    error = '';
    ensure();
    emit();
    try {
      await view.webContents.loadURL(target);
    } catch (e) {
      error = e.message;
      emit();
    }
    return state();
  }
  async function command(action, value) {
    if (action === 'state') return state();
    if (action === 'open') return open(value);
    if (action === 'close') {
      close();
      return state();
    }
    if (!view) return state();
    const wc = view.webContents;
    if (action === 'bounds') {
      const b = value;
      if (!b || !['x', 'y', 'width', 'height'].every((k) => Number.isFinite(b[k])))
        throw Error('Invalid browser bounds');
      const [w, h] = getWindow().getContentSize();
      const x = Math.max(0, Math.min(w, Math.round(b.x))),
        y = Math.max(0, Math.min(h, Math.round(b.y)));
      view.setBounds({
        x,
        y,
        width: Math.max(0, Math.min(w - x, Math.round(b.width))),
        height: Math.max(0, Math.min(h - y, Math.round(b.height))),
      });
    } else if (action === 'back' && wc.navigationHistory.canGoBack()) wc.navigationHistory.goBack();
    else if (action === 'forward' && wc.navigationHistory.canGoForward()) wc.navigationHistory.goForward();
    else if (action === 'reload') {
      error = '';
      wc.reload();
    } else if (action === 'stop') wc.stop();
    else if (action === 'external') await shell.openExternal(webURL(wc.getURL() || target));
    else if (action === 'clear') {
      await wc.session.clearStorageData();
      await wc.session.clearCache();
      close();
    }
    emit();
    return state();
  }
  return { open, command, close };
}
module.exports = { createBrowser, webURL };
