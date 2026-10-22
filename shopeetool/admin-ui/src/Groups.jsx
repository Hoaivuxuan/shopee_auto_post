import { useEffect, useRef, useState } from "react";
import {
  draftGroupComment,
  fetchGroups,
  identifyFacebookAccounts,
  publishGroupComment,
  removeFacebookAccount,
  saveGroup,
  useFacebookAccount,
} from "./api.js";
import FacebookLogin from "./FacebookLogin.jsx";

function accountLabel(account) {
  return account?.name || (account?.id ? `Tài khoản ${account.id}` : "Facebook");
}

function accountInitial(account) {
  const name = (account?.name || "").trim();
  return (name || "f").charAt(0).toUpperCase();
}

function PostComment({ post, autoSend, session, busy, setBusy, setError, onDraft, onPublish }) {
  const [text, setText] = useState("");
  const [sent, setSent] = useState(false);
  const [note, setNote] = useState("");
  const [step, setStep] = useState("");
  const matched = Boolean(post.match?.name && post.match?.link);
  const working = busy === post.permalink;

  async function guarded(nextStep, task) {
    setBusy(post.permalink);
    setStep(nextStep);
    setError("");
    try {
      return await task();
    } catch (err) {
      setError(err.message || String(err));
      return null;
    } finally {
      setStep("");
      setBusy("");
    }
  }

  async function create() {
    setNote("");
    setBusy(post.permalink);
    setStep("draft");
    setError("");
    try {
      const result = await onDraft(post);
      setText(result.comment || "");
      setSent(false);
      if (result.fallback && !autoSend) {
        setNote("Qwen không viết được, đây là câu mẫu. Bạn vẫn sửa được trước khi gửi.");
      }
      if (!autoSend) return;
      setStep("send");
      const posted = await onPublish(post, result.comment || "");
      if (posted) {
        setSent(true);
        if (result.fallback) setNote("Qwen không viết được, đã gửi câu mẫu.");
      }
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setStep("");
      setBusy("");
    }
  }

  async function confirm() {
    setNote("");
    const posted = await guarded("send", () => onPublish(post, text));
    if (posted) setSent(true);
  }

  return (
    <div className="post-comment">
      <div className="actions">
        <button type="button" disabled={!matched || !session || Boolean(busy)} onClick={create}>
          {working ? (step === "send" ? "Đang gửi..." : "Đang viết...") : (autoSend ? "Tạo và gửi comment" : "Tạo comment")}
        </button>
        {sent ? <span className="badge">Đã gửi</span> : null}
      </div>
      {!matched ? <p className="meta">Chưa khớp sản phẩm nên chưa tạo comment được.</p> : null}
      {!session ? <p className="meta">Hãy đăng nhập Facebook trước khi gửi comment.</p> : null}
      {text && !autoSend ? (
        <>
          <textarea
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              setSent(false);
            }}
            maxLength={2000}
            aria-label="Nội dung comment"
          />
          <div className="actions">
            <button type="button" disabled={!text.trim() || !session || Boolean(busy)} onClick={confirm}>
              {working && step === "send" ? "Đang gửi..." : "Xác nhận"}
            </button>
          </div>
        </>
      ) : null}
      {text && autoSend ? <p className="post-caption">{text}</p> : null}
      {note ? <p className="meta">{note}</p> : null}
    </div>
  );
}

