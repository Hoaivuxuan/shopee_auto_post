import { useEffect, useState } from "react";

const EMPTY = {
  enabled: false,
  interval_minutes: 60,
  order: "oldest",
  token: "",
  privacy_status: "public",
  privacy_level: "PUBLIC_TO_EVERYONE",
};

export default function AutoPostCard({
  state,
  onSave,
  hint = "Mỗi lượt đăng một video ngắn đã sẵn sàng.",
  showPrivacy = false,
  showTiktokPrivacy = false,
}) {
  const auto = state?.auto || {};
  const next = state?.next;
  const [form, setForm] = useState(EMPTY);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!state?.auto || ready) return;
    setForm({
      enabled: Boolean(state.auto.enabled),
      interval_minutes: state.auto.interval_minutes || 60,
      order: state.auto.order || "oldest",
      token: "",
      privacy_status: state.youtube?.privacy_status || "public",
      privacy_level: state.tiktok?.privacy_level || "PUBLIC_TO_EVERYONE",
    });
    setReady(true);
  }, [state, ready]);

  const when = auto.enabled
    ? (auto.next_at ? `Lần kế: ${auto.next_at}` : "")
    : "Bật tự động rồi lưu để bắt đầu lịch.";

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  return (
    <article className="card">
      <strong>Đăng tự động</strong>
      <p className="meta">{hint}</p>
      <form
        style={{ marginTop: 16 }}
        onSubmit={(event) => {
          event.preventDefault();
          onSave(form).then(() => update("token", ""));
        }}
      >
        <div className="field">
          <label className="switch">
            <input type="checkbox" checked={form.enabled} onChange={(event) => update("enabled", event.target.checked)} />
            Bật đăng tự động
          </label>
        </div>
        <div className="row">
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="interval">Khoảng cách (phút)</label>
            <input
              id="interval"
              type="number"
              min="1"
              max="1440"
              value={form.interval_minutes}
              onChange={(event) => update("interval_minutes", Number(event.target.value))}
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="order">Thứ tự</label>
            <select id="order" value={form.order} onChange={(event) => update("order", event.target.value)}>
              <option value="oldest">Cũ nhất trước</option>
              <option value="newest">Mới nhất trước</option>
            </select>
          </div>
        </div>
        {showPrivacy ? (
          <div className="field">
            <label htmlFor="privacy">Quyền riêng tư YouTube</label>
            <select
              id="privacy"
              value={form.privacy_status}
              onChange={(event) => update("privacy_status", event.target.value)}
            >
              <option value="public">Công khai</option>
              <option value="unlisted">Không công khai</option>
              <option value="private">Riêng tư</option>
            </select>
          </div>
        ) : null}
        {showTiktokPrivacy ? (
          <div className="field">
            <label htmlFor="tt-privacy">Quyền riêng tư TikTok</label>
            <select
              id="tt-privacy"
              value={form.privacy_level || "PUBLIC_TO_EVERYONE"}
              onChange={(event) => update("privacy_level", event.target.value)}
            >
              <option value="PUBLIC_TO_EVERYONE">Công khai</option>
              <option value="MUTUAL_FOLLOW_FRIENDS">Bạn bè</option>
              <option value="FOLLOWER_OF_CREATOR">Người theo dõi</option>
              <option value="SELF_ONLY">Chỉ mình tôi</option>
            </select>
          </div>
        ) : null}
        <div className="actions" style={{ justifyContent: "flex-start" }}>
          <button className="primary" type="submit">Lưu thiết lập</button>
        </div>
        <p className="next">
          {next ? `Kế tiếp: ${next.title}. ${when}` : `Hết video chưa đăng. ${when}`}
        </p>
      </form>
    </article>
  );
}
