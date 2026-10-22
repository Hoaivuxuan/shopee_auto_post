import { useEffect, useRef, useState } from "react";
import { fetchAutoPost, saveAutoPost } from "./api.js";

const WEEKDAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

function todayKey() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh" }).format(new Date());
}

function addDays(iso, count) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + count);
  return date.toISOString().slice(0, 10);
}

function showDay(iso) {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function showShort(iso) {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

function sameNames(left, right) {
  if (left.length !== right.length) return false;
  return left.every((name) => right.includes(name));
}

function sameDates(left, right) {
  if (left.length !== right.length) return false;
  return left.every((day, index) => day === right[index]);
}

function isoWeek(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const weekday = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - weekday);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
  return `${date.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

function weekDates(weekValue) {
  const match = /^(\d{4})-W(\d{2})$/.exec(weekValue || "");
  if (!match) return [];
  const year = Number(match[1]);
  const week = Number(match[2]);
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const weekday = jan4.getUTCDay() || 7;
  const monday = new Date(jan4);
  monday.setUTCDate(jan4.getUTCDate() - weekday + 1 + (week - 1) * 7);
  const dates = [];
  for (let index = 0; index < 7; index += 1) {
    const day = new Date(monday);
    day.setUTCDate(monday.getUTCDate() + index);
    dates.push(day.toISOString().slice(0, 10));
  }
  return dates;
}

function shiftMonth(cursor, delta) {
  const [year, month] = cursor.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1 + delta, 1));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

function monthCells(cursor) {
  const [year, month] = cursor.split("-").map(Number);
  const first = new Date(Date.UTC(year, month - 1, 1));
  const startPad = (first.getUTCDay() || 7) - 1;
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const cells = [];
  for (let index = 0; index < startPad; index += 1) cells.push("");
  for (let day = 1; day <= days; day += 1) {
    cells.push(`${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`);
  }
  return cells;
}

function datesLabel(list) {
  if (!list.length) return "Chưa chọn ngày";
  if (list.length === 1) return showDay(list[0]);
  const contiguous = list.every((day, index) => index === 0 || day === addDays(list[index - 1], 1));
  if (contiguous) return `${showShort(list[0])} – ${showShort(list[list.length - 1])} · ${list.length} ngày`;
  if (list.length <= 4) return list.map(showShort).join(", ");
  return `${list.length} ngày đã chọn`;
}

function DayCalendar({ dates, today, last, onToggle }) {
  const [cursor, setCursor] = useState((dates[0] || today).slice(0, 7));
  const cells = monthCells(cursor);
  return (
    <div className="auto-cal" role="dialog" aria-label="Chọn nhiều ngày">
      <div className="auto-cal-nav">
        <button type="button" aria-label="Tháng trước" onClick={() => setCursor(shiftMonth(cursor, -1))}>‹</button>
        <b>Tháng {Number(cursor.slice(5))}/{cursor.slice(0, 4)}</b>
        <button type="button" aria-label="Tháng sau" onClick={() => setCursor(shiftMonth(cursor, 1))}>›</button>
      </div>
      <div className="auto-cal-grid auto-cal-head">
        {WEEKDAYS.map((label) => <span key={label}>{label}</span>)}
      </div>
      <div className="auto-cal-grid">
        {cells.map((iso, index) => {
          if (!iso) return <span key={`pad-${index}`} />;
          const enabled = iso >= today && iso <= last;
          const selected = dates.includes(iso);
          return (
            <button
              key={iso}
              type="button"
              className={selected ? "on" : ""}
              disabled={!enabled}
              aria-pressed={selected}
              onClick={() => onToggle(iso)}
            >
              {Number(iso.slice(8))}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function AutoPost({ pageId, pageName, posting, categories, readyItems, onToast }) {
  const today = todayKey();
  const last = addDays(today, 29);
  const [perDay, setPerDay] = useState(6);
  const [chosen, setChosen] = useState([]);
  const [dates, setDates] = useState([today]);
  const [dateMode, setDateMode] = useState("day");
  const [datesTouched, setDatesTouched] = useState(false);
  const [calOpen, setCalOpen] = useState(false);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const calBox = useRef(null);
  const names = categories || [];
  const readyNames = readyItems || [];
  const activeDates = [...dates].filter((day, index, list) => day && list.indexOf(day) === index).sort();

  async function refresh() {
    const data = await fetchAutoPost();
    setStatus(data);
    return data;
  }

  function applyForm(data) {
    setPerDay(data.per_day || 6);
    setChosen(Array.isArray(data.categories) ? data.categories : []);
    const savedDates = Array.isArray(data.dates) ? data.dates.filter(Boolean) : [];
    setDates(savedDates.length ? savedDates : [today]);
    setDateMode(data.date_mode === "days" || data.date_mode === "week" ? data.date_mode : "day");
    setDatesTouched(false);
    setCalOpen(false);
  }

  useEffect(() => {
    refresh()
      .then(applyForm)
      .catch((err) => onToast(err.message || String(err)));
  }, []);

  useEffect(() => {
    if (!status?.running) return undefined;
    const timer = setInterval(() => {
      refresh().catch(() => {});
    }, 4000);
    return () => clearInterval(timer);
  }, [status?.running]);

  useEffect(() => {
    if (!calOpen) return undefined;
    function onPointer(event) {
      if (calBox.current && !calBox.current.contains(event.target)) setCalOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [calOpen]);

  function chooseMode(next) {
    setDateMode(next);
    setCalOpen(false);
    const anchor = activeDates[0] || today;
    let nextDates = activeDates.length ? activeDates : [today];
    if (next === "day") nextDates = [anchor];
    if (next === "week") nextDates = weekDates(isoWeek(anchor)).filter((day) => day >= today && day <= last);
    setDates(nextDates);
    setDatesTouched(true);
  }

  function toggleDate(iso) {
    setDatesTouched(true);
    setDates((current) => {
      const has = current.includes(iso);
      const next = has ? current.filter((day) => day !== iso) : [...current, iso];
      return next.sort();
    });
  }

  async function save(next) {
    if (!posting) {
      onToast("Mạng này chưa có API đăng bài");
      return;
    }
    if (next && !pageId) {
      onToast("Hãy chọn Page Facebook trước");
      return;
    }
    const count = Number(perDay);
    if (!Number.isInteger(count) || count < 1 || count > 48) {
      onToast("Số bài trong ngày từ 1 đến 48");
      return;
    }
    const pickedDates = activeDates.filter((day) => day >= today && day <= last);
    if (next && !pickedDates.length) {
      onToast("Hãy chọn ít nhất một ngày, trong vòng 29 ngày tới");
      return;
    }
    const picked = chosen.length ? names.filter((name) => chosen.includes(name)) : names;
    const allOn = !names.length || picked.length === names.length;
    if (next && names.length && picked.length === 0) {
      onToast("Hãy chọn ít nhất một mục sản phẩm");
      return;
    }
    const scope = allOn ? "mọi mục" : picked.join(", ");
    const scheduled = (status?.slots || []).filter((slot) => slot.ok && pickedDates.includes((slot.at || "").slice(0, 10))).length;
    const total = count * Math.max(pickedDates.length, 1);
    const extra = Math.max(total - scheduled, 0);
    if (next) {
      const when = datesLabel(pickedDates);
      const question = extra > 0
        ? `Xếp ${count} bài mỗi ngày cho ${when}, thuộc ${scope}, lên ${pageName || "trang đã chọn"}? Bài được chia đều suốt ngày, đến 23:59. Hôm nay bài đầu cách hiện tại 12 phút vì Facebook yêu cầu hẹn trước.`
        : `Các ngày đã chọn đã đủ bài. Giữ nguyên lịch này?`;
      if (!window.confirm(question)) return;
    }
    setBusy(true);
    try {
      const data = await saveAutoPost(next, count, pageId || "", allOn ? [] : picked, pickedDates, dateMode);
      setStatus(data);
      applyForm(data);
      onToast(data.message || (next ? "Đã bật tự động đăng" : "Đã tắt tự động đăng"));
    } catch (err) {
      onToast(err.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  const enabled = Boolean(status?.enabled);
  const savedCategories = Array.isArray(status?.categories) ? status.categories : [];
  const savedDates = Array.isArray(status?.dates) ? [...status.dates].sort() : [];
  const activeCategories = savedCategories.length ? savedCategories : names;
  const picked = names.filter((name) => chosen.includes(name));
  const shown = chosen.length ? picked : names;
  const categoriesChanged = enabled && !sameNames(activeCategories, shown.length ? shown : names);
  const countChanged = enabled && Number(perDay) !== Number(status?.per_day);
  const datesChanged = enabled && datesTouched && !sameDates(savedDates, activeDates);
  const selectionChanged = countChanged || categoriesChanged || datesChanged;
  const readyCount = readyNames.filter((name) => shown.includes(name) || !names.length).length;
  const categoryValue = shown.length === 1 ? shown[0] : "all";
  const buttonLabel = status?.running
    ? "Đang xếp lịch..."
    : !enabled
      ? "Bật tự động đăng"
      : selectionChanged
        ? "Áp dụng lịch"
        : "Tắt tự động đăng";
  const scopeLabel = shown.length && shown.length !== names.length ? shown.join(", ") : "mọi mục";
  const locked = busy || status?.running;
  const weekValue = isoWeek(activeDates[0] || today);
  return (
    <section className="auto-post" title={`Lấy bài sẵn sàng thuộc ${scopeLabel}, chưa đăng lên ${pageName || "trang đang chọn"}. Chỉ xếp các ngày đã chọn.`}>
      <span className="ops-label">Tự động đăng</span>
      <label>
        Mục
        <select
          aria-label="Mục tự động đăng"
          value={names.includes(categoryValue) ? categoryValue : "all"}
          onChange={(event) => {
            const next = event.target.value;
            setChosen(next === "all" ? [] : [next]);
          }}
        >
          <option value="all">Mọi mục</option>
          {names.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
      </label>
      <label>
        Bài/ngày
        <input
          type="number"
          min="1"
          max="48"
          value={perDay}
          onChange={(event) => setPerDay(event.target.value)}
        />
      </label>
      <label>
        Lịch
        <select aria-label="Kiểu lịch" value={dateMode} disabled={locked} onChange={(event) => chooseMode(event.target.value)}>
          <option value="day">Một ngày</option>
          <option value="days">Nhiều ngày</option>
          <option value="week">Theo tuần</option>
        </select>
      </label>
      {dateMode === "day" ? (
        <label>
          Ngày
          <input
            type="date"
            aria-label="Ngày đăng"
            min={today}
            max={last}
            value={activeDates[0] || today}
            disabled={locked}
            onChange={(event) => {
              if (!event.target.value) return;
              setDates([event.target.value]);
              setDatesTouched(true);
            }}
          />
        </label>
      ) : null}
      {dateMode === "week" ? (
        <label>
          Tuần
          <input
            type="week"
            aria-label="Tuần đăng"
            min={isoWeek(today)}
            max={isoWeek(last)}
            value={weekValue}
            disabled={locked}
            onChange={(event) => {
              const next = weekDates(event.target.value).filter((day) => day >= today && day <= last);
              if (!next.length) {
                onToast("Tuần này không còn ngày nào trong vòng 29 ngày tới");
                return;
              }
              setDates(next);
              setDatesTouched(true);
            }}
          />
        </label>
      ) : null}
      {dateMode === "days" ? (
        <div className="auto-cal-wrap" ref={calBox}>
          <button type="button" className="ghost" disabled={locked} aria-expanded={calOpen} onClick={() => setCalOpen((open) => !open)}>
            {calOpen ? "Đóng lịch" : "Chọn ngày"}
          </button>
          {calOpen ? (
            <DayCalendar dates={activeDates} today={today} last={last} onToggle={toggleDate} />
          ) : null}
        </div>
      ) : null}
      <button
        type="button"
        className={enabled && !selectionChanged ? "ghost" : ""}
        aria-pressed={enabled}
        disabled={locked}
        onClick={() => save(selectionChanged ? true : !enabled)}
      >
        {buttonLabel}
      </button>
      <span className="meta">{datesLabel(activeDates)}</span>
      <span className="meta">{readyCount} sẵn sàng{enabled ? " · đang bật" : ""}</span>
      <p className="auto-note">
        Chỉ xếp các ngày đã chọn. Mỗi ngày lấy số bài đã nhập và chia đều suốt ngày, từ 00:00 đến 23:59. Hôm nay bài đầu cách hiện tại 12 phút vì Facebook yêu cầu hẹn trước. Tắt tự động không hủy bài đã hẹn trên Facebook.
      </p>
      {status?.message ? <span className="meta">{status.message}</span> : null}
      {status?.slots?.length ? (
        <details className="auto-slots-wrap">
          <summary>Lịch đã xếp ({status.slots.length}){status.running ? " · đang xếp" : ""}</summary>
          <ol className="auto-slots">
            {status.slots.map((slot) => (
              <li key={`${slot.item_id}-${slot.at}`}>
                {slot.ok ? slot.at : "Chưa hẹn"} · {slot.name || slot.item_id}
                {slot.error ? ` — ${slot.error}` : ""}
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </section>
  );
}
