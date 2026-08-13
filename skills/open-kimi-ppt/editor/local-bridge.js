/**
 * NeoDeck Local bridge — no iframe, no cloud.
 * Official neo-ppt talks to us via window.__NEODECK_CONNECT__ instead of Penpal parent.
 */
import {
  basename,
  dirname,
  extractPagePaths,
  joinDeckPath,
  normalizeRelativePath,
  titleFromManifest,
} from "./lib.js";

const state = {
  editor: null, // methods exposed by official editor (setPPTD, ...)
  directoryHandle: null,
  fileIndex: new Map(),
  memoryFiles: new Map(),
  imageMap: Object.create(null), // path → data URL (export host / payload)
  manifestPath: "",
  manifestDirectory: "",
  manifestContent: "",
  deckTitle: "未打开文稿",
  saveQueue: Promise.resolve(),
  imageCache: new Map(),
  readOnly: false,
  ready: false,
  exportMode: false,
  // host (server machine) mode
  hostMode: false,
  hostRoot: "",
  hostFileMap: new Map(), // relative path (under hostRoot) -> absolute path
};

const $ = (sel) => document.querySelector(sel);
const exportMode =
  new URL(location.href).searchParams.get("ndExport") === "1" ||
  new URL(location.href).searchParams.get("export") === "1";
state.exportMode = exportMode;
if (exportMode) {
  document.documentElement.classList.add("nd-export-mode");
  document.documentElement.dataset.deckStatus = "booting";
}

function toast(msg, kind = "info") {
  const el = $("#nd-toast");
  if (!el) return;
  el.hidden = false;
  el.dataset.kind = kind;
  el.textContent = msg;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    el.hidden = true;
  }, 3200);
}

function setStatus(text) {
  const el = $("#nd-status");
  if (el) el.textContent = text;
}

function setTitle(text) {
  state.deckTitle = text;
  const el = $("#nd-title");
  if (el) el.textContent = text;
}

async function indexDirectory(directoryHandle) {
  const index = new Map();
  async function walk(handle, prefix = "") {
    for await (const [name, entry] of handle.entries()) {
      if (name === ".DS_Store") continue;
      const path = prefix ? `${prefix}/${name}` : name;
      if (entry.kind === "directory") await walk(entry, path);
      else index.set(normalizeRelativePath(path), entry);
    }
  }
  await walk(directoryHandle);
  return index;
}

function indexFallbackFiles(fileList) {
  const index = new Map();
  const files = [...fileList];
  const firstPath = files[0]?.webkitRelativePath || files[0]?.name || "";
  const rootName = firstPath.includes("/") ? firstPath.split("/")[0] : "";
  for (const file of files) {
    let path = file.webkitRelativePath || file.name;
    if (rootName && path.startsWith(`${rootName}/`)) path = path.slice(rootName.length + 1);
    index.set(normalizeRelativePath(path), { kind: "file", getFile: async () => file });
  }
  return index;
}

async function textFromIndexed(path) {
  if (state.hostMode) return hostReadText(path);
  const key = normalizeRelativePath(path);
  if (state.memoryFiles.has(key)) return state.memoryFiles.get(key);
  const entry = state.fileIndex.get(key);
  if (!entry) throw new Error(`找不到文件：${path}`);
  return (await entry.getFile()).text();
}

/* ===================== Host (server machine) mode =====================
 * Reads and saves PPTD projects that live on the server, not on the
 * user's computer. The server exposes a constrained POST /ndfs/* API. */

async function ndfsCall(endpoint, payload) {
  let response;
  try {
    response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
  } catch (error) {
    throw new Error(`无法连接主机文件服务：${error.message}`);
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`主机文件服务响应异常 (HTTP ${response.status})`);
  }
  if (!response.ok || data?.ok === false) throw new Error(data?.error || `主机文件接口失败 (HTTP ${response.status})`);
  return data;
}

const ndfsList = (path) => ndfsCall("/ndfs/list", { path });
const ndfsRead = (path) => ndfsCall("/ndfs/read", { path });
const ndfsReadImage = (path) => ndfsCall("/ndfs/read-image", { path });
const ndfsWrite = (path, content) => ndfsCall("/ndfs/write", { path, content });

function hostAbsolute(relPath) {
  const norm = normalizeRelativePath(relPath);
  const abs = state.hostFileMap.get(norm);
  if (!abs) throw new Error(`主机上找不到文件：${relPath}`);
  return abs;
}

