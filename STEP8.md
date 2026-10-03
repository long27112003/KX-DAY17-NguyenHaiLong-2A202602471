# Phân Tích Kết Quả Benchmark (Bước 8 - GUIDE.md)

> **Họ và tên**: Nguyễn Hải Long  
> **MSSV**: 2A202602471  
> **Repo**: KX-DAY17-NguyenHaiLong-2A202602471  

Tài liệu này trả lời chi tiết và khoa học 4 câu hỏi trọng tâm tại **Bước 8 của GUIDE.md**, dựa trên số liệu thực nghiệm đo lường được từ `python src/benchmark.py`.

---

## Bảng Kết Quả Thực Nghiệm Đối Chứng

### Standard Benchmark (10 Hội thoại bình thường)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline Agent** | 2,748 | 19,760 | **0.0%** | 0.20 | 0 B | 0 |
| **Advanced Agent** | 7,712 | 44,669 | **98.2%** | 0.99 | 3,480 B | 2 |

### Long-Context Stress Benchmark (16 Lượt chat dài)
| Agent | Agent tokens only | Prompt tokens processed | Cross-session recall | Response quality | Memory growth | Compactions |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline Agent** | 439 | 23,523 | **0.0%** | 0.20 | 0 B | 0 |
| **Advanced Agent** | 2,443 | **13,395** | **100.0%** | 1.00 | 278 B | **14** |

---

## Câu Hỏi 1: Vì sao Advanced có recall tốt hơn Baseline?

* **Baseline Agent (Recall = 0.0%)**:  
  Baseline Agent chỉ quản lý ngữ cảnh tạm thời trong cùng một phiên chat (`SessionState` gắn với từng `thread_id`). Khi người dùng mở sang một thread mới (như các câu hỏi recall chéo phiên), Baseline không có cơ chế lưu trữ bền vững (persistent storage) nên toàn bộ dữ liệu lịch sử trước đó hoàn toàn biến mất. Do đó, Baseline không thể nhớ được tên, nghề nghiệp hay sở thích của người dùng ở phiên mới.
* **Advanced Agent (Recall = 98.2% – 100.0%)**:  
  Advanced Agent được trang bị tầng **Persistent Memory** với `UserProfileStore`. Mọi thông tin cốt lõi (tên, nơi ở mới nhất sau khi đính chính, nghề nghiệp, đồ uống, sở thích) được tự động trích xuất và lưu vào đĩa dưới dạng file Markdown `User.md`. Khi bước sang bất kỳ thread mới nào, Agent tự động nạp hồ sơ người dùng vào ngữ cảnh prompt, giúp trả lời chính xác tất cả các câu hỏi nhớ lại.

---

## Câu Hỏi 2: Vì sao Advanced có thể tốn hơn ở hội thoại ngắn?

* Trong `Standard Benchmark` (các hội thoại ngắn ~10 lượt), `Prompt tokens processed` của Advanced Agent (44,669 tokens) cao hơn so với Baseline (19,760 tokens).
* **Nguyên nhân**:
  1. **Chi phí nạp hồ sơ ban đầu (Overhead)**: Ở mọi lượt chat, Advanced Agent luôn chèn (inject) toàn bộ nội dung file `User.md` vào phần System Prompt để cá nhân hóa câu trả lời.
  2. **Chưa đủ ngưỡng nén**: Ở hội thoại ngắn, tổng dung lượng chưa vượt quá ngưỡng 800 tokens nên cơ chế nén `CompactMemoryManager` chưa phát huy được ưu thế tiết kiệm.
  3. **Phản hồi có cấu trúc**: Advanced Agent sinh ra các phản hồi chi tiết, có định dạng bullet và lập luận trade-off (7,712 output tokens so với 2,748 output tokens của Baseline).

---

## Câu Hỏi 3: Vì sao Compact giúp Advanced có lợi thế ở hội thoại dài?

* Trong `Long-Context Stress Benchmark` (chuỗi 16 lượt dài gồm nhiều văn bản khoa học NASA, WMO):
  * **Baseline Agent** không có cơ chế nén. Qua từng lượt trao đổi, nó phải gồng gánh toàn bộ lịch sử trò chuyện từ đầu đến cuối, khiến lượng prompt token tích lũy tăng phi mã theo hàm bậc hai $O(N^2)$, cán mốc **23,523 tokens**.
  * **Advanced Agent** liên tục theo dõi tải ngữ cảnh qua `CompactMemoryManager`. Khi dung lượng vượt ngưỡng 800 tokens, nó tự động gom các tin nhắn cũ lại thành một bản tóm tắt súc tích và chỉ giữ lại 4 tin nhắn gần nhất.
* **Kết quả**: Cơ chế nén kích hoạt **14 lần (`Compactions = 14`)**, kéo giảm lượng prompt tokens processed từ 23,523 xuống chỉ còn **13,395 tokens** (tiết kiệm tới **43.8% chi phí ngữ cảnh**) mà vẫn giữ được chất lượng phản hồi điểm tuyệt đối 1.00.

---

## Câu Hỏi 4: File memory tăng trưởng ra sao và rủi ro gì đi kèm?

* **Tốc độ tăng trưởng**:
  * File `User.md` tăng từ 0 lên 3,480 bytes trong 10 hội thoại standard và 278 bytes trong stress test. Khi người dùng cung cấp thêm facts hoặc đính chính thông tin, kích thước file tăng tuyến tính theo số lượng facts được lưu trữ.
* **Các rủi ro tiềm ẩn**:
  1. **Memory Poisoning & Noise (Nhiễm độc bộ nhớ)**: Nếu người dùng nói đùa (*"chắc chuyển sang làm product manager"*) hoặc nhắc đến địa điểm tạm thời (*"ra Hà Nội họp"*), một hệ thống không có bộ lọc sẽ ghi nhầm các dữ liệu rác này vào `User.md`, làm sai lệch toàn bộ các phiên chat sau này. *(Hệ thống đã giải quyết bằng Confidence Threshold $\ge 0.70$)*.
  2. **Conflict & Outdated Facts (Xung đột thông tin cũ - mới)**: Khi người dùng đổi việc hay chuyển nhà, nếu lưu đồng thời cả hai thông tin sẽ gây mâu thuẫn nhận thức cho Agent. *(Hệ thống đã giải quyết bằng cơ chế Conflict Handling ghi đè fact mới và lưu nhật ký điều chỉnh)*.
  3. **Lossy Compression (Mất mát chi tiết khi nén)**: Bản tóm tắt của Compact Memory chỉ giữ lại các ý chính, các số liệu tiểu tiết có thể bị mất đi.
  4. **Quyền riêng tư & Bảo mật (Privacy/GDPR)**: Lưu trữ hồ sơ người dùng dạng plain text đòi hỏi phải có cơ chế mã hóa và chức năng xóa dữ liệu khi người dùng yêu cầu ("Quyền được quên").
