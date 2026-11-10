/**
 * popup.js — Status inspector and manual reconnect trigger for the Nexus Browser Bridge popup UI.
 */

// Refresh status metrics displayed in popup.html by messaging background.js
function refreshPopupStatus() {
  chrome.runtime.sendMessage({ type: "NEXUS_GET_POPUP_STATUS" }, (res) => {
    if (chrome.runtime.lastError || !res) {
      return;
    }
    const badge = document.getElementById("status-badge");
    const port8000 = document.getElementById("port-8000");
    const port8765 = document.getElementById("port-8765");
    const tabCounts = document.getElementById("tab-counts");

    const anyConnected = Boolean(res.apiConnected || res.cliConnected);
    badge.textContent = anyConnected ? "Connected" : "Standby";
    badge.className = anyConnected ? "badge connected" : "badge";

    port8000.textContent = res.apiConnected ? "Connected" : "Standby";
    port8765.textContent = res.cliConnected
      ? "Connected"
      : res.apiConnected
      ? "Routed via 8000"
      : "Standby";
    tabCounts.textContent = `${res.tabCount ?? 0} tabs / ${res.groupCount ?? 0} groups`;
  });
}

document.getElementById("reconnect-btn").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "NEXUS_FORCE_RECONNECT" }, () => {
    setTimeout(refreshPopupStatus, 300);
  });
});

document.addEventListener("DOMContentLoaded", refreshPopupStatus);
