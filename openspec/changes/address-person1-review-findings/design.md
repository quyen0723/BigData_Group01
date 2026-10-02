## Context

- Quyên review PR #1 (4 commit, ~11K dòng). Mọi số dòng trong review khớp code trên nhánh `feat/person2-serving-streaming-integration`. Review nằm ở comment trên PR #1 và `docs/REVIEW_person2_branch.md` (PR #2).
- Các lỗi đều ở đường lỗi: crash giữa `serve_batch`, mất checkpoint, handoff chạy lúc streaming đang ghi, retry sau timeout. Happy path đã có evidence (`evidence/p2_*`).
- Bối cảnh `serve_batch` (`src/streaming/pipeline.py:149`): chạy trên driver, một batch tại một thời điểm. Thứ tự ghi: parquet `curated_ratings` (dòng 191) → `user_rated` → `user_history` → ledger `rating_events` (dòng 250, `ingestedAt` được gán một lần cho cả batch ở dòng 243) → `pipeline_state.ratings_stream {lastBatchId, lastRunAt}` (dòng 256). `foreachBatch` là at-least-once.
- `retrain_trigger` (`src/orchestration/retrain_trigger.py`): đọc `pending = rating_events{ingestedAt > watermark}` (dòng 51), ghi parquet bằng Spark (dòng 72–88), rồi ghi `watermark = now` (dòng 117).
- Đối chiếu của mình khác review ở mức độ, không ở sự thật:
  - B2: `design.md` của `person2-serving-streaming-integration` D-10 (dòng 237) đã ghi nhận append parquet có thể chạy hai lần và giao cho quy tắc latest-wins khi đọc (D4, chờ Quyên). `delta_ratings` của handoff lấy từ **ledger** (mỗi `eventId` một dòng) nên không bị trùng; chỉ đọc trực tiếp `curated_ratings` mới thấy trùng, và `promotion_gate` đang làm đúng việc đó.
  - B4: trên DB đang chạy `popular_movies` = 2, `user_rated` = 32,000,245, `user_history` = 200,960, khác `EXPECTED` trong `bootstrap_registry.py:28`, nên G4 fail và script `return 1` trước khi ghi pointer.
  - B1: review viết `maxEventTimestamp` "không dùng"; thực tế nó vào manifest và checksum, và là `timestamp` của rating, không phải `ingestedAt`.
  - B3: nhánh skip in `already committed (last=…), skipping` rồi `return`; không in `committed`.
- M8 = 03/10/2026.

## Goals / Non-Goals

**Goals:**
- Không event nào bị mất khỏi gói handoff vì handoff chạy lúc streaming đang ghi.
- Mất checkpoint trong khi Mongo còn sống không làm rating mới bị bỏ qua mà không ai biết.
- `promotion_gate` không tính RMSE trên dữ liệu trùng hoặc trên toàn bộ `curated_ratings` khi thiếu mốc cắt.
- Chạy lại `bootstrap_registry` không thể đổi model đang phục vụ; README không hứa điều không đúng.
- Hợp đồng retry của `POST /ratings` rõ ràng ở cả API, spec và trang `/app`.
- Mỗi sửa đổi có cách kiểm chứng riêng (unit test hoặc chạy trên stack thật), kết quả vào `evidence/p2_review_fixes.txt`.

**Non-Goals:**
- Đổi thứ tự ghi của `serve_batch` hoặc làm append parquet exactly-once (Spark ghi file và Mongo không có commit nguyên tử chung).
- Thêm cột `eventId`/`batchId` vào `curated_ratings` (schema đóng băng ở CONTRACTS §2.1, Quyên đọc theo schema đó).
- Bắt `eventId` thành trường bắt buộc của `POST /ratings` (vỡ README, evidence, `seed_demo_users.py`, các client đang chạy).
- Sửa PR #2 hoặc quyết định thay Quyên về D3/D4.

## Decisions

### D-1. Cửa sổ handoff chặn trên bằng event đã commit (B1)

`retrain_trigger` đọc `committedUpTo = pipeline_state.ratings_stream.lastRunAt` một lần ở đầu, rồi:

```
pending   = rating_events{ ingestedAt > watermark  AND  ingestedAt <= committedUpTo }
watermark = committedUpTo            (ghi ở cuối, chỉ khi package đã tạo xong)
windowEnd = committedUpTo            (manifest; createdAt vẫn là now)
```

