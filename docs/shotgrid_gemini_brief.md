# BPE (setup_pro) × ShotGrid Publish 연동 — Gemini 논의용 브리핑

아래 블록 전체를 복사해 Gemini 등에 붙여넣어 대화를 시작하면 됩니다.

---

## [복사 시작]

### 0. 목적

우리는 **BPE (BELUCA Pipeline Engine, 내부명 setup_pro)** 에 **ShotGrid(구 Shotgun) API** 를 써서 **퍼블리시(Publish)** 를 등록하는 기능을 추가하려고 한다.  
이 문서는 **현재 프로그램이 무엇을 하는지**, **데이터·경로 규칙**, **Nuke 연동 방식**, 그리고 **추천 아키텍처**를 정리한 것이다.

---

### 1. 프로그램 개요 (한 줄)

**Nuke용 파이프라인 프리셋 + Shot Builder**: 프로젝트별 FPS / 해상도 / OCIO / Write 납품 포맷 등을 **프리셋(JSON)** 으로 저장하고 Nuke에서 한 번에 적용하며, **샷 폴더 규칙**에 맞춰 `.nk` 스크립트를 생성한다.

- **배포 이름**: README/실행 파일 맥락에서 BPE, 코드/모듈명은 `setup_pro_*` 혼용.
- **버전 예시**: `VERSION.txt` (예: 0.1.87).
- **GUI**: CustomTkinter (`setup_pro_manager.py` → PyInstaller로 `BPE.exe` 등 빌드).
- **Nuke 쪽**: `nuke_setup_pro.py` + `menu.py` 훅 → 메뉴 `setup_pro`.

---

### 2. 소스 구조 (수정 시 주로 보는 경로)

| 경로 | 역할 |
|------|------|
| `src/setup_pro_manager.py` | 메인 GUI (프리셋 관리, Shot Builder 탭, 설정 UI). |
| `src/setup_pro_common.py` | 공통 로직: `presets.json` / `settings.json` / `shot_builder.json`, 샷 경로 빌드, NK 파싱·템플릿 치환 등. |
| `src/nuke_setup_pro.py` | Nuke 메뉴 등록, 프리셋 적용, Write 생성, **QC Checker**(BeforeRender), **Post-Render**(AfterRender에서 Read 생성·Viewer 연결 등). |
| `src/menu.py` | `.nuke` 설치용: `nuke_setup_pro.add_setup_pro_menu()`, `reload_tool_hooks()`. |
| `src/shot_node_template.nk` | Shot Builder가 기반으로 쓰는 노드 트리 템플릿. |

빌드: 루트 `build_exe.bat` → `release/` 에 EXE + Nuke용 파일 복사.

---

### 3. 로컬 데이터 저장 위치

- **앱 루트**: `~/.setup_pro/` (`APP_DIR` in `setup_pro_common.py`).
- **프리셋 파일**: `get_presets_dir() / "presets.json"` — 기본은 `~/.setup_pro`, 설정으로 다른 폴더 지정 가능 (`settings.json` 의 `presets_dir`).
- **앱 설정**: `~/.setup_pro/settings.json` (프리셋 폴더, **BPE Tools** on/off 등).
- **Shot Builder 마지막 값**: `~/.setup_pro/shot_builder.json` — 현재는 대략 `server_root`, `preset` 키.
- **Nuke 포맷/컬러스페이스 캐시**: `~/.setup_pro/cache/*.json`.

ShotGrid 연동 설정(사이트 URL, 스크립트 키, 프로젝트 매핑 등)은 **아직 없음** → 새로 `settings.json` 확장 또는 `shotgrid.json` 같은 전용 파일을 두는 설계가 필요.

---

### 4. 프리셋(`presets.json`)이 담는 것 (개념)

프리셋은 **이름 → dict** 구조. Nuke 루트·Read·Write에 반영되는 필드들이 포함된다 (정확한 키 전체는 코드 `nuke_setup_pro.apply_preset` / `_create_write_node_with_settings` 등 참고).

대표적으로:

- **프로젝트 식별**: `project_code` (서버 경로·Write 경로에 쓰임; Nuke 쪽에서 경로에 코드가 있으면 프리셋 추론에 사용).
- **타이밍**: `fps`, 플레이트 해상도/포맷 이름, **OCIO config 경로**.
- **Write / 납품**: 납품 포맷(EXR/ProRes 등), 컬러스페이스·display/view 관련 필드.
- **경로 패턴**: 플레이트·편집본·렌더 등 **문자열 템플릿** (Shot Builder NK 생성 시 치환).