async function hostReadText(relPath) {
  const data = await ndfsRead(hostAbsolute(relPath));
  return data.content;
}

async function indexHostRoot(root) {
  const map = new Map();
  const stack = [root.replace(/\/+$/, "")];
  let guard = 0;
  while (stack.length && guard < 40000) {
    guard += 1;
    const directory = stack.pop();
    let entries;
    try {
      entries = (await ndfsList(directory)).entries || [];
    } catch (error) {
      console.warn("[neodeck] skip unreadable dir", directory, error.message);
      continue;
    }
    for (const entry of entries) {
      const abs = `${directory}/${entry.name}`;
      if (entry.type === "dir") {
        stack.push(abs);
        continue;
      }
      const rel = abs.startsWith(`${state.hostRoot}/`) ? abs.slice(state.hostRoot.length + 1) : entry.name;
      try {
        map.set(normalizeRelativePath(rel), abs);
      } catch {
        /* skip paths the relative normalizer rejects */
      }
    }
  }
  return map;
}

async function hostResolveImage(path) {
  const base = path.split("/").pop();
  const candidates = [path];
  if (state.manifestDirectory) {
    try {
      candidates.push(joinDeckPath(state.manifestDirectory, path));
    } catch {
      /* ignore */
    }
  }
  if (base) candidates.push(`media/${base}`, `assets/${base}`, `images/${base}`);
  for (const candidate of candidates) {
    let rel;
    try {
      rel = normalizeRelativePath(candidate);
    } catch {
      continue;
    }
    const abs = state.hostFileMap.get(rel);
    if (!abs) continue;
    try {
      const data = await ndfsReadImage(abs);
      if (data.dataUrl) return data.dataUrl;
    } catch (error) {
      console.warn("[neodeck] host image read failed", abs, error.message);
    }
  }
  console.warn("[neodeck] host image not found", path, "tried", candidates.slice(0, 6));
  return "";
}

async function openHostDeck(root) {
  setStatus("扫描主机目录…");
  state.hostMode = true;
  state.hostRoot = root.replace(/\/+$/, "");
  state.hostFileMap = await indexHostRoot(state.hostRoot);
  state.imageCache.clear();
  state.memoryFiles.clear();
  state.directoryHandle = null;
  const manifests = [...state.hostFileMap.keys()].filter((p) => p.toLowerCase().endsWith(".pptd"));
  if (!manifests.length) throw new Error("该目录下没有 .pptd 文稿");
  const manifestPath = manifests.length === 1 ? manifests[0] : manifests.sort()[0];
  await loadDeckFromIndex(manifestPath, `主机 · ${state.hostRoot}`, {
    readOnly: false,
    editable: true,
  });
}

/* ----- host directory browser UI ----- */
let hostCurDir = "/";

async function listHostDir(directory) {
  hostCurDir = directory.replace(/\/+$/, "") || "/";
  const pathEl = $("#nd-host-path");
  if (pathEl) pathEl.textContent = hostCurDir;
  const listEl = $("#nd-host-list");
  if (listEl) listEl.textContent = "";
  const data = await ndfsList(hostCurDir);
  const entries = data.entries || [];
  for (const entry of entries) {
    const isDir = entry.type === "dir";
    const isDeck = !isDir && /\.pptd$/i.test(entry.name);
    const row = document.createElement("div");
    row.className = `nd-host-item${isDir ? " nd-dir" : ""}${isDeck ? " nd-deck" : ""}`;
    row.innerHTML =
      `<span class="nd-ico">${isDir ? "&#9660;" : "&#9632;"}</span>` +
      `<span class="nd-name"></span>` +
      (isDeck ? `<span class="nd-open-tag">打开</span>` : "") +
      (isDir ? "" : `<span class="nd-size"></span>`);
    row.querySelector(".nd-name").textContent = entry.name;
    if (!isDir && entry.size > 0) {
      const size = entry.size >= 1024 * 1024 ? `${(entry.size / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(entry.size / 1024))} KB`;
      row.querySelector(".nd-size").textContent = size;
    }
    row.addEventListener("click", () => {
      const target = `${hostCurDir}/${entry.name}`;
      if (isDir) {
        listHostDir(target).catch((error) => toast(error.message, "error"));
      } else if (isDeck) {
        closeHostModal();
        openHostDeck(hostCurDir).catch((error) => toast(error.message, "error"));
      }
    });
    listEl.appendChild(row);
  }
  const hintEl = $("#nd-host-hint");
  if (hintEl) hintEl.textContent = `${entries.length} 个条目 · 点击 .pptd 直接打开`;
}

