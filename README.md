# yt-longform-gen — 일본어 YouTube 롱폼 영상 생성기

주제 하나 → **대본 → 음성 → 장면 이미지 → 자막 → 1080p 영상 + 썸네일 + 설명란(챕터)** 까지 자동 생성하는 Python CLI.

```
주제 ──(Claude)──> script.json ──(TTS: 문장 단위)──> 음성
                       │                               │ (정확한 자막 타이밍)
                       └──(이미지 생성/검색)──> 장면 이미지
                                                       ▼
                      켄번스(줌/팬) + 자막 입힌 장면 클립 → 이어붙이기 → BGM 믹스
                                                       ▼
          final.mp4 · thumbnail.jpg · subtitles.srt · description.txt(目次 포함)
```

## 설치

```bash
# ffmpeg 필요 (mac: brew install ffmpeg / Windows: winget install ffmpeg)
pip install -r requirements.txt
```
일본어 폰트가 필요합니다. `config.yaml`의 `subtitle.font`를 설치된 폰트 이름으로 맞춰 주세요
(예: Mac `Hiragino Sans`, Windows `Meiryo`, Linux `Noto Sans CJK JP` / `IPAGothic`).

## 사용법

### A. Claude로 대본까지 자동 (권장)
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m ytgen script "睡眠の質を上げる科学的な方法" --minutes 20 --notes "初心者向け。具体例多め"
#  → output/<날짜_주제>/script.json 생성. 열어서 내레이션·이미지 프롬프트를 확인/수정
python -m ytgen build output/<날짜_주제>
```
한 번에: `python -m ytgen run "テーマ" --minutes 20`
참고 자료가 있으면 `--notes-file 資料.txt` (사실 정확도가 크게 올라갑니다).

### B. 전부 무료 (대본을 직접 작성)
`examples/sample_script.txt` 형식으로 작성:
```
# 章の見出し            ← 챕터 (YouTube 目次가 됨)

ナレーション文…          ← 빈 줄로 구분된 단락 = 한 장면(이미지 1장)
[img: english image prompt]   ← 선택
```
```bash
python -m ytgen import examples/sample_script.txt --title "夜更かしの科学"
python -m ytgen build output/<날짜_제목>
```

### 썸네일만 다시 만들기
`python -m ytgen build output/<프로젝트> --thumbnail-only`

## 설정 (`config.yaml`)

| 항목 | 선택지 | 비고 |
|---|---|---|
| `tts.engine` | `edge` (무료, 기본) · `voicevox` (무료, [VOICEVOX](https://voicevox.hiroshiba.jp/) 실행 필요) · `dummy` | 일본 채널에선 VOICEVOX 캐릭터 음성이 인기. 크레딧 표기 규약 확인 |
| `image.provider` | `pollinations` (무료·키 없음) · `openai` (유료, `OPENAI_API_KEY`) · `pexels` (무료 실사진, `PEXELS_API_KEY`) · `placeholder` | 실패 시 자동으로 플레이스홀더로 대체 |
| `claude.channel_style` | 자유 텍스트 | 채널 톤. 대본 품질에 가장 큰 영향 |
| `video.motion` | `kenburns` · `none` | `none`이면 렌더링이 훨씬 빠름 |
| `video.workers` | 숫자 | 클립 병렬 렌더링 수 |
| `subtitle.burn` | `true` · `false` | false면 SRT만 생성 → YouTube에 자막 파일로 업로드 |
| `bgm.path` | 파일 또는 폴더 | 폴더면 랜덤 선택. 저작권 프리 음원 사용 |

## 편리한 점
- **이어서 하기/부분 재생성**: 음성·이미지·클립은 내용 해시로 캐시됩니다. `script.json`에서 한 장면만 고치고 `build`를 다시 돌리면 바뀐 부분만 새로 만듭니다. 마음에 안 드는 이미지는 `work/images/`에서 지우거나 프롬프트를 바꾸면 됩니다.
- **싱크 정확**: 문장 단위로 TTS를 만들고 장면 길이를 프레임 단위로 맞춰 긴 영상에서도 자막/음성이 밀리지 않습니다.
- **설명란 자동**: `description.txt`에 설명 + 目次(챕터 타임스탬프) + 해시태그 + 제목 후보/태그.

## 출력물
```
output/<프로젝트>/
  script.json      대본 (편집 가능)
  final.mp4        완성 영상 (1920x1080, H.264/AAC)
  thumbnail.jpg    1280x720 썸네일
  subtitles.srt    자막 파일
  description.txt  설명란 + 메타데이터
  work/            캐시 (삭제해도 됨)
```

## 수익화 관련 주의
YouTube는 AI 생성/반복적인 "양산형" 콘텐츠에 대해 수익화를 제한할 수 있습니다. 대본 검수·사실 확인, 채널 고유의 관점 추가,
이미지 교체 등 사람의 편집을 거치는 것을 권장합니다. 실사처럼 보이는 AI 이미지는 업로드 시 "변경되거나 합성된 콘텐츠" 표시 대상인지 확인하세요.
