export const SEED_USER = 700008

/** user: "fresh" = a random user with no history, "seed" = the pre-loaded demo user, a number = a fixed userId, null = type one. */
export type CaseUser = 'fresh' | 'seed' | number | null

export interface CaseDef {
  id: string
  label: string
  kind: 'user' | 'event' | 'system'
  user: CaseUser
  /** Show the demo-movie panel (cases 3, 4 and 9). */
  movies?: boolean
  title: string
  what: string
  rec: string
  streaming: string
  retrain: string
  chot: string
  decision?: string
  how: string[]
}

/**
 * The 12 test cases of the old admin page, copied from the use-case table the team agreed on (Google Doc "Notes - BDA501", tab 5).
 * Differences from the old text, both on purpose: the star emoji in the steps is written as the word "sao" (no emoji
 * anywhere in the UI), and the decision of case 1 now says popularity uses the weighted rating, which is live.
 */
export const CASES: CaseDef[] = [
  {
    id: 'free',
    label: '— Nhập userId tự do —',
    kind: 'user',
    user: null,
    title: 'Tự chọn userId',
    what: 'Nhập bất kỳ userId nào ở ô bên cạnh rồi bấm Tải gợi ý.',
    rec: 'Tuỳ lịch sử của user đó.',
    streaming: '—',
    retrain: '—',
    chot: '—',
    how: [],
  },
  {
    id: 'c1',
    label: '1. User có tài khoản, chưa rating',
    kind: 'user',
    user: 'fresh',
    title: 'Case 1 — User có tài khoản, chưa rating',
    what: 'interaction_count = 0',
    rec: 'Popularity Top-N',
    streaming: 'Không',
    retrain: 'Không',
    chot: 'weighted rating (Bayesian/IMDb-style)',
    decision:
      'Popularity xếp theo weighted rating WR = v/(v+m)·R + m/(v+m)·C (m = 1000, C = điểm trung bình tập train) trên các phim có ít nhất 100 rating. Quyên (Person 1) định nghĩa và tính offline (popular_movies.json); khi popularity.live bật, API tính lại từ số liệu tập train cộng rating mới đã áp dụng, xem mục Phổ biến.',
    how: ['Mỗi lần chọn case này, trang sinh một userId mới chưa có lịch sử.', 'Quan sát tier 0_history / POPULARITY.'],
  },
  {
    id: 'c2',
    label: '2. User có rating mới',
    kind: 'user',
    user: 'seed',
    title: 'Case 2 — User có rating mới',
    what: 'Rating mới được validate và cập nhật User History',
    rec: 'Content / Hybrid có thể dùng history mới',
    streaming: 'Có',
    retrain: 'Không ngay',
    chot: 'retrain lịch cố định',
    how: [
      'Chấm sao một phim bất kỳ.',
      'Nhật ký ghi 202 (đã vào Kafka), rồi chuyển sang applied khi streaming xử lý xong.',
      'Phim vừa rate biến mất khỏi gợi ý, interaction_count tăng.',
    ],
  },
  {
    id: 'c3',
    label: '3. Phim mới, chưa có rating',
    kind: 'event',
    user: 'seed',
    movies: true,
    title: 'Case 3 — Phim mới, chưa có rating',
    what: 'Có movieId, title, genres nhưng chưa có interaction',
    rec: 'Content-Based (đánh dấu phim user đã rating)',
    streaming: 'Không nhất thiết',
    retrain: 'Không',
    chot: 'giả lập thêm phim mới vào hệ thống',
    decision:
      'similar_movies được tính sẵn nên phim mới không nằm trong danh sách của phim nào. Hệ thống ghép phim mới theo thể loại user hay xem và dành riêng một vị trí (hạng 3).',
    how: [
      'Nhập tên, chọn thể loại (ví dụ Crime + Drama), bấm Thêm phim.',
      'Phim xuất hiện ở hạng 3 với nhãn MỚI cho user hợp thể loại.',
      'Thử thêm một phim Western: không xuất hiện vì user không có thể loại đó.',
    ],
  },
  {
    id: 'c4',
    label: '4. Phim mới bắt đầu có rating',
    kind: 'event',
    user: 'seed',
    movies: true,
    title: 'Case 4 — Phim mới bắt đầu có rating',
    what: 'Xuất hiện userId – movieId – rating mới',
    rec: 'Content / Hybrid trong thời gian đầu',
    streaming: 'Có',
    retrain: 'Theo lịch',
    chot: '—',
    how: [
      'Thêm một phim Crime/Drama như case 3.',
      'Chấm sao phim có nhãn MỚI.',
      'Rating đi qua Kafka → streaming (không bị quarantine), phim biến mất khỏi gợi ý của user này.',
    ],
  },
  {
    id: 'c5',
    label: '5. Retraining',
    kind: 'system',
    user: null,
    title: 'Case 5 — Retraining',
    what: 'Rating mới đã tích luỹ trong Curated Data',
    rec: 'ALS tạo model/recommendation mới',
    streaming: 'Không',
    retrain: 'Có',
    chot: '1 tuần',
    decision:
      'Trang chỉ hiển thị. Việc train chạy trên Colab của Person 1; hệ thống đóng gói và bàn giao khi đủ event.',
    how: [
      'Xem thanh tiến độ: số event đã áp dụng kể từ lần bàn giao gần nhất so với ngưỡng.',
      'Rate vài phim ở case 2 rồi quay lại: số event tăng.',
    ],
  },
  {
    id: 'c6',
    label: '6. Model mới được promote',
    kind: 'system',
    user: null,
    title: 'Case 6 — Model mới được promote',
    what: 'Model vượt qua validation',
    rec: 'Generate ALS Top-N → MongoDB',
    streaming: 'Không',
    retrain: 'Hoàn tất',
    chot: '—',
    decision:
      'Chỉ chuyển version khi qua cổng kiểm G1–G7. Bất kỳ lỗi nào cũng bị coi là FAIL (fail-closed): version đang chạy không bị đổi.',
    how: ['Xem bảng version: v1.0.0 đang active, v1.1.0 bị rejected kèm các cổng không đạt.'],
  },
  {
    id: 'c7',
    label: '7. User mới tạo tài khoản',
    kind: 'user',
    user: 'fresh',
    title: 'Case 7 — User mới tạo tài khoản',
    what: 'User chưa có interaction history',
    rec: 'Onboarding → Preference Profile → Popularity + Content/Hybrid',
    streaming: 'Không bắt buộc',
    retrain: 'Không',
    chot: 'Giống cái 1',
    decision:
      'Nhóm chốt case 7 giống case 1. Các sao user bấm trên danh sách phổ biến đóng vai onboarding tối giản: hệ thống ghi nhận sở thích qua các rating đầu tiên.',
    how: [
      'Như case 1. Chấm sao vài phim phổ biến để xem hồ sơ sở thích hình thành (tier chuyển sang few_history).',
    ],
  },
  {
    id: 'c8',
    label: '8. User mới bắt đầu rating',
    kind: 'user',
    user: 'seed',
    title: 'Case 8 — User mới bắt đầu rating',
    what: 'Có một vài interaction đầu tiên',
    rec: 'Content / Hybrid, sau đó chuyển dần sang ALS',
    streaming: 'Có',
    retrain: 'Không ngay',
    chot: '—',
    decision: 'Chuyển sang ALS chỉ xảy ra sau lần retrain kế tiếp, khi model có dữ liệu của user này.',
    how: [
      `User ${SEED_USER} được seed sẵn 3 rating (scripts/seed_demo_users.py).`,
      'Quan sát tier few_history / CONTENT+POPULARITY.',
    ],
  },
  {
    id: 'c9',
    label: '9. User mới + phim mới',
    kind: 'event',
    user: 'fresh',
    movies: true,
    title: 'Case 9 — User mới + phim mới',
    what: 'Cả user và item đều thiếu interaction',
    rec: 'Onboarding/Preference + Content/Popularity; có thể thêm LLM re-ranking ở tầng candidate',
    streaming: 'Không nhất thiết',
    retrain: 'Không',
    chot: 'Giống cái 3 + 7',
    decision:
      'LLM re-ranking nằm ngoài phạm vi. Phim mới chỉ nối được với user mới sau khi user có ít nhất một tín hiệu sở thích.',
    how: [
      'User mới chỉ thấy danh sách phổ biến (0_history), chưa có phim mới.',
      'Thêm một phim Crime/Drama.',
      'Chấm sao một phim phổ biến cùng thể loại (ví dụ Shawshank). Khi áp dụng xong, tier chuyển few_history và phim mới xuất hiện.',
    ],
  },
  {
    id: 'als',
    label: 'Đã có rating và có ALS (user 1)',
    kind: 'user',
    user: 1,
    title: 'User đã có rating và có ALS',
    what: 'user 1 có 146 rating và có document ALS',
    rec: 'ALS + Content, loại phim đã rate',
    streaming: 'Có',
    retrain: 'Có',
    chot: '—',
    how: ['Quan sát tier enough_history / ALS+CONTENT.', 'Chấm sao phim hạng 1: phim biến mất khỏi danh sách.'],
  },
  {
    id: 'noals',
    label: 'Đủ lịch sử nhưng thiếu ALS (user 127249)',
    kind: 'user',
    user: 127249,
    title: 'User đủ lịch sử nhưng thiếu ALS',
    what: 'user 127249 có 69 rating nhưng model ALS không sinh gợi ý cho user này',
    rec: 'Hạ cấp: Content + Popularity, ghi fallbackReason',
    streaming: 'Có',
    retrain: 'Có',
    chot: '—',
    decision: '46,340 user thuộc nhóm này. Hệ thống không báo lỗi mà tự hạ cấp và nói rõ lý do.',
    how: ['Quan sát fallbackReason: als_artifact_missing tô màu cam.'],
  },
]

export const caseById = (id: string): CaseDef => CASES.find((c) => c.id === id) ?? CASES[0]!
