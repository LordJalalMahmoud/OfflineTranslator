/**
 * TurboTranslator Web Edition - 100% Offline JavaScript Engine
 * Zero external libraries, high performance, reactive UI
 */

document.addEventListener("DOMContentLoaded", () => {
  // State
  let currentMode = "dual"; // 'dual', 'arabic', 'arabizi'
  let currentEngine = "nllb"; // 'nllb', 'argos'
  let currentDialect = "arz_Arab"; // 'arz_Arab' (Egyptian), 'arb_Arab' (Standard)
  let isLiveTranslate = true;
  let debounceTimer = null;
  let activeTaskId = null;
  let progressPollInterval = null;

  // DOM Elements
  const tabs = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");
  const themeToggle = document.getElementById("themeToggle");
  const modeButtons = document.querySelectorAll(".mode-btn");
  const engineButtons = document.querySelectorAll(".engine-btn");
  const dialectButtons = document.querySelectorAll(".dialect-btn");
  const dialectGroup = document.getElementById("dialectSelectorGroup");
  const gridContainer = document.getElementById("translatorGrid");

  const inputEnglish = document.getElementById("inputEnglish");
  const outputArabic = document.getElementById("outputArabic");
  const outputFranco = document.getElementById("outputFranco");
  const paneArabic = document.getElementById("paneArabic");
  const paneFranco = document.getElementById("paneFranco");

  const btnTranslate = document.getElementById("btnTranslate");
  const btnClear = document.getElementById("btnClear");
  const btnPaste = document.getElementById("btnPaste");
  const liveTranslateCheckbox = document.getElementById("liveTranslateCheckbox");

  const charCount = document.getElementById("charCount");
  const wordCount = document.getElementById("wordCount");
  const badgeArabicTime = document.getElementById("badgeArabicTime");
  const badgeFrancoTime = document.getElementById("badgeFrancoTime");

  const toastContainer = document.getElementById("toastContainer");

  // 1. Theme Management
  const savedTheme = localStorage.getItem("turbo_theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);

  themeToggle.addEventListener("click", () => {
    const currentTheme = document.documentElement.getAttribute("data-theme");
    const nextTheme = currentTheme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", nextTheme);
    localStorage.setItem("turbo_theme", nextTheme);
    showToast(`تم التبديل إلى المظهر ${nextTheme === "dark" ? "الداكن" : "الفاتح"}`);
  });

  // 2. Tab Navigation
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      tabContents.forEach(tc => tc.classList.remove("active"));

      tab.classList.add("active");
      const target = document.getElementById(tab.dataset.target);
      if (target) {
        target.classList.add("active");
      }

      // Initial tab data loading
      if (tab.dataset.target === "tab-files") {
        fetchLocalFiles();
      } else if (tab.dataset.target === "tab-franco") {
        loadFrancoDictionary();
      } else if (tab.dataset.target === "tab-cache") {
        fetchInitialCache();
      }
    });
  });

  // 3. Translation Mode Switching
  modeButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      modeButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentMode = btn.dataset.mode;

      if (currentMode === "dual") {
        gridContainer.className = "translator-grid dual-mode";
        paneArabic.style.display = "flex";
        paneFranco.style.display = "flex";
      } else if (currentMode === "arabic") {
        gridContainer.className = "translator-grid";
        paneArabic.style.display = "flex";
        paneFranco.style.display = "none";
      } else if (currentMode === "arabizi") {
        gridContainer.className = "translator-grid";
        paneArabic.style.display = "none";
        paneFranco.style.display = "flex";
      }

      doTranslate();
    });
  });

  // Engine Switching
  engineButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      engineButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentEngine = btn.dataset.engine;

      if (currentEngine === "nllb") {
        if (dialectGroup) dialectGroup.style.display = "inline-flex";
      } else {
        if (dialectGroup) dialectGroup.style.display = "none";
      }

      doTranslate();
    });
  });

  // Dialect Switching
  dialectButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      dialectButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentDialect = btn.dataset.dialect;
      doTranslate();
    });
  });

  // 4. Input Events & Counters
  inputEnglish.addEventListener("input", () => {
    updateCounters();
    if (isLiveTranslate) {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(doTranslate, 300);
    }
  });

  inputEnglish.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "Enter") {
      e.preventDefault();
      doTranslate();
    }
  });

  liveTranslateCheckbox.addEventListener("change", (e) => {
    isLiveTranslate = e.target.checked;
    if (isLiveTranslate && inputEnglish.value.trim()) {
      doTranslate();
    }
  });

  function updateCounters() {
    const text = inputEnglish.value;
    charCount.textContent = `${text.length} حرف`;
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    wordCount.textContent = `${words} كلمة`;
  }

  // 5. Translation Logic
  btnTranslate.addEventListener("click", () => doTranslate());

  btnClear.addEventListener("click", () => {
    inputEnglish.value = "";
    outputArabic.textContent = "";
    outputFranco.textContent = "";
    updateCounters();
    badgeArabicTime.textContent = "--";
    badgeFrancoTime.textContent = "--";
    inputEnglish.focus();
  });

  btnPaste.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        inputEnglish.value = text;
        updateCounters();
        doTranslate();
      }
    } catch {
      showToast("تعذر الوصول إلى الحافظة تلقائياً، يمكنك استخدام Ctrl+V");
    }
  });

  // Quick Samples
  document.querySelectorAll(".sample-tag").forEach(tag => {
    tag.addEventListener("click", () => {
      inputEnglish.value = tag.dataset.sample;
      updateCounters();
      doTranslate();
    });
  });

  async function doTranslate() {
    const text = inputEnglish.value.trim();
    if (!text) {
      outputArabic.textContent = "";
      outputFranco.textContent = "";
      badgeArabicTime.textContent = "--";
      badgeFrancoTime.textContent = "--";
      return;
    }

    try {
      const resp = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          mode: currentMode,
          engine: currentEngine,
          dialect: currentDialect,
        })
      });

      if (!resp.ok) throw new Error("Translation failed");
      const res = await resp.json();

      outputArabic.textContent = res.arabic || "";
      outputFranco.textContent = res.arabizi || "";

      const engineName = res.engine === "nllb"
        ? (res.dialect === "arz_Arab" ? "NLLB 🇪🇬" : "NLLB 🇸🇦")
        : "Argos ⚡";
      const badgeText = res.source === "cache" 
        ? `⚡ كاش (${engineName}): ${res.elapsed_ms}ms` 
        : `🧠 ${engineName}: ${res.elapsed_ms}ms`;

      badgeArabicTime.textContent = badgeText;
      badgeFrancoTime.textContent = badgeText;

      saveToHistory(text, res.arabic, res.arabizi);
    } catch (err) {
      console.error(err);
      showToast("خطأ أثناء الترجمة: " + err.message);
    }
  }

  // 6. Copy Buttons
  document.getElementById("btnCopyArabic").addEventListener("click", () => {
    copyText(outputArabic.textContent, "تم نسخ النص العربي!");
  });

  document.getElementById("btnCopyFranco").addEventListener("click", () => {
    copyText(outputFranco.textContent, "تم نسخ الفرانكو!");
  });

  function copyText(text, msg) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      showToast(msg);
    });
  }

  // 7. Text-to-Speech (TTS) - Native Offline Browser API
  document.getElementById("btnTtsArabic").addEventListener("click", () => {
    speakText(outputArabic.textContent, "ar");
  });

  document.getElementById("btnTtsFranco").addEventListener("click", () => {
    speakText(outputFranco.textContent, "en-US");
  });

  function speakText(text, lang) {
    if (!text || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.rate = 1.0;
    window.speechSynthesis.speak(utterance);
    showToast("جاري النطق الصوتي...");
  }

  // 8. Translation History
  function saveToHistory(en, ar, fr) {
    try {
      let history = JSON.parse(localStorage.getItem("turbo_history") || "[]");
      // Prevent duplicates
      history = history.filter(item => item.en !== en);
      history.unshift({ en, ar, fr, time: new Date().toLocaleTimeString("ar-EG") });
      if (history.length > 20) history.pop();
      localStorage.setItem("turbo_history", JSON.stringify(history));
      renderHistory();
    } catch {}
  }

  function renderHistory() {
    const list = document.getElementById("historyList");
    if (!list) return;
    try {
      const history = JSON.parse(localStorage.getItem("turbo_history") || "[]");
      if (history.length === 0) {
        list.innerHTML = `<div style="text-align:center; padding: 20px; color: var(--text-muted);">لا توجد ترجمات سابقة بعد.</div>`;
        return;
      }

      list.innerHTML = history.map(item => `
        <div class="local-file-card" style="margin-bottom: 8px;">
          <div style="flex: 1; overflow: hidden; text-overflow: ellipsis;">
            <div style="font-weight: 700; font-size: 0.88rem; direction: ltr; text-align: left;">${escapeHtml(item.en)}</div>
            <div style="font-size: 0.82rem; color: var(--accent-success); margin-top: 4px;">${escapeHtml(item.ar)}</div>
            <div style="font-size: 0.78rem; color: var(--accent-cyan); font-family: var(--font-mono);">${escapeHtml(item.fr)}</div>
          </div>
          <button class="pane-icon-btn restore-history-btn" title="استعادة" data-en="${escapeHtml(item.en)}">
            <svg viewBox="0 0 24 24"><path d="M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18z"/></svg>
          </button>
        </div>
      `).join("");

      document.querySelectorAll(".restore-history-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          inputEnglish.value = btn.dataset.en;
          updateCounters();
          doTranslate();
          showToast("تمت استعادة النص إلى المحرر!");
        });
      });
    } catch {}
  }

  document.getElementById("btnClearHistory").addEventListener("click", () => {
    localStorage.removeItem("turbo_history");
    renderHistory();
    showToast("تم مسح سجل الترجمات!");
  });

  // 9. Batch File Translation Tab
  async function fetchLocalFiles() {
    const container = document.getElementById("localFilesList");
    container.innerHTML = `<div style="color:var(--text-muted); font-size:0.9rem;">جاري البحث عن ملفات JSON في المجلد...</div>`;

    try {
      const resp = await fetch("/api/local_files");
      const data = await resp.json();
      if (!data.files || data.files.length === 0) {
        container.innerHTML = `<div style="color:var(--text-muted);">لم يتم العثور على ملفات .json محلية.</div>`;
        return;
      }

      container.innerHTML = data.files.map(f => `
        <div class="local-file-card select-file-card" data-path="${f.rel_path}">
          <div class="local-file-info">
            <svg style="width:20px; height:20px; fill:var(--accent-primary);" viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
            <div>
              <div style="font-weight:700; font-size:0.9rem;">${f.name}</div>
              <div style="font-size:0.75rem; color:var(--text-muted);">${f.size_mb} MB</div>
            </div>
          </div>
          <span class="file-badge-tag">اختيار</span>
        </div>
      `).join("");

      document.querySelectorAll(".select-file-card").forEach(card => {
        card.addEventListener("click", () => {
          document.getElementById("selectedFilePath").value = card.dataset.path;
          showToast(`تم اختيار الملف: ${card.dataset.path}`);
        });
      });
    } catch (err) {
      container.innerHTML = `<div style="color:var(--accent-danger);">خطأ في جلب الملفات: ${err.message}</div>`;
    }
  }

  // File Dropzone Handling
  const fileDropzone = document.getElementById("fileDropzone");
  const fileInput = document.getElementById("fileInput");
  let uploadedFileContent = null;
  let uploadedFileName = "";

  fileDropzone.addEventListener("click", () => fileInput.click());
  fileDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    fileDropzone.classList.add("dragover");
  });
  fileDropzone.addEventListener("dragleave", () => fileDropzone.classList.remove("dragover"));
  fileDropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    fileDropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  });
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length) {
      handleFileSelected(e.target.files[0]);
    }
  });

  function handleFileSelected(file) {
    uploadedFileName = file.name;
    document.getElementById("dropzoneTitle").textContent = `تم تحميل: ${file.name} (${(file.size / (1024*1024)).toFixed(2)} MB)`;
    const reader = new FileReader();
    reader.onload = (e) => {
      uploadedFileContent = e.target.result;
      document.getElementById("selectedFilePath").value = "";
      showToast(`الملف جاهز للترجمة: ${file.name}`);
    };
    reader.readAsText(file);
  }

  // Handle File Engine changes
  const fileEngineSelect = document.getElementById("fileEngine");
  const fileDialectContainer = document.getElementById("fileDialectContainer");
  const fileBatchSizeSelect = document.getElementById("fileBatchSize");

  if (fileEngineSelect) {
    fileEngineSelect.addEventListener("change", () => {
      if (fileEngineSelect.value === "nllb") {
        if (fileDialectContainer) fileDialectContainer.style.display = "block";
        fileBatchSizeSelect.value = "64";
      } else {
        if (fileDialectContainer) fileDialectContainer.style.display = "none";
        fileBatchSizeSelect.value = "128";
      }
    });
  }

  // Start File Translation
  document.getElementById("btnStartFileTranslation").addEventListener("click", async () => {
    const mode = document.getElementById("fileTransMode").value;
    const batchSize = parseInt(document.getElementById("fileBatchSize").value);
    const selectedPath = document.getElementById("selectedFilePath").value.trim();
    const fileEngine = fileEngineSelect ? fileEngineSelect.value : "nllb";
    const fileDialect = document.getElementById("fileDialect") ? document.getElementById("fileDialect").value : "arz_Arab";

    let payload = {
      mode,
      batch_size: batchSize,
      engine: fileEngine,
      dialect: fileDialect,
    };

    if (selectedPath) {
      payload.type = "path";
      payload.path = selectedPath;
    } else if (uploadedFileContent) {
      payload.type = "content";
      payload.filename = uploadedFileName;
      payload.content = uploadedFileContent;
    } else {
      showToast("يرجى اختيار ملف محلي أو رفع ملف من جهازك أولاً!");
      return;
    }

    try {
      const resp = await fetch("/api/file/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await resp.json();
      if (data.error) throw new Error(data.error);

      activeTaskId = data.task_id;
      showProgressView();
      startPollingProgress();
      showToast("بدأت عملية الترجمة الفائقة!");
    } catch (err) {
      showToast("فشل بدء الترجمة: " + err.message);
    }
  });

  function showProgressView() {
    document.getElementById("progressCard").style.display = "block";
    document.getElementById("btnDownloadFile").style.display = "none";
    document.getElementById("terminalLog").textContent = "🚀 جاري تشغيل المحرك ومعالجة الأسطر...";
  }

  function startPollingProgress() {
    clearInterval(progressPollInterval);
    progressPollInterval = setInterval(async () => {
      if (!activeTaskId) return;

      try {
        const resp = await fetch(`/api/file/progress?task_id=${activeTaskId}`);
        const p = await resp.json();

        document.getElementById("progressPercent").textContent = `${p.progress_percent}%`;
        document.getElementById("progressBarFill").style.width = `${p.progress_percent}%`;
        document.getElementById("statTotalLines").textContent = (p.total_lines || 0).toLocaleString();
        document.getElementById("statProcessedLines").textContent = ((p.cache_hits || 0) + (p.newly_translated || 0)).toLocaleString();
        document.getElementById("statCacheHits").textContent = (p.cache_hits || 0).toLocaleString();
        document.getElementById("statSpeed").textContent = `${p.speed_lps || 0} سطر/ثانية`;

        if (p.current_snippet) {
          const log = document.getElementById("terminalLog");
          log.innerHTML += `\n[${new Date().toLocaleTimeString()}] ${escapeHtml(p.current_snippet)}`;
          log.scrollTop = log.scrollHeight;
        }

        if (p.status === "completed") {
          clearInterval(progressPollInterval);
          document.getElementById("btnDownloadFile").style.display = "inline-flex";
          document.getElementById("btnDownloadFile").href = `/api/file/download?task_id=${activeTaskId}`;
          showToast("🎉 اكتملت ترجمة الملف بنجاح!");
        } else if (p.status === "cancelled" || p.status === "error") {
          clearInterval(progressPollInterval);
          showToast("تم إيقاف الترجمة أو حدث خطأ: " + (p.error || ""));
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 600);
  }

  document.getElementById("btnCancelFile").addEventListener("click", async () => {
    if (!activeTaskId) return;
    try {
      await fetch("/api/file/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: activeTaskId })
      });
      showToast("جاري إلغاء العملية...");
    } catch {}
  });

  // 10. Direct Franco Converter Tool
  const directArabicInput = document.getElementById("directArabicInput");
  const directFrancoOutput = document.getElementById("directFrancoOutput");

  directArabicInput.addEventListener("input", async () => {
    const text = directArabicInput.value;
    if (!text) {
      directFrancoOutput.value = "";
      return;
    }
    try {
      const resp = await fetch("/api/arabizi_direct", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });
      const data = await resp.json();
      directFrancoOutput.value = data.arabizi || "";
    } catch {}
  });

  document.getElementById("btnCopyDirectFranco").addEventListener("click", () => {
    copyText(directFrancoOutput.value, "تم نسخ الفرانكو!");
  });

  async function loadFrancoDictionary() {
    const tbody = document.getElementById("francoTableBody");
    if (!tbody || tbody.children.length > 0) return;
    try {
      const resp = await fetch("/api/arabizi_dictionary");
      const data = await resp.json();
      tbody.innerHTML = data.dictionary.map(row => `
        <tr>
          <td style="font-weight:700; font-size:1.1rem; color:var(--accent-primary);">${row.ar}</td>
          <td style="font-family:var(--font-mono); font-size:1.1rem; color:var(--accent-cyan); font-weight:800;">${row.fr}</td>
          <td style="color:var(--text-secondary);">${row.example}</td>
        </tr>
      `).join("");
    } catch {}
  }

  // 11. Cache Explorer
  const cacheSearchInput = document.getElementById("cacheSearchInput");
  const cacheResultsTable = document.getElementById("cacheResultsTable");
  let cacheSearchTimer = null;

  cacheSearchInput.addEventListener("input", () => {
    clearTimeout(cacheSearchTimer);
    cacheSearchTimer = setTimeout(() => {
      searchCache(cacheSearchInput.value.trim());
    }, 250);
  });

  async function fetchInitialCache() {
    searchCache("sword");
  }

  async function searchCache(query) {
    if (!query) {
      cacheResultsTable.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:20px; color:var(--text-muted);">اكتب كلمة أو جملة للبحث في الـ 93,000 ترجمة المخزنة...</td></tr>`;
      return;
    }

    try {
      const resp = await fetch(`/api/cache/search?q=${encodeURIComponent(query)}&limit=40`);
      const data = await resp.json();

      if (!data.results || data.results.length === 0) {
        cacheResultsTable.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:20px; color:var(--text-muted);">لم يتم العثور على نتائج تطابق "${escapeHtml(query)}" في الكاش.</td></tr>`;
        return;
      }

      cacheResultsTable.innerHTML = data.results.map((r, idx) => `
        <tr>
          <td style="color:var(--text-muted); font-size:0.8rem;">${idx + 1}</td>
          <td style="direction:ltr; text-align:left; font-weight:600;">${escapeHtml(r.en)}</td>
          <td style="color:var(--accent-success);">${escapeHtml(r.ar)}</td>
          <td style="direction:ltr; text-align:left; font-family:var(--font-mono); color:var(--accent-cyan);">${escapeHtml(r.fr)}</td>
          <td style="font-size:0.75rem; color:var(--accent-purple); font-weight:700;">${escapeHtml(r.model || 'Argos')}</td>
        </tr>
      `).join("");
    } catch {}
  }

  // 12. System Health Status on Boot
  async function checkSystemStatus() {
    try {
      const resp = await fetch("/api/status");
      const data = await resp.json();
      if (data.stats) {
        const arCount = (data.stats.arabic_cached_entries || 0).toLocaleString();
        const frCount = (data.stats.arabizi_cached_entries || 0).toLocaleString();
        const nllbCount = (data.stats.nllb_cached_entries || 0).toLocaleString();

        document.getElementById("headerCacheBadge").textContent = `⚡ الكاش: ${arCount} Argos | ${nllbCount} NLLB`;
        document.getElementById("aboutArEntries").textContent = arCount;
        document.getElementById("aboutFrEntries").textContent = frCount;
        const aboutNllb = document.getElementById("aboutNllbEntries");
        if (aboutNllb) aboutNllb.textContent = nllbCount;
        document.getElementById("aboutEngine").textContent = data.stats.model_engine || "CTranslate2";
        document.getElementById("aboutDevice").textContent = data.stats.device || "CPU int8";

        // Check if NLLB is not available
        if (!data.stats.nllb_available) {
          const btnNllb = document.getElementById("btnEngineNllb");
          if (btnNllb) {
            btnNllb.disabled = true;
            btnNllb.title = "نموذج NLLB غير متوفر محلياً";
            btnNllb.classList.remove("active");
            document.getElementById("btnEngineArgos").classList.add("active");
            currentEngine = "argos";
            if (dialectGroup) dialectGroup.style.display = "none";
          }
          if (fileEngineSelect) {
            fileEngineSelect.value = "argos";
            if (fileDialectContainer) fileDialectContainer.style.display = "none";
          }
        }
      }
    } catch (e) {
      console.warn("Status check failed", e);
    }
  }

  // Toast Helper
  function showToast(message) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerHTML = `
      <svg style="width:18px; height:18px; fill:var(--accent-success);" viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>
      <span>${escapeHtml(message)}</span>
    `;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      toast.style.transition = "all 0.3s";
      setTimeout(() => toast.remove(), 300);
    }, 2800);
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // Init
  checkSystemStatus();
  renderHistory();
});