프리셋별 **커스텀 NK 템플릿**: `{presets_dir}/{preset_name}_template.nk` 파일로 오버라이드 가능.

---

### 5. Shot Builder — 샷 이름·폴더 규칙 (퍼블리시 매핑에 중요)

**샷 이름 파싱** (`setup_pro_common.parse_shot_name`):

- 예: `E107_S022_0080` → `ep = "E107"`, `full = "E107_S022_0080"` (대문자 정규화).
- 규칙: `_` 로 split 했을 때 최소 2토큰; 첫 토큰이 에피소드 폴더명.

**서버 경로** (`build_shot_paths(server_root, project_code, shot_name)`):

```
{server_root} / {project_code} / 04_sq / {ep} / {full} / ...
```

하위 키:

- `shot_root`, `nuke_dir` (`.../comp/devl/nuke`), `plate_hi`, `edit`, `renders`, `element` 등.

**ShotGrid와의 연결 힌트**: 스튜디오가 ShotGrid의 **Shot 코드**를 폴더명 `full` 과 동일하게 쓰면 매핑이 쉬움. 다르멀 **커스텀 필드** 또는 **이름 변환 테이블**이 필요.

---

### 6. Nuke 쪽 동작 요약

- 메뉴 `setup_pro` → 프리셋 적용 패널, 캐시 갱신, **BPE Tools** 서브메뉴.
- **Tool Hooks** (`reload_tool_hooks`): `settings.json` 의 `tools` 로 BeforeRender / AfterRender 콜백 등록.
- **QC BeforeRender** (`bpe_qc_before_render`): `nuke.execute()` 컨텍스트 안에서 실행되므로, UI/노드 조작은 **`nuke.executeDeferred`** 로 미루고, **재렌더 시 무한 루프 방지**용 `_bpe_qc_approved` set 사용. (이 패턴은 ShotGrid 업로드가 렌더 직후에 돌 경우에도 동일 제약이 적용될 수 있음.)
- **Post-render** (`bpe_post_render_load`): 출력 Read 생성 등은 deferred.

**검증 철학**: knob `setValue` 후 실제 값 확인, 실패 시 `nuke.tprint` / `nuke.message` 로 피드백 (워크스페이스 규칙).

---

### 7. 기술 스택 · 배포 제약

- **Python 3**, GUI **CustomTkinter**, Nuke 내장 Python 환경과 **별도** — Nuke에서 쓰는 모듈은 Nuke에 **복사되는 `.py`만** 의존하면 됨 (`shotgun_api3` 를 Nuke 쪽에 넣을지, 외부 CLI로만 쓸지 결정 필요).
- **PyInstaller** 빌드 시 `hiddenimports` 등에 ShotGrid 클라이언트 라이브러리를 넣어야 할 수 있음.

---

### 8. ShotGrid 퍼블리시 기능 — 추천 설계 (구현 관점)

#### 8.1 어디에 버튼/엔트리포인트를 둘지

| 위치 | 장점 | 단점 |
|------|------|------|
| **A. Nuke 메뉴** (`nuke_setup_pro`) | 아티스트 워크플로우와 직결, Write 경로·프레임 범위 즉시 접근 | Nuke PYTHONPATH에 `shotgun_api3` 필요할 수 있음 |
| **B. BPE 데스크톱 GUI** | 의존성 패키징 쉬움, 로그인 UI 넣기 좋음 | “지금 스크립트의 Write”와 동기화하려면 NK 경로 전달 또는 파일 픽커 필요 |
| **C. 둘 다** | 유연 | 설정·코드 중복 관리 필요 |

**추천**: 1단계는 **Nuke 메뉴**에서 “현재 선택 Write / 또는 대표 Write” 기준 퍼블리시 + **BPE GUI**에는 **연결 설정·테스트 연결**만. (또는 역으로 GUI에서만 시작해도 됨 — 팀 정책에 따름.)

#### 8.2 인증

