import { useState } from "react";
import { IconButton, Icons } from "./icons.jsx";
import { STATUS, hasAiShort, hasOffer } from "./status.js";

function matches(video, filter, offer, ai, channel, query) {
  if (filter !== "all" && video.status !== filter) return false;
  if (offer === "yes" && !hasOffer(video)) return false;
  if (ai === "yes" && !hasAiShort(video)) return false;
  if (ai === "no" && hasAiShort(video)) return false;
  if (channel !== "all" && video.channel !== channel) return false;
  if (!query) return true;
  const blob = `${video.caption || ""} ${video.title || ""} ${video.description || ""} ${video.channel_name || ""} ${video.id || ""}`.toLowerCase();
  return blob.includes(query);
}

const STATUS_LABEL = { all: "mọi trạng thái", pending: "chưa đăng", published: "đã đăng", error: "lỗi" };

function columnsFor(dateLabel) {
  return [
    ["title", "Video"],
    ["date", dateLabel],
    ["status", "Trạng thái"],
  ];
}

function sortValue(video, key) {
  if (key === "title") return video.title || "";
  if (key === "date") return video.upload_date || "";
  return STATUS[video.status]?.[1] || video.status || "";
}

function compareRows(left, right, key, dir) {
  const a = sortValue(left, key);
  const b = sortValue(right, key);
  if (!a && !b) return 0;
  if (!a) return 1;
  if (!b) return -1;
  const base = key === "date" ? (a < b ? -1 : a > b ? 1 : 0) : a.localeCompare(b, "vi");
  return base * (dir === "asc" ? 1 : -1);
}

const AI_LABEL = { yes: "đã có video ngắn", no: "chưa có video ngắn" };

export default function VideoTable({
  videos,
  filter,
  offer,
  ai = "all",
  channel,
  channels,
  query,
  suggesting,
  activeId,
  onSuggest,
  onPost,
  onPreview,
  onDelete,
  dateLabel = "Ngày Douyin",
  showSuggest = true,
  showOrigin = false,
  scopeLabel = "kênh",
  postLabel = "Đăng",
}) {
  const [sort, setSort] = useState({ key: "", dir: "asc" });
  const [limit, setLimit] = useState(80);
  const q = query.trim().toLowerCase();
  const rows = (videos || []).filter((video) => matches(video, filter, offer, ai, channel, q));
  if (sort.key) rows.sort((left, right) => compareRows(left, right, sort.key, sort.dir));
  const visible = rows.slice(0, limit);

  function toggleSort(key) {
    setSort((current) => {
      if (current.key !== key) return { key, dir: key === "date" ? "desc" : "asc" };
      return { key, dir: current.dir === "asc" ? "desc" : "asc" };
    });
  }
  const columns = columnsFor(dateLabel);
  const channelName = channel === "all"
    ? `mọi ${scopeLabel}`
    : ((channels || []).find((item) => item.url === channel)?.name || `${scopeLabel} đã chọn`);
  return (
    <section className="board">
      <div className="board-head">
        <strong>Video</strong>
        <span className="meta">
          {rows.length} video · {STATUS_LABEL[filter] || filter} · {channelName}
          {offer === "yes" ? " · đã có gợi ý" : ""}
          {AI_LABEL[ai] ? ` · ${AI_LABEL[ai]}` : ""}
        </span>
      </div>
      <table>
        <thead>
          <tr>
            {columns.map(([id, label]) => (
              <th key={id} aria-sort={sort.key === id ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}>
                <button type="button" className={sort.key === id ? "sort on" : "sort"} onClick={() => toggleSort(id)}>
                  {label}{sort.key === id ? (sort.dir === "asc" ? " ▲" : " ▼") : ""}
                </button>
              </th>
            ))}
            <th className="col-actions" aria-label="Thao tác" />
          </tr>
        </thead>
        <tbody>
          {visible.length ? visible.map((video) => {
            const [kind, label] = STATUS[video.status] || STATUS.pending;
            const hasAi = video.source !== "douyin" || Boolean(video.has_ai_short || video.ai?.has_ai);
            const canPost = hasAi && video.status !== "posting" && video.status !== "missing";
            const isRepost = video.status === "published";
            const busy = suggesting.has(video.id) || video.id === activeId;
            return (
              <tr key={video.id} className={video.id === activeId ? "active" : ""}>
                <td className="title">
                  <div className="desc">{(video.caption_vi || video.caption || video.title || "").split("\n").find(Boolean)}</div>
                  {showOrigin && video.translated ? <div className="meta">Gốc: {video.title}</div> : null}
                  {showOrigin && !video.translated ? <div className="meta">Chưa dịch sang tiếng Việt</div> : null}
                  {video.offers?.length ? (
                    <div className="offers">
                      {video.offers.map((item) => (
                        <div className="offer" key={item.item_id}>
                          <b>{item.score}% · {item.name}</b>
                          {item.by?.length ? <div className="by">Gợi ý bởi {item.by.join(" và ")}</div> : null}
                          <span className="meta">
                            {item.price_formatted || ""}
                            {item.reason ? ` · ${item.reason}` : ""}
                          </span>
                          <br />
                          <a href={item.short_link} target="_blank" rel="noreferrer">Mở Shopee</a>
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {video.offer_error ? <div className="meta">{video.offer_error}</div> : null}
                  {video.offer_checked && !video.offer_error && !video.offers?.length ? (
                    <div className="meta">Không có sản phẩm đủ tương thích trong kho.</div>
                  ) : null}
                  {video.error ? <div className="meta">{video.error}</div> : null}
                </td>
                <td>
                  {video.upload_label || ""}
                  {video.channel_name ? <div className="meta">{video.channel_name}</div> : null}
                  {video.duration ? <div className="meta">{video.duration} giây</div> : null}
                </td>
                <td>
                  <span className={`pill ${kind}`}>{label}</span>
                  {video.permalink ? (
                    <a className="icon-link" href={video.permalink} target="_blank" rel="noreferrer" title="Mở bài đã đăng" aria-label="Mở bài đã đăng">
                      {Icons.link}
                    </a>
                  ) : null}
                </td>
                <td className="col-actions">
                  <div className="row-actions icon-actions">
                    {onPreview ? (
                      <IconButton icon={Icons.preview} label="Xem trước" onClick={() => onPreview(video.id)} />
                    ) : null}
                    {showSuggest ? (
                      <IconButton
                        icon={Icons.shop}
                        label={busy ? "Đang tìm sản phẩm…" : "Gợi ý Shopee"}
                        busy={busy}
                        disabled={busy}
                        onClick={() => onSuggest(video.id)}
                      />
                    ) : null}
                    {canPost ? (
                      <IconButton
                        icon={Icons.post}
                        label={isRepost ? `Đăng lại (${postLabel})` : postLabel}
                        primary
                        onClick={() => onPost(video.id)}
                      />
                    ) : null}
                    {onDelete ? (
                      <IconButton
                        icon={Icons.delete}
                        label="Xóa video"
                        danger
                        disabled={busy || video.status === "posting"}
                        onClick={() => onDelete(video.id)}
                      />
                    ) : null}
                  </div>
                </td>
              </tr>
            );
          }) : (
            <tr><td colSpan="4" className="meta">Không có video khớp bộ lọc.</td></tr>
          )}
        </tbody>
      </table>
      {rows.length > visible.length ? (
        <div className="board-foot">
          <button type="button" className="ghost" onClick={() => setLimit((n) => n + 100)}>
            Xem thêm {Math.min(100, rows.length - visible.length)} / còn {rows.length - visible.length}
          </button>
        </div>
      ) : null}
    </section>
  );
}