export default function Groups() {
  const [groups, setGroups] = useState([]);
  const [session, setSession] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [naming, setNaming] = useState(false);
  const namedRef = useRef(false);
  const [url, setUrl] = useState("");
  const [limit, setLimit] = useState(10);
  const [activeId, setActiveId] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [loginOpen, setLoginOpen] = useState(false);
  const [autoSend, setAutoSend] = useState(() => localStorage.getItem("fb-comment-auto") === "1");

  async function load(preferId = "") {
    const data = await fetchGroups();
    const list = data.groups || [];
    setGroups(list);
    setSession(Boolean(data.facebook_session));
    setAccounts(data.facebook_accounts?.accounts || []);
    const wanted = preferId || activeId;
    const nextId = wanted && list.some((group) => group.id === wanted) ? wanted : (list[0]?.id || "");
    setActiveId(nextId);
    const current = list.find((group) => group.id === nextId);
    const fetchError = current?.fetch_error || "";
    const staleLogin = fetchError.startsWith("Chưa đăng nhập Facebook");
    setError(staleLogin ? "" : fetchError);
    return list;
  }

  useEffect(() => {
    localStorage.setItem("fb-comment-auto", autoSend ? "1" : "0");
  }, [autoSend]);

  useEffect(() => {
    load("").catch((err) => setError(err.message || String(err)));
  }, []);

  useEffect(() => {
    if (namedRef.current || !accounts.some((account) => account.id && !account.name)) return undefined;
    namedRef.current = true;
    setNaming(true);
    identifyFacebookAccounts()
      .then((data) => setAccounts(data.facebook_accounts?.accounts || []))
      .catch(() => {})
      .finally(() => setNaming(false));
    return undefined;
  }, [accounts]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(""), 3600);
    return () => clearTimeout(timer);
  }, [toast]);

  const active = groups.find((group) => group.id === activeId) || null;
  const currentAccount = accounts.find((account) => account.active) || null;
  const otherAccounts = accounts.filter((account) => !account.active);

  function applyAccounts(data) {
    setAccounts(data.facebook_accounts?.accounts || []);
    setSession(Boolean(data.facebook_session));
  }

  async function onUseAccount(account) {
    setBusy(`account-${account.id}`);
    setError("");
    try {
      applyAccounts(await useFacebookAccount(account.id));
      setToast(`Đang dùng ${accountLabel(account)}`);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy("");
    }
  }

  async function onRemoveAccount(account) {
    if (!window.confirm(`Gỡ ${accountLabel(account)} khỏi máy chủ?`)) return;
    setBusy(`account-${account.id}`);
    setError("");
    try {
      applyAccounts(await removeFacebookAccount(account.id));
      setToast("Đã gỡ tài khoản");
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy("");
    }
  }

  async function onAdd(event) {
    event.preventDefault();
    const link = url.trim();
    if (!link) return;
    setBusy("add");
    setError("");
    try {
      const result = await saveGroup(link, Number(limit) || 10);
      setUrl("");
      await load(result.group?.id || "");
      if (!result.group?.fetch_error) setToast(`Đã lấy ${(result.group?.posts || []).length} bài mới nhất`);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy("");
    }
  }

  async function onRefresh(group) {
    setBusy(group.id);
    setError("");
    try {
      const result = await saveGroup(group.url, Number(limit) || 10);
      await load(group.id);
      if (!result.group?.fetch_error) setToast(`Đã lấy ${(result.group?.posts || []).length} bài mới nhất`);
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setBusy("");
    }
  }

  async function onDraft(post) {
    setError("");
    return draftGroupComment(post.permalink);
  }

  async function onPublish(post, comment) {
    const message = (comment || "").trim();
    if (!message) return false;
    setError("");
    await publishGroupComment(post.permalink, message);
    setToast("Đã gửi comment lên bài viết");
    return true;
  }

  return (
    <section className="group-page">
      <form className="group-form" onSubmit={onAdd}>
        <label>
          Link nhóm
          <input
            type="url"
            required
            placeholder="https://www.facebook.com/groups/..."
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
        </label>
        <label>
          Số bài mới
          <input
            type="number"
            min="1"
            max="100"
            aria-label="Số bài mới lấy về"
            title="Số bài mới nhất lấy về khi thêm nhóm hoặc bấm Lấy bài mới, từ 1 đến 100"
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
        <button type="submit" disabled={busy === "add"}>
          {busy === "add" ? "Đang lấy bài..." : "Thêm nhóm"}
        </button>
      </form>
      <section className="account-panel">
        <div className="account-current">
          <span className="avatar" aria-hidden="true">{currentAccount ? accountInitial(currentAccount) : "?"}</span>
          <div className="account-copy">
            <b>{currentAccount ? accountLabel(currentAccount) : "Chưa đăng nhập Facebook"}</b>
            <p className="meta">
              {currentAccount
                ? `Đang dùng · mã ${currentAccount.id}${currentAccount.saved_at ? ` · lưu lúc ${currentAccount.saved_at}` : ""}${naming && !currentAccount.name ? " · đang đọc tên" : ""}`
                : "Đăng nhập từ laptop này. Server không cần màn hình."}
            </p>
          </div>
          {currentAccount ? <span className="badge">Đang dùng</span> : null}
          <button type="button" className={session ? "ghost" : ""} onClick={() => setLoginOpen(true)}>
            {session ? "Thêm tài khoản" : "Đăng nhập Facebook"}
          </button>
          {currentAccount ? (
            <button
              type="button"
              className="ghost"
              disabled={busy === `account-${currentAccount.id}`}
              onClick={() => onRemoveAccount(currentAccount)}
            >
              Gỡ
            </button>
          ) : null}
        </div>
        {otherAccounts.length > 0 ? (
          <ul className="account-list">
            {otherAccounts.map((account) => (
              <li key={account.id}>
                <span className="avatar small" aria-hidden="true">{accountInitial(account)}</span>
                <div className="grow">
                  <b>{accountLabel(account)}</b>
                  <p className="meta">Mã {account.id}{account.saved_at ? ` · đăng nhập lúc ${account.saved_at}` : ""}</p>
                </div>
                <button
                  type="button"
                  disabled={busy === `account-${account.id}`}
                  onClick={() => onUseAccount(account)}
                >
                  Dùng tài khoản này
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={busy === `account-${account.id}`}
                  onClick={() => onRemoveAccount(account)}
                >
                  Gỡ
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
      {loginOpen ? (
        <FacebookLogin
          onClose={() => setLoginOpen(false)}
          onReady={() => {
            setLoginOpen(false);
            setToast("Đã lưu phiên Facebook");
            load(activeId).catch((err) => setError(err.message || String(err)));
          }}
        />
      ) : null}
      {error ? <p className="banner">{error}</p> : null}

      {groups.length === 0 ? (
        <p className="empty-card">Chưa có nhóm. Dán link nhóm Facebook vào ô trên.</p>
      ) : (
        <div className="group-layout">
          <aside className="group-list">
            {groups.map((group) => (
              <button
                key={group.id}
                type="button"
                className={group.id === activeId ? "group-chip on" : "group-chip"}
                onClick={() => {
                  setActiveId(group.id);
                  const text = group.fetch_error || "";
                  setError(text.startsWith("Chưa đăng nhập Facebook") ? "" : text);
                }}
              >
                <b>{group.name || group.id}</b>
                <span>{(group.posts || []).length} bài{group.fetch_error ? " · lỗi lấy bài" : ""}</span>
              </button>
            ))}
          </aside>
          {active ? (
            <div className="group-detail">
              <div className="group-head">
                <div>
                  <h2>{active.name || active.id}</h2>
                  <p className="meta">
                    <a href={active.url} target="_blank" rel="noopener">{active.url}</a>
                    {active.fetched_at ? ` · lấy lúc ${active.fetched_at}` : " · chưa lấy được bài"}
                  </p>
                  <p className="meta">
                    {autoSend ? "Qwen viết xong là gửi ngay." : "Qwen viết nháp, bạn sửa rồi xác nhận."}
                  </p>
                </div>
                <div className="actions">
                  <button
                    type="button"
                    className={autoSend ? "" : "ghost"}
                    aria-pressed={autoSend}
                    onClick={() => setAutoSend((value) => !value)}
                  >
                    {autoSend ? "Tự động gửi" : "Sửa rồi xác nhận"}
                  </button>
                  <label>
                    Số bài mới
                    <input
                      type="number"
                      min="1"
                      max="100"
                      aria-label="Số bài mới lấy về"
                      value={limit}
                      onChange={(event) => setLimit(event.target.value)}
                    />
                  </label>
                  <button type="button" disabled={Boolean(busy)} onClick={() => onRefresh(active)}>
                    {busy === active.id ? "Đang lấy..." : `Lấy ${limit || 10} bài mới`}
                  </button>
                </div>
              </div>
              {(active.posts || []).length === 0 ? (
                <p className="empty-card">Nhóm chưa có bài viết nào được lưu.</p>
              ) : (
                <ol className="post-list">
                  {(active.posts || []).map((post, index) => (
                    <li key={`${post.permalink || "post"}-${index}`}>
                      <div className="post-media">
                        {post.image_files?.[0]
                          ? <img alt="" src={`/media/${post.image_files[0]}`} />
                          : <div className="ph large" />}
                      </div>
                      <div>
                        <p className="post-caption">{post.caption || "Bài không có caption"}</p>
                        {post.match ? (
                          <p className="meta">
                            Khớp: {post.match.name}
                            {post.match.price_formatted ? ` · ${post.match.price_formatted}` : ""}
                            {post.match.score ? ` · ${post.match.score} điểm` : ""}
                          </p>
                        ) : <p className="meta">Chưa khớp sản phẩm trong catalog.</p>}
                        {post.permalink ? (
                          <a href={post.permalink} target="_blank" rel="noopener">Mở bài viết</a>
                        ) : null}
                        <PostComment
                          post={post}
                          autoSend={autoSend}
                          session={session}
                          busy={busy}
                          setBusy={setBusy}
                          setError={setError}
                          onDraft={onDraft}
                          onPublish={onPublish}
                        />
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          ) : null}
        </div>
      )}
      {toast ? <div className="toast" role="status">{toast}</div> : null}
    </section>
  );
}