- **스크립트 이름 + API 키** (서버에 등록된 스크립트 사용자): 스튜디오 표준에 맞춤.
- 키는 **코드에 하드코딩 금지** → 환경 변수 또는 `~/.setup_pro/shotgrid_credentials.json` (권한 제한) 또는 OS 자격 증명 저장소.

#### 8.3 무엇을 “Publish” 엔티티로 만들지

일반적 패턴:

1. **PublishedFile** (또는 팀이 쓰는 커스텀 엔티티) 생성.
2. `path` / `path_cache` — 윈도우·리눅스 경로 정책에 맞게 **플랫폼별 필드** 채움.
3. 링크: **`Version`** 에 링크하거나, **`Shot` + `Task`(Comp 등)** 에 링크.
4. **Thumbnail** — 첫 프레임 경로가 있으면 업로드 (선택).

**우리 앱과 맞출 데이터 소스**:

- Write 노드 `file` knob (프레임 패턴 `%04d` 등).
- `root` FPS, 프레임 범위.
- 샷 코드: **스크립트 경로** 또는 **프리셋 `project_code` + 폴더 구조** 또는 **사용자 입력**에서 추출 — 신뢰도 순으로 설계.

#### 8.4 Shot ↔ 파일 경로 매핑

- **이상적**: ShotGrid `Shot.code` == `parse_shot_name` 의 `full`.
- **아니면**: 프리셋에 `shotgrid_project_id` / 코드 접두 규칙 저장, 또는 API로 `Shot` 검색 (`code`, `description`).

#### 8.5 렌더 타이밍과 “퍼블리시 시점”

- **옵션 1**: 렌더 **완료 후** AfterRender에서 자동 퍼블리시 — *주의*: 콜백 안에서는 무거운 API/UI를 **deferred** 로.
- **옵션 2**: 사용자가 **수동** “ShotGrid에 퍼블리시” — 가장 단순·안전.
- **옵션 3**: farm 제출 툴과 연동 — BPE 범위 밖일 수 있음.

**추천**: 먼저 **수동 메뉴** + 로그/에러 메시지 명확화 → 이후 AfterRender 옵션(토글).

#### 8.6 모듈 분리 (코드 품질)

- `shotgrid_client.py` (또는 `setup_pro_shotgrid.py`): 로그인, `create_publish`, 썸네일 업로드, 예외를 사용자 메시지로 변환.
- `setup_pro_common`: ShotGrid 설정 읽기/쓰기만 (선택).
- Nuke/UI는 **얇게** — “수집 컨텍스트 → 클라이언트 호출”.

#### 8.7 의존성

- 공식 **`shotgun_api3`** (또는 팀이 쓰는 래퍼).
- Nuke 쪽 배포: `install_to_nuke.bat` 에 모듈 복사 단계 추가 검토.

#### 8.8 테스트

- 스테이징 ShotGrid 사이트 + 제한된 스크립트 키.
- “연결 테스트” 버튼으로 `sg.find_one('Project', ...)` 정도만 먼저.

---

### 9. Gemini에게 물어보면 좋은 질문 예시

1. 우리 경로 규칙(`04_sq/{ep}/{full}`)과 **ShotGrid 기본 엔티티**를 어떻게 매핑하는 게 덜 깨지는가?
2. **PublishedFileType**, **Link** 를 Comp 출력 EXR 시퀀스에 대해 어떻게 표준적으로 잡는가?
3. Nuke **AfterRender** 에서 ShotGrid API를 호출할 때 **deadlock / already executing** 이슈를 피하는 패턴은?
4. Windows 경로와 ShotGrid `path` 필드 best practice.
5. PyInstaller에 `shotgun_api3` 를 넣을 때 흔한 누락 모듈.

---

### 10. 한 줄 요약 (Gemini용)

**BPE는 CustomTkinter 데스크톱 + Nuke Python 모듈로 프리셋·샷 폴더·Write/QC를 다루는 도구이고, ShotGrid 퍼블리시는 별도 모듈로 API 클라이언트·설정·Nuke 메뉴(또는 GUI) 엔트리포인트를 추가하면 되며, 렌더 콜백에서는 반드시 deferred 패턴을 지켜야 한다.**

## [복사 끝]

---

## 로컬 참고 (이 파일만의 메모)

- 실제 코드 경로: 저장소 `src/` (위 표 참고).
- QC/렌더 콜백 규칙: `.cursor/rules/nuke-render-callbacks.mdc` 요약 참고.
