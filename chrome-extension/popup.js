// popup.js

const API_URL = 'http://localhost:8765/status';

async function checkStatus() {
  try {
    const response = await fetch(API_URL);
    if (response.ok) {
      const data = await response.json();
      document.getElementById('statusDot').classList.remove('offline');
      document.getElementById('statusText').textContent = 'Conectado';
      document.getElementById('tabCount').textContent = data.openTabs || '-';
      document.getElementById('monitorTime').textContent = data.monitorTime || '-';
    } else {
      setOffline();
    }
  } catch {
    setOffline();
  }
}

function setOffline() {
  document.getElementById('statusDot').classList.add('offline');
  document.getElementById('statusText').textContent = 'Desconectado';
}

// Atualizar a cada 5 segundos
checkStatus();
setInterval(checkStatus, 5000);
