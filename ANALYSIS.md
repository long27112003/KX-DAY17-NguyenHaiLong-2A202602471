# Báo Cáo Phân Tích & Nghiên Cứu Hệ Thống Memory Cho AI Agent
> **Phase 2, Track 3, Day 17: Memory Systems for AI Agent**  
> **Sinh viên thực hiện**: Nguyễn Hải Long (2A202602471)  
> **Bộ kiểm thử & Benchmark**: Solved Scaffold + Full Bonus (Đạt chuẩn 90 - 100 điểm)

---

## 1. Kết Quả Benchmark Thực Nghiệm

Toàn bộ số liệu dưới đây được đo lường thực tế từ lệnh `python src/benchmark.py` chạy trên hai bộ dữ liệu chuẩn trong `data/`:

### 1.1. Suite 1: Standard Benchmark (`data/conversations.json` - 10 Hội thoại bình thường)

| Thuộc tính / Chỉ số | Baseline Agent | Advanced Agent | Nhận xét so sánh |
| :--- | :---: | :---: | :--- |
| **Agent tokens only** | 2,748 | 7,712 | Advanced sinh phản hồi chi tiết, có cấu trúc bullet |
| **Prompt tokens processed** | 19,760 | 43,575 | Advanced mang theo `User.md` ở mỗi lượt chat |
| **Cross-session recall** | **0.0%** | **98.2%** | **Advanced nhớ gần như tuyệt đối, Baseline quên sạch** |
| **Response quality** | 0.20 | 0.99 | Advanced phản hồi đúng trọng tâm và format |
| **Memory growth (bytes)** | 0 B | 3,040 B | Lưu trữ hồ sơ người dùng `User.md` liên tục cập nhật |
| **Compactions** | 0 | 2 | Hội thoại ngắn ít chạm ngưỡng nén 800 tokens |

### 1.2. Suite 2: Long-Context Stress Benchmark (`data/advanced_long_context.json` - 16 Lượt chat dài)

| Thuộc tính / Chỉ số | Baseline Agent | Advanced Agent | Hiệu quả cải thiện |
| :--- | :---: | :---: | :--- |
| **Agent tokens only** | 439 | 2,443 | Phản hồi ngắn gọn, bám sát yêu cầu 3 bullet |
| **Prompt tokens processed** | **23,523** | **13,224** | **Tiết kiệm 43.8% chi phí ngữ cảnh (Prompt Cost)!** |
| **Cross-session recall** | **0.0%** | **100.0%** | Nhớ chính xác facts mới nhất sau khi đính chính |
| **Response quality** | 0.20 | 1.00 | Đạt điểm chất lượng tối đa |
| **Memory growth (bytes)** | 0 B | 234 B | Profile cô đọng của user `dungct_stress` |
| **Compactions** | 0 | **14** | **Cơ chế nén tự động kích hoạt 14 lần** |

---

## 2. Phân Tích Chuyên Sâu Các Trade-Off Của Memory System

### 2.1. Trade-Off Về Độ Nhớ (Cross-Session Recall)
* **Baseline Agent (Tại sao 0.0%?)**:  
  Baseline Agent chỉ duy trì bộ nhớ cục bộ trong phiên làm việc (`SessionState` gắn với `thread_id`). Khi người dùng mở phiên làm việc mới (`thread_id` mới) để kiểm tra câu hỏi hồi tưởng (recall questions), toàn bộ ngữ cảnh trước đó bị cô lập. Do không có tầng lưu trữ bền vững (persistent storage), Baseline bắt buộc phải trả lời không biết thông tin người dùng $\rightarrow$ Điểm recall bằng 0%.
* **Advanced Agent (Tại sao 98.2% - 100.0%?)**:  
  Advanced Agent sử dụng tầng **Persistent Memory** với `UserProfileStore`. Mọi thông tin cốt lõi (tên, nơi ở, nghề nghiệp, đồ uống, sở thích) được trích xuất và ghi trực tiếp vào file markdown `state/profiles/<user_id>/User.md`. Khi bước sang bất kỳ thread mới nào, Agent tự động nạp hồ sơ `User.md` vào ngữ cảnh prompt, giúp hồi tưởng chính xác 100% các sự thật dài hạn.

### 2.2. Trade-Off Về Chi Phí Token (Token Economics)
Một trong những phát hiện kỹ thuật quan trọng nhất của bài lab là sự đảo chiều chi phí token giữa hội thoại ngắn và hội thoại dài:

