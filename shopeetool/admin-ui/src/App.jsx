import { useEffect, useMemo, useRef, useState } from "react";
import {
  catalogRefreshStatus,
  changePassword,
  checkFacebook,
  createUser,
  deleteUser,
  downloadMissingShortLinks,
  fetchBoard,
  fetchConfig,
  fetchMe,
  fetchNetworks,
  fetchUsers,
  importShortLinks,
  login,
  logout,
  postProducts,
  saveConfig,
  saveNetworkPage,
  saveShortLink,
  setUnauthorizedHandler,
  shortLinkStatus,
  startCatalogRefresh,
  startShortLinks,
} from "./api.js";
import AutoPost from "./AutoPost.jsx";
import Groups from "./Groups.jsx";

const PAGE_SIZE = 20;
const MIN_AUTO_MINUTES = 5;
const MAX_AUTO_MINUTES = 24 * 60;

function autoRefreshKey(username) {
  return username ? `catalog-auto-refresh:${username}` : "catalog-auto-refresh";
}

function clampAutoMinutes(value) {
  const minutes = Math.round(Number(value));
  if (!Number.isFinite(minutes)) return 60;
  return Math.min(MAX_AUTO_MINUTES, Math.max(MIN_AUTO_MINUTES, minutes));
}

function readAutoRefresh(username) {
  try {
    const raw = JSON.parse(localStorage.getItem(autoRefreshKey(username)) || "null");
    const minutes = clampAutoMinutes(raw?.minutes);
    const unit = raw?.unit === "hour" ? "hour" : "minute";
    const enabled = Boolean(raw?.enabled);
    const nextAt = Number(raw?.nextAt) || 0;
    return { enabled, minutes, unit, nextAt };
  } catch {
    return { enabled: false, minutes: 60, unit: "minute", nextAt: 0 };
  }
}

function writeAutoRefresh(username, value) {
  try {
    localStorage.setItem(autoRefreshKey(username), JSON.stringify(value));
  } catch {
    /* Trình duyệt chặn lưu thì lịch vẫn chạy trong phiên này. */
  }
}

function amountFor(minutes, unit) {
  if (unit === "hour") return String(Math.min(24, Math.max(1, Math.round(minutes / 60))));
  return String(clampAutoMinutes(minutes));
}

function commitAutoInterval(amount, unit) {
  const nextUnit = unit === "hour" ? "hour" : "minute";
  const raw = Math.round(Number(amount));
  if (nextUnit === "hour") {
    const hours = Math.min(24, Math.max(1, Number.isFinite(raw) ? raw : 1));
    return { amount: String(hours), unit: nextUnit, minutes: hours * 60 };
  }
  const minutes = clampAutoMinutes(Number.isFinite(raw) ? raw : 60);
  return { amount: String(minutes), unit: nextUnit, minutes };
}

function formatNextRun(ts) {
  const target = new Date(ts);
  const time = new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    hour: "2-digit",
    minute: "2-digit",
  }).format(target);
  const day = (date) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(date);
  if (day(new Date()) === day(target)) return time;
  const date = new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    day: "2-digit",
    month: "2-digit",
  }).format(target);
  return `${time} ${date}`;
}

const FILTER_GROUPS = [
  {
    id: "overview",
    label: "Tổng quan",
    items: [
      ["all", "Tất cả"],
      ["ready", "Sẵn sàng"],
      ["has_short", "Có link"],
      ["has_image", "Có ảnh"],
      ["has_video", "Có video"],
    ],
  },
  {
    id: "missing",
    label: "Còn thiếu",
    items: [
      ["no_short", "Link"],
      ["no_image", "Ảnh"],
      ["no_video", "Video"],
      ["no_source", "Không video"],
    ],
  },
  {
    id: "publish",
    label: "Đăng",
    items: [
      ["unposted", "Chưa đăng"],
      ["scheduled", "Đã hẹn"],
      ["posted", "Đã đăng"],
    ],
  },
];

function matches(product, filter, query) {
  if (query) {
    const blob = `${product.name} ${product.shop_name} ${product.category_name || ""} ${product.item_id} ${product.shop_id} ${product.short_link}`.toLowerCase();
    if (!blob.includes(query)) return false;
  }
  if (filter === "ready") return product.ready;
  if (filter === "no_short") return !product.short_link;
  if (filter === "has_short") return Boolean(product.short_link);
  if (filter === "no_image") return !product.image_file;
  if (filter === "has_image") return Boolean(product.image_file);
  if (filter === "no_video") return product.video_state === "missing";
  if (filter === "has_video") return product.video_state === "ready";
  if (filter === "no_source") return product.video_state === "none";
  if (filter === "posted") return product.facebook_status === "published";
  if (filter === "scheduled") return product.facebook_status === "scheduled";
  if (filter === "unposted") return !product.facebook_video_id;
  return true;
}

function postedOn(product, platform, pageId) {
  if (!pageId) return false;
  const pubs = product.publications || [];
  if (pubs.some((pub) => pub.platform === platform && pub.page_id === pageId && (pub.video_id || pub.status === "published" || pub.status === "scheduled"))) {
    return true;
  }
  return platform === "facebook" && product.facebook_page_id === pageId && Boolean(product.facebook_video_id);
}

function canPost(product, platform, pageId, posting) {
  return Boolean(posting) && Boolean(pageId) && Boolean(product.video_file)
    && Boolean(product.short_link || product.has_long_link)
    && !postedOn(product, platform, pageId);
}

function facebookLabel(product) {
  if (product.facebook_status === "published") return ["ok", "Đã đăng"];
  if (product.facebook_status === "scheduled") return ["wait", "Đã hẹn giờ"];
  if (product.facebook_status === "processing") return ["wait", "Đang xử lý"];
  if (product.facebook_status === "error") return ["wait", "Lỗi Facebook"];
  if (product.facebook_video_id) return ["wait", "Chưa kiểm tra"];
  return ["none", "Chưa đăng"];
}

function labelFor(product, platform, pageId) {
  const pub = (product.publications || []).find((item) => item.platform === platform && item.page_id === pageId);
  if (pub) return facebookLabel({ facebook_status: pub.status, facebook_video_id: pub.video_id });
  if (platform === "facebook" && product.facebook_page_id === pageId) return facebookLabel(product);
  const count = (product.publications || []).length;
  if (count) return ["wait", `${count} kênh khác`];
  return ["none", "Chưa đăng"];
}

function videoLabel(state) {
  if (state === "ready") return ["ok", "Đã tải"];
  if (state === "missing") return ["wait", "Chưa tải"];
  return ["none", "Không có video"];
}

const VIDEO_ORDER = { none: 0, missing: 1, ready: 2 };
const CHANNEL_ORDER = {
  "Chưa đăng": 0,
  "Chưa kiểm tra": 1,
  "Lỗi Facebook": 2,
  "Đang xử lý": 3,
  "Đã hẹn giờ": 4,
  "Đã đăng": 5,
};

