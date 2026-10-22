let onUnauthorized = null;

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

async function request(url, options = {}) {
  const res = await fetch(url, {
    credentials: "include",
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) {
    onUnauthorized?.();
  }
  return res;
}

async function jsonRequest(url, options = {}) {
  const res = await request(url, options);
  const payload = await res.json().catch(() => ({}));
  if (!res.ok || payload.ok === false) {
    const err = new Error(payload.error || payload.message || "Yêu cầu thất bại");
    err.status = res.status;
    err.auth = Boolean(payload.auth === false || res.status === 401);
    throw err;
  }
  return payload;
}

export async function fetchMe() {
  const res = await request("/api/auth/me");
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.error || "Không kiểm tra được phiên đăng nhập");
  return payload;
}

export async function login(username, password) {
  return jsonRequest("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function logout() {
  return jsonRequest("/api/auth/logout", {
    method: "POST",
    body: "{}",
  });
}

export async function fetchUsers() {
  return jsonRequest("/api/auth/users");
}

export async function createUser(username, password, role = "user") {
  return jsonRequest("/api/auth/users", {
    method: "POST",
    body: JSON.stringify({ username, password, role }),
  });
}

export async function deleteUser(username) {
  return jsonRequest("/api/auth/users/delete", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
}

export async function changePassword(currentPassword, newPassword) {
  return jsonRequest("/api/auth/password", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export async function fetchConfig() {
  return jsonRequest("/api/config");
}

export async function saveConfig(payload) {
  return jsonRequest("/api/config", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchBoard() {
  const res = await request("/api/board");
  if (!res.ok) {
    if (res.status === 401) throw Object.assign(new Error("Chưa đăng nhập"), { auth: true, status: 401 });
    throw new Error("Không đọc được danh sách sản phẩm");
  }
  return res.json();
}

export async function startCatalogRefresh(category) {
  return jsonRequest("/api/products/refresh", {
    method: "POST",
    body: JSON.stringify({ category: category || "" }),
  });
}

export async function catalogRefreshStatus() {
  return jsonRequest("/api/products/refresh");
}

export async function startShortLinks() {
  return jsonRequest("/api/short-link/generate", {
    method: "POST",
    body: "{}",
  });
}

export async function shortLinkStatus() {
  return jsonRequest("/api/short-link/generate");
}

export async function downloadMissingShortLinks() {
  const res = await request("/api/short-link/export");
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.error || "Không xuất được file Excel");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "Batch Custom Links.xlsx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return Number(res.headers.get("X-Link-Count") || "0");
}

export async function importShortLinks(file) {
  const body = new FormData();
  body.append("file", file);
  const res = await request("/api/short-link/import", { method: "POST", body, headers: {} });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok || !payload.ok) throw new Error(payload.error || "Không nhập được file CSV");
  return payload;
}

export async function saveShortLink(itemId, shortLink) {
  return jsonRequest("/api/short-link", {
    method: "POST",
    body: JSON.stringify({ item_id: itemId, short_link: shortLink }),
  });
}

export async function fetchNetworks() {
  const res = await request("/api/networks");
  if (!res.ok) throw new Error("Không đọc được danh sách kênh");
  return res.json();
}

export async function saveNetworkPage(payload) {
  return jsonRequest("/api/networks/page", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchAutoPost() {
  return jsonRequest("/api/auto-post");
}

export async function saveAutoPost(enabled, perDay, pageId, categories, dates, dateMode) {
  return jsonRequest("/api/auto-post", {
    method: "POST",
    body: JSON.stringify({
      enabled,
      per_day: perDay,
      page_id: pageId,
      categories: categories || [],
      dates: dates || [],
      date_mode: dateMode || "day",
    }),
  });
}

export async function postProducts(itemIds, mode, scheduleAt, platform, pageId) {
  return jsonRequest("/api/facebook/post", {
    method: "POST",
    body: JSON.stringify({
      item_ids: itemIds,
      mode,
      schedule_at: scheduleAt || "",
      platform,
      page_id: pageId,
    }),
  });
}

export async function fetchGroups() {
  const res = await request("/api/groups");
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.error || "Không đọc được danh sách nhóm");
  return payload;
}

export async function saveGroup(url, limit = 10) {
  return jsonRequest("/api/groups", {
    method: "POST",
    body: JSON.stringify({ url, limit }),
  });
}

export async function draftGroupComment(permalink) {
  return jsonRequest("/api/groups/comment/draft", {
    method: "POST",
    body: JSON.stringify({ permalink }),
  });
}

export async function publishGroupComment(permalink, comment) {
  return jsonRequest("/api/groups/comment", {
    method: "POST",
    body: JSON.stringify({ permalink, comment }),
  });
}

export async function startFacebookLogin() {
  return jsonRequest("/api/facebook/login/start", {
    method: "POST",
    body: "{}",
  });
}

export async function facebookLoginStatus() {
  return jsonRequest("/api/facebook/login/status");
}

export async function facebookLoginFrame() {
  const res = await request(`/api/facebook/login/frame?t=${Date.now()}`);
  if (res.status === 204) return "";
  if (!res.ok) throw new Error("Không lấy được khung hình đăng nhập");
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function sendFacebookLoginEvent(body) {
  return jsonRequest("/api/facebook/login/event", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function useFacebookAccount(id) {
  return jsonRequest("/api/facebook/accounts/use", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

export async function removeFacebookAccount(id) {
  return jsonRequest("/api/facebook/accounts/remove", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

export async function identifyFacebookAccounts() {
  return jsonRequest("/api/facebook/accounts/identify", {
    method: "POST",
    body: "{}",
  });
}

export async function cancelFacebookLogin() {
  return jsonRequest("/api/facebook/login/cancel", {
    method: "POST",
    body: "{}",
  });
}

export async function checkFacebook(itemId) {
  return jsonRequest("/api/facebook/check", {
    method: "POST",
    body: JSON.stringify(itemId ? { item_id: itemId } : {}),
  });
}
