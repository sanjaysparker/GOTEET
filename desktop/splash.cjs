const enter = document.getElementById('enter');
window.goteetStartup.onReady(() => {
  document.body.classList.add('ready');
  document.getElementById('status').textContent = 'Your workspace is ready';
  enter.disabled = false;
  enter.focus();
});
enter.addEventListener('click', () => window.goteetStartup.enter());
document.getElementById('quit').addEventListener('click', () => window.goteetStartup.quit());
