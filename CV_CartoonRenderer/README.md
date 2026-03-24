# ToonCraft

OpenCV 기반 이미지 만화 스타일 변환 프로그램입니다.

## 과제 조건 대응

- 필수 기능: 이미지 처리 기법으로 입력 이미지를 만화 스타일로 변환
- README 포함 내용:
  - 만화 느낌이 잘 표현되는 데모
  - 만화 느낌이 잘 표현되지 않는 데모
  - 알고리즘 한계점 분석

## 알고리즘 개요

1. Bilateral Filter로 텍스처를 줄이면서 윤곽은 유지
2. K-means 색상 양자화로 색상 수를 줄여 만화 느낌 강화
3. 스타일 프리셋(soft/vivid/cinematic)으로 분위기 보정
4. 강도 슬라이더로 원본-카툰 혼합 비율 제어
5. 선택적으로 얼굴 영역만 톤/노이즈 보정

## 실행 환경

- Python 3.10+
- OpenCV (`opencv-python` 또는 `opencv-contrib-python`)
- NumPy

설치 예시:

```powershell
python -m pip install opencv-python numpy
```

## 실행 방법

### 가장 간단한 사용법 (권장)

1. 프로젝트 폴더 안에 `input/` 폴더를 만들고 처리할 이미지를 넣습니다.
2. 아래 명령어만 실행하면 `input/` 안의 이미지들을 한 번에 처리합니다.

```powershell
python cartoon_renderer.py
```

출력 파일은 `outputs/파일명_cartoon.png` 형식으로 저장됩니다.

### 단일 이미지 직접 지정

```powershell
python cartoon_renderer.py --input examples/good_case.jpg --output outputs/good_case_cartoon.png --compare --save-steps
```

주요 옵션:

- `--input`: 입력 이미지 또는 폴더 경로 (기본 `input`)
- `--output`: 단일 이미지 모드에서 출력 파일 경로
- `--output-dir`: 출력 폴더 경로 (기본 `outputs`)
- `--k-colors`: 색상 클러스터 수 (기본 8)
- `--bilateral-d`, `--bilateral-sigma-color`, `--bilateral-sigma-space`: smoothing 강도
- `--edge-block-size`, `--edge-c-value`, `--edge-blur-ksize`: 엣지 검출 강도
- `--style`: 렌더링 프리셋 (`basic`, `soft`, `vivid`, `cinematic`)
- `--cartoon-strength`: 카툰 강도 (`0.0`~`1.0`)
- `--face-enhance`: 얼굴 영역 보정 ON
- `--face-enhance-strength`: 얼굴 보정 강도 (`0.0`~`1.0`)
- `--auto-search`: 스타일/파라미터 후보들을 자동 탐색 후 추천 결과 선택
- `--contact-sheet`: 배치 처리 결과를 `outputs/contact_sheet.png`로 요약 저장
- `--compare`: 원본/결과 비교 이미지 저장
- `--save-steps`: 중간 결과(양자화, 엣지) 저장
- `--show`: 결과 창 표시

프리셋 예시:

```powershell
python cartoon_renderer.py --style soft --compare
python cartoon_renderer.py --style vivid --compare
python cartoon_renderer.py --style cinematic --compare --contact-sheet
```

신규 고급 기능 예시:

```powershell
# 1) 카툰 강도 슬라이더
python cartoon_renderer.py --style vivid --cartoon-strength 0.35
python cartoon_renderer.py --style vivid --cartoon-strength 0.85

# 2) 얼굴 보정
python cartoon_renderer.py --style soft --face-enhance --face-enhance-strength 0.6 --compare

# 3) 자동 탐색 모드 (후보 + 추천)
python cartoon_renderer.py --auto-search --face-enhance --compare
```

`--auto-search` 사용 시 이미지마다 아래 파일이 추가로 생성됩니다.

- `outputs/<파일명>_candidate_*.png`: 탐색 후보 결과들
- `outputs/<파일명>_search_sheet.png`: 원본/후보를 한 장에 모은 비교 시트

## 데모 (필수)

아래 두 케이스 이미지를 `input/`에 넣고 실행해서 결과 이미지를 첨부하세요.

### 1) 잘 표현되는 이미지 데모

권장 입력 특성:

- 피사체 윤곽이 뚜렷함
- 배경이 단순함
- 조명이 비교적 균일함

예시 파일:

- 입력: `input/good_case.jpg`
- 출력: `outputs/good_case_cartoon.png`
- 비교: `outputs/good_case_cartoon_compare.png`

실행:

```powershell
python cartoon_renderer.py --input input --output-dir outputs --compare --save-steps
```

### 2) 잘 표현되지 않는 이미지 데모

권장 입력 특성:

- 복잡한 텍스처(나뭇잎, 잔디, 머리카락 등)
- 조명/노이즈 변화가 큼
- 윤곽이 약하거나 겹침이 많음

예시 파일:

- 입력: `input/bad_case.jpg`
- 출력: `outputs/bad_case_cartoon.png`
- 비교: `outputs/bad_case_cartoon_compare.png`

실행:

```powershell
python cartoon_renderer.py --input input --output-dir outputs --compare --save-steps
```

## 알고리즘 한계점

- 미세한 텍스처가 많은 영역은 과도하게 뭉개지거나 노이즈처럼 남을 수 있음
- 밝기 대비가 약한 경계는 엣지 검출이 실패할 수 있음
- 이미지 장면에 따라 최적 파라미터가 달라 고정 파라미터의 일반화가 어려움
- K-means 양자화로 인해 색상 banding이 발생할 수 있음

## 참고

- `CV_VideoRecorder/video_recorder.py`의 OpenCV 기반 구조를 참고하되,
  본 프로젝트는 이미지 기반 cartoon rendering에 맞춰 별도 구현했습니다.