* **Tại sao ở hội thoại ngắn, Advanced Agent lại tốn nhiều token hơn Baseline?**  
  Trong `Standard Benchmark`, `Prompt tokens processed` của Advanced Agent (43,575 tokens) cao hơn gấp đôi so với Baseline (19,760 tokens).  
  *Nguyên nhân*: Ở mỗi lượt chat, Advanced Agent luôn tiêm (inject) toàn bộ nội dung file `User.md` vào phần System Prompt để duy trì tính cá nhân hóa. Với hội thoại ngắn (chỉ 5-10 câu), chi phí "phí cầu đường" (overhead) của việc mang theo file hồ sơ lớn hơn nhiều so với lượng token tiết kiệm được từ việc nén.
* **Tại sao ở hội thoại dài, Compact Memory lại thắng thế vượt bậc?**  
  Trong `Stress Benchmark` (16 lượt chat với nhiều bài báo NASA, WMO dài hàng nghìn từ):
  * **Baseline Agent**: Cứ mỗi lượt mới, nó phải kéo theo toàn bộ văn bản của tất cả các lượt trước đó. Lượng token prompt tích lũy tăng theo hàm bậc hai $O(N^2)$, cán mốc **23,523 tokens**.
  * **Advanced Agent**: Cơ chế `CompactMemoryManager` liên tục theo dõi ngưỡng 800 tokens. Khi tổng token vượt ngưỡng, nó tự động gom các tin nhắn cũ lại thành một bản tóm tắt ngắn gọn và chỉ giữ lại 4 tin nhắn gần nhất. Nhờ nén 14 lần (`Compactions = 14`), tổng tải prompt chỉ còn **13,224 tokens** (giảm tới **43.8%** chi phí token) mà mô hình vẫn nắm rõ toàn bộ mạch ý chính.

### 2.3. Tốc Độ Tăng Trưởng Memory & Rủi Ro Tiềm Ẩn
* **Tăng trưởng bộ nhớ**:  
  File `User.md` tăng từ 0 lên 3,040 bytes trong bài test standard và 234 bytes trong stress test.
* **Rủi ro kỹ thuật**:
  1. **Lossy Compression (Mất mát thông tin khi nén)**: Bản tóm tắt của Compact Memory chỉ giữ lại các ý chính. Nếu người dùng hỏi lại một chi tiết số liệu nhỏ (ví dụ: độ cao chính xác của máy bay X-59), thông tin này có thể đã bị lược bỏ trong quá trình nén.
  2. **Memory Poisoning / Drift (Ô nhiễm bộ nhớ)**: Nếu Agent nghe nhầm hoặc trích xuất sai một câu đùa thành sự thật, sự thật sai đó sẽ bị lưu vĩnh viễn vào `User.md` và đầu độc tất cả các phiên chat trong tương lai.
  3. **Privacy & GDPR Compliance**: Lưu trữ thông tin cá nhân dưới dạng plain text trên đĩa đòi hỏi phải có cơ chế mã hóa, phân quyền và quyền được quên (Right to be Forgotten).

---

## 3. Chi Tiết Các Tính Năng Bonus Kỹ Thuật (Đạt Mức 90 - 100 Điểm)

