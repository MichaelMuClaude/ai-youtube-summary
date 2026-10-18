/** YouTube Video Summary - Side Panel */
var API            = "http://127.0.0.1:9877";
// The model name shown in status text; actual summarization runs server-side
// (server/api.py), not in this page — Ollama returns 403 on requests whose
// Origin is chrome-extension://..., so this proxies through our own server.
var OLLAMA_MODEL    = "qwen3.6:35b-a3b";

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
  return checkApiResponse(resp);
}

async function apiPost(path, body) {
  var resp  = await fetch(API + path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  return checkApiResponse(resp);
}

async function checkApiResponse(resp) {
  var json   = await resp.json().catch(function() { return null; });
  if (!resp.ok) {
    throw new Error((json && json.error) ? json.error : ("API " + resp.status));
  }
  return json;
}

/* ---- Manual download (audio or video file, saved into the local Media library) ---- */
var isDownloading = false;

function setDownloadStatus(msg, cls) {
  var el   = $("download-status");
  if (!cls || cls === "") { el.className = "status hidden"; return; }
  el.textContent   = msg || "";
  el.className     = "status " + cls;
}

async function pollDownload(taskId, maxRetries) {
  maxRetries = maxRetries || 90;
  for (var i = 0; i < maxRetries; i += 1) {
    try {
      var data   = await apiGet("/task/" + taskId);
      if (data.status === "done") return data;
      if (data.status === "failed") {
        setDownloadStatus(data.progress || "Download failed", "error");
        return null;
      }
    } catch (err) {
      console.warn("Download poll error:", err.message);
    }
    await new Promise(function(r) { setTimeout(r, 5000); });
  }
  setDownloadStatus("Timed out", "error");
  return null;
}

// Opens the browser's native Save As dialog over the file the server just saved into
// the Media library, so the user can additionally keep a copy wherever they pick. The
// library copy is unaffected either way (and is what `check`/dedup looks at).
function promptSaveAs(taskId, savedPath) {
  if (!chrome.downloads || !chrome.downloads.download) return;
  var suggestedName   = savedPath.split("/").pop();
  try {
    chrome.downloads.download({
      url: API + "/download/file/" + taskId,
      filename: suggestedName,
      saveAs: true,
    }, function() {
      if (chrome.runtime.lastError) {
        console.warn("Save As dialog failed:", chrome.runtime.lastError.message);
      }
    });
  } catch (err) {
    console.warn("Save As dialog failed:", err.message);
  }
}

async function doDownload(url, kind) {
  if (isDownloading || !url) return;
  isDownloading   = true;

  $("btn-download").disabled        = true;
  $("btn-download-text").textContent = "Downloading...";
  setDownloadStatus("Starting download...", "loading");

  try {
    var resp   = await apiPost("/download", { url: url, kind: kind });
    var data   = await pollDownload(resp.id);
    if (data) {
      setDownloadStatus("Saved to: " + data.path + " — pick a location in the dialog to also keep a copy there...", "loading");
      promptSaveAs(resp.id, data.path);
      setDownloadStatus("Saved to: " + data.path, "ok");
    }
  } catch (err) {
    setDownloadStatus(err.message || "Download failed", "error");
  }

  isDownloading                      = false;
  $("btn-download").disabled         = false;
  $("btn-download-text").textContent = "Download";
}

/* ---- Local-model summarization ---- */
async function summarizeWithOllama(title, transcript, lang) {
  var data   = await apiPost("/summarize", { title: title, transcript: transcript, lang: lang });
  if (!data.content) throw new Error(data.error || "Summarization returned no content");
  return data.content;
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
// Small, dependency-free markdown renderer: headings, bullet lists, **bold**,
// falls back to plain paragraphs for everything else.
function renderMd(text) {
  if (!text) return "<p>Nothing to show.</p>";
  var lines   = text.split("\n");
  var html    = "";
  var inList  = false;

  function closeList() { if (inList) { html += "</ul>"; inList = false; } }
  function inline(s) {
    return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  for (var i = 0; i < lines.length; i += 1) {
    var line   = lines[i].trim();
    if (line.length === 0) { closeList(); continue; }

    var heading   = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      closeList();
      var level   = Math.min(heading[1].length + 2, 6); // keep headings small in a side panel
      html += "<h" + level + ">" + inline(heading[2]) + "</h" + level + ">";
      continue;
    }

    var bullet   = /^[-*]\s+(.*)$/.exec(line);
    if (bullet) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += "<li>" + inline(bullet[1]) + "</li>";
      continue;
    }

    closeList();
    html += "<p>" + inline(line) + "</p>";
  }
  closeList();
  return html;
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

  $("btn-fetch").disabled     = true;
  $("btn-text").textContent  = "Starting...";
  doHide(["video-info", "tabs", "content-area"]);
  clearTabs();
  $("panel-summary").innerHTML   = "";
  setStatus("Fetching transcript...", "loading");

  try {
    var resp       = await apiPost("/fetch", { url: url, lang: [lang || "en"] });
    var data     = await pollTask(resp.id);
    if (!data) return;

    showVideoInfo(data.manifest);
    doShow(true, ["video-info", "tabs", "content-area"]);
    switchTab("summary");

    if (data.timestamped) {
      $("panel-transcript").querySelector("pre").textContent  = data.timestamped;
    }
    var rawJson   = JSON.stringify(data.manifest, null, 2);
    $("panel-raw").querySelector("pre").textContent   = rawJson;

    // Summarize with the local model. If it's unreachable or fails, fall
    // back to showing the raw transcript instead of leaving the tab blank.
    setStatus("Summarizing with local model (" + OLLAMA_MODEL + ")...", "loading");
    try {
      var lang       = $("lang-select").value;
      var summary   = await summarizeWithOllama(data.manifest.title, data.transcript, lang);
      $("panel-summary").innerHTML   = renderMd(summary);
      setStatus("", "");
    } catch (sumErr) {
      console.warn("Summarization failed:", sumErr.message);
      $("panel-summary").innerHTML   =
        "<p class=\"warn\">Local model summarization failed (" + esc(sumErr.message) +
        "). Showing the raw transcript instead — check that Ollama is running on localhost:11434.</p>" +
        renderMd(data.transcript);
      setStatus("", "");
    }

    $("btn-fetch").disabled     = false;
    $("btn-text").textContent  = "Refresh";

  } catch (err) {
    setStatus(err.message || "Fetch failed", "error");
    isPolling   = false;
    $("btn-fetch").disabled   = false;
    $("btn-text").textContent  = "Retry";
    return;
  }
  isPolling   = false;
}

/* ---- Event Handlers ---- */
document.querySelectorAll(".tab[data-target]").forEach(function(tab) {
  tab.addEventListener("click", function() { switchTab(this.getAttribute("data-target")); });
});

$("btn-fetch").addEventListener("click", function() {
  if (currentUrl) doFetch(currentUrl, "en");
});

$("btn-download").addEventListener("click", function() {
  var url   = currentUrl || $("url-input").value.trim();
  if (!url) { setDownloadStatus("No video URL yet — open a YouTube tab or paste a URL below.", "error"); return; }
  doDownload(url, $("download-kind").value);
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
