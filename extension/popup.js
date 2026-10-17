document.getElementById("open-sidepanel").addEventListener("click", async function() {
  // Get the active tab's URL
  var tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  var tab  = tabs[0];
  
  if (tab) {
    // Send URL to side panel via a messaging channel
    if (chrome.runtime && chrome.runtime.openSidePanel) {
      chrome.runtime.openSidePanel();
    } else {
      console.warn("openSidePanel not available");
    }
  }
});
