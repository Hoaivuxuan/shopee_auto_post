import { useEffect, useRef, useState } from "react";
import {
  cancelFacebookLogin,
  facebookLoginFrame,
  facebookLoginStatus,
  sendFacebookLoginEvent,
  startFacebookLogin,
} from "./api.js";

export default function FacebookLogin({ onClose, onReady }) {
  const [status, setStatus] = useState("starting");
  const [message, setMessage] = useState("Đang mở trang đăng nhập...");
  const [frame, setFrame] = useState("");
  const [draft, setDraft] = useState("");
  const [fields, setFields] = useState({});
  const [values, setValues] = useState({ email: "", pass: "" });
  const [layout, setLayout] = useState({ w: 0, h: 0, nw: 0, nh: 0 });
  const [localError, setLocalError] = useState("");
  const frameRef = useRef("");
  const shownRef = useRef("");
  const doneRef = useRef(false);
  const screenRef = useRef(null);
  const imgRef = useRef(null);
  const queueRef = useRef(Promise.resolve());
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  function rememberFrame(next) {
    frameRef.current = next || "";
    setFrame(next || "");
  }

  function onFrameLoad() {
    if (shownRef.current && shownRef.current !== frameRef.current) {
      URL.revokeObjectURL(shownRef.current);
    }
    shownRef.current = frameRef.current;
  }

  useEffect(() => {
    let stop = false;
    startFacebookLogin().catch((err) => {
      if (!stop) setLocalError(err.message || String(err));
    });
    const timer = setInterval(async () => {
      if (stop || doneRef.current) return;
      try {
        const state = await facebookLoginStatus();
        setStatus(state.status || "");
        setMessage(state.message || "");
        setFields(state.fields || {});
        if (state.status === "logged_in") {
          doneRef.current = true;
          onReadyRef.current();
          return;
        }
        if (state.status === "waiting" || state.status === "starting") {
          const url = await facebookLoginFrame();
          if (!stop && url) rememberFrame(url);
        }
      } catch (err) {
        if (!stop) setLocalError(err.message || String(err));
      }
    }, 700);
    return () => {
      stop = true;
      clearInterval(timer);
      if (!doneRef.current) cancelFacebookLogin().catch(() => {});
      if (shownRef.current) URL.revokeObjectURL(shownRef.current);
      if (frameRef.current && frameRef.current !== shownRef.current) URL.revokeObjectURL(frameRef.current);
    };
  }, []);

  async function close() {
    try {
      await cancelFacebookLogin();
    } catch {
      /* cửa sổ server tự đóng khi hết giờ */
    }
    onClose();
  }

  function measure() {
    const img = imgRef.current;
    if (!img) return;
    setLayout({
      w: img.clientWidth,
      h: img.clientHeight,
      nw: img.naturalWidth,
      nh: img.naturalHeight,
    });
  }

  function fieldStyle(box) {
    if (!box || !layout.nw || !layout.nh || !layout.w || !layout.h) return null;
    return {
      left: (box.x / layout.nw) * layout.w,
      top: (box.y / layout.nh) * layout.h,
      width: (box.width / layout.nw) * layout.w,
      height: (box.height / layout.nh) * layout.h,
    };
  }

  function sendLater(body) {
    const run = () => sendFacebookLoginEvent(body).catch((err) => {
      setLocalError(err.message || String(err));
    });
    queueRef.current = queueRef.current.then(run, run);
    return queueRef.current;
  }

  function onFill(name, text) {
    setValues((prev) => ({ ...prev, [name]: text }));
    return sendLater({ action: "fill", field: name, text });
  }

  function submitLogin() {
    return sendLater({ action: "submit" });
  }

  async function onImageClick(event) {
    const img = event.currentTarget;
    screenRef.current?.focus();
    const rect = img.getBoundingClientRect();
    if (!rect.width || !rect.height || !img.naturalWidth || !img.naturalHeight) return;
    const x = ((event.clientX - rect.left) * img.naturalWidth) / rect.width;
    const y = ((event.clientY - rect.top) * img.naturalHeight) / rect.height;
    try {
      await sendFacebookLoginEvent({ action: "click", x, y });
    } catch (err) {
      setLocalError(err.message || String(err));
    }
  }

  async function onTypeKey(event) {
    if (event.target.closest("input, textarea, button")) return;
    const key = event.key;
    if (key === "Shift" || key === "Control" || key === "Alt" || key === "Meta") return;
    const named = ["Enter", "Backspace", "Tab", "Escape", "ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"];
    if (key.length !== 1 && !named.includes(key)) return;
    event.preventDefault();
    try {
      if (key.length === 1) await sendFacebookLoginEvent({ action: "type", text: key });
      else await sendFacebookLoginEvent({ action: "press", key });
    } catch (err) {
      setLocalError(err.message || String(err));
    }
  }

  async function onWheel(event) {
    event.preventDefault();
    try {
      await sendFacebookLoginEvent({ action: "scroll", dy: event.deltaY });
    } catch (err) {
      setLocalError(err.message || String(err));
    }
  }

  async function sendDraft(event) {
    event.preventDefault();
    const text = draft;
    if (!text) {
      submitLogin();
      return;
    }
    setDraft("");
    try {
      await sendFacebookLoginEvent({ action: "type", text });
    } catch (err) {
      setLocalError(err.message || String(err));
    }
  }

  async function press(key) {
    try {
      await sendFacebookLoginEvent({ action: "press", key });
    } catch (err) {
      setLocalError(err.message || String(err));
    }
  }

  return (
    <section className="fb-login">
      <div className="group-head">
        <div>
          <h2>Đăng nhập Facebook</h2>
          <p className="meta">{message || "Gõ vào ô viền xanh, rồi bấm nút Đăng nhập màu xanh."}</p>
        </div>
        <button type="button" className="ghost" onClick={close}>Đóng</button>
      </div>
      {localError ? <p className="banner">{localError}</p> : null}
      <form className="group-form" onSubmit={sendDraft}>
        <label>
          Gõ vào ô đang chọn
          <input
            value={draft}
            autoComplete="off"
            placeholder="Email, mật khẩu hoặc mã xác nhận"
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
        <button type="submit">Gõ</button>
        <button type="button" onClick={submitLogin}>Đăng nhập</button>
        <button type="button" className="ghost" onClick={() => press("Backspace")}>Xóa lùi</button>
      </form>
      <div
        className="fb-screen"
        tabIndex={0}
        ref={screenRef}
        onKeyDown={onTypeKey}
      >
        {frame
          ? (
            <div className="fb-stage">
              <img
                ref={imgRef}
                src={frame}
                alt="Trang đăng nhập Facebook"
                onLoad={() => {
                  onFrameLoad();
                  measure();
                }}
                onClick={onImageClick}
                onWheel={onWheel}
              />
              {["email", "pass"].map((name) => {
                const style = fieldStyle(fields[name]);
                if (!style) return null;
                return (
                  <input
                    key={name}
                    className="fb-field"
                    style={style}
                    type={name === "pass" ? "password" : "text"}
                    autoComplete="off"
                    aria-label={name === "pass" ? "Mật khẩu" : "Email hoặc số di động"}
                    placeholder={name === "pass" ? "Mật khẩu" : "Email hoặc số di động"}
                    value={values[name]}
                    onChange={(event) => onFill(name, event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key !== "Enter") return;
                      event.preventDefault();
                      submitLogin();
                    }}
                  />
                );
              })}
              {fieldStyle(fields.login) ? (
                <button
                  type="button"
                  className="fb-submit"
                  style={fieldStyle(fields.login)}
                  onClick={submitLogin}
                >
                  Đăng nhập
                </button>
              ) : null}
            </div>
          )
          : <p className="meta">{status === "error" ? "Không mở được Facebook." : "Đang tải khung hình..."}</p>}
      </div>
    </section>
  );
}
