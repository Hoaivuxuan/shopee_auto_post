export const TARGETS = [
  {
    id: "facebook",
    short: "Facebook",
    title: "Douyin → Facebook",
    blurb: "Đăng video ngắn lên Facebook Page",
    unit: "Page",
    authReady: "đã lưu token",
    authMissing: "chưa có token",
    postLabel: "Đăng FB",
    reviewLabel: "Đăng Facebook",
  },
  {
    id: "youtube",
    short: "YouTube",
    title: "Douyin → YouTube",
    blurb: "Đăng Shorts lên kênh YouTube",
    unit: "Channel",
    authReady: "đã ủy quyền",
    authMissing: "chưa ủy quyền",
    postLabel: "Đăng YT",
    reviewLabel: "Đăng YouTube",
  },
  {
    id: "tiktok",
    short: "TikTok",
    title: "Douyin → TikTok",
    blurb: "Đăng video lên TikTok (Content Posting API)",
    unit: "Account",
    authReady: "đã ủy quyền",
    authMissing: "chưa ủy quyền",
    postLabel: "Đăng TT",
    reviewLabel: "Đăng TikTok",
  },
  {
    id: "instagram",
    short: "Instagram",
    title: "Douyin → Instagram",
    blurb: "Đăng Reels lên Instagram Professional",
    unit: "IG",
    authReady: "đã liên kết",
    authMissing: "chưa liên kết",
    postLabel: "Đăng IG",
    reviewLabel: "Đăng Instagram",
  },
];

export function targetMeta(id) {
  return TARGETS.find((item) => item.id === id) || TARGETS[0];
}

export function normalizeTarget(raw) {
  return TARGETS.some((item) => item.id === raw) ? raw : "facebook";
}
