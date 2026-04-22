(() => {
  const API_BASE =
    (typeof window !== "undefined" && window.__API_BASE__) ||
    "__API_BASE_PLACEHOLDER__";

  const form = document.getElementById("form");
  const urlInput = document.getElementById("url");
  const fmtSelect = document.getElementById("fmt");
  const previewBtn = document.getElementById("preview-btn");
  const downloadBtn = document.getElementById("download-btn");
  const statusEl = document.getElementById("status");
  const previewEl = document.getElementById("preview");
  const previewThumb = document.getElementById("preview-thumb");
  const previewTitle = document.getElementById("preview-title");
  const previewUploader = document.getElementById("preview-uploader");
  const previewDuration = document.getElementById("preview-duration");

  function setStatus(message, kind = "") {
    statusEl.className = "status" + (kind ? ` ${kind}` : "");
    statusEl.innerHTML = "";
    if (!message) return;
    if (kind === "loading") {
      const s = document.createElement("span");
      s.className = "spinner";
      statusEl.appendChild(s);
    }
    const text = document.createElement("span");
    text.textContent = message;
    statusEl.appendChild(text);
  }

  function formatDuration(seconds) {
    if (seconds == null || isNaN(seconds)) return "";
    const s = Math.round(Number(seconds));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
  }

  function isLikelyYouTube(u) {
    try {
      const url = new URL(u);
      return /(^|\.)youtube\.com$|^youtu\.be$|(^|\.)youtube-nocookie\.com$/i.test(
        url.hostname
      );
    } catch {
      return false;
    }
  }

  async function fetchInfo(url) {
    const r = await fetch(
      `${API_BASE}/api/info?url=${encodeURIComponent(url)}`,
      { method: "GET" }
    );
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || `HTTP ${r.status}`);
    return body;
  }

  previewBtn.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!isLikelyYouTube(url)) {
      setStatus("Это не похоже на ссылку YouTube.", "error");
      return;
    }
    setStatus("Загружаем данные о видео…", "loading");
    previewBtn.disabled = true;
    try {
      const info = await fetchInfo(url);
      previewThumb.src = info.thumbnail || "";
      previewThumb.alt = info.title || "";
      previewTitle.textContent = info.title || "";
      previewUploader.textContent = info.uploader
        ? `Автор: ${info.uploader}`
        : "";
      previewDuration.textContent = info.duration
        ? `Длительность: ${formatDuration(info.duration)}`
        : "";
      previewEl.classList.remove("hidden");
      setStatus("Готово. Можно скачивать.", "ok");
    } catch (e) {
      previewEl.classList.add("hidden");
      setStatus(e.message || "Не удалось получить данные.", "error");
    } finally {
      previewBtn.disabled = false;
    }
  });

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const url = urlInput.value.trim();
    const fmt = fmtSelect.value;
    if (!isLikelyYouTube(url)) {
      setStatus("Это не похоже на ссылку YouTube.", "error");
      return;
    }

    downloadBtn.disabled = true;
    previewBtn.disabled = true;
    setStatus(
      "Скачиваем и конвертируем… Это может занять до минуты.",
      "loading"
    );

    try {
      const resp = await fetch(
        `${API_BASE}/api/download?url=${encodeURIComponent(
          url
        )}&fmt=${encodeURIComponent(fmt)}`,
        { method: "GET" }
      );
      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try {
          const j = await resp.json();
          if (j && j.error) msg = j.error;
        } catch {}
        throw new Error(msg);
      }

      const cd = resp.headers.get("content-disposition") || "";
      let filename = `audio.${fmt === "vorbis" ? "ogg" : fmt === "aac" ? "m4a" : fmt}`;
      const mStar = /filename\*=UTF-8''([^;]+)/i.exec(cd);
      const m = /filename="?([^";]+)"?/i.exec(cd);
      if (mStar) {
        try { filename = decodeURIComponent(mStar[1]); } catch {}
      } else if (m) {
        filename = m[1];
      }

      const blob = await resp.blob();
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(objUrl), 60_000);

      setStatus(`Готово: ${filename}`, "ok");
    } catch (e) {
      setStatus(e.message || "Ошибка загрузки", "error");
    } finally {
      downloadBtn.disabled = false;
      previewBtn.disabled = false;
    }
  });
})();
