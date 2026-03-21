# setup_pro (Nuke 프로젝트 세팅 자동화)

`setup_pro`는 드라마/영화 프로젝트별로 다른 환경 설정을 프리셋으로 저장하고, Nuke 안에서 선택 적용하는 도구입니다.
특히 컴프팀 실무용으로 필수값 검증과 해상도 프리셋 버튼을 포함합니다.

## 구성

- `setup_pro_manager.py`: 프리셋 저장/수정용 GUI 앱
- `setup_pro_common.py`: 프리셋 JSON 저장/로드 공용 모듈
- `nuke_setup_pro.py`: Nuke 패널 및 프리셋 적용 로직
- `menu.py`: Nuke 상단 메뉴 등록 파일

## 동작 개요

1. `setup_pro_manager.py`에서 프리셋 이름 + 설정값 저장
2. Nuke 실행 후 상단 `setup_pro` 메뉴 열기
3. 저장된 프리셋 선택
4. 선택한 값으로 Nuke 루트/Write 기본값 적용

적용 대상:
- FPS
- Plate Size (Root format)
- OCIO config path
- Write 기본 렌더 설정(file_type, colorspace, codec 일부)
- 프로젝트 타입/코드 메타데이터 (Nuke 패널 표시용)

## 컴프팀 강화 기능

- 프로젝트 타입: 드라마/영화/광고/OTT/기타
- 프로젝트 코드 필수 입력 (영문 대문자, 숫자, `_` 허용)
- 해상도 프리셋 버튼: HD, 2K Scope, UHD, 4K DCI
- 필수값 누락 시 저장 차단 + 누락 항목 목록 표시
- Nuke 패널에서 `타입 | 코드 | 프리셋명` 형태로 선택 가능

## 사용자는 이렇게만 하면 됩니다 (아주 쉬운 버전)

### A. 독립 실행 프로그램(EXE) 만들기 및 배포

1. `build_exe.bat` 더블클릭
2. 완료되면 `dist` 폴더에 exe + Nuke 연동 파일이 모두 생성됨
3. **`dist` 폴더에 들어가서** `setup_pro_manager.exe` 또는 `실행.bat` 더블클릭 → 프로그램 실행
4. 배포 시: `dist` 폴더 전체를 압축(zip)하여 전달
5. 받는 쪽: 압축 해제 후, 해제된 폴더에 들어가서 `setup_pro_manager.exe` 또는 `실행.bat` 실행 (Python 설치 불필요)

빌드 중 `Python Python Python` 같은 메시지가 나오면:
- Python이 실제 설치/연결되지 않은 상태입니다.
- `build_exe.bat`가 원인 안내를 출력하니 안내대로 Python 설치 + PATH 설정 후 다시 실행하세요.
- 최신 `build_exe.bat`는 Python이 없으면 `winget`으로 자동 설치를 시도합니다.

### B. Nuke에 연동하기

1. `install_to_nuke.bat` 더블클릭
2. Nuke 재시작
3. 상단 메뉴 `setup_pro` 확인
4. 처음 1회만 `setup_pro > Refresh setup_pro lists (Write/Formats)` 실행 (드롭다운 목록 채우기)

## 실행 사용법

1. `setup_pro_manager.exe` 실행
2. 프로젝트 타입/프로젝트 코드/프리셋 이름 입력
3. 납품 포맷, fps, plate size, ocio 경로, render 옵션 설정
4. 필요하면 해상도 버튼(HD/2K/UHD/4K) 클릭
5. `저장` 버튼 클릭
6. Nuke에서 `setup_pro > Open setup_pro panel`
7. 프리셋 선택 후 적용

## 기술 참고 (필요한 경우만)

- 프리셋은 `~/.setup_pro/presets.json` 파일에 저장됩니다.
- Nuke는 `.nuke` 폴더의 `menu.py`를 시작 시 자동 로드합니다.
- 따라서 구조는 항상 2개로 나뉩니다:
  - 독립 실행 EXE: 설정 저장
  - Nuke 패널: 저장값 선택/적용

## 주의사항

- 프리셋은 사용자 홈 폴더의 `~/.setup_pro/presets.json`에 저장됩니다.
- Nuke 버전에 따라 OCIO 관련 knob 이름이 다를 수 있어, 코드에서 여러 후보 knob를 순차 적용합니다.
- `render_codec`는 파일 타입별로 knob 이름이 다를 수 있어 `mov64_codec` 기준 기본값을 넣습니다.

필요하면 다음 단계로 확장 가능합니다:
- 쇼/시즌/에피소드 단위 프리셋 그룹
- 팀 공용 네트워크 프리셋 저장소
- Write 노드 자동 생성 템플릿
- 프로젝트별 폴더 생성 자동화
"# Beluca__Pipeline-in-house-" 