function closeHostModal() {
  const modal = $("#nd-host-modal");
  if (modal) modal.hidden = true;
}

function wireHostUi() {
  const openBtn = $("#nd-host-open");
  openBtn?.addEventListener("click", async () => {
    $("#nd-host-modal").hidden = false;
    try {
      await listHostDir(hostCurDir);
    } catch (error) {
      toast(error.message, "error");
    }
  });
  $("#nd-host-close")?.addEventListener("click", closeHostModal);
  $("#nd-host-modal")?.addEventListener("click", (ev) => {
    if (ev.target === ev.currentTarget) closeHostModal();
  });
  $("#nd-host-up")?.addEventListener("click", () => {
    const parent = hostCurDir.replace(/\/[^/]*$/, "") || "/";
    listHostDir(parent).catch((error) => toast(error.message, "error"));
  });
  $("#nd-host-refresh")?.addEventListener("click", () => {
    listHostDir(hostCurDir).catch((error) => toast(error.message, "error"));
  });
  const gotoDir = () => {
    const input = $("#nd-host-input");
    const value = (input?.value || "").trim() || "/";
    listHostDir(value).catch((error) => toast(error.message, "error"));
  };
  $("#nd-host-goto-btn")?.addEventListener("click", gotoDir);
  $("#nd-host-input")?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") gotoDir();
  });
  $("#nd-host-open-deck")?.addEventListener("click", () => {
    openHostDeck(hostCurDir)
      .then(closeHostModal)
      .catch((error) => toast(error.message, "error"));
  });
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function lookupImageMap(path) {
  if (!path || !state.imageMap) return "";
  if (state.imageMap[path]) return state.imageMap[path];
  const keys = Object.keys(state.imageMap);
  const hit = keys.find(
    (key) => path.endsWith(`/${key}`) || key.endsWith(`/${path}`) || key === path || key.endsWith(`/${path.split("/").pop()}`),
  );
  return hit ? state.imageMap[hit] : "";
}

