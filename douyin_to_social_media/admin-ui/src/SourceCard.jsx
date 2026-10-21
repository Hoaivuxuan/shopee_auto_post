import { useState } from "react";

function UrlField({ id, label, placeholder, value, onChange, busy, action, onSubmit }) {
  return (
    <form
      className="url-field"
      onSubmit={(event) => {
        event.preventDefault();
        const url = value.trim();
        if (!url || busy) return;
        onSubmit(url);
      }}
    >
      <label htmlFor={id}>{label}</label>
      <div className="url-shell">
        <input
          id={id}
          type="text"
          inputMode="url"
          autoComplete="off"
          spellCheck="false"
          placeholder={placeholder}
          value={value}
          disabled={busy}
          onChange={(event) => onChange(event.target.value)}
        />
        <button className="primary" type="submit" disabled={busy || !value.trim()}>
          {busy ? "Đang lấy…" : action}
        </button>
      </div>
    </form>
  );
}

export default function SourceCard({
  sync,
  onSyncChannel,
  onDownload,
  title = "Lấy video từ YouTube",
  hint = "Video trùng link sẽ được bỏ qua",
  channelLabel = "Link kênh",
  channelPlaceholder = "https://www.youtube.com/@tenkenh/shorts",
  channelAction = "Đồng bộ kênh",
  videoLabel = "Link một video",
  videoPlaceholder = "https://www.youtube.com/shorts/...",
  videoAction = "Tải video",
}) {
  const [channel, setChannel] = useState("");
  const [video, setVideo] = useState("");
  const busy = Boolean(sync?.running);
  const channels = sync?.channels || [];

  return (
    <section className="card source">
      <div className="source-head">
        <strong>{title}</strong>
        <span className="meta">{hint}</span>
      </div>
      <div className="source-grid">
        <UrlField
          id="channel-url"
          label={channelLabel}
          placeholder={channelPlaceholder}
          value={channel}
          onChange={setChannel}
          busy={busy}
          action={channelAction}
          onSubmit={onSyncChannel}
        />
        <UrlField
          id="video-url"
          label={videoLabel}
          placeholder={videoPlaceholder}
          value={video}
          onChange={setVideo}
          busy={busy}
          action={videoAction}
          onSubmit={(url) => {
            onDownload(url).then((ok) => {
              if (ok) setVideo("");
            });
          }}
        />
      </div>
      {channels.length ? (
        <div className="chips" aria-label="Kênh đang theo dõi">
          {channels.map((item) => (
            <span className="chip" key={item.url || item.name}>{item.name || item.url}</span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
