import { useEffect, useState } from "react";
import { IconButton, Icons } from "./icons.jsx";
import ProgressSteps from "./ProgressSteps.jsx";

export default function DouyinReview({
  videos,
  selectedId,
  onSelect,
  translating,
  saving,
  onTranslate,
  onTranslateAll,
  translateJob,
  onSave,
  onPost,
  onAiProcess,
  onDelete,
  aiJob,
  target = "facebook",
}) {
  const reviewLabel = {
    facebook: "Đăng Facebook",
    youtube: "Đăng YouTube",
    tiktok: "Đăng TikTok",
    instagram: "Đăng Instagram",
  }[target] || "Đăng";
  const reviewTitle = {
    facebook: "Đăng bản video ngắn AI lên Facebook",
    youtube: "Đăng bản video ngắn AI lên YouTube Shorts",
    tiktok: "Đăng bản video ngắn AI lên TikTok",
    instagram: "Đăng bản video ngắn AI lên Instagram Reels",
  }[target] || "Đăng video ngắn";
  const list = videos || [];
  const video = list.find((item) => item.id === selectedId) || list[0] || null;
  const isYoutube = target === "youtube";
  const [draft, setDraft] = useState("");
  const [titleDraft, setTitleDraft] = useState("");
  const [descDraft, setDescDraft] = useState("");
  const [dirty, setDirty] = useState(false);
  const [source, setSource] = useState("original");
  const pendingCount = list.filter((item) => !item.translated).length;
  const batch = translateJob || {};
  const batchRunning = Boolean(batch.running);
  const globalAi = aiJob || {};

  useEffect(() => {
    setDraft(video?.caption_vi || "");
    setTitleDraft(video?.title_vi || (video?.caption_vi || "").split("\n").find(Boolean) || "");
    setDescDraft(video?.description_vi || "");
    setDirty(false);
  }, [video?.id, video?.caption_vi, video?.title_vi, video?.description_vi]);

  useEffect(() => {
    const ai = video?.ai || {};
    if (ai.has_ai) setSource("ai");
    else setSource("original");
  }, [video?.id, video?.ai?.has_ai]);

  if (!video) {
    return (
      <section className="board review-empty">
        <strong>Chưa có video Douyin</strong>
        <p className="sub">Hãy tải video ở màn Cấu hình, rồi quay lại đây để xem và dịch trước khi đăng.</p>
      </section>
    );
  }

  const ai = video.ai || {};
  const publish = video.publish || {};
  const aiRunning = ai.status === "running" || (globalAi.running && globalAi.video_id === video.id);
  const aiBusyOther = Boolean(globalAi.running && globalAi.video_id && globalAi.video_id !== video.id);
  const postRunning = publish.status === "running" || video.status === "posting";
  const busy = translating === video.id || batchRunning;
  const showAi = source === "ai" && ai.has_ai;
  const aiProgress = aiRunning
    ? {
        ...ai,
        status: "running",
        message: ai.message || globalAi.message || "Đang tạo video ngắn…",
        started_at: ai.started_at || globalAi.started_at || "",
        steps: (ai.steps && ai.steps.length) ? ai.steps : (globalAi.steps || []),
      }
    : ai;
  const showAiProgress = aiRunning
    || ["done", "error"].includes(ai.status)
    || (ai.steps || []).some((s) => s.status !== "pending");
  const showPublishProgress = postRunning || ["done", "error"].includes(publish.status) || (publish.steps || []).some((s) => s.status !== "pending");
  const mediaSrc = showAi
    ? `/api/douyin/ai-media/${video.id}`
    : `/api/douyin/media/${video.id}`;
  const original = video.description && video.description !== video.title
    ? `${video.title}\n\n${video.description}`
    : (video.title || "");
  const headline = (text) => (text || "").split("\n").find(Boolean) || "";
  const aiLabel = (item) => {
    const row = item.ai || {};
    if (row.status === "running") return "Đang tạo ngắn";
    if (row.has_ai) return "Có bản ngắn";
    if (row.status === "error") return "Lỗi AI";
    return "";
  };
  const publishLabel = (item) => {
    const row = item.publish || {};
    if (item.status === "posting" || row.status === "running") return "Đang đăng";
    if (item.status === "published" || row.status === "done") return "Đã đăng";
    if (item.status === "error" || row.status === "error") return "Lỗi đăng";
    return "";
  };

  return (
    <section className="review">
      <aside className="review-list">
        <div className="review-batch">
          <button
            className="ghost"
            type="button"
            disabled={batchRunning || pendingCount === 0}
            onClick={onTranslateAll}
          >
            {batchRunning
              ? `Đang dịch ${batch.done || 0}/${batch.total || pendingCount}…`
              : pendingCount
                ? `Dịch tất cả (${pendingCount})`
                : "Đã dịch hết"}
          </button>
          {batch.message ? <span className="meta">{batch.message}</span> : null}
        </div>
        {list.map((item) => {
          const tag = aiLabel(item);
          const pub = publishLabel(item);
          return (
            <button
              key={item.id}
              type="button"
              className={item.id === video.id ? "on" : ""}
              onClick={() => onSelect(item.id)}
            >
              <b>{headline(item.caption_vi) || item.title}</b>
              <span>
                {item.translated ? "Đã dịch" : "Chưa dịch"}
                {tag ? ` · ${tag}` : ""}
                {pub ? ` · ${pub}` : ""}
                {item.upload_label ? ` · ${item.upload_label}` : ""}
              </span>
            </button>
          );
        })}
      </aside>
      <div className="review-stage">
        <div className="player">
          <div className="player-sources">
            <button
              type="button"
              className={source === "original" ? "on" : ""}
              onClick={() => setSource("original")}
            >
              Gốc
            </button>
            <button
              type="button"
              className={source === "ai" ? "on" : ""}
              disabled={!ai.has_ai}
              onClick={() => setSource("ai")}
            >
              Video ngắn AI
            </button>
          </div>
          {video.has_file || showAi ? (
            <video
              key={`${video.id}-${showAi ? "ai" : "orig"}`}
              src={mediaSrc}
              controls
              playsInline
              preload="metadata"
            />
          ) : (
            <p className="meta">Không thấy file video trên máy.</p>
          )}
          <p className="meta">
            {showAi ? "Đang xem bản ngắn AI" : (video.channel_name || "Douyin")}
            {showAi && ai.duration ? ` · ~${Math.round(ai.duration)} giây` : ""}
            {!showAi && video.duration ? ` · ${video.duration} giây` : ""}
          </p>
          <div className="ai-actions icon-actions">
            {!ai.has_ai && !showAi ? (
              <IconButton
                icon={Icons.spark}
                label={aiRunning ? "Đang tạo video ngắn…" : "Tạo video ngắn"}
                busy={aiRunning}
                disabled={!video.has_file || aiRunning || aiBusyOther}
                onClick={() => onAiProcess(video.id, false)}
              />
            ) : null}
            {showAi ? (
              <IconButton
                icon={Icons.refresh}
                label={aiRunning ? "Đang tạo lại…" : "Tạo lại video ngắn"}
                busy={aiRunning}
                disabled={!video.has_file || aiRunning || aiBusyOther}
                onClick={() => onAiProcess(video.id, true)}
              />
            ) : null}
            {aiRunning ? (
              <span className="ai-live-label">Đang tạo video ngắn…</span>
            ) : null}
            {ai.status === "done" && ai.has_ai && !aiRunning ? (
              <span className="ai-live-label ok">Đã tạo xong video ngắn</span>
            ) : null}
            {ai.status === "error" && !aiRunning ? (
              <span className="ai-live-label err">Tạo video ngắn lỗi</span>
            ) : null}
            {aiBusyOther ? (
              <span className="meta">Đang tạo ngắn cho video khác — đợi xong rồi thử lại.</span>
            ) : null}
          </div>
          {showAiProgress || aiRunning ? (
            <ProgressSteps
              title="Tiến trình tạo video ngắn"
              progress={aiProgress}
              forceShow={aiRunning}
            />
          ) : null}
        </div>
        <div className="review-copy">
          <label>Nội dung gốc</label>
          <p className="original">{original}</p>
          {isYoutube ? (
            <>
              <div className="yt-fields">
                <label htmlFor="title-vi">Tiêu đề được dịch</label>
                <input
                  id="title-vi"
                  className="yt-title"
                  value={titleDraft}
                  maxLength={90}
                  placeholder="Tiêu đề Shorts (hệ thống sẽ thêm #Shorts khi đăng)"
                  onChange={(event) => {
                    setTitleDraft(event.target.value);
                    setDirty(true);
                  }}
                />
                <p className="meta">
                  Khi đăng sẽ kết thúc bằng <b>#Shorts</b>
                  {titleDraft.trim() ? ` · xem trước: ${titleDraft.trim()} #Shorts` : ""}
                </p>
                <label htmlFor="desc-vi">Mô tả được chọn lọc từ nội dung của video</label>
                <textarea
                  id="desc-vi"
                  className="yt-desc"
                  value={descDraft}
                  placeholder="Mô tả Shorts — chọn lọc từ nội dung video, không cần thêm hashtag Douyin."
                  onChange={(event) => {
                    setDescDraft(event.target.value);
                    setDirty(true);
                  }}
                />
                <p className="meta">
                  Tag cố định khi đăng: <b>#shortviral #kienthucthuvi #khampha #vuive</b>
                </p>
              </div>
              <p className="meta">
                {video.translated || titleDraft.trim()
                  ? `Sửa tiêu đề (không gắn tag dịch) và phần chữ mô tả trước khi đăng${video.translation_engine ? ` · dịch bằng ${video.translation_engine}` : ""}.`
                  : "Chưa có bản tiếng Việt — bấm Dịch hoặc nhập tay."}
              </p>
            </>
          ) : (
            <>
              <label htmlFor="caption-vi">Bản tiếng Việt sẽ đăng</label>
              <textarea
                id="caption-vi"
                value={draft}
                placeholder="Bấm Dịch để tạo bản tiếng Việt, rồi sửa lại nếu cần."
                onChange={(event) => {
                  setDraft(event.target.value);
                  setDirty(true);
                }}
              />
              <p className="meta">
                {video.translated
                  ? `Đã dịch${video.translation_engine ? ` bằng ${video.translation_engine}` : ""}. Có thể sửa trước khi đăng.`
                  : "Chưa có bản tiếng Việt."}
              </p>
            </>
          )}
          <div className="row-actions review-actions icon-actions">
            <IconButton
              icon={Icons.translate}
              label={busy ? "Đang dịch…" : video.caption_vi ? "Dịch lại" : "Dịch sang tiếng Việt"}
              busy={busy && translating === video.id}
              disabled={busy}
              onClick={() => onTranslate(video.id, Boolean(video.caption_vi))}
            />
            <IconButton
              icon={Icons.save}
              label={saving ? "Đang lưu…" : (isYoutube ? "Lưu tiêu đề & mô tả" : "Lưu bản dịch")}
              busy={saving}
              disabled={
                saving
                || !dirty
                || (isYoutube ? !(titleDraft.trim() || descDraft.trim()) : !draft.trim())
              }
              onClick={() => {
                if (isYoutube) {
                  onSave(video.id, {
                    title_vi: titleDraft,
                    description_vi: descDraft,
                    caption: [titleDraft.trim(), descDraft.trim()].filter(Boolean).join("\n\n"),
                  });
                } else {
                  onSave(video.id, draft);
                }
              }}
            />
            {showAi ? (
              <IconButton
                icon={Icons.post}
                label={postRunning ? "Đang đăng…" : (video.status === "published" ? `Đăng lại — ${reviewLabel}` : reviewTitle)}
                primary
                busy={postRunning}
                disabled={!ai.has_ai || aiRunning || postRunning}
                onClick={() => onPost(video.id)}
              />
            ) : null}
            {onDelete ? (
              <IconButton
                icon={Icons.delete}
                label="Xóa video"
                danger
                disabled={busy || aiRunning || postRunning}
                onClick={() => onDelete(video.id)}
              />
            ) : null}
          </div>
          {showPublishProgress ? (
            <div className="publish-progress-wrap">
              <ProgressSteps
                title={`Tiến trình đăng ${reviewLabel.replace(/^Đăng\s+/, "")}`}
                progress={publish}
              />
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
