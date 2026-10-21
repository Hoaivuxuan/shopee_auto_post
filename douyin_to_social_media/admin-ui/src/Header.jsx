import { TARGETS, targetMeta } from "./targets.js";

export default function Header({ page, tab, onTab, target, onTarget }) {
  const name = page?.name || "Chưa kết nối";
  const meta = targetMeta(target);
  return (
    <header className="top">
      <div>
        <div className="source-switch target-switch" role="tablist" aria-label="Đích đăng">
          {TARGETS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={target === item.id ? "on" : ""}
              onClick={() => onTarget(item.id)}
            >
              {item.short}
            </button>
          ))}
        </div>
        <h1>Douyin <span>→</span> {meta.short}</h1>
        <p className="sub">
          {meta.blurb}
          {" · "}
          {page?.url ? <a href={page.url} target="_blank" rel="noreferrer">{name}</a> : name}
          {" · "}{meta.unit} ID {page?.id || "—"}
          {" · "}{page?.has_token ? meta.authReady : meta.authMissing}
        </p>
      </div>
      <nav className="tabs" aria-label="Màn hình">
        <button type="button" className={tab === "work" ? "on" : ""} onClick={() => onTab("work")}>
          Làm việc
        </button>
        <button type="button" className={tab === "review" ? "on" : ""} onClick={() => onTab("review")}>
          Xem trước
        </button>
        <button type="button" className={tab === "config" ? "on" : ""} onClick={() => onTab("config")}>
          Cấu hình
        </button>
      </nav>
    </header>
  );
}