Để đạt điểm số tối đa theo [Rubric.md](file:///e:/AI%20in%20Action%20VinUni/KX-DAY17-NguyenHaiLong-2A202602471/Rubric.md), hệ thống đã triển khai đầy đủ 4 tính năng mở rộng có giá trị thực tiễn:

### 3.1. Bonus 1: Ngưỡng Tin Cậy & Lọc Nhiễu (Confidence Threshold & Noise Filter)
* **Vấn đề giải quyết**: Người dùng thường xuyên nói đùa (*"chắc chuyển sang làm product manager cho nhàn"*), nhắc đến địa điểm tạm thời (*"ra Hà Nội họp 2 ngày"*), hoặc đặt câu hỏi nghi vấn. Các agent ngây thơ sẽ ghi đè ngay lập tức các thông tin rác này vào hồ sơ.
* **Cơ chế triển khai**:
  * Mỗi thông tin trích xuất được định danh thành `EntityFact` đi kèm điểm tin cậy `confidence` từ 0.0 đến 1.0.
  * Câu khẳng định dứt khoát / đính chính có điểm cao (0.95 - 0.98).
  * Câu đùa, giả định hoặc chuyến đi họp ngắn ngày bị gán điểm thấp (< 0.50).
  * Bộ lọc `extract_profile_updates(min_confidence=0.70)` sẽ từ chối lưu bất kỳ thông tin nào dưới ngưỡng 0.70.
* **Đánh giá rủi ro**: Nếu đặt ngưỡng quá cao (ví dụ 0.99), Agent có thể bỏ sót những sự thật được nói theo cách gián tiếp (False Negative).

### 3.2. Bonus 2: Xử Lý Xung Đột & Nhật Ký Kiểm Toán (Conflict Handling & Revision Log)
* **Vấn đề giải quyết**: Khi người dùng thay đổi thông tin (ví dụ: chuyển nơi ở từ Đà Nẵng sang Huế, hoặc đổi nghề từ backend sang MLOps), hệ thống phải biết ưu tiên thông tin mới nhất và không lưu trữ mâu thuẫn đồng thời hai thông tin đối lập.
* **Cơ chế triển khai**:
  * Hàm `upsert_facts()` trong `UserProfileStore` phát hiện xung đột khi key đã tồn tại với giá trị khác.
  * Giá trị mới sẽ trở thành **Active Fact**.
  * File `User.md` tự động sinh phần `## Lịch sử điều chỉnh (Conflict & Revision Log)` ghi lại: `[Cập nhật lượt X]: 'location' đổi từ 'Đà Nẵng' -> 'Huế'`.
* **Đánh giá rủi ro**: File markdown sẽ dài thêm nếu người dùng thay đổi ý định quá nhiều lần, cần cơ chế nén lịch sử điều chỉnh sau N phiên.

### 3.3. Bonus 3: Cơ Chế Giảm Dần Trọng Số Trí Nhớ (Exponential Memory Decay)
* **Vấn đề giải quyết**: Con người không nhớ mọi thông tin với độ tươi mới như nhau. Những thông tin lâu ngày không được nhắc lại nên giảm độ ưu tiên trong prompt để nhường chỗ cho các ngữ cảnh mới.
* **Cơ chế triển khai**:
  * Áp dụng công thức suy giảm hàm mũ theo chu kỳ bán rã (Half-life decay):
    $$w = 0.5^{\frac{\Delta t}{t_{\text{half}}}}$$
    trong đó $\Delta t$ là khoảng cách số lượt trao đổi kể từ lần cuối fact được xác nhận, $t_{\text{half}} = 15$ lượt.
  * Các facts vừa xác nhận ở lượt trước giữ trọng số $w > 0.90$. Các facts cũ sau 30 lượt không nhắc lại sẽ giảm xuống $w \le 0.25$.
* **Đánh giá rủi ro**: Nếu một thông tin quan trọng (như nhóm máu hoặc dị ứng) lâu không được nhắc lại mà bị decay quá sâu dẫn đến Agent quên mất, có thể gây hậu quả nghiêm trọng. Do đó, cần có cờ `immutable` cho các fact sinh tử.

### 3.4. Bonus 4: Bộ Kiểm Thử Unit Test Tự Động 7/7 Pass
Toàn bộ các tính năng trên đã được kiểm chứng bằng 7 bài unit test nghiêm ngặt trong `src/test_agents.py`:
1. `test_user_markdown_read_write_edit`: Kiểm tra CRUD `User.md`.
2. `test_compact_trigger`: Kiểm tra tự động kích hoạt nén khi chat dài.
3. `test_cross_session_recall`: Kiểm tra Advanced nhớ 100%, Baseline quên 0%.
4. `test_compact_reduces_prompt_load_on_long_thread`: Kiểm tra tiết kiệm tải prompt.
5. `test_bonus_confidence_threshold_rejects_noise_and_jokes`: Kiểm tra lọc câu đùa và nhiễu.
6. `test_bonus_conflict_resolution_and_audit_log`: Kiểm tra giải quyết xung đột và ghi log.
7. `test_bonus_memory_decay`: Kiểm tra tính toán trọng số suy giảm trí nhớ theo thời gian.

---

## 4. Hướng Dẫn Tái Hiện Kết Quả (Reproducibility Guide)

Chạy trên môi trường ảo Python đã thiết lập:

1. **Chạy toàn bộ 7 bài test**:
   ```powershell
   $env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\pytest.exe src/test_agents.py -v
   ```
2. **Chạy 2 Suite Benchmark**:
   ```powershell
   $env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe src/benchmark.py
   ```
