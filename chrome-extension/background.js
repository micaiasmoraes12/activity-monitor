// background.js - Service Worker para rastrear abas e tempo

const API_URL = 'http://localhost:8765/track';

// Armazena tempo por tab
const tabTimes = {};
const tabLastActive = {};

// Envia dados a cada 30 segundos
const REPORT_INTERVAL = 30000;

function getDomain(url) {
  try {
    const hostname = new URL(url).hostname;
    return hostname.replace('www.', '');
  } catch {
    return 'unknown';
  }
}

function getToday() {
  return new Date().toISOString().split('T')[0];
}

async function sendData() {
  const today = getToday();
  const data = {
    date: today,
    tabs: [],
    timestamp: new Date().toISOString()
  };

  for (const [tabId, info] of Object.entries(tabTimes)) {
    if (info.totalTime > 0) {
      data.tabs.push({
        tabId: parseInt(tabId),
        url: info.url,
        domain: info.domain,
        totalTime: info.totalTime,
        activeTime: info.activeTime,
        title: info.title || ''
      });
    }
  }

  if (data.tabs.length > 0) {
    try {
      await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      console.log('[ActivityMonitor] Dados enviados:', data.tabs.length, 'tabs');
    } catch (e) {
      console.log('[ActivityMonitor] Erro ao enviar dados:', e.message);
    }
  }
}

// Atualizar tempo da aba ativa
function updateActiveTabTime() {
  const now = Date.now();
  
  // Atualizar aba que estava ativa antes
  for (const [tabId, lastTime] of Object.entries(tabLastActive)) {
    if (tabTimes[tabId]) {
      const elapsed = (now - lastTime) / 1000;
      tabTimes[tabId].totalTime += elapsed;
      // Se era a aba ativa (está em tabLastActive), conta como activeTime
      tabTimes[tabId].activeTime += elapsed;
    }
  }
  
  // Atualizar lastActive para todas as abas
  for (const tabId of Object.keys(tabTimes)) {
    tabLastActive[tabId] = now;
  }
}

// Quando uma aba é atualizada
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url || changeInfo.title) {
    const domain = getDomain(tab.url || '');
    
    if (!tabTimes[tabId]) {
      tabTimes[tabId] = {
        url: tab.url || '',
        domain: domain,
        title: tab.title || '',
        totalTime: 0,
        activeTime: 0
      };
    } else {
      tabTimes[tabId].url = tab.url || '';
      tabTimes[tabId].domain = domain;
      tabTimes[tabId].title = tab.title || '';
    }
  }
});

// Quando uma aba é removida
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabTimes[tabId]) {
    // Enviar dados da aba antes de remover
    sendTabData(tabId);
    delete tabTimes[tabId];
    delete tabLastActive[tabId];
  }
});

// Quando a aba ativa muda
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  const now = Date.now();
  const previousActiveTabId = activeInfo.previousTabId;
  
  // Atualizar tempo da aba anterior
  if (previousActiveTabId && tabTimes[previousActiveTabId]) {
    if (tabLastActive[previousActiveTabId]) {
      const elapsed = (now - tabLastActive[previousActiveTabId]) / 1000;
      tabTimes[previousActiveTabId].totalTime += elapsed;
    }
  }
  
  // Marcar nova aba como ativa
  tabLastActive[activeInfo.tabId] = now;
  
  // Garantir que a aba existe no tracking
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    if (tab.url && !tab.url.startsWith('chrome://')) {
      const domain = getDomain(tab.url);
      if (!tabTimes[activeInfo.tabId]) {
        tabTimes[activeInfo.tabId] = {
          url: tab.url,
          domain: domain,
          title: tab.title || '',
          totalTime: 0,
          activeTime: 0
        };
      }
    }
  } catch (e) {
    // Tab pode não existir mais
  }
});

// Enviar dados periodicamente
setInterval(() => {
  updateActiveTabTime();
  sendData();
  // Resetar contadores após enviar
  for (const tabId of Object.keys(tabTimes)) {
    tabTimes[tabId].totalTime = 0;
    tabTimes[tabId].activeTime = 0;
  }
}, REPORT_INTERVAL);

// Enviar dados quando extensão é instalada/atualizada
chrome.runtime.onInstalled.addListener(() => {
  console.log('[ActivityMonitor] Extensão instalada');
});

// Enviar dados de uma tab específica
function sendTabData(tabId) {
  const info = tabTimes[tabId];
  if (!info || info.totalTime === 0) return;
  
  fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      date: getToday(),
      tabs: [{
        tabId: tabId,
        url: info.url,
        domain: info.domain,
        totalTime: info.totalTime,
        activeTime: info.activeTime,
        title: info.title
      }],
      timestamp: new Date().toISOString()
    })
  });
}
