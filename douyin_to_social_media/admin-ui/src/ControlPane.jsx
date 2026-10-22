import { AI_FILTERS, FILTERS, OFFER_FILTERS, hasAiShort, hasOffer } from "./status.js";

export default function ControlPane({
  state,
  filter,
  offer,
  ai = "all",
  channel,
  query,
  onFilter,
  onOffer,
  onAi,
  onChannel,
  onQuery,
  showOffer = true,
  showAi = false,
  channelHeading = "Lọc theo kênh",
  allChannelsLabel = "Tất cả kênh",
}) {
  const counts = state?.counts || {};
  const channels = state?.sync?.channels || [];
  const videos = state?.videos || [];
  const channelCounts = {};
  for (const video of videos) {
    if (!video.channel) continue;
    channelCounts[video.channel] = (channelCounts[video.channel] || 0) + 1;
  }
  const statusCounts = {
    all: counts.total || videos.length,
    pending: counts.pending || 0,
    published: counts.published || 0,
    error: counts.error || 0,
  };
  const offerCounts = {
    all: videos.length,
    yes: videos.filter(hasOffer).length,
  };
  const withAi = videos.filter(hasAiShort).length;
  const aiCounts = {
    all: videos.length,
    yes: withAi,
    no: videos.length - withAi,
  };

  return (
    <aside className="side">
      <section className="card">
        <strong>Lọc theo trạng thái</strong>
        <div className="choice-list" role="group" aria-label="Lọc theo trạng thái">
          {FILTERS.map(([id, label]) => (
            <button key={id} type="button" className={filter === id ? "on" : ""} onClick={() => onFilter(id)}>
              <span>{label}</span>
              <span className="count">{statusCounts[id] ?? 0}</span>
            </button>
          ))}
        </div>
        {showAi ? (
          <>
            <strong>Lọc video ngắn</strong>
            <div className="choice-list" role="group" aria-label="Lọc video ngắn">
              {AI_FILTERS.map(([id, label]) => (
                <button key={id} type="button" className={ai === id ? "on" : ""} onClick={() => onAi?.(id)}>
                  <span>{label}</span>
                  <span className="count">{aiCounts[id] ?? 0}</span>
                </button>
              ))}
            </div>
          </>
        ) : null}
        {showOffer ? (
          <>
            <strong>Lọc gợi ý Shopee</strong>
            <div className="choice-list" role="group" aria-label="Lọc gợi ý Shopee">
              {OFFER_FILTERS.map(([id, label]) => (
                <button key={id} type="button" className={offer === id ? "on" : ""} onClick={() => onOffer(id)}>
                  <span>{label}</span>
                  <span className="count">{offerCounts[id] ?? 0}</span>
                </button>
              ))}
            </div>
          </>
        ) : null}
        <strong>{channelHeading}</strong>
        <div className="choice-list" role="group" aria-label={channelHeading}>
          <button type="button" className={channel === "all" ? "on" : ""} onClick={() => onChannel("all")}>
            <span>{allChannelsLabel}</span>
            <span className="count">{videos.length}</span>
          </button>
          {channels.map((item) => (
            <button
              key={item.url}
              type="button"
              className={channel === item.url ? "on" : ""}
              onClick={() => onChannel(item.url)}
            >
              <span>{item.name}</span>
              <span className="count">{channelCounts[item.url] || 0}</span>
            </button>
          ))}
        </div>
        <div className="field">
          <label htmlFor="query">Tìm tiêu đề</label>
          <input
            id="query"
            type="search"
            placeholder="Tìm tiêu đề"
            value={query}
            onChange={(event) => onQuery(event.target.value)}
          />
        </div>
      </section>
    </aside>
  );
}
