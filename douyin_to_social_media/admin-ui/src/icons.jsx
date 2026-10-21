/** Icon SVG gọn — dùng trong nút thao tác video. */

function Svg({ children, ...props }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export const Icons = {
  preview: (
    <Svg>
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
    </Svg>
  ),
  post: (
    <Svg>
      <path d="M12 19V5" />
      <path d="m5 12 7-7 7 7" />
    </Svg>
  ),
  delete: (
    <Svg>
      <path d="M3 6h18" />
      <path d="M8 6V4h8v2" />
      <path d="m19 6-.8 14a2 2 0 0 1-2 1.9H7.8a2 2 0 0 1-2-1.9L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
    </Svg>
  ),
  translate: (
    <Svg>
      <path d="M5 8h8" />
      <path d="M9 8c0 5-2 8-6 9" />
      <path d="M11 12c1.2 1.7 2.8 3 5 3.5" />
      <path d="m14 20 4-9 4 9" />
      <path d="M15.5 17h5" />
    </Svg>
  ),
  save: (
    <Svg>
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z" />
      <path d="M17 21v-8H7v8" />
      <path d="M7 3v5h8" />
    </Svg>
  ),
  spark: (
    <Svg>
      <path d="M12 3v4" />
      <path d="M12 17v4" />
      <path d="M3 12h4" />
      <path d="M17 12h4" />
      <path d="m5.6 5.6 2.8 2.8" />
      <path d="m15.6 15.6 2.8 2.8" />
      <path d="m18.4 5.6-2.8 2.8" />
      <path d="m8.4 15.6-2.8 2.8" />
      <circle cx="12" cy="12" r="2.5" />
    </Svg>
  ),
  refresh: (
    <Svg>
      <path d="M21 12a9 9 0 1 1-2.6-6.2" />
      <path d="M21 3v6h-6" />
    </Svg>
  ),
  shop: (
    <Svg>
      <path d="M4 7h16l-1.2 12.2A2 2 0 0 1 16.8 21H7.2a2 2 0 0 1-2-1.8L4 7Z" />
      <path d="M9 10V7a3 3 0 0 1 6 0v3" />
    </Svg>
  ),
  link: (
    <Svg>
      <path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1" />
      <path d="M14 11a5 5 0 0 0-7.1 0l-2 2a5 5 0 0 0 7.1 7.1l1.1-1.1" />
    </Svg>
  ),
};

export function IconButton({
  icon,
  label,
  onClick,
  disabled = false,
  danger = false,
  primary = false,
  busy = false,
}) {
  return (
    <button
      type="button"
      className={`icon-btn${danger ? " danger" : ""}${primary ? " primary" : ""}${busy ? " busy" : ""}`}
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
    >
      {busy ? <span className="icon-spinner" aria-hidden="true" /> : icon}
    </button>
  );
}
