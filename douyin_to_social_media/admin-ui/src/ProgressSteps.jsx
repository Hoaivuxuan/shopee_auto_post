import { useEffect, useState } from "react";

const STATUS_LABEL = {
  pending: "Chờ",
  running: "Đang chạy",
  done: "Xong",
  error: "Lỗi",
  skipped: "Bỏ qua",
};

const DEFAULT_AI_STEPS = [
  { id: "asr", label: "ASR — nhận dạng tiếng Trung", status: "pending" },
  { id: "highlight", label: "Chọn highlight", status: "pending" },
  { id: "cut", label: "Cắt / ghép video", status: "pending" },
  { id: "script", label: "Viết kịch bản tiếng Việt", status: "pending" },
  { id: "voice", label: "TTS lồng tiếng", status: "pending" },
  { id: "mux", label: "Ghép audio vào video", status: "pending" },
  { id: "subtitle", label: "Burn phụ đề", status: "pending" },
];

function elapsedText(startedAt) {
  if (!startedAt) return "";
  const start = Date.parse(String(startedAt).replace(" ", "T") + "+07:00");
  if (!Number.isFinite(start)) return "";
  const sec = Math.max(0, Math.floor((Date.now() - start) / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m} phút ${s} giây` : `${s} giây`;
}

export default function ProgressSteps({
  title = "Tiến trình",
  progress,
  emptyHint = "",
  forceShow = false,
}) {
  const [, tick] = useState(0);
  const status = progress?.status || "idle";
  const running = status === "running";

  useEffect(() => {
    if (!running) return undefined;
    const timer = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  let steps = progress?.steps;
  if ((!steps || !steps.length) && (running || forceShow || status === "done" || status === "error")) {
    steps = DEFAULT_AI_STEPS.map((step, index) => (
      index === 0 && running
        ? { ...step, status: "running", detail: progress?.message || "Đang khởi động…" }
        : step
    ));
  }

  if (!progress || (!steps?.length && !forceShow && status === "idle")) {
    if (!emptyHint) return null;
    return (
      <div className="progress-panel">
        <strong>{title}</strong>
        <p className="meta">{emptyHint}</p>
      </div>
    );
  }

  const doneCount = (steps || []).filter((s) => s.status === "done").length;
  const total = (steps || []).length || 0;
  const current = (steps || []).find((s) => s.status === "running");
  const elapsed = elapsedText(progress.started_at || progress.startedAt);
  const headline = status === "done"
    ? (progress.message || "Hoàn thành")
    : status === "error"
      ? (progress.error || progress.message || "Có lỗi")
      : status === "running"
        ? (progress.message || current?.label || "Đang xử lý…")
        : (progress.message || "");

  return (
    <div className={`progress-panel status-${status}${forceShow || running ? " visible" : ""}`}>
      <div className="progress-head">
        <strong>{title}</strong>
        {status && status !== "idle" ? (
          <span className={`progress-badge ${status}`}>
            {status === "done" ? "Thành công" : status === "error" ? "Lỗi" : status === "running" ? "Đang chạy" : status}
          </span>
        ) : null}
      </div>
      {running || status === "done" || status === "error" ? (
        <div className="progress-stats">
          <span>{doneCount}/{total} bước</span>
          {current ? <span>· {current.label}</span> : null}
          {elapsed && running ? <span>· đã chạy {elapsed}</span> : null}
          {progress.finished_at && !running ? <span>· xong lúc {progress.finished_at}</span> : null}
        </div>
      ) : null}
      {headline ? (
        <p className={`progress-summary${status === "error" ? " ai-error" : ""}`}>{headline}</p>
      ) : null}
      {progress.permalink ? (
        <p className="meta">
          <a href={progress.permalink} target="_blank" rel="noreferrer">Mở bài đã đăng</a>
        </p>
      ) : null}
      <ol className="progress-steps">
        {(steps || []).map((step) => (
          <li key={step.id} className={`progress-step ${step.status}`}>
            <span className="progress-dot" aria-hidden="true" />
            <div className="progress-body">
              <div className="progress-line">
                <b>{step.label}</b>
                <span className="progress-state">{STATUS_LABEL[step.status] || step.status}</span>
              </div>
              {step.detail && step.status !== "error" ? (
                <div className="meta">{step.detail}</div>
              ) : null}
              {step.error ? (
                <div className="meta ai-error">{step.error}</div>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