`lastRunAt` được ghi ở bước 7 của `serve_batch`, sau khi ledger của batch đó đã chèn xong. `serve_batch` chạy tuần tự nên `ingestedAt` của batch đang chạy luôn lớn hơn `lastRunAt` của batch trước. Hệ quả:
- batch đang ghi dở (kể cả `insert_many` mới chèn một nửa) có `ingestedAt` > `committedUpTo`, bị loại hẳn và vào cửa sổ kế tiếp;
- event nào có `ingestedAt <= committedUpTo` thì batch của nó đã commit xong, nên cả batch nằm trọn trong cửa sổ;
- crash giữa chèn ledger và bước 7: các dòng ledger đó nằm ngoài cửa sổ tới khi batch được chạy lại và commit; lúc đó `lastRunAt` mới lớn hơn, còn `ingestedAt` vẫn lớn hơn watermark cũ, nên chúng vào cửa sổ kế tiếp.

Không có `ratings_stream` (streaming chưa từng chạy) thì không có gì để handoff.

**Phương án đã cân nhắc:**
- *Gợi ý của review: watermark = max `ingestedAt` của `pending`.* Bỏ được lỗ `now`, nhưng cả batch dùng chung một `ingestedAt` và `insert_many` không nguyên tử, nên handoff chạy giữa lúc chèn sẽ thấy một phần batch rồi `$gt` làm mất phần còn lại. Lỗ nhỏ hơn, nhưng vẫn còn.
- *`$gte` kèm danh sách `eventId` đã xuất:* phải lưu tập id trong `pipeline_state`, to dần.
- *Transaction/snapshot read của Mongo:* cần replica set, hạ tầng hiện là single node.
- Không dùng `max_event_ts` (dòng 96) làm watermark: đó là thời điểm rating, thuộc trục thời gian khác `ingestedAt`.

### D-2. Guard `batchId` gắn với danh tính checkpoint (B3)

Spark ghi `<checkpoint>/metadata` với `{"id": "<uuid>"}` khi query bắt đầu; mất checkpoint thì id mới. Đã kiểm trên volume thật: `movielens32m/stream/checkpoints/valid/metadata` có file này. `serve_batch` đọc id đó (lazy, ở batch đầu tiên, cache lại) và lưu cùng `lastBatchId`:

```
decide(state, batch_id, stream_id):
  state rỗng                         → process
  stream_id không đọc được           → process + WARN (một lần)      # an toàn: ledger dedup lo phần còn lại
  state.streamId vắng (bản ghi cũ)   → process + WARN "no recorded stream identity"; ghi streamId ở lần commit
  state.streamId != stream_id        → process + WARN "checkpoint changed", lastBatchId đặt lại về -1
  cùng stream_id                     → skip nếu batch_id <= lastBatchId, ngược lại process
```

Nói gọn: chỉ skip khi **cả danh tính checkpoint lẫn `batch_id <= lastBatchId` đều khớp**; mọi trường hợp còn lại là process.

Bản ghi cũ chưa có `streamId` cũng là process (không phải "coi là cùng stream"). Phát hiện khi tái hiện lỗi trên stack thật (task 3.1): state `lastBatchId=69` đi cùng một checkpoint mới đánh số batch lại từ 0; nếu bản ghi không có danh tính được coi là cùng stream thì lỗi vẫn còn nguyên ở lần chạy đầu sau khi nâng cấp. Xử lý batch trong trường hợp đó vẫn an toàn vì dedup ledger.

Logic quyết định là một hàm thuần (`decide_batch_action`) để unit test; phần đọc file và ghi Mongo ở `serve_batch`. Bước 7 ghi `streamId` cùng `lastBatchId`.

**`serve_batch` luôn đọc batch trước khi quyết định skip** (`collect()` đứng trước `decide_batch_action`). Phát hiện khi tái hiện B3 trên stack thật: guard cũ `return` mà không đụng vào `batch_df`, nên toán tử có state của Q2 (`dropDuplicatesWithinWatermark`) không chạy và không ghi file `.delta` nào cho batch đó, trong khi Spark vẫn coi batch là đã commit. Sau checkpoint mới (offsets 0,1,2; commits 0,1; `state/0/0` chỉ có `_metadata`), batch 2 đòi `1.delta` và query chết với `FileNotFoundException`, container crash-loop. Đọc batch trước khi skip giữ state store đi cùng offset log dù guard quyết định thế nào; chi phí là một `collect()` trên batch nhỏ (bị chặn bởi `maxOffsetsPerTrigger`).

