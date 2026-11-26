# Open Electricity NEM — manifest dữ liệu

## Trạng thái

- Dataset mục tiêu duy nhất sau migration: Open Electricity NEM.
- Trạng thái hiện tại: **candidate, chưa được xác nhận là production dataset**.
- Các file dưới đây được tổ chức từ những file có sẵn trong repository; việc di chuyển không xác minh độc lập nguồn tải.
- Chưa có bằng chứng file daily và file 5 phút được tạo từ cùng một lần trích xuất.
- Dữ liệu demand trong bộ NEM này được xem là **scheduled demand**; không gọi là tổng điện năng tiêu thụ của toàn xã hội.
- Timezone phải được xác nhận theo contract và metadata nguồn. Không suy ra timezone IANA chỉ từ offset trong timestamp.

## Raw/candidate 5 phút và JSON

| File | Khoảng thời gian quan sát được | Độ phân giải | Metric/metadata quan sát được | Ghi chú |
|---|---|---|---|---|
| data/raw/openelectricity/nem/market/history_30days_demand_5m.csv | 2026-10-25 00:00 đến 2026-11-23 23:55, offset +10:00 | 5 phút, 8.640 dòng | Demand_MW; CSV không có metadata riêng xác nhận đơn vị/network | Candidate; raw values giữ nguyên |
| data/raw/openelectricity/nem/market/history_7days_demand_5m.json | 2026-11-17 00:00 đến 2026-11-23 23:55, offset +10:00 | 5 phút, 2.016 điểm | JSON ghi NEM, demand, MW, 5m | Khớp các điểm tương ứng trong CSV 30 ngày |
| data/raw/openelectricity/nem/market/snapshot_2026-11-23_demand_5m.json | 2026-11-23, offset +10:00 | 5 phút, 288 điểm | JSON ghi NEM, demand, MW, 5m | Khớp ngày tương ứng trong CSV raw |
| data/raw/openelectricity/nem/market/snapshot_2026-11-24_demand_5m.json | 2026-11-24, offset +10:00 | 5 phút, 288 điểm | JSON ghi NEM, demand, MW, 5m | Snapshot ngày kế tiếp |
| data/raw/openelectricity/nem/market/latest_available_unverified.json | 2026-11-24 00:00 đến 2026-11-25 12:25, offset +10:00 | 5 phút, 438 điểm | Timestamp/value; không có envelope NEM/metric/unit | Chưa xác minh metadata và provenance |

Các JSON envelope quan sát được ghi version 4.5.20; trường created_at mang offset +11:00, còn timestamp dữ liệu mang +10:00. Chưa xác minh endpoint, quy tắc timezone hoặc lý do khác offset.

## Daily candidate

| File | Khoảng thời gian | Độ phân giải | Metric quan sát được | Ghi chú |
|---|---|---|---|---|
| data/processed/openelectricity/nem/daily/multivariate_1year_candidate.csv | 2025-11-25 đến 2026-11-24 | Daily, 365 dòng | Demand, price, demand energy, renewable generation, renewable proportion theo tên cột | Candidate; nguồn và định nghĩa metric chưa được xác minh |
| data/processed/openelectricity/nem/daily/multivariate_30days_candidate.csv | 2026-10-25 đến 2026-11-23 | Daily, 30 dòng | Cùng các cột multivariate | 30 ngày trùng khớp file một năm |
| data/processed/openelectricity/nem/daily/demand_1year_candidate.csv | 2025-11-25 đến 2026-11-24 | Daily, 365 dòng | Demand theo tên cột | Candidate; CSV không có metadata nguồn |

Tên cột không được xem là bằng chứng đầy đủ cho định nghĩa/đơn vị. Trong các file multivariate, Demand_Energy_MWh gần tỷ lệ với Demand_MW × 24; quan hệ này chưa xác nhận cách tạo hoặc ý nghĩa chính thức.

## File clean chưa xác minh

- data/experiments/openelectricity/nem/history_30days_clean_unverified.csv
- File này khác raw đúng ba giá trị 0; các giá trị thay thế lần lượt là 21,412.635; 23,253.69; và 24,522.775 MW tại các thời điểm 2026-11-01 21:55, 2026-11-08 19:00, 2026-11-13 16:10 (offset +10:00).
- Chưa có bằng chứng giải thích hoặc xác nhận các thay đổi. Không dùng làm nguồn pipeline chính thức trước khi xác minh.

## Experiments

- data/experiments/openelectricity/nem/classification/: các file classification_*.csv đã liệt kê trong repository.
- data/experiments/openelectricity/nem/clustering/: các file clustering_*.csv và clustering_*.png đã liệt kê trong repository.
- data/experiments/openelectricity/nem/prediction/: các file prediction_*.csv đã liệt kê trong repository.
- Đây là kết quả thử nghiệm, không phải dữ liệu nguồn/import chính thức.

## Giới hạn provenance

Không tìm thấy script, notebook, README, log hoặc metadata trong repository xác nhận endpoint, lần gọi, cách chuyển JSON sang CSV, cách tạo daily, hoặc quy trình tạo file clean. Việc khớp số liệu giữa các file chỉ là đối chiếu nội dung; không chứng minh chúng cùng một lần trích xuất. Cần bổ sung provenance, timezone, định nghĩa metric và phương pháp aggregation trước khi xác nhận production.
