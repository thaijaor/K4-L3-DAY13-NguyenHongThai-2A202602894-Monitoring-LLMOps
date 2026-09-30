# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Hồng Thái
- **MSSV:** 2A202602894
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/thaijaor/K4-L3-DAY13-NguyenHongThai-2A202602894-Monitoring-LLMOps
- **Commit SHA cuối:**
- **Challenge ID:**
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602894`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (thiếu field bắt buộc, 0 correlation ID, thiếu enrichment) | | |
| `validate_dashboard.py` | 6/6 | | |
| `pytest` | 22 passed | | |
| Số traces hợp lệ | 0 (chỉ có root, chưa có child span) | | |
| Số PII leak | 0 | | |
| Latency P95 / TTFT P95 | 7407 ms / 50 ms (10 request) | | |
| Retrieval success rate | 100% | | |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `app/middleware.py` xóa contextvars cũ, nhận `x-request-id` nếu hợp lệ (`[A-Za-z0-9._-]{1,64}`, chống log injection), ngược lại sinh `req-<8 hex>`. ID được bind vào structlog contextvars, gắn vào `request.state`, truyền vào `agent.run()` (trace metadata) và trả lại qua header `x-request-id` cùng `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`; context bind trong `app/main.py`: `user_id_hash` (SHA-256, 12 ký tự), `session_id`, `feature`, `model`, `env`; `response_sent` thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` (`app/logging_config.py`) scrub đệ quy mọi field string (không chỉ `payload`), đặt sau `format_exc_info` và trước `JsonlFileProcessor`/`JSONRenderer`. `app/pii.py` có pattern email, thẻ, CCCD, SĐT VN, hộ chiếu; thẻ chạy trước CCCD/SĐT và bắt buộc cùng một dấu phân cách để không nuốt nhầm SĐT + CCCD liền nhau.
- **Cách kiểm chứng kết quả:** `validate_logs.py` 30 → 100/100 ([02](evidence/02-log-validator.txt)); log mẫu [04](evidence/04-structured-log.txt); request chứa đủ 4 loại PII giả → log chỉ còn nhãn `[REDACTED_*]` ([05](evidence/05-pii-redaction.txt)). Tests: `tests/test_pii.py`, `tests/test_correlation_id.py` (sinh/nhận ID, từ chối ID không an toàn, không rò ID giữa 2 request).

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** trace sinh từ `load_test.py --concurrency 5` với key của project `day13-k4-l3b-2A202602894`; mỗi trace có `correlation_id` trùng một dòng trong `data/logs.jsonl` của máy tôi.
- **Cấu trúc root/retrieval/generation observations:** `day13-agent-request` → `lab-agent-run` (agent) → `retrieval` (retriever: query preview đã scrub, `doc_count`, level `ERROR` khi retrieval lỗi) + `llm-generation` (generation: model, prompt link, `usage_details` input/output, `cost_details`, `completion_start_time` để Langfuse tính TTFT). Input/output chỉ là preview đã scrub PII.
- **Cách nối trace với log:** `correlation_id` do middleware sinh được truyền vào `agent.run()` và đặt trong trace metadata qua `propagate_attributes`, nên tìm được trace từ log line và ngược lại.
- **Prompt name:** `day13-chat` (tạo bằng `scripts/setup_prompts.py`)
- **Version/label baseline:** v1 — labels `baseline`, `production` (template gốc 3 biến)
- **Version/label candidate:** v2 — label `candidate` (thêm yêu cầu trả lời ≤ 3 bullet; tokens_in 32 → 49 với cùng input)
- **Trace ID của mỗi version:** v1 `851e0f4e6ab79d13ea160b9074578c27` (`req-prompt-baseline`); v2 `d5bf32ddd9b2dcd9b2b29bbb9c319e1a` (`req-prompt-candidate`)
- **Cách promote và rollback `production`:**

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** endpoint `GET /dashboard` (`app/dashboard.py`) đọc `data/logs.jsonl` theo `config/dashboard.yaml`: time range 60 phút, refresh 30s, mỗi panel có đơn vị, threshold (đường đứt đỏ) và trạng thái OK/vượt ngưỡng. Latency có P50/P95/P99 + TTFT P95; Errors có error rate, breakdown và retrieval success.
- **SLO và lý do chọn:** giữ `fast_successful_requests`: 99.5% request thành công và ≤ 3000 ms trong 28 ngày. Baseline P95 ~1450 ms, P99 ~1600 ms, 0 lỗi → 3000 ms dư ~2x cho tail nhưng vẫn bắt được retrieval chậm thêm 2.5 s.
- **Cách tính error budget:** 100% − 99.5% = 0.5%. 10,000 request/28 ngày → tối đa 50 request lỗi hoặc > 3000 ms. Burn rate = tỉ lệ request xấu / 0.5%; > 1 kéo dài là sẽ hết budget trước hạn.
- **Ba alert và runbook tương ứng:** `HighLatencyP95` (warning, P95 > 3000 ms/5m), `HighErrorRate` (critical, > 2%/5m), `LowRetrievalSuccess` (warning, < 90%/10m); Slack `#k4-l3b-alerts`, owner `student-2A202602894`. Xem `config/alert_rules.yaml`, runbook `docs/alerts.md`.

> Ví dụ cách viết error budget: "SLO 99.5% trong 28 ngày nghĩa là error budget 0.5%. Nếu workload có 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng SLO."

## 7. Điều tra challenge

- **Challenge ID:**
- **Khoảng thời gian điều tra:**
- **Triệu chứng từ metrics:**
- **Log line và correlation ID liên quan:**
- **Trace ID và span gây ảnh hưởng:**
- **Root cause:**
- **Fix action:**
- **Preventive measure:**

> Gợi ý cách viết ngắn, không thay cho evidence thực tế: "Metric cho thấy `[latency/error/cost/quality]` bất thường trong `[khoảng thời gian]`. Log line `[event]` có `correlation_id=[...]` đại diện cho request bị ảnh hưởng. Trace cùng `correlation_id` cho thấy span `[retrieval/generation/prompt/tool]` có dấu hiệu `[chậm/lỗi/token tăng]`. Root cause là `[nguyên nhân suy ra từ evidence]`. Fix action là `[hành động khôi phục]`; preventive measure là `[alert/runbook/test/guardrail để ngăn tái diễn]`."

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:**
- **Cách tìm nguyên nhân và xử lý:**
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
