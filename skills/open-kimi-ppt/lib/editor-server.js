import { createReadStream, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const defaultEditorDirectory = resolve(packageRoot, "editor");

const contentTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".wasm", "application/wasm"],
]);

function respond(response, statusCode, message) {
  response.writeHead(statusCode, {
    "Content-Type": "text/plain; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  response.end(message);
}

function respondJson(response, statusCode, object) {
  const body = JSON.stringify(object);
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  response.end(body);
}

function readJsonBody(request) {
  return new Promise((resolvePromise, reject) => {
    let data = "";
    request.on("data", (chunk) => {
      data += chunk;
      if (data.length > 1024 * 1024) {
        reject(new Error("请求体过大"));
        request.destroy();
      }
    });
    request.on("end", () => {
      try {
        resolvePromise(data ? JSON.parse(data) : {});
      } catch {
        reject(new Error("JSON 解析失败"));
      }
    });
    request.on("error", reject);
  });
}

/* ============================================================
 * Host filesystem API (POST /ndfs/*)
 *
 * Lets the local browser editor read and save PPTD projects that
 * live on the server (host) machine, since showDirectoryPicker()
 * can only reach the user's own computer.
 *
 * Deliberately constrained:
 *   - list:       any directory (needed to browse to a project)
 *   - read:       text files only (whitelisted extensions, <=2MB)
 *   - read-image: images only (whitelisted extensions, <=20MB)
 *   - write:      .pptd / .page only
 * ============================================================ */

const HOSTFS_TEXT_EXT = new Set([
  ".pptd", ".page", ".yaml", ".yml", ".json", ".md", ".txt", ".csv", ".jsonl",
]);
const HOSTFS_IMAGE_EXT = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]);
const HOSTFS_MAX_TEXT_BYTES = 2 * 1024 * 1024;
const HOSTFS_MAX_IMAGE_BYTES = 20 * 1024 * 1024;
const HOSTFS_IMAGE_MIME = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  webp: "image/webp",
  svg: "image/svg+xml",
};

function ndfsList(requestedPath) {
  let stats;
  try {
    stats = statSync(requestedPath);
  } catch {
    return { ok: false, error: `目录不存在：${requestedPath}` };
  }
  if (!stats.isDirectory()) return { ok: false, error: `不是目录：${requestedPath}` };
  let names;
  try {
    names = readdirSync(requestedPath);
  } catch (error) {
    return { ok: false, error: `无法读取目录：${error.message}` };
  }
  const entries = names
    .map((name) => {
      let type = "file";
      let size = 0;
      try {
        const entryStats = statSync(join(requestedPath, name));
        type = entryStats.isDirectory() ? "dir" : "file";
        size = entryStats.size;
      } catch {
        /* skip unreadable entries */
      }
      return { name, type, size };
    })
    .sort((a, b) =>
      a.type === b.type ? a.name.localeCompare(b.name) : a.type === "dir" ? -1 : 1,
    );
  return { ok: true, path: requestedPath, entries };
}

function ndfsReadText(requestedPath) {
  const ext = extname(requestedPath).toLowerCase();
  if (!HOSTFS_TEXT_EXT.has(ext)) {
    return { ok: false, error: `不允许读取该类型文件：${ext || "(无扩展名)"}` };
  }
  let stats;
  try {
    stats = statSync(requestedPath);
  } catch {
    return { ok: false, error: `文件不存在：${requestedPath}` };
  }
  if (!stats.isFile()) return { ok: false, error: `不是文件：${requestedPath}` };
  if (stats.size > HOSTFS_MAX_TEXT_BYTES) {
    return { ok: false, error: `文件过大（${stats.size} 字节，上限 ${HOSTFS_MAX_TEXT_BYTES}）` };
  }
  try {
    return { ok: true, path: requestedPath, content: readFileSync(requestedPath, "utf8") };
  } catch (error) {
    return { ok: false, error: `读取失败：${error.message}` };
  }
}