function channelRank(product, platformId, pageId) {
  const [, text] = labelFor(product, platformId, pageId);
  if (Object.prototype.hasOwnProperty.call(CHANNEL_ORDER, text)) return CHANNEL_ORDER[text];
  if (String(text).includes("kênh")) return 1;
  return 0;
}

function compareProducts(a, b, key, platformId, pageId) {
  if (key === "name") return (a.name || "").localeCompare(b.name || "", "vi", { sensitivity: "base", numeric: true });
  if (key === "price") return (Number(a.price) || 0) - (Number(b.price) || 0);
  if (key === "image") return (a.image_file ? 1 : 0) - (b.image_file ? 1 : 0);
  if (key === "link") {
    const rank = (item) => (item.short_link ? 2 : item.has_long_link ? 1 : 0);
    const byRank = rank(a) - rank(b);
    if (byRank) return byRank;
    return (a.short_link || "").localeCompare(b.short_link || "", "vi");
  }
  if (key === "video") return (VIDEO_ORDER[a.video_state] ?? 0) - (VIDEO_ORDER[b.video_state] ?? 0);
  if (key === "channel") return channelRank(a, platformId, pageId) - channelRank(b, platformId, pageId);
  return 0;
}

export default function App() {
  const [session, setSession] = useState(null);
  const [booting, setBooting] = useState(true);
  const [loginUser, setLoginUser] = useState("");
  const [loginPass, setLoginPass] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [board, setBoard] = useState(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [category, setCategory] = useState("all");
  const [sort, setSort] = useState({ key: "", dir: "asc" });
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState("");
  const [toast, setToast] = useState("");
  const [busy, setBusy] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState("");
  const [linkNote, setLinkNote] = useState("");
  const savedAuto = useRef(null);
  const [autoOn, setAutoOn] = useState(false);
  const [autoAmount, setAutoAmount] = useState("60");
  const [autoUnit, setAutoUnit] = useState("minute");
  const [autoEvery, setAutoEvery] = useState(60);
  const [autoNextAt, setAutoNextAt] = useState(0);
  const refreshCatalogRef = useRef(null);
  const refreshingRef = useRef(false);
  const autoOnRef = useRef(autoOn);
  const autoEveryRef = useRef(autoEvery);
  const [chosen, setChosen] = useState([]);
  const [scheduleAt, setScheduleAt] = useState("");
  const [report, setReport] = useState([]);
  const [networks, setNetworks] = useState([]);
  const [platformId, setPlatformId] = useState("facebook");
  const [pageId, setPageId] = useState("");
  const [view, setView] = useState("products");
  const [secrets, setSecrets] = useState({
    app_id: "",
    app_secret: "",
    api_version: "v25.0",
    has_app_secret: false,
    sheet_url: "",
    sheet_token: "",
    sheet_tab: "",
    has_sheet_token: false,
  });
  const [secretsBusy, setSecretsBusy] = useState(false);
  const [accountUsers, setAccountUsers] = useState([]);
  const [newUser, setNewUser] = useState({ username: "", password: "", role: "user" });
  const [pwdForm, setPwdForm] = useState({ current: "", next: "" });

  function applyAutoSettings(username) {
    const saved = readAutoRefresh(username);
    savedAuto.current = saved;
    setAutoOn(saved.enabled);
    setAutoAmount(amountFor(saved.minutes, saved.unit));
    setAutoUnit(saved.unit);
    setAutoEvery(saved.minutes);
    setAutoNextAt(saved.enabled ? saved.nextAt : 0);
  }

  async function load(keepId = selectedId) {
    const data = await fetchBoard();
    setBoard(data);
    setError("");
    if (keepId && !data.products.some((item) => item.item_id === keepId)) {
      setSelectedId("");
    }
    return data;
  }

  async function loadConfigPanels(user) {
    try {
      const data = await fetchConfig();
      const facebook = data.config?.facebook || {};
      const sheet = data.config?.sheet || {};
      setSecrets({
        app_id: facebook.app_id || "",
        app_secret: "",
        api_version: facebook.api_version || "v25.0",
        has_app_secret: Boolean(facebook.has_app_secret),
        sheet_url: sheet.url || "",
        sheet_token: "",
        sheet_tab: sheet.tab || "",
        has_sheet_token: Boolean(sheet.has_token),
      });
    } catch (err) {
      setToast(err.message || String(err));
    }
    if (user?.role === "admin") {
      try {
        const data = await fetchUsers();
        setAccountUsers(data.users || []);
      } catch {
        setAccountUsers([]);
      }
    } else {
      setAccountUsers([]);
    }
  }

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setSession(null);
      setBoard(null);
      setNetworks([]);
      setError("");
    });
    fetchMe()
      .then((data) => {
        if (data.authenticated) {
          const user = { username: data.username, role: data.role };
          setSession(user);
          applyAutoSettings(user.username);
        }
      })
      .catch(() => setSession(null))
      .finally(() => setBooting(false));
  }, []);

  useEffect(() => {
    if (!session) return undefined;
    load("").catch((err) => setError(err.message || String(err)));
    fetchNetworks()
      .then((data) => setNetworks(data.platforms || []))
      .catch((err) => setError(err.message || String(err)));
    loadConfigPanels(session);
    return undefined;
  }, [session?.username]);

  const platform = networks.find((item) => item.id === platformId) || networks[0];
  useEffect(() => {
    if (!platform) return;
    const enabled = (platform.pages || []).filter((page) => page.enabled);
    const current = (platform.pages || []).some((page) => page.id === pageId);
    if (!current) setPageId((enabled[0] || platform.pages?.[0] || {}).id || "");
  }, [platform, pageId]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(""), 3200);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    refreshingRef.current = refreshing;
  }, [refreshing]);

  useEffect(() => {
    autoOnRef.current = autoOn;
  }, [autoOn]);

  useEffect(() => {
    autoEveryRef.current = autoEvery;
  }, [autoEvery]);

  useEffect(() => {
    if (!session) return undefined;
    const username = session.username;
    if (!autoOn) {
      writeAutoRefresh(username, { enabled: false, minutes: autoEvery, unit: autoUnit, nextAt: 0 });
      setAutoNextAt(0);
      return undefined;
    }
    let stop = false;
    let timer = 0;
    const minutes = clampAutoMinutes(autoEvery);

    function arm(delay) {
      const at = Date.now() + delay;
      setAutoNextAt(at);
      writeAutoRefresh(username, { enabled: true, minutes: clampAutoMinutes(autoEveryRef.current), unit: autoUnit, nextAt: at });
      timer = window.setTimeout(fire, delay);
    }

    async function fire() {
      if (stop || !autoOnRef.current) return;
      if (refreshingRef.current) {
        timer = window.setTimeout(fire, 15000);
        return;
      }
      arm(clampAutoMinutes(autoEveryRef.current) * 60 * 1000);
      await refreshCatalogRef.current?.();
    }

    const saved = readAutoRefresh(username);
    let delay = minutes * 60 * 1000;
    if (saved.enabled && saved.minutes === minutes && saved.nextAt) {
      delay = saved.nextAt > Date.now() + 500 ? saved.nextAt - Date.now() : 2000;
    }
    arm(delay);
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, [session?.username, autoOn, autoEvery, autoUnit]);

  useEffect(() => {
    if (!refreshing) return undefined;
    let stop = false;
    let sinceBoard = 0;
    const timer = setInterval(async () => {
      try {
        const state = await catalogRefreshStatus();
        if (stop) return;
        setRefreshNote(state.message || "");
        sinceBoard += 2000;
        if (state.status === "running" && sinceBoard >= 8000) {
          sinceBoard = 0;
          try {
            await load(selectedId);
          } catch {
            /* Danh sách đang ghi. Lần hỏi sau sẽ tải lại ảnh. */
          }
        }
        if (state.status === "done" || state.status === "error") {
          refreshingRef.current = false;
          setRefreshing(false);
          await load(selectedId);
          showToast(state.message || (state.status === "done" ? "Đã cập nhật danh sách" : "Không cập nhật được danh sách"));
        }
      } catch {
        /* Mất một nhịp kết nối thì hỏi lại, không hủy lượt cập nhật. */
      }
    }, 2000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, [refreshing]);

  useEffect(() => {
    shortLinkStatus().then((state) => {
      if (state.status === "running") {
        setBusy("links");
        setLinkNote(state.message || "");
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (busy !== "links") return undefined;
    let stop = false;
    let sinceBoard = 0;
    const timer = setInterval(async () => {
      try {
        const state = await shortLinkStatus();
        if (stop) return;
        setLinkNote(state.message || "");
        sinceBoard += 2000;
        if (state.status === "running" && sinceBoard >= 8000) {
          sinceBoard = 0;
          try {
            await load(selectedId);
          } catch {
            /* Danh sách đang ghi. Lần hỏi sau sẽ tải lại. */
          }
        }
        if (state.status === "done" || state.status === "error") {
          stop = true;
          clearInterval(timer);
          setBusy("");
          await load(selectedId);
          showToast(state.message || (state.status === "done" ? "Đã tạo link rút gọn" : "Không tạo được link rút gọn"));
        }
      } catch {
        /* Mất một nhịp kết nối thì hỏi lại. */
      }
    }, 2000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, [busy]);

  const products = board?.products || [];
  const categories = useMemo(() => {
    if (Array.isArray(board?.categories) && board.categories.length) return board.categories;
    const names = [];
    for (const item of products) {
      const name = item.category_name || "";
      if (name && !names.includes(name)) names.push(name);
    }
    return names;
  }, [board, products]);
  const selected = products.find((item) => item.item_id === selectedId) || null;
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = products.filter((item) => {
      if (category !== "all" && (item.category_name || "Chưa phân loại") !== category) return false;
      return matches(item, filter, q);
    });
    const copy = [...list];
    if (sort.key) {
      copy.sort((a, b) => {
        const result = compareProducts(a, b, sort.key, platform?.id, pageId);
        return sort.dir === "desc" ? -result : result;
      });
    }
    return copy;
  }, [products, filter, category, query, sort, platform?.id, pageId]);

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pages);
  const start = (safePage - 1) * PAGE_SIZE;
  const slice = filtered.slice(start, start + PAGE_SIZE);
  const postedHere = (item) => postedOn(item, platform?.id, pageId);
  const canPostHere = (item) => canPost(item, platform?.id, pageId, platform?.posting);
  const selectableIds = slice.filter((item) => !postedHere(item)).map((item) => item.item_id);
  const allOnPage = selectableIds.length > 0 && selectableIds.every((id) => chosen.includes(id));
  const picked = products.filter((item) => chosen.includes(item.item_id));
  const postableCount = picked.filter(canPostHere).length;
  const duplicateCount = picked.filter(postedHere).length;
  const activePage = (platform?.pages || []).find((item) => item.id === pageId);

  const narrowed = Boolean(query.trim()) || filter !== "all" || category !== "all";
  const filterCounts = useMemo(() => {
    const q = query.trim().toLowerCase();
    const scoped = products.filter((item) => {
      if (category !== "all" && (item.category_name || "Chưa phân loại") !== category) return false;
      return matches(item, "all", q);
    });
    const counts = { all: scoped.length };
    for (const group of FILTER_GROUPS) {
      for (const [id] of group.items) {
        if (id === "all") continue;
        counts[id] = scoped.filter((item) => matches(item, id, "")).length;
      }
    }
    return counts;
  }, [products, category, query]);

  function applyAutoInterval(amount, unit) {
    const next = commitAutoInterval(amount, unit);
    setAutoAmount(next.amount);
    setAutoUnit(next.unit);
    setAutoEvery(next.minutes);
    return next;
  }

  function onAutoUnit(unit) {
    const current = commitAutoInterval(autoAmount, autoUnit);
    const next = commitAutoInterval(unit === "hour" ? Math.max(1, Math.round(current.minutes / 60)) : current.minutes, unit);
    setAutoAmount(next.amount);
    setAutoUnit(next.unit);
    setAutoEvery(next.minutes);
  }

  function toggleAuto() {
    const next = applyAutoInterval(autoAmount, autoUnit);
    setAutoOn((on) => {
      if (!on) setAutoNextAt(Date.now() + next.minutes * 60 * 1000);
      return !on;
    });
  }

  async function onRefreshCatalog() {
    if (refreshingRef.current) return;
    refreshingRef.current = true;
    const scope = category === "all" ? "*" : category;
    const scopeLabel = category === "all" ? "mọi mục" : `mục ${category}`;
    setRefreshing(true);
    setRefreshNote(`Đang chuẩn bị cập nhật ${scopeLabel}...`);
    try {
      const state = await startCatalogRefresh(scope);
      setRefreshNote(state.message || "");
      if (state.queued_name) showToast(state.message || `Xong lượt này sẽ cập nhật ${state.queued_name}.`);
      if (state.status === "done" || state.status === "error") {
        refreshingRef.current = false;
        setRefreshing(false);
        await load(selectedId);
        showToast(state.message || "Đã cập nhật danh sách");
      }
    } catch (err) {
      refreshingRef.current = false;
      setRefreshing(false);
      const text = err.message === "Failed to fetch"
        ? "Máy chủ đang bận ghi danh sách. Hãy bấm Cập nhật danh sách lại."
        : (err.message || String(err));
      showToast(text);
    }
  }
  refreshCatalogRef.current = onRefreshCatalog;

  function showToast(text) {
    setToast(text);
  }

  async function onLogin(event) {
    event.preventDefault();
    setLoginBusy(true);
    setLoginError("");
    try {
      const data = await login(loginUser.trim(), loginPass);
      const user = { username: data.username, role: data.role };
      setSession(user);
      applyAutoSettings(user.username);
      setLoginPass("");
    } catch (err) {
      setLoginError(err.message || String(err));
    } finally {
      setLoginBusy(false);
    }
  }

  async function onLogout() {
    try {
      await logout();
    } catch {
      /* Phiên hết hạn vẫn thoát giao diện. */
    }
    setSession(null);
    setBoard(null);
    setNetworks([]);
    setView("products");
  }

  async function onSaveSecrets(event) {
    event.preventDefault();
    setSecretsBusy(true);
    try {
      const payload = {
        facebook: {
          app_id: secrets.app_id,
          api_version: secrets.api_version,
        },
        sheet: {
          url: secrets.sheet_url,
          tab: secrets.sheet_tab,
        },
      };
      if (secrets.app_secret.trim()) payload.facebook.app_secret = secrets.app_secret.trim();
      if (secrets.sheet_token.trim()) payload.sheet.token = secrets.sheet_token.trim();
      await saveConfig(payload);
      await loadConfigPanels(session);
      showToast("Đã lưu cấu hình riêng của tài khoản");
    } catch (err) {
      showToast(err.message || String(err));
    } finally {
      setSecretsBusy(false);
    }
  }

  async function onCreateUser(event) {
    event.preventDefault();
    try {
      const data = await createUser(newUser.username.trim(), newUser.password, newUser.role);
      setAccountUsers(data.users || []);
      setNewUser({ username: "", password: "", role: "user" });
      showToast(`Đã tạo tài khoản ${data.user?.username}`);
    } catch (err) {
      showToast(err.message || String(err));
    }
  }

  async function onDeleteUser(username) {
    if (!window.confirm(`Xóa tài khoản ${username}? Workspace dữ liệu vẫn giữ trên đĩa.`)) return;
    try {
      const data = await deleteUser(username);
      setAccountUsers(data.users || []);
      showToast(`Đã xóa tài khoản ${username}`);
    } catch (err) {
      showToast(err.message || String(err));
    }
  }

  async function onChangePassword(event) {
    event.preventDefault();
    try {
      await changePassword(pwdForm.current, pwdForm.next);
      setPwdForm({ current: "", next: "" });
      showToast("Đã đổi mật khẩu");
    } catch (err) {
      showToast(err.message || String(err));
    }
  }

  function clearFilters() {
    setQuery("");
    setFilter("all");
    setCategory("all");
    setPage(1);
  }

  function toggleSort(key) {
    setSort((current) => {
      if (current.key !== key) return { key, dir: "asc" };
      if (current.dir === "asc") return { key, dir: "desc" };
      return { key: "", dir: "asc" };
    });
    setPage(1);
  }

  async function onSaveLink(itemId, value) {
    setBusy(itemId);
    try {
      await saveShortLink(itemId, value);
      await load(itemId);
      showToast(value.trim() ? "Đã lưu link hoa hồng" : "Đã xóa link hoa hồng");
    } catch (err) {
      showToast(err.message || String(err));
    } finally {
      setBusy("");
    }
  }

  async function onCheck(itemId) {
    setBusy(itemId || "all");
    try {
      const result = await checkFacebook(itemId);
      await load(itemId || selectedId);
      const count = (result.checked || []).length;
      showToast(`Đã kiểm tra ${count} bài Facebook`);
    } catch (err) {
      showToast(err.message || String(err));
    } finally {
      setBusy("");
    }
  }

  function toggleChosen(itemId) {
    const product = products.find((item) => item.item_id === itemId);
    if (product && postedHere(product)) return;
    setChosen((current) => (
      current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]
    ));
  }

  function togglePage(ids) {
    setChosen((current) => {
      const allOn = ids.length > 0 && ids.every((id) => current.includes(id));
      if (allOn) return current.filter((id) => !ids.includes(id));
      return [...new Set([...current, ...ids])];
    });
  }

  async function onPost(mode) {
    const pickedNow = products.filter((item) => chosen.includes(item.item_id));
    const duplicates = pickedNow.filter(postedHere);
    const postable = pickedNow.filter(canPostHere);
    if (!postable.length) {
      showToast("Các dòng đã chọn thiếu video, thiếu link, hoặc đã có bài đăng");
      return;
    }
    if (postable.length > 20) {
      showToast("Mỗi lần đăng tối đa 20 sản phẩm");
      return;
    }
    const when = mode === "now"
      ? "đăng ngay, caption có tag tìm kiếm, không kèm link; bình luận kèm ảnh và link"
      : `hẹn giờ ${scheduleAt.replace("T", " ")}, caption có tag, không kèm link; ảnh kèm link được bình luận khi bài lên`;
    const skipNote = duplicates.length ? ` Bỏ qua ${duplicates.length} bài đã đăng.` : "";
    const targetName = activePage?.name || "trang đã chọn";
    if (!window.confirm(`Gửi ${postable.length} sản phẩm lên ${platform?.label || ""} / ${targetName}: ${when}?${skipNote}`)) return;
    setBusy("post");
    try {
      const result = await postProducts(postable.map((item) => item.item_id), mode, scheduleAt, platform.id, pageId);
      const rows = result.results || [];
      await load(selectedId);
      const okIds = rows.filter((row) => row.ok).map((row) => row.item_id);
      setChosen((current) => current.filter((id) => !okIds.includes(id)));
      setReport(rows);
      const ok = okIds.length;
      const dup = rows.filter((row) => row.duplicate).length;
      const bad = rows.length - ok - dup;
      const parts = [`Đã gửi ${ok} bài`];
      if (dup) parts.push(`${dup} bài đã đăng nên bỏ qua`);
      if (bad) parts.push(`${bad} dòng lỗi`);
      showToast(parts.join(", "));
    } catch (err) {
      showToast(err.message || String(err));
    } finally {
      setBusy("");
    }
  }

  async function onExportLinks() {
    setBusy("export");
    try {
      const count = await downloadMissingShortLinks();
      showToast(count ? `Đã tải Excel với ${count} link gốc` : "Đã tải file Excel");
    } catch (err) {
      showToast(err.message || String(err));
    } finally {
      setBusy("");
    }
  }

  async function onImportLinks(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy("import");
    try {
      const result = await importShortLinks(file);
      await load(selectedId);
      const parts = [`Đã gán ${result.updated} link rút gọn`];
      if (result.failed) parts.push(`${result.failed} dòng lỗi`);
      if (result.unmatched) parts.push(`${result.unmatched} link không khớp sản phẩm`);
      if (result.skipped_existing) parts.push(`${result.skipped_existing} sản phẩm đã có link`);
      showToast(parts.join(". "));
    } catch (err) {
      showToast(err.message || String(err));
    } finally {
      setBusy("");
    }
  }

  async function onGenerateLinks() {
    setBusy("links");
    setLinkNote("Đang mở trang Custom Link");
    try {
      const state = await startShortLinks();
      setLinkNote(state.message || "");
      if (state.status === "done" || state.status === "error") {
        setBusy("");
        await load(selectedId);
        showToast(state.message || "Đã tạo link rút gọn");
      }
    } catch (err) {
      setBusy("");
      setLinkNote("");
      showToast(err.message || String(err));
    }
  }

  async function copyLink(url) {
    try {
      await navigator.clipboard.writeText(url);
      showToast("Đã sao chép link");
    } catch {
      showToast("Trình duyệt không cho sao chép");
    }
  }

  const autoStatus = autoOn
    ? (autoNextAt > Date.now() ? `Tự cập nhật đang bật · lần tới ${formatNextRun(autoNextAt)}` : "Tự cập nhật đang bật · sắp chạy")
    : "Tự cập nhật đang tắt";

  if (booting) {
    return (
      <div className="login-page">
        <div className="login-card">
          <h1>Shopee <span>→</span> MXH</h1>
          <p className="meta">Đang mở phiên làm việc...</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="login-page">
        <form className="login-card" onSubmit={onLogin}>
          <h1>Shopee <span>→</span> MXH</h1>
          <p className="meta">Đăng nhập để vào kho video và cấu hình riêng của bạn.</p>
          <label>
            <span>Tên đăng nhập</span>
            <input
              value={loginUser}
              onChange={(event) => setLoginUser(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            <span>Mật khẩu</span>
            <input
              type="password"
              value={loginPass}
              onChange={(event) => setLoginPass(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {loginError ? <p className="banner">{loginError}</p> : null}
          <button type="submit" disabled={loginBusy}>{loginBusy ? "Đang đăng nhập..." : "Đăng nhập"}</button>
        </form>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <h1>Shopee <span>→</span> MXH</h1>
          <p className="sub">
            {board ? (board.updated_at || "Danh sách chưa có mốc") : error ? "Danh sách chưa tải được" : "Đang tải danh sách..."}
            {board?.facebook_checked_at ? ` · FB ${board.facebook_checked_at}` : ""}
            {refreshing ? ` · ${refreshNote || "Đang cập nhật danh sách"}` : ""}
          </p>
        </div>
        <nav className="view-switch" aria-label="Màn hình">
          <button type="button" className={view === "products" ? "on" : ""} aria-current={view === "products" ? "page" : undefined} onClick={() => setView("products")}>
            Sản phẩm
          </button>
          <button type="button" className={view === "groups" ? "on" : ""} aria-current={view === "groups" ? "page" : undefined} onClick={() => setView("groups")}>
            Nhóm
          </button>
          <button type="button" className={view === "config" ? "on" : ""} aria-current={view === "config" ? "page" : undefined} onClick={() => setView("config")}>
            Cấu hình
          </button>
        </nav>
        <div className="user-chip">
          <span title={session.role === "admin" ? "Quản trị viên" : "Người dùng"}>{session.username}</span>
          <button type="button" className="ghost" onClick={onLogout}>Thoát</button>
        </div>
      </header>

      {view === "groups" ? <Groups /> : null}

      {view === "config" ? (
        <div className="config-page">
          <section className="config-card">
            <h2>Kênh đăng</h2>
            <p className="meta">Token Page/kênh chỉ thuộc tài khoản {session.username}. Người khác không thấy và không dùng chung.</p>
            <Channels
              manage
              networks={networks}
              platformId={platform?.id || "facebook"}
              pageId={pageId}
              onPlatform={(id) => { setPlatformId(id); setChosen([]); setReport([]); }}
              onPage={(id) => { setPageId(id); setChosen([]); setReport([]); }}
              onChanged={() => fetchNetworks().then((data) => setNetworks(data.platforms || [])).catch((err) => showToast(err.message))}
              onToast={showToast}
            />
          </section>

          <section className="config-card">
            <h2>API &amp; khóa riêng</h2>
            <p className="meta">App Facebook và token Sheet lưu trong workspace của bạn. Để trống ô mật khẩu/token nếu không muốn đổi.</p>
            <form className="secrets-form" onSubmit={onSaveSecrets}>
              <label>
                <span>Facebook App ID</span>
                <input value={secrets.app_id} onChange={(event) => setSecrets((prev) => ({ ...prev, app_id: event.target.value }))} />
              </label>
              <label>
                <span>Facebook App Secret {secrets.has_app_secret ? "(đã có)" : ""}</span>
                <input
                  type="password"
                  autoComplete="off"
                  placeholder={secrets.has_app_secret ? "••••••••" : ""}
                  value={secrets.app_secret}
                  onChange={(event) => setSecrets((prev) => ({ ...prev, app_secret: event.target.value }))}
                />
              </label>
              <label>
                <span>API version</span>
                <input value={secrets.api_version} onChange={(event) => setSecrets((prev) => ({ ...prev, api_version: event.target.value }))} />
              </label>
              <label>
                <span>Sheet URL</span>
                <input value={secrets.sheet_url} onChange={(event) => setSecrets((prev) => ({ ...prev, sheet_url: event.target.value }))} />
              </label>
              <label>
                <span>Sheet token {secrets.has_sheet_token ? "(đã có)" : ""}</span>
                <input
                  type="password"
                  autoComplete="off"
                  placeholder={secrets.has_sheet_token ? "••••••••" : ""}
                  value={secrets.sheet_token}
                  onChange={(event) => setSecrets((prev) => ({ ...prev, sheet_token: event.target.value }))}
                />
              </label>
              <label>
                <span>Sheet tab</span>
                <input value={secrets.sheet_tab} onChange={(event) => setSecrets((prev) => ({ ...prev, sheet_tab: event.target.value }))} />
              </label>
              <button type="submit" disabled={secretsBusy}>{secretsBusy ? "Đang lưu..." : "Lưu khóa riêng"}</button>
            </form>
          </section>

          <section className="config-card">
            <h2>Tài khoản đăng nhập</h2>
            <p className="meta">Đổi mật khẩu của bạn. Cookie Facebook / Shopee vẫn nằm trong workspace riêng.</p>
            <form className="secrets-form compact" onSubmit={onChangePassword}>
              <label>
                <span>Mật khẩu hiện tại</span>
                <input type="password" value={pwdForm.current} onChange={(event) => setPwdForm((prev) => ({ ...prev, current: event.target.value }))} required />
              </label>
              <label>
                <span>Mật khẩu mới</span>
                <input type="password" value={pwdForm.next} onChange={(event) => setPwdForm((prev) => ({ ...prev, next: event.target.value }))} required minLength={4} />
              </label>
              <button type="submit">Đổi mật khẩu</button>
            </form>
            {session.role === "admin" ? (
              <>
                <p className="meta config-note">Admin tạo tài khoản mới — mỗi người có kho video và cấu hình riêng.</p>
                <form className="secrets-form compact" onSubmit={onCreateUser}>
                  <label>
                    <span>Tên đăng nhập</span>
                    <input value={newUser.username} onChange={(event) => setNewUser((prev) => ({ ...prev, username: event.target.value }))} required />
                  </label>
                  <label>
                    <span>Mật khẩu</span>
                    <input type="password" value={newUser.password} onChange={(event) => setNewUser((prev) => ({ ...prev, password: event.target.value }))} required minLength={4} />
                  </label>
                  <label>
                    <span>Vai trò</span>
                    <select value={newUser.role} onChange={(event) => setNewUser((prev) => ({ ...prev, role: event.target.value }))}>
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </label>
                  <button type="submit">Thêm tài khoản</button>
                </form>
                <ul className="account-list">
                  {accountUsers.map((item) => (
                    <li key={item.username}>
                      <div>
                        <b>{item.username}</b>
                        <span className="meta"> · {item.role}{item.created_at ? ` · ${item.created_at}` : ""}</span>
                      </div>
                      {item.username !== session.username ? (
                        <button type="button" className="ghost" onClick={() => onDeleteUser(item.username)}>Xóa</button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </section>

          <section className="config-card">
            <h2>Tự cập nhật danh sách</h2>
            <p className="meta">Tự lấy sản phẩm mới theo mục đang chọn ở màn Sản phẩm. Khoảng cách từ 5 phút đến 24 giờ.</p>
            <div className="toolbar config-row">
              <div className="auto-refresh">
                <label className="select-field">
                  <span>
                    {autoOn && autoNextAt > Date.now()
                      ? `Lần tới ${formatNextRun(autoNextAt)}`
                      : autoOn
                        ? "Sắp cập nhật"
                        : "Tự động"}
                  </span>
                  <span className="auto-refresh-controls">
                    <input
                      type="number"
                      min={autoUnit === "hour" ? 1 : MIN_AUTO_MINUTES}
                      max={autoUnit === "hour" ? 24 : MAX_AUTO_MINUTES}
                      step="1"
                      inputMode="numeric"
                      aria-label="Khoảng thời gian tự động cập nhật danh sách"
                      title="Tự lấy sản phẩm mới theo mục đang chọn"
                      value={autoAmount}
                      onChange={(event) => setAutoAmount(event.target.value)}
                      onBlur={() => applyAutoInterval(autoAmount, autoUnit)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") event.currentTarget.blur();
                      }}
                    />
                    <select
                      value={autoUnit}
                      aria-label="Đơn vị thời gian"
                      onChange={(event) => onAutoUnit(event.target.value)}
                    >
                      <option value="minute">phút</option>
                      <option value="hour">giờ</option>
                    </select>
                  </span>
                </label>
                <button
                  type="button"
                  className={autoOn ? "refresh-btn on" : "ghost refresh-btn"}
                  aria-pressed={autoOn}
                  title={autoOn ? "Tắt tự động cập nhật danh sách" : "Bật tự động cập nhật danh sách theo khoảng thời gian đã nhập"}
                  onClick={toggleAuto}
                >
                  {autoOn ? "Tắt" : "Bật"}
                </button>
              </div>
            </div>
            <p className="meta config-note">{autoStatus}</p>
          </section>

          <section className="config-card">
            <h2>Danh sách sản phẩm</h2>
            <p className="meta">Lấy sản phẩm mới từ Shopee, rồi kiểm tra bài đã đăng trên trang đang chọn.</p>
            <div className="config-actions">
              <button type="button" className="ghost refresh-btn" disabled={refreshing} onClick={onRefreshCatalog}>
                {refreshing ? (refreshNote || "Đang cập nhật...") : "Cập nhật danh sách"}
              </button>
              <button className="ghost" type="button" disabled={busy === "all"} onClick={() => onCheck("")}>
                {busy === "all" ? "Đang kiểm tra..." : "Kiểm tra bài"}
              </button>
              <button type="button" className="ghost" onClick={() => load(selectedId).catch((err) => setError(err.message))}>
                Tải lại
              </button>
            </div>
          </section>

          <section className="config-card">
            <h2>Link rút gọn</h2>
            <p className="meta">Tạo link trên Shopee, xuất Excel những sản phẩm còn thiếu, hoặc nhập CSV kết quả để gán link.</p>
            <div className="config-actions">
              <button
                type="button"
                className="ghost"
                title="Lấy link rút gọn trên trang Custom Link của Shopee cho sản phẩm còn thiếu"
                disabled={!board || busy === "links" || (board.stats.total - board.stats.short_link) <= 0}
                onClick={onGenerateLinks}
              >
                {busy === "links"
                  ? (linkNote || "Đang tạo link...")
                  : `Tạo link rút gọn (${Math.max(0, (board?.stats?.total || 0) - (board?.stats?.short_link || 0))})`}
              </button>
              <button
                type="button"
                className="ghost"
                title="Xuất sản phẩm chưa có link rút gọn. Tải file lên Custom Link của Shopee."
                disabled={!board || busy === "export" || (board.stats.total - board.stats.short_link) <= 0}
                onClick={onExportLinks}
              >
                {busy === "export" ? "Đang xuất..." : `Xuất Excel (${Math.max(0, (board?.stats?.total || 0) - (board?.stats?.short_link || 0))})`}
              </button>
              <label className={busy === "import" ? "file-btn off" : "file-btn"} title="Nhập CSV kết quả từ Shopee để gán link rút gọn">
                {busy === "import" ? "Đang nhập..." : "Nhập CSV"}
                <input type="file" accept=".csv,text/csv" disabled={busy === "import"} onChange={onImportLinks} />
              </label>
            </div>
          </section>

          <section className="config-card">
            <h2>Tự động đăng</h2>
            <p className="meta">Xếp bài sẵn sàng lên trang đang chọn, theo số bài mỗi ngày và các ngày đã chọn.</p>
            <AutoPost
              pageId={pageId}
              pageName={activePage?.name || ""}
              posting={Boolean(platform?.posting)}
              categories={categories}
              readyItems={products.filter(canPostHere).map((item) => item.category_name || "Chưa phân loại")}
              onToast={showToast}
            />
          </section>
        </div>
      ) : null}

      {view === "products" ? (
        <div className="workspace">
          <aside className="controls" aria-label="Lọc dữ liệu">
            <div className="controls-scroll">
            {error ? <p className="banner">{error}</p> : null}

            <section className="control-block">
              <span className="ops-label">Kênh</span>
              <Channels
                networks={networks}
                platformId={platform?.id || "facebook"}
                pageId={pageId}
                onPlatform={(id) => { setPlatformId(id); setChosen([]); setReport([]); }}
                onPage={(id) => { setPageId(id); setChosen([]); setReport([]); }}
                onChanged={() => fetchNetworks().then((data) => setNetworks(data.platforms || [])).catch((err) => showToast(err.message))}
                onToast={showToast}
                onOpenConfig={() => setView("config")}
              />
            </section>

            <section className="control-block">
              <span className="ops-label">Lọc danh sách</span>
              <div className="filter-panel">
                <div className="toolbar">
                  <label className="search-field">
                    <span>Tìm</span>
                    <input
                      type="search"
                      placeholder="Tên, shop, mã, link"
                      value={query}
                      onChange={(event) => {
                        setQuery(event.target.value);
                        setPage(1);
                      }}
                    />
                  </label>
                  <label className="select-field">
                    <span>Mục</span>
                    <select
                      value={category}
                      onChange={(event) => {
                        setCategory(event.target.value);
                        setPage(1);
                      }}
                      aria-label="Mục sản phẩm"
                    >
                      <option value="all">Mọi mục</option>
                      {categories.map((name) => (
                        <option key={name} value={name}>{name}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="status-filters" role="toolbar" aria-label="Lọc trạng thái">
                  {FILTER_GROUPS.map((group) => (
                    <div className="status-group" key={group.id}>
                      <span className="status-label">{group.id === "publish" ? (platform?.label || group.label) : group.label}</span>
                      <div className="status-pills">
                        {group.items.map(([id, label]) => (
                          <button
                            key={id}
                            type="button"
                            className={filter === id ? "on" : ""}
                            aria-pressed={filter === id}
                            onClick={() => {
                              setFilter(id);
                              setPage(1);
                            }}
                          >
                            {label}
                            <span className="count">{board ? (filterCounts[id] ?? 0) : "–"}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                  {narrowed ? (
                    <button type="button" className="ghost clear-filters" onClick={clearFilters}>Xóa lọc</button>
                  ) : null}
                </div>
              </div>
            </section>
            </div>
          </aside>
          <main className="catalog">
        <div className="table-card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    checked={allOnPage}
                    disabled={selectableIds.length === 0}
                    onChange={() => togglePage(selectableIds)}
                    aria-label="Chọn các sản phẩm chưa đăng trên trang này"
                  />
                </th>
                {[
                  ["image", "Ảnh"],
                  ["name", "Sản phẩm"],
                  ["price", "Giá"],
                  ["link", "Link"],
                  ["video", "Video"],
                  ["channel", platform?.label || "Kênh"],
                ].map(([key, label]) => (
                  <th key={key} className="sort" aria-sort={sort.key === key ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
                    <button
                      type="button"
                      className={sort.key === key ? "sort-btn on" : "sort-btn"}
                      title="Bấm để sắp xếp. Bấm lần nữa để đảo chiều. Bấm lần thứ ba để về thứ tự gốc."
                      onClick={() => toggleSort(key)}
                    >
                      {label}
                      <span className="sort-mark" aria-hidden="true">{sort.key === key ? (sort.dir === "asc" ? "↑" : "↓") : "↕"}</span>
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!board && !error ? (
                <tr>
                  <td colSpan={7} className="empty">Đang tải danh sách...</td>
                </tr>
              ) : slice.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty">Không có sản phẩm khớp bộ lọc.</td>
                </tr>
              ) : slice.map((product) => {
                const [videoKind, videoText] = videoLabel(product.video_state);
                const [fbKind, fbText] = labelFor(product, platform?.id, pageId);
                return (
                  <tr
                    key={product.item_id}
                    className={`${product.item_id === selectedId ? "selected" : ""} ${postedHere(product) ? "posted" : ""}`.trim()}
                    onClick={() => setSelectedId(product.item_id)}
                  >
                    <td onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={chosen.includes(product.item_id)}
                        disabled={postedHere(product)}
                        title={postedHere(product) ? "Đã đăng lên trang này, không đăng lại" : "Chọn để đăng"}
                        onChange={() => toggleChosen(product.item_id)}
                        aria-label={`Chọn ${product.item_id}`}
                      />
                    </td>
                    <td>
                      {product.image_file
                        ? <img className="thumb" alt="" src={`/media/${product.image_file}`} />
                        : <div className="ph" />}
                    </td>
                    <td>
                      <div className="name">{product.name}</div>
                      <div className="meta">{product.category_name || "Chưa phân loại"} · {product.shop_name || "Chưa có shop"} · {product.shop_id}_{product.item_id}</div>
                    </td>
                    <td>
                      <div>{product.price_formatted || "–"}</div>
                      <div className="meta">{product.commission_rate || ""}</div>
                    </td>
                    <td>
                      {product.short_link
                        ? <span className="link-text">{product.short_link.replace("https://", "")}</span>
                        : <span className="pill none">{product.has_long_link ? "Chỉ có link dài" : "Chưa có"}</span>}
                    </td>
                    <td><span className={`pill ${videoKind}`}>{videoText}</span></td>
                    <td><span className={`pill ${fbKind}`}>{fbText}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
          <div className="pager">
            <span>{!board && !error ? "Đang tải..." : filtered.length ? `${start + 1}–${Math.min(start + PAGE_SIZE, filtered.length)} / ${filtered.length}` : "0 sản phẩm"}</span>
            <span>
              <button type="button" className="ghost" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}>Trước</button>
              <button type="button" className="ghost" disabled={safePage >= pages} onClick={() => setPage(safePage + 1)}>Sau</button>
            </span>
          </div>
          <section className="table-publish" aria-label="Đăng sản phẩm đã chọn">
            <div className="publish-panel">
              <div className="publish-count">
                <b>{chosen.length ? `${chosen.length} đã chọn` : "Chưa chọn sản phẩm"}</b>
                <span>
                  {chosen.length ? (
                    <>
                      {postableCount} đăng được
                      {duplicateCount ? ` · bỏ ${duplicateCount} bài đã đăng` : ""}
                      {platform?.posting ? ` · ${activePage?.name || "chưa chọn trang"}` : ` · ${platform?.label || "mạng này"} chưa đăng được`}
                    </>
                  ) : (activePage?.name || "Chọn trang và sản phẩm trong bảng")}
                </span>
              </div>
              <label>
                Giờ đăng
                <input type="datetime-local" value={scheduleAt} onChange={(event) => setScheduleAt(event.target.value)} />
              </label>
              <div className="publish-actions">
                <button type="button" disabled={busy === "post" || !platform?.posting || postableCount === 0} onClick={() => onPost("now")}>
                  {busy === "post" ? "Đang đăng..." : "Đăng ngay"}
                </button>
                <button type="button" className="ghost" disabled={busy === "post" || !platform?.posting || postableCount === 0 || !scheduleAt} onClick={() => onPost("schedule")}>
                  Hẹn giờ
                </button>
                <button type="button" className="ghost" disabled={!chosen.length && !report.length} onClick={() => { setChosen([]); setReport([]); }}>Bỏ chọn</button>
              </div>
            </div>
            {report.length ? (
              <details className="report-wrap" open>
                <summary>Kết quả lần đăng gần nhất ({report.length})</summary>
                <ul className="report">
                  {report.map((row) => (
                    <li key={row.item_id}>
                      {row.ok ? "Đã gửi" : row.duplicate ? "Bỏ qua, đã đăng" : "Chưa đăng"} {row.item_id}
                      {row.warning ? ` — ${row.warning}` : ""}
                      {row.error ? ` — ${row.error}` : ""}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </section>
        </div>
        {selected ? (
          <Detail
            product={selected}
            busy={busy === selected.item_id}
            onClose={() => setSelectedId("")}
            onSave={onSaveLink}
            onCheck={onCheck}
            onCopy={copyLink}
          />
        ) : null}
          </main>
        </div>
      ) : null}
      {toast ? <div className="toast" role="status">{toast}</div> : null}
    </div>
  );
}

function Detail({ product, busy, onClose, onSave, onCheck, onCopy }) {
  const [draft, setDraft] = useState(product.short_link || "");
  useEffect(() => {
    setDraft(product.short_link || "");
  }, [product.item_id, product.short_link]);

  const [fbKind, fbText] = labelFor(product, "facebook", product.facebook_page_id);
  const pubs = product.publications || [];

  return (
    <aside className="drawer">
      <div className="drawer-head">
        <h2>Chi tiết</h2>
        <button type="button" className="ghost" onClick={onClose}>Đóng</button>
      </div>
      <div className="preview">
        {product.video_file
          ? <video key={product.video_file} src={`/media/${product.video_file}`} poster={product.image_file ? `/media/${product.image_file}` : undefined} controls />
          : product.image_file
            ? <img alt="" src={`/media/${product.image_file}`} />
            : <div className="ph large" />}
      </div>
      <h3>{product.name}</h3>
      <p className="meta">{product.category_name || "Chưa phân loại"} · {product.shop_name || "Chưa có shop"} · {product.shop_id}_{product.item_id}</p>
      <p className="price">{product.price_formatted || "–"} <span>{product.commission_rate}</span></p>
      <label className="field">
        Link hoa hồng rút gọn
        <input
          type="url"
          value={draft}
          placeholder="https://s.shopee.vn/..."
          onChange={(event) => setDraft(event.target.value)}
        />
      </label>
      <div className="drawer-actions">
        <button type="button" disabled={busy} onClick={() => onSave(product.item_id, draft)}>
          {busy ? "Đang lưu..." : "Lưu link"}
        </button>
        <button type="button" className="ghost" disabled={!draft.trim()} onClick={() => onCopy(draft.trim())}>
          Sao chép
        </button>
      </div>
      {!product.short_link && product.has_long_link
        ? <p className="meta">Sản phẩm này vẫn có link hoa hồng dài. Dán link rút gọn vào ô trên khi bạn tạo được.</p>
        : null}
      <div className="fb-box">
        <div>
          <span className={`pill ${fbKind}`}>{fbText}</span>
          <p className="meta">
            {product.facebook_page_name || "Chưa gắn Page"}
            {product.facebook_scheduled_at ? ` · ${product.facebook_scheduled_at}` : ""}
          </p>
        </div>
        <button type="button" className="ghost" disabled={busy || !product.facebook_video_id} onClick={() => onCheck(product.item_id)}>
          Kiểm tra bài này
        </button>
      </div>
      {pubs.length ? (
        <ul className="pub-list">
          {pubs.map((pub) => (
            <li key={`${pub.platform}-${pub.page_id}`}>
              <b>{pub.page_name || pub.page_id}</b>
              <span>{pub.platform}</span>
              {pub.permalink ? <a href={pub.permalink} target="_blank" rel="noopener">Mở bài</a> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {product.facebook_error ? <p className="meta">{product.facebook_error}</p> : null}
    </aside>
  );
}

function Channels({ networks, platformId, pageId, onPlatform, onPage, onChanged, onToast, manage = false, onOpenConfig }) {
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [token, setToken] = useState("");
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState(false);
  const platform = networks.find((item) => item.id === platformId);
  const pageCount = platform?.pages?.length || 0;

  useEffect(() => {
    if (manage && platform && pageCount === 0) setAdding(true);
  }, [manage, platform, pageCount]);

  async function addPage(event) {
    event.preventDefault();
    setSaving(true);
    try {
      await saveNetworkPage({ platform: platformId, id, name, token, enabled: true });
      setName("");
      setId("");
      setToken("");
      setAdding(false);
      await onChanged();
      onToast("Đã lưu trang");
    } catch (err) {
      onToast(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="channels">
      <div className="channel-bar">
        <div className="platform-tabs">
          {networks.map((item) => (
            <button
              key={item.id}
              type="button"
              className={item.id === platformId ? "on" : "ghost"}
              onClick={() => onPlatform(item.id)}
            >
              {item.label}
              <span>{item.pages.length}</span>
            </button>
          ))}
        </div>
        {platform ? (
          <div className="page-row">
            {pageCount === 0 ? (
              manage
                ? <span className="meta">Chưa có {platform.unit.toLowerCase()}</span>
                : <button type="button" className="ghost" onClick={onOpenConfig}>Thêm {platform.unit.toLowerCase()} ở Cấu hình</button>
            ) : null}
            {(platform.pages || []).map((page) => (
              <button
                key={page.id}
                type="button"
                className={page.id === pageId ? "page-chip on" : "page-chip"}
                title={!page.enabled ? "Đang tắt" : page.has_token ? "Sẵn sàng" : "Chưa có token"}
                onClick={() => onPage(page.id)}
              >
                {page.name}
                {!page.enabled ? " · tắt" : ""}
                {page.has_token ? "" : " · thiếu token"}
              </button>
            ))}
          </div>
        ) : null}
        {manage && platform ? (
          <button type="button" className="ghost" onClick={() => setAdding((open) => !open)}>
            {adding ? "Đóng" : `Thêm ${platform.unit.toLowerCase()}`}
          </button>
        ) : null}
      </div>
      {manage && platform && adding ? (
        <form className="add-page" onSubmit={addPage}>
          <label>
            <span>Tên {platform.unit}</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={platform.id === "facebook" ? "Gia Dụng Việt" : `Tên ${platform.unit.toLowerCase()}`}
              required
            />
          </label>
          <label>
            <span>{platform.id === "facebook" ? "Page ID" : `Mã ${platform.unit.toLowerCase()}`}</span>
            <input
              value={id}
              onChange={(event) => setId(event.target.value)}
              placeholder={platform.id === "facebook" ? "Dãy số của Page" : "Mã tài khoản"}
              required
            />
          </label>
          <label>
            <span>{platform.id === "facebook" ? "Page Access Token" : "Token"}</span>
            <input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder={platform.id === "facebook" ? "Token của đúng Page này" : "Có thể để trống"}
              type="password"
              autoComplete="off"
              required={platform.id === "facebook"}
            />
          </label>
          <button type="submit" disabled={saving}>{saving ? "Đang lưu..." : "Lưu"}</button>
          <p className="add-page-note">
            {platform.id === "facebook"
              ? "Page Gia Dụng Việt đăng được bài vì đã có đủ ba mục: tên hiển thị, Page ID và Page Access Token. Page ID là dãy số trong Graph API Explorer khi gọi me/accounts (trường id). Page Access Token là trường access_token của đúng Page đó, không phải token người dùng. App ID và App Secret không nhập ở đây."
              : `Nhập tên và mã ${platform.unit.toLowerCase()} để hiện trong danh sách. Token có thể để trống vì đăng bài lên ${platform.label} chưa gắn.`}
          </p>
        </form>
      ) : null}
    </section>
  );
}
