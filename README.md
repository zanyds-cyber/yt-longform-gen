# ytgen — 일본 YouTube 자동 운영 파이프라인

**조사 → 주제 3개 제안 → 대본 → 스톡 영상 수집 → VOICEVOX 음성 → 편집·합성 → 숏츠 → 업로드**를
CLI와 웹 편집 화면(버튼)으로 처리합니다. 기본값은 **ずんだもん × 四国めたん 掛け合い(대화형) 해설 롱폼**입니다.

```
① 조사      YouTube Data API: 키워드 검색 / 일본 급상승 → 조회수·구독자·떡상지수·댓글
② 주제      Claude가 조사 데이터를 분석해 주제 3개 제안 → 선택 → 대화형 대본(챕터·장면)
③ 화면 소스  장면별 영어 검색어로 Pexels/Pixabay 무료 스톡 영상 자동 다운로드 (없으면 AI 이미지)
④ 음성      VOICEVOX (로컬, 무료, 캐릭터별 화자) — 문장 단위로 합성해 자막 싱크 정확
⑤ 합성      스톡 영상 + 캐릭터 스탠딩 이미지 + 화자별 색 자막 + BGM → final.mp4, 썸네일, 설명란(목차·크레딧)
   숏츠     롱폼 대본에서 Claude가 하이라이트를 뽑아 9:16 숏츠 하위 프로젝트 생성
⑥ 업로드    YouTube Data API (OAuth): 제목·설명·태그·썸네일·자막·예약 공개·AI 합성 표시
```

## 설치

```bash
pip install -r requirements.txt          # + ffmpeg 필요 (mac: brew install ffmpeg / Win: winget install ffmpeg)
cp .env.example .env                     # API 키 입력
```
1. **VOICEVOX** 앱 설치·실행 → https://voicevox.hiroshiba.jp/ (실행 중이면 `http://127.0.0.1:50021`에서 엔진 대기)
   `python -m ytgen voices` 로 화자 ID 확인 → `config.yaml`의 `tts.characters[].speaker`
2. **캐릭터 스탠딩 이미지(立ち絵)** — 투명 PNG를 받아 `tts.characters[].image`에 경로 지정
   (예: 坂本アヒル 님의 ずんだもん/四国めたん 立ち絵. **배포처의 이용 규약을 꼭 확인**)
3. **일본어 폰트** — `subtitle.font` (Mac `Hiragino Sans`, Win `Meiryo`, Linux `Noto Sans CJK JP`)

| 키 | 용도 | 발급 |
|---|---|---|
| `YOUTUBE_API_KEY` | 조사 | Google Cloud → YouTube Data API v3 사용 설정 → 사용자 인증 정보 → API 키 |
| `ANTHROPIC_API_KEY` | 주제·대본·숏츠 | console.anthropic.com |
| `PEXELS_API_KEY` | 스톡 영상 (무료) | pexels.com/api |
| `PIXABAY_API_KEY` | 스톡 영상 (무료) | pixabay.com/api/docs |

## 사용법 — 웹 편집 화면 (권장)

```bash
python -m ytgen web        # → http://127.0.0.1:8765
```
- **조사 시작**: 키워드·기간·길이 → 상위 영상 표 (떡상지수 = 조회수 ÷ 구독자)
- **주제 3개 제안받기** → 카드에서 **이 주제로 대본 작성**
- **장면 편집**: 대사 수정 · [미리보기] (그 장면만 렌더링) · [소스 교체] (다른 스톡 영상) · [파일 올리기] (내 영상/이미지) · [＋아래 추가] · [삭제]
- **전체 렌더링** → 영상·썸네일·설명란 확인/수정
- **롱폼에서 숏츠 만들기**
- **업로드** (비공개/일부 공개/공개, 예약 공개)

## 사용법 — CLI

```bash
python -m ytgen research "雑学 動物" --days 30 --duration medium   # 또는 --trending --category education
python -m ytgen topics output/<프로젝트>
python -m ytgen script output/<프로젝트> --pick 2                 # 선택한 주제로 대본
python -m ytgen build output/<프로젝트>
python -m ytgen preview output/<프로젝트> 5                       # 장면 5만
python -m ytgen shorts output/<프로젝트> --count 2 --build
python -m ytgen upload output/<프로젝트> --privacy private --publish-at 2026-11-10T19:00:00+09:00
```
대본을 직접 쓸 때: `python -m ytgen import examples/sample_dialogue.txt --title "猫と箱の秘密"`
(형식: `# 챕터` / 빈 줄 = 장면 / `ずんだもん：대사` / `[img: english keywords]`)

## 유튜브 업로드 설정 (처음 한 번)
1. Google Cloud Console에서 조사용 키와 **같은 프로젝트**의 `OAuth 동의 화면` 설정 (외부, 테스트 사용자에 채널 계정 추가)
2. 사용자 인증 정보 → **OAuth 클라이언트 ID → 데스크톱 앱** → JSON 다운로드 → `credentials/client_secret.json`
3. 첫 업로드 때 브라우저가 열리면 채널 계정으로 로그인 → `credentials/token.json` 저장 (이후 자동)
- 기본 할당량: 업로드 하루 100회, 검색 하루 100회
- 맞춤 썸네일 업로드는 채널 **전화번호 인증**이 필요합니다
- 실사처럼 보이는 AI 합성 장면이 있으면 `upload.contains_synthetic_media: true`

## VOICEVOX 이용 시 꼭 지킬 것
- 설명란에 **`VOICEVOX:ずんだもん` 형식의 크레딧** — 자동으로 들어갑니다 (`■ クレジット`)
- 캐릭터마다 별도 이용 규약이 있습니다 (예: 東北ずん子・ずんだもんプロジェクト 가이드라인). 정치·종교·성적·타인 비방 콘텐츠 금지 등
- 立ち絵 이미지는 음성과 **별도 규약**입니다

## 수익화 안전 가이드
- 2025년 7월부터 YouTube는 **대량 생산·반복적 콘텐츠(inauthentic content)** 를 수익화 대상에서 제외한다고 명시했습니다.
  주제 선택·대본 검수·사실 확인은 사람이 하고, 영상마다 구성과 관점이 달라지게 하세요.
- **남의 유튜브 영상을 내려받아 쓰는 기능은 없습니다** (약관 위반·저작권). 조사한 영상은 기획 참고용이고,
  화면 소스는 Pexels/Pixabay(상업 이용 가능)·AI 이미지·직접 올린 파일만 씁니다.

## 폴더 구조
```
output/<날짜_키워드>/
  research.json/.md  topics.json  script.json(편집 가능, 장면별 선택된 소스 기록)
  final.mp4  thumbnail.jpg  subtitles.srt  description.txt  upload.json
  shorts/1/ …        work/ (캐시: audio, stock, images, clips, preview)
```
