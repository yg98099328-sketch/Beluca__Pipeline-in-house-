# setup_pro (Nuke 프로젝트 세팅 · Shot Builder)

프로젝트별 FPS / 해상도 / OCIO / Write 등을 **프리셋**으로 저장하고, Nuke에서 한 번에 적용합니다.  
**Shot Builder** 탭으로 샷 경로에 맞는 `.nk` 템플릿을 생성할 수 있습니다.

## 폴더 구조 (개발 · Cursor에서 수정할 때)

| 경로 | 설명 |
|------|------|
| **`src/`** | **여기만 주로 수정** — `setup_pro_manager.py`, `setup_pro_common.py`, `nuke_setup_pro.py`, `menu.py`, `shot_node_template.nk` |
| `scripts/` | `install_to_nuke.bat`, `reset_deploy.bat`, `run_dev.bat` |
| `docs/` | 팀 배포용 안내 `배포_사용법.txt` |
| `build_exe.bat` | EXE 빌드 → 결과는 **`release/`** |
| `VERSION.txt` | 앱 버전 (빌드 시 patch 자동 증가) |

배포할 때는 **`release/` 폴더 전체**를 zip 하거나 폴더째 복사하면 됩니다.

## 빠른 시작 (개발)

1. `scripts\run_dev.bat` — Python으로 GUI만 실행 (빌드 없음)
2. Nuke 연동: `scripts\install_to_nuke.bat` (`.nuke`에 `menu.py` 등 복사)

## EXE 빌드 · 배포

1. 루트에서 **`build_exe.bat`** 실행  
2. **`release\`** 에 `setup_pro_manager.exe`, Nuke용 `.py`, `install_to_nuke.bat`, `실행.bat`, `README_사용법.txt` 생성  
3. **`release\` 전체**를 팀에 전달

자가 업데이트(프로그램 내 버튼)는 `release\setup_pro_manager_next.exe`를 만들고, **저장소 루트**에 `build_exe.bat`가 있어야 동작합니다.

## Nuke 쪽 (받는 사람)

1. 배포 폴더에서 `install_to_nuke.bat` 실행  
2. Nuke 재시작 → 메뉴 **`setup_pro`**  
3. 처음 1회 `setup_pro > Refresh setup_pro lists` 권장  

## 데이터 저장 위치

- 프리셋: `~/.setup_pro/presets.json` (또는 앱에서 지정한 폴더)
- Shot Builder 설정: `~/.setup_pro/shot_builder.json`

## 기술 참고

- Nuke는 `~/.nuke/menu.py` 로드 시 `nuke_setup_pro` 를 불러옵니다.
- OCIO/Write knob 이름은 Nuke 버전별로 달라 `nuke_setup_pro.py`에서 후보를 순차 시도합니다.

자세한 사용자 안내는 **`docs/배포_사용법.txt`** (빌드 시 `release/README_사용법.txt`로 복사됨)를 참고하세요.
