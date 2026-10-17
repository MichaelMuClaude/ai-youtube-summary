/** YouTube Video Summary - Side Panel */
var API     = "http://127.0.0.1:9877";
var currentUrl  = null;
var isPolling   = false;

function $(id) { return document.getElementById(id); }

/* ---- Helpers ---- */
function formatDuration(sec) {
  if (!sec || isNaN(sec)) return "";
  var m   = Math.floor(sec / 60), s   = sec % 60;
  return String(m) + ":" + ("0" + String(s)).slice(-2);
}

function showVideoInfo(info) {
  if (!info || !info.title) return;
  $("video-title").textContent   = info.title || "Unknown";
  var dur   = formatDuration(info.duration_seconds);
  $("video-meta").textContent    = String(info.channel).replace(/\s/g, "") + " " + dur;
}

/* ---- API calls ---- */
async function apiGet(path) {
  var resp  = await fetch(API + path);
  if (!resp.ok) throw new Error("API " + resp.status);
  return resp.json();
}

async function apiPost(path, body) {
  var resp  = await fetch(API + path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error("API " + resp.status);
  return resp.json();
}

/* ---- UI helpers ---- */
function doShow(show, ids) {
  ids.forEach(function(id) {
    var el = $(id);
    if (el) show ? el.classList.remove("hidden") : el.classList.add("hidden");
  });
}
function doHide(ids)     { doShow(false, ids); }

function setStatus(msg, cls) {
  var el   = $("status");
  if (!cls || cls === "") { el.className = "status hidden"; return; }
  el.textContent   = msg || "";
  el.className     = "status " + cls;
}

/* ---- Rendering ---- */
function renderMd(text) {
  if (!text) return "<p>Nothing to show.</p>";
  var html    = "<div>";
  var lines   = text.split("\n").filter(function(l) { return l.trim().length > 0; });
  for (var i = 0; i < lines.length; i += 1) {
    var content   = lines[i].trim();
    html += "<p>" + esc(content) + "</p>";
  }
  return html + "</div>";
}

function esc(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function clearTabs() {
  document.querySelectorAll(".tab").forEach(function(t) { t.classList.remove("active"); });
}

function switchTab(name) {
  clearTabs();
  var tab   = document.querySelector('[data-target="' + name + '"]');
  if (tab) tab.classList.add("active");
  
  ["summary", "transcript", "raw"].forEach(function(pane) {
    var el   = $("panel-" + pane);
    if (!el) return;
    if (pane === name) el.classList.remove("hidden"); else el.classList.add("hidden");
  });
}

/* ---- Polling ---- */
async function pollTask(taskId, maxRetries) {
  maxRetries = maxRetries || 60;
  for (var i = 0; i < maxRetries; i += 1) {
    try {
      var data   = await apiGet("/task/" + taskId);
      if (data.status === "done") return data;
      if (data.status === "failed") {
        setStatus(data.progress || "Fetch failed", "error");
        isPolling   = false;
        $("btn-fetch").disabled   = false;
        $("btn-text").textContent  = "Retry";
        return null;
      }
    } catch (err) {
      console.warn("Poll error:", err.message);
    }
    await new Promise(function(r) { setTimeout(r, 10000); });
  }
  setStatus("Timed out", "error");
  isPolling   = false;
  $("btn-fetch").disabled   = false;
  $("btn-text").textContent  = "Retry";
  return null;
}

/* ---- Main Fetch Flow ---- */
async function doFetch(url, lang) {
  if (isPolling) return;
  isPolling   = true;
  currentUrl  = url;
  
  $("btn-fetch").disabled     = false;
  $("btn-text").textContent  = "Starting...";
  doHide(["video-info", "tabs", "content-area"]);
  clearTabs();
  $("panel-summary").innerHTML   = "";
  
  try {
    var resp       = await apiPost("/fetch", { url: url, lang: [lang || "en"] });
    var data     = await pollTask(resp.id);
    if (!data) return;
    
    showVideoInfo(data.data.manifest);
    doShow(true, ["video-info", "tabs", "content-area"]);
    switchTab("summary");
    
    $("panel-summary").innerHTML      = renderMd(data.data.transcript);
    if (data.data.timestamped) {
      $("panel-transcript").textContent  = data.data.timestamped;
    }
    var rawJson   = JSON.stringify(data.data.manifest, null, 2);
    $("panel-raw").innerHTML       = "<pre class=\"raw\">" + esc(rawJson) + "</pre>";
    
    $("btn-fetch").disabled     = false;
    $("btn-text").textContent  = "Refresh";
    
  } catch (err) {
    setStatus(err.message || "Fetch failed", "error");
    isPolling   = false;
    $("btn-fetch").disabled   = false;
    $("btn-text").textContent  = "Retry";
  }
}

/* ---- Event Handlers ---- */
document.querySelectorAll(".tab[data-target]").forEach(function(tab) {
  tab.addEventListener("click", function() { switchTab(this.getAttribute("data-target")); });
});

$("btn-fetch").addEventListener("click", function() {
  if (currentUrl) doFetch(currentUrl, "en");
});

$("btn-manual").addEventListener("click", function() {
  var url = $("url-input").value.trim();
  if (url.length > 0) doFetch(url, "en");
});

$("url-input").addEventListener("keydown", function(e) {
  if (e.key === "Enter") {
    var url = $("url-input").value.trim();
    if (url.length > 0) doFetch(url, "en");
  }
});

/* ---- Detect YouTube on load ---- */
window.addEventListener("DOMContentLoaded", async function() {
  try {
    var tabs      = await chrome.tabs.query({ active: true, currentWindow: true });
    var tab       = tabs && tabs[0];
    
    if (tab && tab.url) {
      var isYt     = /^https?:\/\/www\.youtube\.com\/watch\?/.test(tab.url);
      if (isYt) {
        currentUrl   = tab.url;
        doShow(true, ["btn-fetch"]);
        
        try {
          var info   = await apiGet("/info?url=" + encodeURIComponent(tab.url));
          showVideoInfo(info);
        } catch (innerErr) {
          console.warn("Could not fetch video info:", innerErr.message);
        }
      }
    }
  } catch (outerErr) {
    console.warn("Tab detection failed:", outerErr.message);
  }
});

window.addEventListener("beforeunload", function() { isPolling = false; });
