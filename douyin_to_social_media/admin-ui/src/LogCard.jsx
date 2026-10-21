export default function LogCard({
  log,
  target,
  token,
  onToken,
  onSaveToken,
  youtube,
  tiktok,
  instagram,
  onAuthYoutube,
  onAuthTiktok,
  tiktokForm,
  onTiktokForm,
  onSaveTiktokCreds,
}) {
  const rows = (log || []).slice(0, 12);
  const label = {
    facebook: "Facebook",
    youtube: "YouTube",
    tiktok: "TikTok",
    instagram: "Instagram",
  }[target] || target;

  return (
    <article className="card">
      <strong>Nhật ký {label}</strong>
      <ul className="log">
        {rows.length ? rows.map((item) => (
          <li key={`${item.at}-${item.video_id}`}>
            <b>{item.ok ? "Đã đăng" : "Lỗi"}</b> · {item.at}
            <br />
            {item.title}
            {item.message ? <><br /><span className="meta">{item.message}</span></> : null}
          </li>
        )) : <li className="meta">Chưa có lượt đăng.</li>}
      </ul>

      {target === "youtube" ? (
        <div className="token-box">
          <strong>Ủy quyền YouTube</strong>
          <p className="meta">
            Đặt <code>data/douyin/client_secrets.json</code> rồi bấm ủy quyền.
            {youtube?.channel_title ? ` Kênh: ${youtube.channel_title}.` : ""}
            {youtube?.auth_job?.message ? ` ${youtube.auth_job.message}` : ""}
          </p>
          <p className="meta">
            Secrets: {youtube?.has_secrets ? "có" : "thiếu"} · Token: {youtube?.has_token ? "có" : "chưa"} ·{" "}
            {youtube?.has_auth ? "sẵn sàng" : "chưa sẵn sàng"}
          </p>
          <button
            className="primary"
            type="button"
            disabled={Boolean(youtube?.auth_job?.running) || !youtube?.has_secrets}
            onClick={onAuthYoutube}
          >
            {youtube?.auth_job?.running ? "Đang OAuth…" : "Ủy quyền YouTube"}
          </button>
        </div>
      ) : null}

      {target === "tiktok" ? (
        <div className="token-box">
          <strong>TikTok Developer</strong>
          <p className="meta">
            Tạo app trên developers.tiktok.com, bật Content Posting API + Direct Post, scope{" "}
            <code>video.publish</code>. Redirect: <code>http://127.0.0.1:8768/callback</code>
            {tiktok?.account_name ? ` · ${tiktok.account_name}` : ""}
            {tiktok?.auth_job?.message ? ` · ${tiktok.auth_job.message}` : ""}
          </p>
          <div className="field">
            <label htmlFor="tt-key">Client key</label>
            <input
              id="tt-key"
              value={tiktokForm.client_key}
              onChange={(event) => onTiktokForm("client_key", event.target.value)}
              placeholder="client_key"
              autoComplete="off"
            />
          </div>
          <div className="field">
            <label htmlFor="tt-secret">Client secret</label>
            <input
              id="tt-secret"
              type="password"
              value={tiktokForm.client_secret}
              onChange={(event) => onTiktokForm("client_secret", event.target.value)}
              placeholder="client_secret"
              autoComplete="off"
            />
          </div>
          <div className="row-actions" style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="primary" type="button" onClick={onSaveTiktokCreds}>
              Lưu key
            </button>
            <button
              className="ghost"
              type="button"
              disabled={Boolean(tiktok?.auth_job?.running) || !(tiktok?.has_client || (tiktokForm.client_key && tiktokForm.client_secret))}
              onClick={onAuthTiktok}
            >
              {tiktok?.auth_job?.running ? "Đang OAuth…" : "Ủy quyền TikTok"}
            </button>
          </div>
          <p className="meta" style={{ marginTop: 8 }}>
            Client: {tiktok?.has_client ? "có" : "thiếu"} · Token: {tiktok?.has_token ? "có" : "chưa"} ·{" "}
            {tiktok?.has_auth ? "sẵn sàng" : (tiktok?.error || "chưa sẵn sàng")}
          </p>
        </div>
      ) : null}

      {target === "instagram" ? (
        <form
          className="token-box"
          onSubmit={(event) => {
            event.preventDefault();
            onSaveToken();
          }}
        >
          <strong>Instagram (Meta)</strong>
          <p className="meta">
            Dùng Page Access Token của Page đã gắn Instagram Professional. Hệ thống tự đọc{" "}
            <code>instagram_business_account</code>. Có thể để trống nếu đã lưu token ở tab Facebook.
            {instagram?.account_name ? ` Tài khoản: @${instagram.account_name}.` : ""}
            {instagram?.error ? ` ${instagram.error}` : ""}
          </p>
          <div className="field">
            <label htmlFor="ig-token">Page Access Token (tuỳ chọn ghi đè)</label>
            <input
              id="ig-token"
              type="password"
              autoComplete="off"
              placeholder="Dán token Page"
              value={token}
              onChange={(event) => onToken(event.target.value)}
            />
          </div>
          <button className="primary" type="submit" disabled={!token.trim()}>Lưu token IG</button>
        </form>
      ) : null}

      {target === "facebook" ? (
        <form
          className="token-box"
          onSubmit={(event) => {
            event.preventDefault();
            onSaveToken();
          }}
        >
          <strong>Page Access Token</strong>
          <p className="meta">Token hết hạn thì dán token mới vào đây rồi bấm Lưu token.</p>
          <div className="field">
            <label htmlFor="token">Token mới của đúng Page này</label>
            <input
              id="token"
              type="password"
              autoComplete="off"
              placeholder="Dán token mới"
              value={token}
              onChange={(event) => onToken(event.target.value)}
            />
          </div>
          <button className="primary" type="submit" disabled={!token.trim()}>Lưu token</button>
        </form>
      ) : null}
    </article>
  );
}