async function resolveImage(requestedPath) {
  if (requestedPath == null || requestedPath === "") return "";
  const raw = String(requestedPath);
  if (/^(?:data:image\/|https?:\/\/|blob:)/i.test(raw)) return raw;

  let path;
  try {
    path = normalizeRelativePath(raw.replace(/^file:\/\/+/, "").replace(/^\.\//, ""));
  } catch {
    path = raw.replace(/^file:\/\/+/, "").replace(/^\.\//, "").replaceAll("\\", "/");
  }

  if (state.hostMode) return hostResolveImage(path);

  const mapped = lookupImageMap(path);
  if (mapped) return mapped;

  const candidates = [];
  const add = (p) => {
    if (p && !candidates.includes(p)) candidates.push(p);
  };
  add(path);
  if (state.manifestDirectory) {
    try {
      add(joinDeckPath(state.manifestDirectory, path));
    } catch {
      /* ignore */
    }
  }
  // common media layouts
  const base = path.split("/").pop();
  if (base) {
    add(`media/${base}`);
    add(`assets/${base}`);
    add(`images/${base}`);
    if (state.manifestDirectory) {
      try {
        add(joinDeckPath(state.manifestDirectory, `media/${base}`));
      } catch {
        /* ignore */
      }
    }
  }

  // fuzzy: any indexed file ending with same relative suffix or basename
  for (const key of state.fileIndex.keys()) {
    if (key === path || key.endsWith("/" + path) || (base && key.endsWith("/" + base)) || key === base) {
      add(key);
    }
  }

  for (const c of candidates) {
    if (!state.fileIndex.has(c) && !state.memoryFiles.has(c)) continue;
    const cacheKey = c;
    if (!state.imageCache.has(cacheKey)) {
      try {
        if (state.fileIndex.has(c)) {
          const file = await state.fileIndex.get(c).getFile();
          state.imageCache.set(cacheKey, await fileToDataUrl(file));
        } else {
          // memory text shouldn't be image; skip
          continue;
        }
      } catch (e) {
        console.warn("[neodeck] image read failed", c, e);
        continue;
      }
    }
    const url = await state.imageCache.get(cacheKey);
    if (url) return url;
  }
  console.warn("[neodeck] image not found", requestedPath, "tried", candidates.slice(0, 8));
  return "";
}

async function getImages(payload = {}) {
  // Official contract: { chatId, filePath: string[] } -> string[] (data URLs / public URLs)
  let paths = payload?.filePath;
  if (paths == null) paths = [];
  if (!Array.isArray(paths)) paths = [paths];
  const out = [];
  for (const p of paths) {
    try {
      out.push(await resolveImage(p));
    } catch (e) {
      console.warn("[neodeck] getImages item failed", p, e);
      out.push("");
    }
  }
  return out;
}

async function writeIndexedFile(path, content) {
  if (state.hostMode) {
    const rel = normalizeRelativePath(path);
    const abs = `${state.hostRoot}/${rel}`;
    await ndfsWrite(abs, content);
    state.memoryFiles.set(rel, content);
    state.hostFileMap.set(rel, abs);
    return;
  }
  if (state.readOnly || !state.directoryHandle) {
    state.memoryFiles.set(path, content);
    return;
  }
  const parts = path.split("/");
  let dir = state.directoryHandle;
  for (let i = 0; i < parts.length - 1; i++) {
    dir = await dir.getDirectoryHandle(parts[i], { create: true });
  }
  const handle = await dir.getFileHandle(parts[parts.length - 1], { create: true });
  const writable = await handle.createWritable();
  await writable.write(content);
  await writable.close();
  state.fileIndex.set(path, handle);
  state.memoryFiles.set(path, content);
}

async function onSave(payload) {
  const changes = payload?.changes || payload?.files || [];
  const list = Array.isArray(changes) ? changes : [];
  setStatus("正在保存…");
  try {
    for (const change of list) {
      if (!change?.path) continue;
      const path = normalizeRelativePath(change.path);
      if (!/\.(?:pptd|page)$/i.test(path)) continue;
      await writeIndexedFile(path, change.content ?? "");
    }
    setStatus(state.readOnly ? "只读 · 已存内存" : "已保存到本地");
  } catch (e) {
    setStatus("保存失败");
    toast(`保存失败：${e.message || e}`, "error");
    throw e;
  }
}

/** Called by patched official editor instead of Penpal connect */
window.__NEODECK_CONNECT__ = function neoDeckConnect(options) {
  const methods = options?.methods || {};
  state.editor = methods;
  state.ready = true;
  setStatus("编辑器就绪");
  // Force light chrome immediately (official default is system → OS dark FOUC).
  Promise.resolve(
    methods.setSlideConfig?.({ editable: true, locale: "zh-CN", theme: "light" }),
  ).catch((e) => console.warn("[neodeck] setSlideConfig", e));
  // host methods the editor will call via connection.promise
  const host = {
    close() {
      toast("本地模式无需关闭");
    },
    reenter() {},
    async toggleFullScreen(want) {
      try {
        const el = document.documentElement;
        const isFs = Boolean(document.fullscreenElement);
        if (want === true || (want !== false && !isFs)) {
          if (!isFs && el.requestFullscreen) await el.requestFullscreen();
        } else if (want === false || isFs) {
          if (isFs && document.exitFullscreen) await document.exitFullscreen();
        }
      } catch (e) {
        console.warn("[neodeck] fullscreen", e);
      }
      return Boolean(document.fullscreenElement);
    },
    showFeedback() {},
    sendPrompt() {
      toast("本地模式已禁用 AI", "warning");
    },
    showMessage(payload) {
      const message = typeof payload === "string" ? payload : payload?.message || payload?.content;
      if (message) toast(String(message));
    },
    hideMessage() {},
    onSave,
    getImages,
    setAnnotationMode() {},
    setAnnotationCurrentPage() {},
    upsertAnnotation() {},
    removeAnnotation() {},
    clearAnnotations() {},
  };

  if (state.exportMode) {
    loadExportPayload().catch((error) => {
      console.error("[neodeck] export payload failed", error);
      document.documentElement.dataset.deckStatus = "error";
      window.exportHostError = String(error?.stack || error);
      setStatus("导出载荷加载失败");
    });
  } else {
    // Auto-open demo if nothing loaded after a beat
    setTimeout(() => {
      if (!state.manifestPath) openDemo().catch((e) => console.error(e));
    }, 400);
  }

  return {
    promise: Promise.resolve(host),
    destroy() {
      state.editor = null;
      state.ready = false;
    },
  };
};

/** Headless / agent-browser export: load deck from ./payload.json (no folder picker). */
async function loadExportPayload() {
  state.hostMode = false;
  document.documentElement.dataset.deckStatus = "loading";
  setStatus("载入导出载荷…");
  const response = await fetch("./payload.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`payload HTTP ${response.status}`);
  const payload = await response.json();
  if (!state.editor?.setPPTD) throw new Error("编辑器尚未就绪");

  state.directoryHandle = null;
  state.readOnly = true;
  state.fileIndex = new Map();
  state.memoryFiles = new Map();
  state.imageCache = new Map();
  state.imageMap = Object.create(null);
  for (const [key, value] of Object.entries(payload.imageMap || {})) {
    try {
      state.imageMap[normalizeRelativePath(key)] = value;
    } catch {
      state.imageMap[String(key).replaceAll("\\", "/")] = value;
    }
    state.imageCache.set(key, value);
  }

  const manifestPath = payload.manifestPath || "deck.pptd";
  state.manifestPath = manifestPath;
  state.manifestDirectory = dirname(manifestPath);
  state.manifestContent = payload.manifestContent || "";
  state.memoryFiles.set(normalizeRelativePath(manifestPath), state.manifestContent);
  for (const page of payload.pages || []) {
    if (!page?.path) continue;
    state.memoryFiles.set(normalizeRelativePath(page.path), page.content ?? "");
  }

  const title = payload.title || titleFromManifest(state.manifestContent, basename(manifestPath));
  setTitle(title);

  await state.editor.setSlideConfig?.({
    editable: true,
    locale: "zh-CN",
    theme: "light",
    slideId: payload.id,
  });
  await state.editor.setPPTD(payload.id || `export-${Date.now()}`, {
    pptdContent: state.manifestContent,
    pages: payload.pages || [],
    pptdPath: manifestPath,
    basePath: "",
    isCreate: false,
  });
  await state.editor.setEditable?.(true);

  window.exportRemote = state.editor;
  try {
    window.exportSlideStatus = await state.editor.getSlideStatus?.();
  } catch {
    window.exportSlideStatus = null;
  }
  setStatus(`导出模式 · ${title}`);
  document.documentElement.dataset.deckStatus = "ready";
}

async function loadDeckFromIndex(manifestPath, sourceLabel, options = {}) {
  if (typeof options === "boolean") {
    options = { readOnly: options, editable: !options };
  }
  const readOnly = Boolean(options.readOnly);
  const editable = options.editable !== false;
  if (!state.editor?.setPPTD) throw new Error("编辑器尚未就绪");
  const manifestContent = await textFromIndexed(manifestPath);
  const pagePaths = extractPagePaths(manifestContent);
  const pages = [];
  const missing = [];
  const manifestDirectory = dirname(manifestPath);
  for (const pagePath of pagePaths.slice(0, 500)) {
    const indexedPath = joinDeckPath(manifestDirectory, pagePath);
    try {
      pages.push({ path: pagePath, content: await textFromIndexed(indexedPath) });
    } catch {
      missing.push(pagePath);
    }
  }
  if (missing.length) throw new Error(`缺少页面：${missing.slice(0, 5).join(", ")}`);
  const title = titleFromManifest(manifestContent, basename(manifestPath));
  state.manifestPath = manifestPath;
  state.manifestDirectory = manifestDirectory;
  state.manifestContent = manifestContent;
  state.readOnly = readOnly;
  setTitle(title);
  setStatus(sourceLabel);

  // isCreate:true leaves the official UI in a "generating / loading" state and
  // disables export / present until generate_end — use false for local opens.
  await state.editor.setPPTD(`local-${Date.now()}`, {
    pptdContent: manifestContent,
    pages,
    basePath: "",
    pptdPath: manifestPath,
    isCreate: false,
  });
  await state.editor.setEditable?.(editable);
  await state.editor.setSlideConfig?.({ editable, locale: "zh-CN", theme: "light" });
  toast(`已载入「${title}」· ${pages.length} 页`);
}

async function openDemo() {
  state.hostMode = false;
  state.directoryHandle = null;
  state.fileIndex.clear();
  state.imageCache.clear();
  state.memoryFiles.clear();
  const manifest = JSON.stringify({
    version: "v2",
    title: "NeoDeck Local",
    size: [960, 540],
    pages: ["pages/01.page", "pages/02.page"],
  });
  const page1 = JSON.stringify({
    pageType: "content",
    background: { color: "#f7f8fc" },
    elements: [
      {
        elementId: "title",
        elementType: "text",
        bounds: [80, 160, 800, 120],
        content: {
          text: '<p><span style="font-size:48px;color:#171923;font-weight:700">完全本地离线</span></p>',
        },
      },
      {
        elementId: "sub",
        elementType: "text",
        bounds: [80, 300, 720, 60],
        content: {
          text: '<p><span style="font-size:20px;color:#667085">官方编辑器镜像 · 无 iframe · 无云端接口</span></p>',
        },
      },
    ],
  });
  const page2 = JSON.stringify({
    pageType: "content",
    background: { color: "#171923" },
    elements: [
      {
        elementId: "t",
        elementType: "text",
        bounds: [80, 200, 800, 80],
        content: {
          text: '<p><span style="font-size:36px;color:#fff;font-weight:700">打开 PPTD 文件夹开始编辑</span></p>',
        },
      },
    ],
  });
  state.memoryFiles.set("presentation.pptd", manifest);
  state.memoryFiles.set("pages/01.page", page1);
  state.memoryFiles.set("pages/02.page", page2);
  state.fileIndex.clear();
  // synthetic index for demo
  for (const [path, content] of state.memoryFiles) {
    state.fileIndex.set(path, {
      kind: "file",
      getFile: async () => new File([content], basename(path), { type: "text/plain" }),
    });
  }
  // Editable in UI; readOnly only means "don't write to disk" (saves stay in memory).
  await loadDeckFromIndex("presentation.pptd", "内置示例 · 内存", {
    readOnly: true,
    editable: true,
  });
}

async function openDirectoryHandle(handle) {
  state.hostMode = false;
  setStatus("扫描文件夹…");
  state.directoryHandle = handle;
  state.fileIndex = await indexDirectory(handle);
  state.imageCache.clear();
  state.memoryFiles.clear();
  const manifests = [...state.fileIndex.keys()].filter((p) => p.toLowerCase().endsWith(".pptd"));
  if (!manifests.length) throw new Error("文件夹内没有 .pptd");
  const manifestPath = manifests.length === 1 ? manifests[0] : manifests.sort()[0];
  await loadDeckFromIndex(manifestPath, `${handle.name} · 可写`, {
    readOnly: false,
    editable: true,
  });
}

async function openFallbackFiles(fileList) {
  state.hostMode = false;
  setStatus("读取上传…");
  state.directoryHandle = null;
  state.readOnly = true;
  state.fileIndex = indexFallbackFiles(fileList);
  state.imageCache.clear();
  state.memoryFiles.clear();
  const manifests = [...state.fileIndex.keys()].filter((p) => p.toLowerCase().endsWith(".pptd"));
  if (!manifests.length) throw new Error("没有 .pptd");
  await loadDeckFromIndex(manifests.sort()[0], "上传 · 只读", {
    readOnly: true,
    editable: true,
  });
}

function wireUi() {
  $("#nd-open")?.addEventListener("click", async () => {
    try {
      if (window.showDirectoryPicker) {
        const handle = await window.showDirectoryPicker({ mode: "readwrite" });
        await openDirectoryHandle(handle);
      } else {
        $("#nd-folder")?.click();
      }
    } catch (e) {
      if (e?.name === "AbortError") return;
      toast(e.message || String(e), "error");
    }
  });
  $("#nd-folder")?.addEventListener("change", async (ev) => {
    const files = ev.target.files;
    if (!files?.length) return;
    try {
      await openFallbackFiles(files);
    } catch (e) {
      toast(e.message || String(e), "error");
    }
    ev.target.value = "";
  });
}

// Force sdk query params so official app enters ppt-editor external mode
(function forceSdkQuery() {
  const url = new URL(location.href);
  let changed = false;
  const params = {
    sdkMode: "ppt-editor",
    pptPlatform: "neodeck-local",
    functional: JSON.stringify({
      fullscreen: true,
      present: true,
      export: true,
      close: false,
      annotation: false,
      feedback: false,
      share: false,
      versionHistory: false,
    }),
    sdkSaveMode: "external",
    sdkImageMode: "external",
  };
  for (const [k, v] of Object.entries(params)) {
    if (url.searchParams.get(k) !== v) {
      url.searchParams.set(k, v);
      changed = true;
    }
  }
  if (changed) history.replaceState(null, "", url);
})();

wireUi();
wireHostUi();
setStatus("等待编辑器…");
