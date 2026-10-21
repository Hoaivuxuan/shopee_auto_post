import { TARGETS } from "./targets.js";

export default function PlatformsCard({ target }) {
  return (
    <article className="card">
      <strong>Đích đăng</strong>
      <p className="meta">Cùng kho Douyin + video ngắn AI — mỗi nền tảng một hàng đăng riêng.</p>
      <ul className="platform-list">
        {TARGETS.map((item) => (
          <li key={item.id} className={`platform-item ${target === item.id ? "ready" : "soon"}`}>
            <div>
              <span className="platform-name">{item.title}</span>
              <span className="platform-note">{item.blurb}</span>
            </div>
            <span className="platform-badge">{target === item.id ? "Đang xem" : "Khác tab"}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}