Vì sao an toàn khi `process` thay vì skip: guard chỉ là tối ưu. Mọi replay đều đi qua dedup ledger (bước 2): batch đã commit trước đó có `new_rows` rỗng nên không ghi gì thêm, kể cả parquet. Guard không bảo vệ gì mà ledger chưa bảo vệ.

**Phương án đã cân nhắc:**
- *Bỏ hẳn guard:* đơn giản nhất và đúng về correctness. Không chọn vì D-10 bước 1, spec "Batch replay after crash" và evidence hiện có dựa vào dòng log skip; giữ lại cho đúng tài liệu. Nếu việc đọc `metadata` gây rắc rối thì bỏ guard là đường lùi hợp lệ.
- *Gợi ý của review: FAIL khi `batch_id=0 && lastBatchId>0`:* chỉ bắt được batch 0; restart từ một checkpoint cũ hơn (không phải 0) vẫn lọt.

### D-3. Dedup holdout ở `promotion_gate`, giữ append parquet at-least-once (B2)

Sau khi đọc `curated_ratings` và lọc `timestamp >= cut_test`, gate gộp theo `(userId, movieId)` lấy `rating` của dòng có `timestamp` lớn nhất (`groupBy(...).agg(max_by("rating","timestamp"))`) rồi mới tính RMSE.

Dữ liệu gốc của MovieLens không có cặp `(userId, movieId)` lặp, nên với holdout gốc con số RMSE không đổi và vẫn so sánh được với số Quyên báo; chỉ các dòng do streaming nạp trùng (hoặc user rate lại) bị gộp.

Ghi nhận trong `design.md` D-10 của change `person2-serving-streaming-integration`: parquet vẫn at-least-once; nơi trung hoà là (a) `delta_ratings` lấy từ ledger nên không trùng, (b) gate dedup như trên, (c) phía retrain của Quyên theo D4 (chờ xác nhận, xem Open Questions).

**Phương án đã cân nhắc:**
- *Thêm `eventId`/`batchId` vào schema curated:* phá schema đóng băng.
- *Ghi ledger trước parquet:* đổi "crash → có thể ghi trùng" thành "crash → mất rating khỏi curated mà không dấu vết"; mất dữ liệu train tệ hơn trùng.
- *Marker "đã append batch N" trong `pipeline_state`:* thu hẹp cửa sổ lỗi nhưng không đóng được (vẫn có khoảng giữa append và ghi marker), thêm một trạng thái phải giữ nhất quán.

### D-4. Bootstrap từ chối ghi đè pointer khác version (B4)

Ngay sau khi kết nối, `bootstrap_registry` đọc `serving_meta.active`. Nếu có và `modelVersion != --version` thì in lý do, chỉ sang `promotion_gate`/`manage_versions`, và thoát mã 2 trước khi chạy kiểm tra hay ghi `model_registry`. Cùng version thì cho chạy như hiện nay (đăng ký lại cùng version là vô hại). README bước 2: bỏ "idempotent — safe to rerun", ghi rõ đây là bước nạp lần đầu và sẽ fail G4 khi đã có rating mới hay đã nạp version thứ hai.

**Phương án đã cân nhắc:** cờ `--force-activate` (thêm bề mặt thao tác nguy hiểm không ai cần, đã có `manage_versions`); chuyển `EXPECTED` từ FAIL sang WARN (đổi ý nghĩa của gate nạp dữ liệu, ngoài phạm vi).

### D-5. Gate fail-closed khi thiếu `cut_test` (M1)

Hàm thuần `resolve_cut_test(candidate_card, active_card)` trả về giá trị hoặc `None`. `None` → G1–G3 FAIL với lý do `no split.cut_test in either model card; refusing to evaluate on the full curated ratings`, không đọc parquet và không nạp model; G4–G7 vẫn chạy để báo cáo đầy đủ. Dùng lại nhánh `rmse_error` đang có để báo cáo giữ nguyên định dạng.

### D-6. Hợp đồng timeout của `POST /ratings` (M2)

- 503 do `flush()` quá hạn nghĩa là kết quả chưa biết (librdkafka vẫn có thể gửi sau). Thông báo: `kafka delivery timed out; the rating may still be delivered, retry with the same eventId`.
- `eventId` vẫn tùy chọn. Server tự sinh UUID chỉ phù hợp cho client không retry; spec ghi rõ client muốn retry an toàn phải tự gửi `eventId`.
- `/app` giữ một `eventId` cho mỗi `(userId, movieId, số sao)` đang thử lại: dùng lại sau mọi kết quả khác 202 (lỗi mạng, 5xx), xoá khi nhận 202 hoặc 422.
- Hệ quả khi vẫn lọt trùng: `user_rated` upsert theo `(userId, movieId)` nên trạng thái phục vụ không đổi; chỉ `curated_ratings` có thêm một dòng, được trung hoà bởi D-3.

