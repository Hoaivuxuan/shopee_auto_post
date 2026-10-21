import { useEffect, useState } from "react";

function SyncSchedule({ syncAuto, onSave, label = "Đồng bộ kênh đã lưu tự động" }) {
  const [form, setForm] = useState({ enabled: false, interval_minutes: 60 });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!syncAuto || ready) return;
    setForm({
      enabled: Boolean(syncAuto.enabled),
      interval_minutes: syncAuto.interval_minutes || 60,
    });
    setReady(true);
  }, [syncAuto, ready]);

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSave(form).then((saved) => {
          if (!saved) return;
          setForm({
            enabled: Boolean(saved.enabled),
            interval_minutes: saved.interval_minutes || 60,
          });
        });
      }}
    >
      <label className="switch">
        <input
          type="checkbox"
          checked={form.enabled}
          onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
        />
        {label}
      </label>
      <div className="field" style={{ marginTop: 10, marginBottom: 8 }}>
        <label htmlFor="sync-interval">Khoảng cách (phút)</label>
        <input
          id="sync-interval"
          type="number"
          min="1"
          max="1440"
          value={form.interval_minutes}
          onChange={(event) => setForm((current) => ({
            ...current,
            interval_minutes: Number(event.target.value),
          }))}
        />
      </div>
      <button className="ghost" type="submit">Lưu lịch đồng bộ</button>
      <p className="sub">
        {syncAuto?.enabled && syncAuto?.next_at
          ? `Lần kế: ${syncAuto.next_at}`
          : "Bật rồi lưu để chạy theo lịch."}
      </p>
    </form>
  );
}

export default function ActionsCard({ state, onSync, onSaveSyncAuto, onToggleSuggest, onPostNext, showSuggest = true, syncLabel = "Đồng bộ kênh đã lưu" }) {
  const sync = state?.sync;
  const suggestAuto = state?.suggest_auto;
  const posting = Boolean(state?.job?.running);
  const next = state?.next;

  return (
    <section className="card">
      <strong>Thao tác</strong>
      <div className="stack">
        <button className="ghost" type="button" disabled={Boolean(sync?.running)} onClick={onSync}>
          {sync?.running ? "Đang đồng bộ…" : syncLabel}
        </button>
        <SyncSchedule
          syncAuto={state?.sync_auto}
          onSave={onSaveSyncAuto}
          label={showSuggest ? "Đồng bộ kênh đã lưu tự động" : "Đồng bộ tài khoản đã lưu tự động"}
        />
        {showSuggest ? (
          <button className={suggestAuto?.enabled ? "primary" : "ghost"} type="button" onClick={onToggleSuggest}>
            {suggestAuto?.enabled ? "Tắt gợi ý tự động" : "Bật gợi ý tự động"}
          </button>
        ) : null}
        <button className="ghost" type="button" disabled={posting || !next} onClick={onPostNext}>
          Đăng video kế tiếp
        </button>
      </div>
      <p className="next">{next ? `Kế tiếp: ${next.title}` : "Hết video chưa đăng."}</p>
      {sync?.message ? <p className="sub">{sync.message}</p> : null}
      {showSuggest && suggestAuto?.message ? <p className="sub">{suggestAuto.message}</p> : null}
    </section>
  );
}