function ndfsReadImage(requestedPath) {
  const ext = extname(requestedPath).toLowerCase().slice(1);
  if (!HOSTFS_IMAGE_EXT.has(`.${ext}`)) {
    return { ok: false, error: `不允许读取该图片类型：${extname(requestedPath) || "(无扩展名)"}` };
  }
  let stats;
  try {
    stats = statSync(requestedPath);
  } catch {
    return { ok: false, error: `图片不存在：${requestedPath}` };
  }
  if (!stats.isFile()) return { ok: false, error: `不是文件：${requestedPath}` };
  if (stats.size > HOSTFS_MAX_IMAGE_BYTES) {
    return { ok: false, error: `图片过大（${stats.size} 字节，上限 ${HOSTFS_MAX_IMAGE_BYTES}）` };
  }
  try {
    const buffer = readFileSync(requestedPath);
    const mime = HOSTFS_IMAGE_MIME[ext] || "application/octet-stream";
    return { ok: true, path: requestedPath, dataUrl: `data:${mime};base64,${buffer.toString("base64")}` };
  } catch (error) {
    return { ok: false, error: `读取失败：${error.message}` };
  }
}

function ndfsWriteText(requestedPath, content) {
  if (typeof content !== "string") return { ok: false, error: "content 必须为字符串" };
  if (!/\.(?:pptd|page)$/i.test(requestedPath)) {
    return { ok: false, error: `仅允许保存 .pptd/.page：${requestedPath}` };
  }
  try {
    mkdirSync(dirname(requestedPath), { recursive: true });
    writeFileSync(requestedPath, content, "utf8");
    return { ok: true, path: requestedPath };
  } catch (error) {
    return { ok: false, error: `写入失败：${error.message}` };
  }
}

async function handleHostFs(request, response, pathname) {
  let body;
  try {
    body = await readJsonBody(request);
  } catch (error) {
    respondJson(response, 400, { ok: false, error: error.message });
    return;
  }
  const requestedPath = typeof body?.path === "string" && body.path ? body.path : "";
  if (!requestedPath) {
    respondJson(response, 400, { ok: false, error: "path 必填" });
    return;
  }

  let result;
  switch (pathname) {
    case "/ndfs/list":
      result = ndfsList(requestedPath);
      break;
    case "/ndfs/read":
      result = ndfsReadText(requestedPath);
      break;
    case "/ndfs/read-image":
      result = ndfsReadImage(requestedPath);
      break;
    case "/ndfs/write":
      result = ndfsWriteText(requestedPath, body.content);
      break;
    default:
      respondJson(response, 404, { ok: false, error: "未知接口" });
      return;
  }
  respondJson(response, 200, result);
}

export function createEditorServer({ editorDirectory = defaultEditorDirectory } = {}) {
  const root = resolve(editorDirectory);
  const rootPrefix = `${root}${sep}`;

  return createServer((request, response) => {
    let pathname;
    try {
      pathname = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname);
    } catch {
      respond(response, 400, "Bad Request");
      return;
    }

    if (request.method === "POST" && pathname.startsWith("/ndfs/")) {
      handleHostFs(request, response, pathname);
      return;
    }

    if (request.method !== "GET" && request.method !== "HEAD") {
      respond(response, 405, "Method Not Allowed");
      return;
    }

    if (pathname.endsWith("/")) pathname += "index.html";
    const filePath = resolve(root, `.${pathname}`);
    if (filePath !== root && !filePath.startsWith(rootPrefix)) {
      respond(response, 403, "Forbidden");
      return;
    }

    let stats;
    try {
      stats = statSync(filePath);
    } catch {
      respond(response, 404, "Not Found");
      return;
    }

    if (!stats.isFile()) {
      respond(response, 404, "Not Found");
      return;
    }

    response.writeHead(200, {
      "Content-Type": contentTypes.get(extname(filePath).toLowerCase()) ?? "application/octet-stream",
      "Content-Length": stats.size,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    });

    if (request.method === "HEAD") {
      response.end();
      return;
    }

    const stream = createReadStream(filePath);
    stream.on("error", () => response.destroy());
    stream.pipe(response);
  });
}

export function startEditorServer({ host = "127.0.0.1", port = 55173 } = {}) {
  const server = createEditorServer();

  return new Promise((resolvePromise, reject) => {
    const onError = (error) => reject(error);
    server.once("error", onError);
    server.listen(port, host, () => {
      server.off("error", onError);
      const address = server.address();
      const actualPort = typeof address === "object" && address ? address.port : port;
      resolvePromise({ server, url: `http://${host}:${actualPort}/` });
    });
  });
}
