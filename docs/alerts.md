# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-2A202602894`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: SLO `fast_successful_requests` (`response_sent.latency_ms <= 3000`, 99.5%/28 ngày)
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` liên tục 5 phút
- Ảnh hưởng tới người dùng: phải chờ > 3 giây mới có câu trả lời; đốt error budget latency
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Latency (`/dashboard`): xác định P95/P99 tăng từ phút nào, TTFT có tăng theo không (TTFT không đổi → chậm trước bước LLM).
  2. Lọc `data/logs.jsonl` event `response_sent` có `latency_ms > 3000` trong khoảng đó, lấy `correlation_id`.
  3. Mở trace có cùng `correlation_id` trên Langfuse, so thời gian span `retrieval` và `llm-generation`.
- Mitigation tạm thời: retrieval chậm → giảm timeout/tạm dùng fallback answer, kiểm tra vector store; generation chậm → rollback label `production` về prompt version trước, giảm output tokens.
- Owner: `student-2A202602894`

## Alert 2

- Tên: `HighErrorRate`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: SLO `fast_successful_requests`; guardrail `error_rate_pct_max: 2`
- Điều kiện và thời gian duy trì: `request_failed / request_received * 100 > 2%` liên tục 5 phút
- Ảnh hưởng tới người dùng: nhận HTTP 500, không có câu trả lời; mỗi request lỗi trừ thẳng vào error budget
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Errors: xem error rate, breakdown theo `error_type` và retrieval success cùng khoảng thời gian.
  2. Lọc `data/logs.jsonl` event `request_failed`, đọc `error_type`, `payload.detail`, lấy `correlation_id`.
  3. Mở trace cùng `correlation_id`, tìm span có level `ERROR` (`retrieval` hay `llm-generation`).
- Mitigation tạm thời: lỗi ở retrieval → trả fallback answer không dùng context thay vì 500; lỗi sau deploy/đổi prompt → rollback version; báo owner dependency nếu lỗi từ vector store/LLM provider.
- Owner: `student-2A202602894`

## Alert 3

- Tên: `LowRetrievalSuccess`
- Severity: `warning`
- Duration: `10m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: guardrail `retrieval_success_rate_pct_min: 90`; ảnh hưởng gián tiếp quality proxy
- Điều kiện và thời gian duy trì: `tool_success == true` / tổng request có `tool_success` `< 90%` liên tục 10 phút
- Ảnh hưởng tới người dùng: câu trả lời thiếu context tài liệu, dễ sai hoặc chung chung; quality score giảm
- Ba bước kiểm tra đầu tiên:
  1. Mở panel Errors (retrieval success) và panel Quality: xác nhận hai chỉ số cùng giảm trong một khoảng.
  2. Lọc log `tool_success == false`, lấy `correlation_id` và `error_type`.
  3. Mở trace cùng `correlation_id`, xem output của span `retrieval` (`doc_count`, level, status message).
- Mitigation tạm thời: chuyển sang fallback answer có cảnh báo, kiểm tra index/vector store; nếu do thay đổi query/prompt gần đây thì rollback.
- Owner: `student-2A202602894`
