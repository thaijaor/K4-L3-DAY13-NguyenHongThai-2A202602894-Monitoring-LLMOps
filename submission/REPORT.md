# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Chỉ cần 3 output text và 5 ảnh runtime; dùng đường dẫn tương đối, ví dụ `evidence/03-incident-trace.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Hồng Thái
- **MSSV:** 2A202602894
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/thaijaor/K4-L3-DAY13-NguyenHongThai-2A202602894-Monitoring-LLMOps
- **Commit SHA cuối:** `bb2e2278f34880cc89fd341d4b88d0140bfffa9d` (code + evidence; commit sau chỉ điền dòng này)
- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602894`

## 2. Evidence index

Giữ đúng ba output text và năm ảnh dưới đây. Không tách thêm ảnh; nếu cần giải thích, ghi bằng chữ trong các mục sau.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/pytest.txt` |
| Log validator | `evidence/log-validator.txt` |
| Dashboard validator | `evidence/dashboard-validator.txt` |
| Structured log + incident log | `evidence/01-incident-log.png` |
| Trace list | `evidence/02-trace-list.png` |
| Trace waterfall + metadata + incident trace | `evidence/03-incident-trace.png` |
| Prompt versions + promote/rollback | `evidence/04-prompt-versioning.png` |
| Dashboard + incident metric | `evidence/05-dashboard-incident.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (thiếu field bắt buộc, 0 correlation ID, thiếu enrichment) | 100/100 | correlation ID, enrichment, PII scrub đều đạt |
| `validate_dashboard.py` | 6/6 | 6/6 | contract giữ nguyên; thêm dashboard runtime `/dashboard` |
| `pytest` | 22 passed | 33 passed | +11 test: PII, correlation ID, child observations, dashboard, concurrency |
| Số traces hợp lệ | 0 (chỉ có root, chưa có child span) | 36 | root + retrieval + generation, có correlation ID |
| Số PII leak | 0 | 0 | request có đủ 4 loại PII giả chỉ còn `[REDACTED_*]` |
| Latency P95 / TTFT P95 | 7407 ms / 50 ms (10 request) | 1601 ms / 50 ms bình thường; 2652 ms / 50 ms trong challenge | baseline cao do timeout TLS tới Langfuse khi chưa có prompt |
| Retrieval success rate | 100% | 100% | `rag_slow` làm chậm, không làm lỗi retrieval |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `app/middleware.py` xóa contextvars cũ, nhận `x-request-id` nếu hợp lệ (`[A-Za-z0-9._-]{1,64}`, chống log injection), ngược lại sinh `req-<8 hex>`. ID được bind vào structlog contextvars, gắn vào `request.state`, truyền vào `agent.run()` (trace metadata) và trả lại qua header `x-request-id` cùng `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`; context bind trong `app/main.py`: `user_id_hash` (SHA-256, 12 ký tự), `session_id`, `feature`, `model`, `env`; `response_sent` thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` (`app/logging_config.py`) scrub đệ quy mọi field string (không chỉ `payload`), đặt sau `format_exc_info` và trước `JsonlFileProcessor`/`JSONRenderer`. `app/pii.py` có pattern email, thẻ, CCCD, SĐT VN, hộ chiếu; thẻ chạy trước CCCD/SĐT và bắt buộc cùng một dấu phân cách để không nuốt nhầm SĐT + CCCD liền nhau.
- **Cách kiểm chứng kết quả:** `validate_logs.py` 30 → 100/100, 0 PII leak ([log-validator.txt](evidence/log-validator.txt)); log mẫu [01-incident-log](evidence/01-incident-log.png); request `req-piidemo1` chứa email, SĐT, CCCD, thẻ giả → log `[REDACTED_EMAIL] [REDACTED_PHONE_VN] [REDACTED_CCCD] [REDACTED_CREDIT_CARD]`. Tests: `tests/test_pii.py`, `tests/test_correlation_id.py` (sinh/nhận ID, từ chối ID không an toàn, không rò ID giữa 2 request).

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** trace sinh từ `load_test.py --concurrency 5` với key của project `day13-k4-l3b-2A202602894`; mỗi trace có `correlation_id` trùng một dòng trong `data/logs.jsonl` của máy tôi.
- **Cấu trúc root/retrieval/generation observations:** `day13-agent-request` → `lab-agent-run` (agent) → `retrieval` (retriever: query preview đã scrub, `doc_count`, level `ERROR` khi retrieval lỗi) + `llm-generation` (generation: model, prompt link, `usage_details` input/output, `cost_details`, `completion_start_time` để Langfuse tính TTFT). Input/output chỉ là preview đã scrub PII.
- **Cách nối trace với log:** `correlation_id` do middleware sinh được truyền vào `agent.run()` và đặt trong trace metadata qua `propagate_attributes`, nên tìm được trace từ log line và ngược lại.
- **Prompt name:** `day13-chat` (tạo bằng `scripts/setup_prompts.py`)
- **Version/label baseline:** v1 — labels `baseline`, `production` (template gốc 3 biến)
- **Version/label candidate:** v2 — label `candidate` (thêm yêu cầu trả lời ≤ 3 bullet; tokens_in 32 → 49 với cùng input)
- **Trace ID của mỗi version:** v1 `851e0f4e6ab79d13ea160b9074578c27` (`req-prompt-baseline`); v2 `d5bf32ddd9b2dcd9b2b29bbb9c319e1a` (`req-prompt-candidate`)
- **Cách promote và rollback `production`:** chuyển label `production` sang v2 (Langfuse UI hoặc `python scripts/set_production.py 2`), restart API (SDK cache 60s): `req-prod-v2` → trace `9ac16e538bb9646dadfef88bae58c6b4`, `prompt_label=production`, `prompt_version=2`, tokens_in 49. Rollback `python scripts/set_production.py 1`: `req-prod-rollback-v1` → trace `2436e2a7cb7c049a2138ed25e5b5b934`, `production` v1, tokens_in 32. Không sửa code. Ảnh: [04-prompt-versioning](evidence/04-prompt-versioning.png).

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** endpoint `GET /dashboard` (`app/dashboard.py`) đọc `data/logs.jsonl` theo `config/dashboard.yaml`: time range 60 phút, refresh 30s, mỗi panel có đơn vị, threshold (đường đứt đỏ) và trạng thái OK/vượt ngưỡng. Latency có P50/P95/P99 + TTFT P95; Errors có error rate, breakdown và retrieval success.
- **SLO và lý do chọn:** giữ `fast_successful_requests`: 99.5% request thành công và ≤ 3000 ms trong 28 ngày. Baseline P95 ~1450 ms, P99 ~1600 ms, 0 lỗi → 3000 ms dư ~2x cho tail nhưng vẫn bắt được retrieval chậm thêm 2.5 s.
- **Cách tính error budget:** 100% − 99.5% = 0.5%. 10,000 request/28 ngày → tối đa 50 request lỗi hoặc > 3000 ms. Burn rate = tỉ lệ request xấu / 0.5%; > 1 kéo dài là sẽ hết budget trước hạn.
- **Ba alert và runbook tương ứng:** `HighLatencyP95` (warning, P95 > 3000 ms/5m), `HighErrorRate` (critical, > 2%/5m), `LowRetrievalSuccess` (warning, < 90%/10m); Slack `#k4-l3b-alerts`, owner `student-2A202602894`. Xem `config/alert_rules.yaml`, runbook `docs/alerts.md`.


## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1` (cohort K4, feature bị ảnh hưởng `monitoring`)
- **Khoảng thời gian điều tra:** 2026-09-30 10:45:54–10:46:09 (GMT+7); tắt incident lúc 10:46:56, chạy lại cùng query lúc 10:46:57 để xác nhận hồi phục.
- **Triệu chứng từ metrics:** panel Latency: 5/5 request `monitoring` có `latency_ms` 2651–2653 (P50/P95 ≈ 2652 ms), vượt `latency_threshold_ms` 2000 của challenge; lượt bình thường ngay trước đó P50 151 ms. TTFT P95 giữ 50 ms, error rate 0%, retrieval success 100%, tokens/cost/quality không đổi → thời gian tăng nằm trước bước LLM.
- **Log line và correlation ID liên quan:** `response_sent` của `req-37af7664`: `feature=monitoring`, `latency_ms=2652`, `ttft_ms=50`, `tool_success=true`, ts `03:45:58.685Z`.
- **Trace ID và span gây ảnh hưởng:** trace `0acc9534aea9684859215f8656b53b72` (cùng `correlation_id`): `lab-agent-run` 2652 ms = `retrieval` **2501 ms** + `llm-generation` 151 ms. Request bình thường `req-766c2adc` (trace `11520e7f37b4da7231a4392b09fc22bd`): retrieval 0 ms, generation 151 ms.
- **Root cause:** bước retrieval (vector store) chậm thêm ~2.5 s mỗi request (incident `rag_slow`); LLM, prompt (v1) và token không đổi. Phụ: `/chat` là `async def` nhưng gọi `agent.run()` đồng bộ nên retrieval chậm chặn event loop — 5 request đồng thời bị xếp hàng, client thấy 8–13 s dù log server ghi 2.65 s.
- **Fix action:** khôi phục retrieval (`inject_incident.py --disable`); chạy lại cùng 5 query challenge: 630–790 ms phía client, retrieval về 0 ms. Sửa thêm lỗi chặn event loop: `/chat` gọi `agent.run()` qua `run_in_threadpool` (`app/main.py`). Kiểm chứng bằng practice `rag_slow` với cùng 5 query, concurrency 5: phía client 8–13 s → 2.67 s (bằng latency server 2.65 s); trace vẫn đủ root/retrieval/generation (`f3d622d025c511c912b676088f39ba74`); test `tests/test_concurrency.py`.
- **Preventive measure:** alert `HighLatencyP95` (P95 > 3000 ms/5m) cộng thêm ngưỡng riêng cho span retrieval (vd. > 1000 ms); timeout + fallback answer cho retrieval; test `tests/test_concurrency.py` giữ cho code đồng bộ không quay lại chặn event loop; đo latency phía client/gateway vì log server bỏ sót thời gian xếp hàng.


## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** tự dựng dashboard `/dashboard` (Python + SVG, đọc `data/logs.jsonl` và `config/dashboard.yaml`) thay vì thêm Grafana/Streamlit: không thêm dependency nên repo chạy lại được chỉ với `requirements.txt`, và ngưỡng lấy thẳng từ contract nên dashboard luôn khớp validator. Đánh đổi: không có zoom/filter như Grafana.
- **Một lỗi/blocker đã gặp:** (1) đưa pattern thẻ lên trước CCCD làm regex thẻ nuốt nhầm "4567 001203004567" (đuôi SĐT + CCCD), để lộ `090 123` trong log mà validator không bắt được. (2) Trace của 2 request đầu không lên Langfuse.
- **Cách tìm nguyên nhân và xử lý:** (1) phát hiện khi đọc lại log của request PII demo; sửa regex thẻ bắt buộc cùng một dấu phân cách (``), thêm test PII liền nhau, xóa log bị lộ và chạy lại. (2) Server bị tắt trước khi SDK gửi batch span; thêm `flush()` khi app shutdown.
- **Cách hiểu luồng Metrics → Logs → Traces:** metric cho biết có vấn đề gì và từ lúc nào (latency 2652 ms, TTFT không đổi); log chọn ra request cụ thể bị ảnh hưởng qua `correlation_id` (`req-37af7664`); trace của đúng request đó tách thời gian theo từng bước (retrieval 2501 ms) nên kết luận root cause dựa trên bằng chứng, không đoán.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** prompt là config ảnh hưởng trực tiếp token/cost/quality; v2 tăng tokens_in 32 → 49 (+53%) với cùng input. Gắn version vào trace giúp quy regression về đúng version, rollback bằng đổi label không cần deploy. SLO/error budget quyết định khi nào phải dừng thay đổi để ổn định hệ thống.
- **Điều quan trọng nhất đã học:** latency đo ở server có thể sai lệch với trải nghiệm người dùng: log ghi 2.65 s nhưng client chờ 8–13 s vì `agent.run()` đồng bộ chặn event loop, request đồng thời phải xếp hàng.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** dashboard không đo latency phía client; alert mới định nghĩa trong YAML, chưa nối Slack thật; khi cache prompt trống, mọi request đồng thời cùng gọi Langfuse (timeout TLS làm latency tăng lên ~7.6 s trong một lần thử).

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Có đúng 3 file text và 5 ảnh runtime theo hướng dẫn.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
