export const STATUS = {
  pending: ["pending", "Chưa đăng"],
  published: ["published", "Đã đăng"],
  error: ["error", "Lỗi"],
  missing: ["missing", "Thiếu file"],
  posting: ["posting", "Đang đăng"],
};

export const FILTERS = [
  ["all", "Tất cả"],
  ["pending", "Chưa đăng"],
  ["published", "Đã đăng"],
  ["error", "Lỗi"],
];

export const OFFER_FILTERS = [
  ["all", "Tất cả"],
  ["yes", "Đã có gợi ý"],
];

export function hasOffer(video) {
  return Array.isArray(video?.offers) && video.offers.length > 0;
}
