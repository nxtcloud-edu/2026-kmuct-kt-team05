# 미래관 층 표기 대응표 (floor mapping)

작성: 2026-09-20 · **모든 `canonical_floor_id` 는 미확정(null)**

## 왜 4종류로 분리하는가

미래관 도면에서 **웹페이지 탭 이름과 도면 내부 인쇄 표기가 불일치**한다.
어느 한쪽을 서비스 층 ID 로 자동 승격하면 층간 경로가 통째로 틀어지므로
아래 4개를 각각 다른 필드에 저장한다.

| 필드 | 뜻 | 출처 |
|---|---|---|
| `source_tab_label` | 공식 페이지의 탭 버튼 글자 | 페이지 HTML |
| `source_filename` | 자산 파일명 | 페이지 HTML `<img src>` |
| `drawing_floor_label` | **도면 안에 인쇄된 표제부 글자** | 원본 PNG OCR + 육안 |
| `canonical_floor_id` | 서비스에서 쓸 층 ID | **아직 없음 (null)** |

## 대응표

| # | 웹 탭 (`source_tab_label`) | 페이지 탭 ID | 파일 (`source_filename`) | 도면 내부 표기 (`drawing_floor_label`) | `canonical_floor_id` | `mapping_status` |
|---|---|---|---|---|---|---|
| 1 | 3층 | mi-f3 | Mirae_3F.png | 지상 3층 | **null** | pending_review |
| 2 | 4층 | mi-f4 | Mirae_4F.png | 지상 4층 | **null** | pending_review |
| 3 | 5층 | mi-f5 | Mirae_5F.png | 지상 5층 | **null** | pending_review |
| 4 | 6층 | mi-f6 | Mirae_6F.png | 지상 6층 | **null** | pending_review |
| 5 | 7층 | mi-f7 | Mirae_7F.png | 지상 7층 | **null** | pending_review |
| 6 | 지하 1층 | mi-b1 | Mirae_B1.png | 지하 1층 | **null** | pending_review |
| 7 | **지하 2층-①** | mi-b2a | Mirae_B2_1.png | **지상 1층** | **null** | **source_label_conflict** |
| 8 | **지하 2층-②** | mi-b2b | Mirae_B2_2.png | **지상 2층** | **null** | **source_label_conflict** |

판독 방법: `scripts/record_floor_labels.py` (Windows.Media.Ocr, ko, 표제부 확대 3배).
8/8 판독 성공. 첨부 목록에 기록이 있던 5건은 **전부 일치**(`drawing_floor_label_agrees=true`),
5·6·7층은 첨부 목록이 null 이었고 이번에 신규 판독했다.

## 충돌 2건의 상세

```
웹 탭 "지하 2층-①"  →  Mirae_B2_1.png  →  도면 표제부 "지상1층 평면도 / 미래관"
웹 탭 "지하 2층-②"  →  Mirae_B2_2.png  →  도면 표제부 "지상2층 평면도 / 미래관"
```

### 확인된 사실

- 표제부 글자는 OCR 과 육안 판독이 일치한다.
- `Mirae_B2_1.png` 의 호실은 `102`, `109`, `123`, `122-1` 등 **1xx 계열**이다.
- `Mirae_B2_2.png` 의 호실은 `201`–`237` 의 **2xx 계열**이다.
- 두 파일의 호실 번호 계열은 각자의 도면 내부 표기와 정합한다.
- 이 8개 목록에는 별도의 「1층」·「2층」 탭이 없다.

### 하지 않은 것

- **원인 단정.** 웹 탭 라벨 오류로 보이지만 이번 조사만으로 확정하지 않는다.
- **두 B2 파일을 하나의 지하층 구역으로 병합.** 하지 않았다.
- **파일명에서 층 확정.** `B2_1` → `B2` 로 읽지 않았다.
- **"1·2층 버튼이 없으니 1·2층 도면이 없다"는 결론.** 실제로는 1·2층 도면이
  잘못된 탭 이름 아래 있는 것으로 보인다. 역으로 **진짜 지하 2층 도면은 이 목록에
  공개되지 않았을 수 있다.**
- **3층과 B2_2 의 상하 인접 관계 확정.** `sort_order` 는 임시값이다.

### 서비스에서의 임시 처리

`data/published/mirae_indoor_v1.json` 에서 B2_2 대응 층은
`canonical_floor_id` 를 비워둔 채 **임시 ID** 를 쓴다.

```
floor_id = "mirae/DRAWING-2F"
label    = "원본상 2층 (서비스 층 미확정)"
notes    = ["웹 탭='지하 2층-②', 도면 내부 표기='지상2층'. 원인 미확인.", ...]
```

3층은 웹 탭과 도면 표기가 일치하므로 `mirae/F3` 를 쓰되, `mapping_status` 는
현장 표지 대조 전까지 `pending_review` 로 유지한다.

## 확정에 필요한 현장/추가 자료

| 확인 대상 | 방법 | 이 확인이 풀어주는 것 |
|---|---|---|
| 미래관 각 층 현장 층수 표지 | 건물 내 층별 표지판·엘리베이터 버튼 사진 | `canonical_floor_id` 전체 |
| 202호가 실제로 몇 층인지 | 202호 문 앞 층 표지 확인 | B2_2 의 층 확정 |
| 「지하 2층」 도면 존재 여부 | 시설 부서 문의 또는 추가 공개자료 | 목록 완전성 |
| 3층과 202호 층의 상하 관계 | 계단/엘리베이터 표시 대조 | `sort_order`, 층간 경로 |
| 1층 주 출입구가 만나는 지면 높이 | 현장 확인 | 실외 연결 |

이 항목들은 `docs/data_gaps.md` 에 대상 ID 별로 다시 적었다.