### D-7. Dọn nhỏ

- **Điểm phim mới chèn vào (`new_items.py`)**: mọi phim chèn nhận điểm của phần tử đầu tiên bị đẩy xuống (`final[index].score`; nếu chèn cuối danh sách thì điểm phần tử cuối). Dãy điểm giữ không tăng, hòa thay vì đảo. Hôm nay `slots=1` nên chưa lộ ra.
- **`kafkaTimestamp`**: schema `build_parsed_stream` khai `TimestampType`. Chưa nổ vì không câu lệnh nào chọn cột này; kiểm bằng chạy lại streaming thật.
- **Đổi datetime sang epoch**: một hàm `to_epoch(dt)` thuần (naive coi là UTC) trong `src/serving/`, dùng ở `repository.get_user_history` và `retrain_trigger` thay cho hai cách làm khác nhau.
- **`MongoClient`**: tạo một lần trong closure của `serve_batch`, dùng lại cho mọi batch, bỏ `close()` mỗi batch. `MongoClient` an toàn khi dùng lại và tự kết nối lại khi mất kết nối.

## Risks / Trade-offs

- **[D-1/D-2 đụng đường chạy streaming đang hoạt động]** → Unit test cho hàm thuần, và chạy thật trên Docker: giả lập mất checkpoint, tạo handoff giữa lúc batch ghi dở. Ghi vào evidence.
- **[`lastRunAt` cập nhật cả với batch rỗng]** → Đúng ý: mọi event có `ingestedAt <= lastRunAt` đã commit. Streaming dừng thì `committedUpTo` đứng yên và handoff chỉ lấy tới đó, event chưa commit sẽ vào lần sau.
- **[Đọc file `metadata` thất bại (checkpoint không phải filesystem cục bộ)]** → `stream_id = None` → luôn `process`, dựa vào ledger. Mất tối ưu, không mất đúng đắn.
- **[Bản ghi `ratings_stream` cũ chưa có `streamId`]** → xử lý batch đầu tiên thay vì skip và ghi `streamId` ở lần commit; mất duy nhất một lần tra ledger cho batch đó, không mất đúng đắn.
- **[D-3 làm gate chậm hơn do thêm một lần gộp]** → Holdout khoảng 4.8M dòng, gộp theo khóa chạy trong chế độ local; ghi thời gian đo thật vào evidence. Nếu quá chậm thì chỉ gộp phần dòng có `timestamp > max_ts` gốc.
- **[D-4 chặn một thao tác hợp lệ: nạp lại sau khi xoá Mongo]** → Khi Mongo trống thì không có pointer và script chạy bình thường; hướng dẫn ghi vào README.
- **[Thời gian đến M8]** → Thứ tự làm: D-1, D-2, D-3 (cần stack thật) trước; D-4, D-5, D-6, D-7 sau (chủ yếu unit test).

## Migration Plan

1. Không có migrate dữ liệu. `streamId` là trường mới của `pipeline_state.ratings_stream`, bản ghi cũ vẫn đọc được; code cũ bỏ qua trường lạ.
2. Triển khai bằng restart `api` và `streaming` (src được mount, không rebuild). Batch đầu tiên sau restart ghi `streamId`.
3. Rollback: revert commit và restart; `streamId` thừa không gây hại.

## Open Questions

- **(Quyên, D4)** Retrain của B6 có đọc `curated_ratings` trực tiếp không, và có dedup latest-wins theo `(userId, movieId)` không? Quyết định mức nghiêm trọng thực tế của B2 phía retrain và của B1 (nếu train từ `delta_ratings` thì B1 làm mất dữ liệu train).
- **(Quyên, D3)** Holdout `timestamp ≥ cut_test` tự lớn lên khi streaming ghi rating mới (timestamp là hiện tại), trong khi delta cho retrain cũng nằm đúng cửa sổ đó. Nên cố định holdout gốc bằng cận trên, hay chấp nhận holdout động? Ngoài phạm vi change này; chỉ nêu để Quyên chốt trước B6.
- Có cần đưa kiểm tra "tắt checkpoint" vào `docs/TESTING_GUIDE.md` như một ca chạy chính thức, hay chỉ giữ trong evidence? Đề xuất: thêm một mục ngắn.
