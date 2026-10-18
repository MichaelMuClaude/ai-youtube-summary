document.getElementById("open-sidepanel").addEventListener("click", async function() {
  // Get the active tab's URL
  var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  var tab  = tabs[0];

  if (tab) {
    if (chrome.sidePanel && chrome.sidePanel.open) {
      chrome.sidePanel.open({ windowId: tab.windowId });
    } else {
      console.warn("chrome.sidePanel API not available in this browser");
    }
  }
});
