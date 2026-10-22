import { useCallback, useEffect, useState } from "react";
import { request } from "./api.js";
import ActionsCard from "./ActionsCard.jsx";
import DouyinReview from "./DouyinReview.jsx";
import AutoPostCard from "./AutoPostCard.jsx";
import ControlPane from "./ControlPane.jsx";
import Header from "./Header.jsx";
import LogCard from "./LogCard.jsx";
import PlatformsCard from "./PlatformsCard.jsx";
import SourceCard from "./SourceCard.jsx";
import VideoTable from "./VideoTable.jsx";
import { normalizeTarget, targetMeta } from "./targets.js";

export default function App() {
  const [state, setState] = useState(null);
  const [toast, setToast] = useState("");
  const [filter, setFilter] = useState("all");
  const [aiFilter, setAiFilter] = useState("all");
  const [channel, setChannel] = useState("all");
  const [query, setQuery] = useState("");
  const [token, setToken] = useState("");
  const [reviewId, setReviewId] = useState("");
  const [translating, setTranslating] = useState("");
  const [savingCaption, setSavingCaption] = useState(false);
  const [tab, setTab] = useState("work");
  const [target, setTarget] = useState(() => normalizeTarget(window.localStorage.getItem("dts-target")));
  const [tiktokForm, setTiktokForm] = useState({ client_key: "", client_secret: "" });
  const meta = targetMeta(target);

  function chooseTarget(next) {
    const value = normalizeTarget(next);
    setTarget(value);
    window.localStorage.setItem("dts-target", value);
    setFilter("all");
    setAiFilter("all");
    setChannel("all");
    setQuery("");
    setToken("");
    setReviewId("");
    setState(null);
  }

  const api = useCallback((path, body) => {
    if (path === "/state") {
      return request(`/api/douyin/state?target=${encodeURIComponent(target)}`);
    }
    const payload = { ...(body || {}), target };
    return request(`/api/douyin${path}`, payload);
  }, [target]);

  const notify = useCallback((text) => {
    setToast(text);
    window.clearTimeout(notify._t);
    notify._t = window.setTimeout(() => setToast(""), 3200);
  }, []);

  const refresh = useCallback(async () => {
    const data = await api("/state");
    setState(data);
    if (data?.tiktok && target === "tiktok") {
      setTiktokForm((current) => ({
        client_key: current.client_key || data.tiktok.client_key || "",
        client_secret: current.client_secret || "",
      }));
    }
    return data;
  }, [api, target]);

  useEffect(() => {
    refresh().catch((err) => notify(err.message));
    const busy = Boolean(state?.ai_job?.running || state?.job?.running || state?.translate?.running || state?.sync?.running);
    // Idle: poll chậm hơn (payload ~900 video). Busy: poll nhanh để hiện tiến trình.
    const timer = window.setInterval(() => {
      refresh().catch(() => {});
    }, busy ? 2000 : 10000);
    return () => window.clearInterval(timer);
  }, [refresh, notify, target, state?.ai_job?.running, state?.job?.running, state?.translate?.running, state?.sync?.running]);

  async function saveToken() {
    if (!token.trim()) return;
    try {
      setState(await api("/settings", { token: token.trim() }));
      setToken("");
      notify("Đã lưu token");
    } catch (err) {
      notify(err.message);
    }
  }

  async function saveSettings(form) {
    const body = {
      enabled: form.enabled,
      interval_minutes: form.interval_minutes,
      order: form.order,
    };
    if ((target === "facebook" || target === "instagram") && token.trim()) {
      body.token = token.trim();
    }
    if (target === "youtube" && form.privacy_status) body.privacy_status = form.privacy_status;
    if (target === "tiktok" && form.privacy_level) body.privacy_level = form.privacy_level;
    try {
      setState(await api("/settings", body));
      setToken("");
      notify("Đã lưu thiết lập");
    } catch (err) {
      notify(err.message);
    }
  }

  async function authYoutube() {
    try {
      setState(await api("/youtube/auth", {}));
      notify("Đã mở OAuth YouTube — hoàn tất trên trình duyệt");
    } catch (err) {
      notify(err.message);
    }
  }

  async function authTiktok() {
    try {
      setState(await api("/tiktok/auth", {}));
      notify("Đang chờ OAuth TikTok trên cổng 8768 — mở URL in ra terminal nếu trình duyệt không tự mở");
    } catch (err) {
      notify(err.message);
    }
  }

  async function saveTiktokCreds() {
    try {
      setState(await api("/settings", {
        client_key: tiktokForm.client_key.trim(),
        client_secret: tiktokForm.client_secret.trim(),
      }));
      notify("Đã lưu TikTok client key/secret");
    } catch (err) {
      notify(err.message);
    }
  }

  async function saveSyncAuto(form) {
    try {
      const data = await api("/sync-auto", {
        enabled: form.enabled,
        interval_minutes: form.interval_minutes,
      });
      setState(data);
      notify(form.enabled
        ? `Đã bật đồng bộ tài khoản đã lưu, mỗi ${data.sync_auto?.interval_minutes || form.interval_minutes} phút`
        : "Đã tắt đồng bộ tự động");
      return data.sync_auto;
    } catch (err) {
      notify(err.message);
      return null;
    }
  }

  async function syncVideos() {
    try {
      setState(await api("/sync", {}));
      notify("Đang lấy video mới, video trùng link sẽ được bỏ qua");
    } catch (err) {
      notify(err.message);
    }
  }

  async function syncChannel(url) {
    try {
      const data = await api("/sync", { url });
      setState(data);
      notify(data.sync?.message || "Đang đồng bộ tài khoản");
    } catch (err) {
      notify(err.message);
    }
  }

  async function downloadVideo(url) {
    try {
      const data = await api("/download", { url });
      setState(data);
      notify(data.sync?.message || "Đang tải video");
      return true;
    } catch (err) {
      notify(err.message);
      return false;
    }
  }

  async function postVideo(id) {
    const row = (state?.videos || []).find((item) => item.id === id);
    if (row?.status === "published") {
      const title = (row.caption || row.title || id || "").split("\n").find(Boolean) || id;
      if (!window.confirm(`Video này đã đăng ${meta.short} trước đó.\n\nĐăng lại thành video mới?\n\n${title}`)) {
        return;
      }
    }
    try {
      const data = await api("/post", { id });
      setState(data);
      notify(data.job?.title ? `Đang đăng ${meta.short}: ${data.job.title}` : `Đang đăng ${meta.short}`);
    } catch (err) {
      notify(err.message);
    }
  }

  function openReview(id) {
    setReviewId(id || "");
    setTab("review");
  }

  async function translateVideo(id, force = false) {
    setTranslating(id);
    try {
      setState(await api("/translate", { id, force }));
      notify(force ? "Đã dịch lại sang tiếng Việt" : "Đã dịch sang tiếng Việt");
    } catch (err) {
      notify(err.message);
    } finally {
      setTranslating("");
    }
  }

  async function translateAll() {
    try {
      setState(await api("/translate-all", {}));
      notify("Đang dịch lần lượt tiêu đề còn tiếng Trung");
    } catch (err) {
      notify(err.message);
    }
  }

  async function saveCaption(id, captionOrFields) {
    setSavingCaption(true);
    try {
      const payload = typeof captionOrFields === "string"
        ? { id, caption: captionOrFields }
        : {
          id,
          caption: captionOrFields?.caption || "",
          title_vi: captionOrFields?.title_vi,
          description_vi: captionOrFields?.description_vi,
        };
      setState(await api("/caption", payload));
      notify(payload.title_vi != null || payload.description_vi != null
        ? "Đã lưu tiêu đề & mô tả YouTube"
        : "Đã lưu bản tiếng Việt");
    } catch (err) {
      notify(err.message);
    } finally {
      setSavingCaption(false);
    }
  }

  async function aiProcess(id, force = false) {
    const message = force ? "Đang tạo lại video ngắn AI…" : "Đang tạo video ngắn AI…";
    // Optimistic UI — hiện panel ngay, không đợi response
    setState((prev) => {
      if (!prev) return prev;
      const started = new Date().toLocaleString("sv-SE", { timeZone: "Asia/Ho_Chi_Minh" }).replace("T", " ");
      return {
        ...prev,
        ai_job: {
          ...(prev.ai_job || {}),
          running: true,
          video_id: id,
          status: "running",
          message,
          started_at: started,
        },
        videos: (prev.videos || []).map((item) => (
          item.id === id
            ? {
                ...item,
                ai: {
                  ...(item.ai || {}),
                  status: "running",
                  message,
                  started_at: started,
                  has_ai: item.ai?.has_ai || false,
                  steps: item.ai?.steps || [],
                },
              }
            : item
        )),
      };
    });
    notify(message);
    try {
      setState(await api("/ai-process", { id, force }));
    } catch (err) {
      notify(err.message);
      setState((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          ai_job: { ...(prev.ai_job || {}), running: false, status: "error", message: err.message, error: err.message },
          videos: (prev.videos || []).map((item) => (
            item.id === id
              ? { ...item, ai: { ...(item.ai || {}), status: "error", message: err.message, error: err.message } }
              : item
          )),
        };
      });
    }
  }

  async function deleteVideo(id) {
    const video = (state?.videos || []).find((item) => item.id === id);
    const title = (video?.caption || video?.title || id || "").split("\n").find(Boolean) || id;
    if (!window.confirm(`Xóa video Douyin này?\n\n${title}\n\nSẽ xóa file gốc, video ngắn AI, bản dịch và lịch sử đăng trên mọi nền tảng.`)) {
      return false;
    }
    try {
      const data = await api("/delete", { id });
      setState(data);
      if (reviewId === id) setReviewId("");
      notify(data.delete?.message || "Đã xóa video");
      return true;
    } catch (err) {
      notify(err.message);
      return false;
    }
  }

  const autoHint = {
    facebook: "Mỗi lượt đăng một video ngắn AI lên Facebook Page.",
    youtube: "Mỗi lượt đăng một video ngắn AI lên YouTube Shorts.",
    tiktok: "Mỗi lượt đăng một video ngắn AI lên TikTok (Direct Post).",
    instagram: "Mỗi lượt đăng một Instagram Reels (Page gắn IG Professional).",
  }[target];

  return (
    <div className={tab === "config" ? "wrap config" : "wrap work"}>
      <Header page={state?.page} tab={tab} onTab={setTab} target={target} onTarget={chooseTarget} />
      {tab === "review" ? (
        <DouyinReview
          videos={state?.videos}
          selectedId={reviewId}
          onSelect={setReviewId}
          translating={translating}
          saving={savingCaption}
          onTranslate={translateVideo}
          onTranslateAll={translateAll}
          translateJob={state?.translate}
          onSave={saveCaption}
          onPost={postVideo}
          onAiProcess={aiProcess}
          onDelete={deleteVideo}
          aiJob={state?.ai_job}
          target={target}
        />
      ) : tab === "config" ? (
        <section className="config-page">
          <SourceCard
            sync={state?.sync}
            onSyncChannel={syncChannel}
            onDownload={downloadVideo}
            title="Lấy video từ Douyin"
            hint="Kho chung cho mọi đích đăng. Nếu Douyin chặn, xuất cookie vào douyin_cookies.txt."
            channelLabel="Link trang cá nhân"
            channelPlaceholder="https://www.douyin.com/user/..."
            channelAction="Đồng bộ tài khoản"
            videoPlaceholder="https://v.douyin.com/... hoặc /video/..."
          />
          <div className="config-grid">
            <div className="config-stack">
              <ActionsCard
                key={target}
                state={state}
                onSync={syncVideos}
                onSaveSyncAuto={saveSyncAuto}
                onToggleSuggest={() => {}}
                onPostNext={() => postVideo("next")}
                showSuggest={false}
                syncLabel="Đồng bộ tài khoản đã lưu"
              />
              <AutoPostCard
                key={target}
                state={state}
                onSave={saveSettings}
                hint={autoHint}
                showPrivacy={target === "youtube"}
                showTiktokPrivacy={target === "tiktok"}
              />
              <PlatformsCard target={target} />
            </div>
            <LogCard
              log={state?.log}
              target={target}
              token={token}
              onToken={setToken}
              onSaveToken={saveToken}
              youtube={state?.youtube}
              tiktok={state?.tiktok}
              instagram={state?.instagram}
              onAuthYoutube={authYoutube}
              onAuthTiktok={authTiktok}
              tiktokForm={tiktokForm}
              onTiktokForm={(field, value) => setTiktokForm((current) => ({ ...current, [field]: value }))}
              onSaveTiktokCreds={saveTiktokCreds}
            />
          </div>
        </section>
      ) : (
        <div className="workspace">
          <ControlPane
            state={state}
            filter={filter}
            offer="all"
            ai={aiFilter}
            channel={channel}
            query={query}
            onFilter={setFilter}
            onOffer={() => {}}
            onAi={setAiFilter}
            onChannel={setChannel}
            onQuery={setQuery}
            showOffer={false}
            showAi
            channelHeading="Lọc theo tài khoản"
            allChannelsLabel="Tất cả tài khoản"
          />
          <VideoTable
            videos={state?.videos}
            filter={filter}
            offer="all"
            ai={aiFilter}
            channel={channel}
            channels={state?.sync?.channels}
            query={query}
            suggesting={new Set()}
            activeId=""
            onSuggest={() => {}}
            onPost={postVideo}
            onPreview={openReview}
            onDelete={deleteVideo}
            dateLabel="Ngày Douyin"
            showOrigin
            showSuggest={false}
            scopeLabel="tài khoản"
            postLabel={meta.postLabel}
          />
        </div>
      )}
      {toast ? <div className="toast">{toast}</div> : null}
    </div>
  );
}
