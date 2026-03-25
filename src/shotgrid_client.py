"""
BPE ShotGrid 연동 — shotgun_api3 래퍼.
UI 스레드에서 직접 호출하지 말고 백그라운드 스레드에서 호출할 것.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 내장 Beluca 자격 증명 (사용자가 따로 설정하지 않아도 연결됨) ──────
_BELUCA_BASE_URL    = "https://beluca.shotgrid.autodesk.com"
_BELUCA_SCRIPT_NAME = "belucaAPI"
_BELUCA_SCRIPT_KEY  = "dnolt2flVfbdoehoknpfp)bbc"

# 스레드별 Shotgun 인스턴스 (동시 API 호출 시 단일 클라이언트 공유로 인한 불안정 방지)
_TLS_SG = threading.local()

try:
    from shotgun_api3 import Shotgun
except ImportError as _e:
    Shotgun = None  # type: ignore
    _SHOTGUN_IMPORT_ERROR = _e
else:
    _SHOTGUN_IMPORT_ERROR = None
    # S3 PUT / multipart 시 URLError·일시 오류 재시도 (기본 3 → 넉넉히)
    # MAX_ATTEMPTS 는 shotgun_api3 기본값(3) 유지 — 과도한 재시도는 프리즈를 유발

## PUT timeout 패치 제거 — shotgun_api3 원본 동작 사용
# 커서가 추가한 120초 timeout 패치가 대용량/느린 회선에서 타임아웃을 유발.
# shotgun_api3 자체 config.timeout_secs(720초)와 내부 재시도로 충분.

# ── 디버그 세션 9b9c60 (NDJSON) — Cursor_save + 워크스페이스 루트 둘 다 시도
_DEBUG_9B9C60_LOG_PATHS = [
    Path(__file__).resolve().parent.parent / "debug-9b9c60.log",
    Path(__file__).resolve().parents[2] / "debug-9b9c60.log",
]


def _debug_9b9c60_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    try:
        rec = {
            "sessionId": "9b9c60",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        for _p in _DEBUG_9B9C60_LOG_PATHS:
            try:
                _p.parent.mkdir(parents=True, exist_ok=True)
                with _p.open("a", encoding="utf-8") as fp:
                    fp.write(line)
            except Exception:
                pass
    except Exception:
        pass
    # #endregion


## 업로드 진행률 몽키패치 제거 — shotgun_api3 원본 동작 사용
# _upload_file_to_storage / _multipart_upload_file_to_storage 패치가
# MOV가 Version에 안 붙는 문제를 유발. shotgun_api3 원본 메서드를 건드리지 않는다.


class ShotGridError(Exception):
    """ShotGrid API / 설정 오류."""


# ── 디버그 세션 로그 (NDJSON) ─────────────────────────────────────────
_DEBUG_SESSION_ID = "876743"
_DEBUG_LOG_FILE = Path(__file__).resolve().parent.parent / "debug-876743.log"

# ── 디버그 세션 f68a10 ────────────────────────────────────────────────
_DEBUG_F68A10_LOG = Path(__file__).resolve().parent.parent / "debug-f68a10.log"


def _dbg(hypothesis_id: str, location: str, message: str, data: Optional[Dict[str, Any]] = None, run_id: str = "run1") -> None:
    # #region agent log
    try:
        import json as _json
        rec = {"sessionId": "f68a10", "runId": run_id, "hypothesisId": hypothesis_id, "location": location, "message": message, "data": data or {}, "timestamp": int(time.time() * 1000)}
        _DEBUG_F68A10_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_F68A10_LOG.open("a", encoding="utf-8") as _fp:
            _fp.write(_json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion


def _debug_876743_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    run_id: str = "upload-fix",
) -> None:
    # #region agent log
    try:
        rec = {
            "sessionId": _DEBUG_SESSION_ID,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        _DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG_FILE.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion


def _path_is_likely_network(path: str) -> bool:
    """Windows: 맵된 네트워크 드라이브(W: 등) 또는 UNC 경로."""
    p = (path or "").strip()
    if not p:
        return False
    if p.startswith("\\\\"):
        return True
    if sys.platform != "win32":
        return p.startswith("//")
    try:
        import ctypes

        drive = Path(p).drive
        if not drive:
            return False
        root = drive + "\\"
        DRIVE_REMOTE = 4
        t = int(ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)))
        return t == DRIVE_REMOTE
    except Exception:
        return False


# 큰 파일은 네트워크 드라이브가 아니어도 SMB/동기화 폴더에서 읽기·업로드가 겹치며 실패할 수 있음
_UPLOAD_STAGE_MIN_BYTES = 64 * 1024 * 1024  # 64 MiB


def _should_stage_movie_locally(movie_path: str, file_size: int) -> bool:
    if _path_is_likely_network(movie_path):
        return True
    if file_size >= _UPLOAD_STAGE_MIN_BYTES:
        return True
    flag = (os.environ.get("BPE_SG_UPLOAD_ALWAYS_LOCAL_COPY") or "").strip().lower()
    if flag in ("1", "true", "yes", "y", "on"):
        return True
    return False


# ── 회사 Task 상태 프리셋 ─────────────────────────────────────────────
BELUCA_TASK_STATUS_PRESETS: List[Tuple[str, str]] = [
    ("wtg",    "Waiting to Start"),
    ("assign", "Assign"),
    ("wip",    "work in process"),
    ("retake", "retake"),
    ("cfrm",   "SV Confirmed"),
    ("tm",     "team confirm"),
    ("sv",     "supervisor confirm"),
    ("pub-s",  "pulish sent"),
    ("pubok",  "publish ok"),
    ("ct",     "client confirm"),
    ("cts",    "client confirm sent"),
    ("ctr",    "client retake"),
    ("cto",    "Client confirm ok"),
    ("disent", "DI sent"),
    ("fin",    "Final"),
    ("hld",    "Hold"),
    ("nocg",   "nocg"),
    ("omt",    "Omit"),
    ("error",  "Error"),
]


def task_status_preset_combo_labels() -> List[str]:
    return [f"{code} — {label}" for code, label in BELUCA_TASK_STATUS_PRESETS]


def parse_task_status_selection(selection: str) -> Optional[str]:
    s = (selection or "").strip()
    if not s or s == "(비움)":
        return None
    if s.startswith("(스키마에서 목록 없음"):
        return None
    sep = " — "
    if sep in s:
        return s.split(sep, 1)[0].strip() or None
    return s


def merge_task_status_combo_options(schema_values: List[str]) -> List[str]:
    preset_codes = {c for c, _ in BELUCA_TASK_STATUS_PRESETS}
    labels = task_status_preset_combo_labels()
    seen_codes = set(preset_codes)
    out = ["(비움)"] + list(labels)
    for raw in schema_values:
        v = str(raw).strip()
        if not v or v in seen_codes:
            continue
        seen_codes.add(v)
        out.append(v)
    return out


# ── 내부 헬퍼 ────────────────────────────────────────────────────────
def _require_shotgun() -> type:
    if Shotgun is None:
        raise ShotGridError(
            "shotgun_api3 패키지가 없습니다. pip install shotgun_api3 후 다시 실행하세요."
        ) from _SHOTGUN_IMPORT_ERROR
    return Shotgun


# ── 연결 ─────────────────────────────────────────────────────────────

def get_default_sg() -> Any:
    """
    내장 Beluca 자격으로 Shotgun 인스턴스를 반환합니다.
    호출 스레드마다 하나의 클라이언트를 캐시합니다(동시 다중 스레드에서 공유 1개 사용 방지).
    """
    sg = getattr(_TLS_SG, "client", None)
    if sg is None:
        sg = connect_from_settings(
            _BELUCA_BASE_URL,
            _BELUCA_SCRIPT_NAME,
            _BELUCA_SCRIPT_KEY,
        )
        _TLS_SG.client = sg
    return sg


def reset_default_sg() -> None:
    """설정 변경 시 현재 스레드의 캐시만 초기화합니다."""
    if hasattr(_TLS_SG, "client"):
        try:
            delattr(_TLS_SG, "client")
        except Exception:
            _TLS_SG.client = None  # type: ignore[attr-defined]


def connect_from_settings(
    base_url: str,
    script_name: str,
    script_key: str,
    *,
    sudo_as_login: Optional[str] = None,
) -> Any:
    """Shotgun 인스턴스 생성. 빈 값이면 내장 Beluca 자격으로 보완.

    sudo_as_login 이 있으면 이벤트 로그·오버뷰에 해당 HumanUser가 행위자로 표시됩니다.
    (스크립트에 ShotGrid 관리자 쪽 sudo/대리 인증 권한이 있어야 합니다.)
    """
    SG = _require_shotgun()
    base_url    = (base_url    or _BELUCA_BASE_URL).strip().rstrip("/")
    script_name = (script_name or _BELUCA_SCRIPT_NAME).strip()
    script_key  = (script_key  or _BELUCA_SCRIPT_KEY).strip()
    sudo_login = (sudo_as_login or "").strip() or None
    if not base_url:
        raise ShotGridError("ShotGrid 사이트 URL이 비어 있습니다.")
    if not script_name or not script_key:
        raise ShotGridError("Script 이름 또는 Script Key가 비어 있습니다.")
    sg = SG(
        base_url,
        script_name=script_name,
        api_key=script_key,
        sudo_as_login=sudo_login,
    )
    # RPC + S3 멀티파트 청크 PUT 각각에 긴 타임아웃 (패치로 PUT 에도 적용)
    # BPE_SG_PUT_TIMEOUT_SECS 환경변수로 오버라이드 가능
    _put_timeout_env = (os.environ.get("BPE_SG_PUT_TIMEOUT_SECS") or "").strip()
    _put_timeout = 720.0
    if _put_timeout_env:
        try:
            _put_timeout = max(60.0, float(_put_timeout_env))
        except (ValueError, TypeError):
            pass
    try:
        sg.config.timeout_secs = _put_timeout
    except Exception:
        pass
    return sg


def _mask_login_for_log(value: str) -> str:
    """디버그 로그용 — login/email 일부만 남김."""
    t = (value or "").strip()
    if not t:
        return ""
    if "@" in t:
        local, _, domain = t.partition("@")
        if not local:
            return "***@" + domain
        return local[:1] + "***@" + domain
    if len(t) <= 2:
        return "***"
    return t[0] + "***" + t[-1]


def resolve_sudo_login(
    sg: Any,
    human_user_id: int,
    *,
    fallback_login: Optional[str] = None,
) -> Optional[str]:
    """
    sudo_as_login 에 넣을 문자열을 HumanUser 레코드에서 구합니다.
    login 이 비어 있으면 email 을 시도합니다. 둘 다 없으면 fallback_login(비어 있지 않을 때만).
    """
    uid = int(human_user_id)
    u = sg.find_one(
        "HumanUser",
        [["id", "is", uid]],
        ["id", "name", "login", "email"],
    )
    if not u:
        fb = (fallback_login or "").strip()
        return fb or None
    login = (u.get("login") or "").strip()
    if login:
        return login
    email = (u.get("email") or "").strip()
    if email:
        return email
    fb = (fallback_login or "").strip()
    return fb or None


def get_shotgun_for_version_mutation(sudo_login: Optional[str]) -> Any:
    """
    Version 생성·파일 업로드 전용 Shotgun 인스턴스.
    sudo_login 이 있으면 새 연결(스크립트 + sudo_as_login), 없으면 캐시된 기본 연결.
    """
    sl = (sudo_login or "").strip() or None
    if not sl:
        return get_default_sg()
    sg = connect_from_settings(
        _BELUCA_BASE_URL,
        _BELUCA_SCRIPT_NAME,
        _BELUCA_SCRIPT_KEY,
        sudo_as_login=sl,
    )
    _dbg(
        "sudo",
        "shotgrid_client.py:get_shotgun_for_version_mutation",
        "using_sudo_as_login",
        {"sudo_as_login_masked": _mask_login_for_log(sl)},
        run_id="post-fix",
    )
    return sg


def test_connection(sg: Any) -> str:
    one = sg.find_one("Project", [], ["id", "name"])
    if one is None:
        return "연결 성공 (프로젝트 0개 또는 조회 제한)."
    return f"연결 성공 — 프로젝트 예시: {one.get('name', '')} (id={one.get('id')})"


# ── 프로젝트 ─────────────────────────────────────────────────────────

def list_projects(sg: Any, limit: int = 500) -> List[Dict[str, Any]]:
    return sg.find(
        "Project",
        [],
        ["id", "name", "code"],
        order=[{"field_name": "name", "direction": "asc"}],
        limit=limit,
    )


def find_project_by_code(sg: Any, code: str) -> Optional[Dict[str, Any]]:
    """파일명에서 추출한 코드로 Project 검색."""
    code = (code or "").strip()
    if not code:
        return None
    return sg.find_one(
        "Project",
        [["code", "is", code]],
        ["id", "name", "code"],
    )


# ── 샷 ───────────────────────────────────────────────────────────────

def find_shot(sg: Any, project_id: int, shot_code: str) -> Optional[Dict[str, Any]]:
    code = (shot_code or "").strip()
    if not code:
        return None
    return sg.find_one(
        "Shot",
        [
            ["project", "is", {"type": "Project", "id": int(project_id)}],
            ["code", "is", code],
        ],
        ["id", "code", "project"],
    )


def find_shot_any_project(sg: Any, shot_code: str) -> Optional[Dict[str, Any]]:
    """프로젝트 무관하게 샷 코드로 샷을 찾습니다 (파일명 자동 파싱 시 사용).
    대소문자 무관 검색: 정확 일치 → 대문자 → 소문자 순으로 시도합니다.
    """
    code = (shot_code or "").strip()
    if not code:
        return None
    # 시도 순서: 원본 → 대문자 → 소문자 (ShotGrid "is" 필터는 서버 대소문자 설정에 따름)
    for candidate in dict.fromkeys([code, code.upper(), code.lower()]):
        shot = sg.find_one(
            "Shot",
            [["code", "is", candidate]],
            ["id", "code", "project"],
        )
        if shot:
            # #region agent log
            _debug_876743_log(
                "H-PARSE",
                "shotgrid_client.py:find_shot_any_project",
                "found",
                {"query": candidate, "shot_id": shot.get("id"), "code": shot.get("code")},
            )
            # #endregion
            return shot
    # 못 찾으면 contains 로 폭넓게 재시도
    try:
        shots = sg.find(
            "Shot",
            [["code", "contains", code.split("_")[0]]],
            ["id", "code", "project"],
            limit=20,
        )
        for s in shots:
            if (s.get("code") or "").lower() == code.lower():
                return s
    except Exception:
        pass
    return None


def list_shots_for_project(
    sg: Any, project_id: int, limit: int = 800
) -> List[Dict[str, Any]]:
    return sg.find(
        "Shot",
        [["project", "is", {"type": "Project", "id": int(project_id)}]],
        ["id", "code"],
        order=[{"field_name": "code", "direction": "asc"}],
        limit=limit,
    )


# ── Task ─────────────────────────────────────────────────────────────

def find_tasks_for_shot(sg: Any, shot_id: int) -> List[Dict[str, Any]]:
    return sg.find(
        "Task",
        [["entity", "is", {"type": "Shot", "id": int(shot_id)}]],
        ["id", "content", "sg_status_list", "project"],
        order=[{"field_name": "content", "direction": "asc"}],
    )


def search_tasks_for_shot(
    sg: Any, shot_id: int, query: str, limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Task 자동완성 — shot_id 하위의 Task 중 content 에 query 가 포함된 것.
    """
    filters: list = [["entity", "is", {"type": "Shot", "id": int(shot_id)}]]
    q = (query or "").strip()
    if q:
        filters.append(["content", "contains", q])
    return sg.find(
        "Task",
        filters,
        ["id", "content", "sg_status_list", "project", "entity"],
        order=[{"field_name": "content", "direction": "asc"}],
        limit=limit,
    )


def pick_task_by_content(
    tasks: List[Dict[str, Any]], content_filter: str
) -> Optional[Dict[str, Any]]:
    needle = (content_filter or "").strip().lower()
    if not needle:
        return tasks[0] if tasks else None
    for t in tasks:
        c = (t.get("content") or "").strip().lower()
        if c == needle or needle in c:
            return t
    return tasks[0] if tasks else None


# ── HumanUser (Artist 자동완성) ───────────────────────────────────────

def search_human_users(
    sg: Any, query: str, limit: int = 15
) -> List[Dict[str, Any]]:
    """
    Artist 자동완성용 HumanUser 검색.
    name / login 중 query 가 포함된 사용자 반환.
    """
    q = (query or "").strip()
    if not q:
        return []
    # 이름 검색 (한국어 이름 포함). 결과 없으면 로그인으로 재시도.
    results = sg.find(
        "HumanUser",
        [["name", "contains", q]],
        ["id", "name", "login", "email"],
        limit=limit,
    )
    if not results:
        try:
            results = sg.find(
                "HumanUser",
                [["login", "contains", q]],
                ["id", "name", "login", "email"],
                limit=limit,
            )
        except Exception:
            pass
    return results


# ── comp Task / 담당자 자동 채움 ─────────────────────────────────────

def get_comp_task_and_assignee(
    sg: Any, shot_id: int
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    샷의 comp 태스크와 첫 번째 담당자(HumanUser)를 반환합니다.
    태스크 없으면 (None, None), 담당자 없으면 (task, None).
    """
    try:
        tasks = sg.find(
            "Task",
            [
                ["entity", "is", {"type": "Shot", "id": int(shot_id)}],
                ["content", "is", "comp"],
            ],
            ["id", "content", "task_assignees"],
            limit=1,
        )
        if not tasks:
            return None, None
        task = tasks[0]
        assignees = task.get("task_assignees") or []
        return task, (assignees[0] if assignees else None)
    except Exception as e:
        logger.debug("get_comp_task_and_assignee failed shot_id=%s: %s", shot_id, e)
        return None, None


# ── 파일명 / 경로 파싱 ────────────────────────────────────────────────

# 지원하는 샷 코드 패턴 목록 (우선순위 순)
# 1) E107_S022_0080   — 에피소드_샷_컷 (기존)
# 2) EP09_s16_c0130   — EP##_s##_c#### (HSA 등)
# 3) TLS_101_029_0005 — 쇼코드_###_###_#### (숫자 3구간; comp_v### 접미사 앞까지 매칭)
# 4) E107_S022        — 에피소드_샷 2-part
# 5) 폴더 경로 역방향 탐색 (위 패턴이 파일명에 없을 때)
#
# EP… 패턴 뒤에 두는 이유: EP09_s16_c0130 은 s/c 구간에 문자가 있어 아래 "숫자만" 패턴과 구분됨.
_SHOT_CODE_PATTERNS: List[re.Pattern] = [
    re.compile(r"E\d{2,3}_S\d{2,3}_\d{4}", re.IGNORECASE),       # E107_S022_0080
    re.compile(r"EP\d{1,4}_[Ss]\d{1,4}_[Cc]\d{4}", re.IGNORECASE),  # EP09_s16_c0130
    re.compile(r"EP\d{1,4}_[Ss]\d{1,4}_[Cc]\d{1,3}", re.IGNORECASE),  # EP09_s16_c013 (짧은 변형)
    # 쇼 프리픽스(문자만 2~8자) + 밑줄 + 숫자구간 3개 (VFX 파이프라인별 가변 길이)
    re.compile(
        r"(?<![A-Za-z0-9])[A-Za-z]{2,8}_\d{2,5}_\d{2,5}_\d{2,5}",
        re.IGNORECASE,
    ),
    re.compile(r"E\d{2,3}_S\d{2,3}", re.IGNORECASE),              # E107_S022 (2-part)
]


def _try_patterns(text: str) -> Optional[str]:
    """패턴 목록으로 샷 코드 추출. 매칭되면 원본 대소문자 유지."""
    t = (text or "").replace("/", "_").replace("\\", "_")
    for pat in _SHOT_CODE_PATTERNS:
        m = pat.search(t)
        if m:
            return m.group(0)
    return None


def parse_shot_code_from_filename(filename: str) -> Optional[str]:
    """
    파일명(또는 전체 경로)에서 샷 코드를 추출합니다.

    지원 패턴:
    - E107_S022_0080  (에피소드_샷_컷)
    - EP09_s16_c0130  (EP##_s##_c####)
    - TLS_101_029_0005 (쇼코드_숫자_숫자_숫자, 예: …_comp_v003.mov)
    - E107_S022       (에피소드_샷)

    파일명에서 못 찾으면 경로의 디렉토리 부분도 역방향으로 탐색합니다.
    """
    name = (filename or "").strip()
    # 1) 파일명(확장자 제외) 우선 탐색
    stem = Path(name).stem
    result = _try_patterns(stem)
    if result:
        # #region agent log
        _debug_876743_log(
            "H-PARSE",
            "shotgrid_client.py:parse_shot_code_from_filename",
            "found_in_stem",
            {"stem": stem, "result": result},
        )
        # #endregion
        return result
    # 2) 전체 파일명(확장자 포함) 탐색
    result = _try_patterns(Path(name).name)
    if result:
        return result
    # 3) 경로의 각 디렉토리 부분을 역방향으로 탐색
    for part in reversed(Path(name).parts):
        result = _try_patterns(part)
        if result:
            # #region agent log
            _debug_876743_log(
                "H-PARSE",
                "shotgrid_client.py:parse_shot_code_from_filename",
                "found_in_dir_part",
                {"part": part, "result": result},
            )
            # #endregion
            return result
    # #region agent log
    _debug_876743_log(
        "H-PARSE",
        "shotgrid_client.py:parse_shot_code_from_filename",
        "not_found",
        {"name": Path(name).name, "patterns_tried": len(_SHOT_CODE_PATTERNS)},
    )
    # #endregion
    return None


def parse_version_name_from_filename(filename: str) -> str:
    """
    파일명(확장자 제외)을 Version Name으로 반환합니다.
    예) E107_S022_0080_comp_v001.1001.mov → E107_S022_0080_comp_v001.1001
    """
    stem = Path(filename).stem
    return stem


# ── Version 엔티티 생성 + 영상 업로드 ─────────────────────────────────

def create_version(
    sg: Any,
    *,
    project_id: int,
    shot_id: int,
    task_id: Optional[int],
    version_name: str,
    description: str = "",
    artist_id: Optional[int] = None,
    sg_status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    ShotGrid Version 엔티티 생성.
    영상 파일 업로드는 upload_movie_to_version 으로 별도 수행.
    """
    version_name = (version_name or "").strip()
    if not version_name:
        raise ShotGridError("Version Name이 비어 있습니다.")

    # #region agent log
    _dbg("H1/H2", "shotgrid_client.py:create_version", "create_version called",
         {"version_name": version_name, "artist_id": artist_id, "task_id": task_id, "project_id": project_id, "shot_id": shot_id})
    # #endregion

    data: Dict[str, Any] = {
        "project":     {"type": "Project", "id": int(project_id)},
        "entity":      {"type": "Shot",    "id": int(shot_id)},
        "code":        version_name,
        "description": (description or "").strip(),
    }
    if task_id is not None:
        data["sg_task"] = {"type": "Task", "id": int(task_id)}
    if artist_id is not None:
        data["user"] = {"type": "HumanUser", "id": int(artist_id)}
    if sg_status:
        data["sg_status_list"] = sg_status.strip()

    return sg.create("Version", data)


def _copy_file_chunked_with_progress(
    src: str,
    dst: str,
    total: int,
    on_frac: Optional[Callable[[float], None]],
    chunk: int = 8 * 1024 * 1024,
) -> None:
    """로컬 스테이징 복사 시 진행률(0~1) 콜백."""
    done = 0
    with open(src, "rb") as rf, open(dst, "wb") as wf:
        while True:
            b = rf.read(chunk)
            if not b:
                break
            wf.write(b)
            done += len(b)
            if on_frac and total > 0:
                try:
                    on_frac(min(1.0, done / float(total)))
                except Exception:
                    pass


def upload_movie_to_version(
    sg: Any,
    version_id: int,
    movie_path: str,
    *,
    progress_cb: Optional[Callable[[float], None]] = None,
) -> None:
    """
    Version 엔티티에 MOV 파일을 업로드합니다.
    sg_uploaded_movie 필드 사용 (ShotGrid 표준).
    progress_cb: 선택. 전체 진행 0.0~1.0 (스테이징 복사 + ShotGrid 전송).
    """
    movie_path = (movie_path or "").strip()
    # #region agent log
    _is_file = bool(movie_path) and Path(movie_path).is_file()
    _debug_9b9c60_log(
        "H1",
        "shotgrid_client.py:upload_movie_to_version",
        "entry_path_check",
        {
            "version_id": int(version_id),
            "path_len": len(movie_path),
            "path_is_file": _is_file,
            "suffix": (Path(movie_path).suffix.lower() if movie_path else ""),
        },
    )
    # #endregion
    if not movie_path or not Path(movie_path).is_file():
        raise ShotGridError(f"파일을 찾을 수 없습니다: {movie_path}")

    file_size = os.path.getsize(movie_path)
    stage_local = _should_stage_movie_locally(movie_path, file_size)

    def _overall(frac_0_1: float) -> None:
        if progress_cb is None:
            return
        try:
            progress_cb(max(0.0, min(1.0, float(frac_0_1))))
        except Exception:
            pass

    # #region agent log
    _debug_876743_log(
        "H-A",
        "shotgrid_client.py:upload_movie_to_version",
        "pre_upload",
        {
            "version_id": int(version_id),
            "basename": Path(movie_path).name,
            "size_bytes": file_size,
            "likely_network_drive": _path_is_likely_network(movie_path),
            "stage_local_copy": stage_local,
        },
    )
    _debug_9b9c60_log(
        "H1",
        "shotgrid_client.py:upload_movie_to_version",
        "pre_upload_meta",
        {
            "version_id": int(version_id),
            "basename": Path(movie_path).name,
            "size_bytes": file_size,
            "stage_local": stage_local,
        },
    )
    _dbg(
        "H3/H4",
        "shotgrid_client.py:upload_movie_to_version",
        "pre_upload",
        {
            "version_id": int(version_id),
            "basename": Path(movie_path).name,
            "size_bytes": file_size,
            "stage_local": stage_local,
            "path": movie_path,
        },
    )
    # #endregion

    _overall(0.02)
    upload_src = movie_path
    tmp_copy: Optional[str] = None
    if stage_local:
        try:
            suf = Path(movie_path).suffix or ".mov"
            fd, tmp_copy = tempfile.mkstemp(prefix="bpe_sg_upload_", suffix=suf)
            os.close(fd)

            def _stage_frac(local_f: float) -> None:
                _overall(0.05 + 0.13 * max(0.0, min(1.0, local_f)))

            if progress_cb is not None:
                _copy_file_chunked_with_progress(movie_path, tmp_copy, file_size, _stage_frac)
            else:
                shutil.copy2(movie_path, tmp_copy)
            upload_src = tmp_copy
            _overall(0.18)
            # #region agent log
            _debug_876743_log(
                "H-B",
                "shotgrid_client.py:upload_movie_to_version",
                "network_path_copied_to_temp",
                {"temp_basename": Path(tmp_copy).name, "size_bytes": file_size},
            )
            _debug_9b9c60_log(
                "H3",
                "shotgrid_client.py:upload_movie_to_version",
                "staging_ok",
                {"temp_exists": os.path.isfile(tmp_copy), "upload_src_is_temp": True},
            )
            # #endregion
        except Exception as e:
            # #region agent log
            _debug_9b9c60_log(
                "H3",
                "shotgrid_client.py:upload_movie_to_version",
                "staging_failed",
                {"error_type": type(e).__name__, "error": str(e)[:400]},
            )
            # #endregion
            if tmp_copy and os.path.isfile(tmp_copy):
                try:
                    os.unlink(tmp_copy)
                except OSError:
                    pass
            raise ShotGridError(
                "업로드 전 로컬 임시 폴더로 복사하지 못했습니다. "
                "디스크 여유 공간과 경로 접근 권한을 확인하세요."
            ) from e
    else:
        _overall(0.18)

    sg_logger = logging.getLogger("shotgun_api3")
    _old_level = sg_logger.level
    fh: Optional[logging.FileHandler] = None
    attach_id: Optional[int] = None
    try:
        fh = logging.FileHandler(_DEBUG_LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        sg_logger.addHandler(fh)
        sg_logger.setLevel(logging.DEBUG)

        # ShotGrid 전송 구간은 절대 frac_cb(클래스 패치)를 켜지 않는다.
        # 패치된 멀티파트/PUT이 원본과 미세하게 달라 MOV가 Version에 안 붙는 사례가 있음.
        # 스테이징 복사 위에서만 progress_cb로 진행률을 갱신한다.
        # #region agent log
        _debug_9b9c60_log(
            "FIX2",
            "shotgrid_client.py:upload_movie_to_version",
            "sg_upload_stock_shotgun_only",
            {
                "basename": Path(upload_src).name,
                "size_bytes": os.path.getsize(upload_src)
                if os.path.isfile(upload_src)
                else -1,
            },
            run_id="post-fix",
        )
        # #endregion
        # sg.upload 내부에도 재시도가 있지만, S3 타임아웃/연결 리셋 등
        # 내부 MAX_ATTEMPTS 소진 후에도 외부에서 한 번 더 시도할 여지를 둔다.
        upload_rounds = 3
        _overall(0.55)
        for attempt_idx in range(1, upload_rounds + 1):
            try:
                # #region agent log
                _debug_9b9c60_log(
                    "H2",
                    "shotgrid_client.py:upload_movie_to_version",
                    "sg_upload_attempt",
                    {
                        "attempt": attempt_idx,
                        "upload_src_basename": Path(upload_src).name,
                        "field": "sg_uploaded_movie",
                    },
                )
                # #endregion
                _up_ret = sg.upload(
                    "Version", int(version_id), upload_src, "sg_uploaded_movie"
                )
                try:
                    attach_id = int(_up_ret) if _up_ret is not None else None
                except (TypeError, ValueError):
                    attach_id = None
                break
            except Exception as round_e:
                msg = str(round_e)
                _msg_lower = msg.lower()
                retryable = (
                    "timed out" in _msg_lower
                    or "timeout" in _msg_lower
                    or "max attempts" in _msg_lower
                    or "Connection reset" in msg
                    or "Connection aborted" in msg
                    or "URLError" in type(round_e).__name__
                )
                _debug_876743_log(
                    "H-R",
                    "shotgrid_client.py:upload_movie_to_version",
                    "upload_round",
                    {
                        "attempt": attempt_idx,
                        "max_rounds": upload_rounds,
                        "error_type": type(round_e).__name__,
                        "error": msg[:400],
                        "will_retry": retryable and attempt_idx < upload_rounds,
                    },
                )
                _debug_9b9c60_log(
                    "H2",
                    "shotgrid_client.py:upload_movie_to_version",
                    "sg_upload_round_error",
                    {
                        "attempt": attempt_idx,
                        "error_type": type(round_e).__name__,
                        "error": msg[:500],
                        "retryable": retryable,
                    },
                )
                if not retryable or attempt_idx >= upload_rounds:
                    raise
                _wait = min(60.0, 10.0 * attempt_idx)
                logger.info("업로드 재시도 대기 %.0f초 (%d/%d)", _wait, attempt_idx, upload_rounds)
                time.sleep(_wait)
        _overall(0.92)
        # #region agent log
        vf: Optional[Dict[str, Any]] = None
        try:
            vf = sg.find_one(
                "Version",
                [["id", "is", int(version_id)]],
                ["id", "sg_uploaded_movie"],
            )
        except Exception as ve:
            _debug_9b9c60_log(
                "H5",
                "shotgrid_client.py:upload_movie_to_version",
                "post_upload_find_failed",
                {"error_type": type(ve).__name__, "error": str(ve)[:300]},
            )
        mov_field = (vf or {}).get("sg_uploaded_movie")
        _debug_9b9c60_log(
            "H5",
            "shotgrid_client.py:upload_movie_to_version",
            "upload_ok_verify_field",
            {
                "version_id": int(version_id),
                "attachment_id": attach_id,
                "sg_uploaded_movie_is_none": mov_field is None,
                "sg_uploaded_movie_type": type(mov_field).__name__ if mov_field is not None else None,
            },
        )
        if vf is not None and mov_field is None:
            raise ShotGridError(
                "ShotGrid API가 업로드 성공을 반환했지만, "
                "Version의 sg_uploaded_movie 필드가 비어 있습니다.\n"
                "ShotGrid 관리자에게 문의하거나 수동으로 MOV를 재업로드하세요."
            )
        _debug_876743_log(
            "H-C",
            "shotgrid_client.py:upload_movie_to_version",
            "upload_ok",
            {"version_id": int(version_id)},
            run_id="post-fix",
        )
        # #endregion
        _overall(1.0)
    except Exception as e:
        # #region agent log
        _debug_876743_log(
            "H-D",
            "shotgrid_client.py:upload_movie_to_version",
            "upload_failed",
            {"error_type": type(e).__name__, "error": str(e)[:500]},
        )
        _debug_9b9c60_log(
            "H2",
            "shotgrid_client.py:upload_movie_to_version",
            "upload_failed",
            {"error_type": type(e).__name__, "error": str(e)[:600]},
        )
        _dbg(
            "H3/H4",
            "shotgrid_client.py:upload_movie_to_version",
            "upload_FAILED",
            {
                "error_type": type(e).__name__,
                "error": str(e)[:800],
                "upload_src": upload_src,
                "is_temp_copy": tmp_copy is not None,
            },
        )
        # #endregion
        if isinstance(e, ShotGridError):
            raise
        err_lower = str(e).lower()
        err_s = str(e)
        if (
            "timed out" in err_lower
            or "timeout" in err_lower
            or "max attempts" in err_lower
        ):
            raise ShotGridError(
                "S3 클라우드 스토리지 업로드 타임아웃(또는 재시도 한도 초과)입니다.\n"
                "• 회사 방화벽이 ShotGrid S3 엔드포인트를 차단할 수 있습니다. IT에 확인해 보세요.\n"
                "• 64MB 이상·네트워크 경로는 로컬 임시 복사 후 올립니다. "
                "항상 복사하려면 환경 변수 BPE_SG_UPLOAD_ALWAYS_LOCAL_COPY=1 을 설정해 보세요.\n"
                "• PUT 소켓 타임아웃은 환경 변수 BPE_SG_PUT_TIMEOUT_SECS(초)로 조정할 수 있습니다. "
                "(값을 너무 작게 하면 느린 회선에서 실패할 수 있습니다.)\n"
                "• 프록시(HTTP_PROXY)가 필요한지 IT에 확인해 보세요.\n"
                "• 관련 로그: debug-876743.log\n"
                f"(원본 오류: {err_s[:400]})"
            ) from e
        raise
    finally:
        if fh is not None:
            try:
                sg_logger.removeHandler(fh)
                fh.close()
            except Exception:
                pass
        try:
            sg_logger.setLevel(_old_level)
        except Exception:
            pass
        if tmp_copy and os.path.isfile(tmp_copy):
            try:
                os.unlink(tmp_copy)
            except OSError:
                pass


# ── Version 썸네일 업로드 ─────────────────────────────────────────────


def _extract_first_frame(
    movie_path: str,
    dest_path: str,
    *,
    timeout_sec: float = 30.0,
) -> bool:
    """
    ffmpeg 로 MOV/MP4 의 첫 프레임을 JPEG 로 추출.
    ffmpeg 가 없거나 실패하면 False 반환 (호출부에서 fallback 처리).
    """
    import subprocess as _sp

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.debug("ffmpeg not found — skip first-frame extraction")
        return False
    try:
        _sp.run(
            [
                ffmpeg_bin,
                "-y",
                "-i", movie_path,
                "-vframes", "1",
                "-q:v", "2",
                dest_path,
            ],
            stdout=_sp.DEVNULL,
            stderr=_sp.DEVNULL,
            timeout=timeout_sec,
            check=True,
        )
        return Path(dest_path).is_file() and Path(dest_path).stat().st_size > 0
    except Exception as e:
        logger.debug("ffmpeg first-frame extraction failed: %s", e)
        return False


def upload_thumbnail_to_version(
    sg: Any,
    version_id: int,
    image_path: Optional[str] = None,
    movie_path: Optional[str] = None,
) -> bool:
    """
    Version 엔티티에 썸네일(image 필드)을 업로드합니다.

    - image_path 가 주어지면 해당 이미지를 직접 업로드.
    - image_path 가 없고 movie_path 가 주어지면 ffmpeg 로 첫 프레임을 추출하여 업로드.
    - 둘 다 없거나 추출 실패 시 False 반환.
    """
    tmp_thumb: Optional[str] = None
    upload_src: Optional[str] = None

    try:
        # 1) 명시적 이미지 경로
        if image_path and Path(image_path).is_file():
            upload_src = image_path

        # 2) MOV 에서 첫 프레임 추출
        if upload_src is None and movie_path and Path(movie_path).is_file():
            fd, tmp_thumb = tempfile.mkstemp(prefix="bpe_thumb_", suffix=".jpg")
            os.close(fd)
            if _extract_first_frame(movie_path, tmp_thumb):
                upload_src = tmp_thumb
            else:
                # ffmpeg 실패 — 임시 파일 정리
                try:
                    os.unlink(tmp_thumb)
                except OSError:
                    pass
                tmp_thumb = None

        if upload_src is None:
            logger.debug("upload_thumbnail_to_version: no image source available")
            return False

        sg.upload_thumbnail("Version", int(version_id), upload_src)
        logger.info(
            "Thumbnail uploaded for Version %d from %s",
            version_id,
            Path(upload_src).name,
        )
        return True

    except Exception as e:
        logger.warning("upload_thumbnail_to_version failed: %s", e)
        return False
    finally:
        if tmp_thumb and os.path.isfile(tmp_thumb):
            try:
                os.unlink(tmp_thumb)
            except OSError:
                pass


# ── 레거시 PublishedFile (이전 기능 호환) ────────────────────────────

def resolve_published_file_type(
    sg: Any, type_name_or_code: str
) -> Dict[str, Any]:
    raw = (type_name_or_code or "").strip()
    if not raw:
        raise ShotGridError("PublishedFileType 이름/코드가 비어 있습니다.")
    pft = sg.find_one("PublishedFileType", [["code", "is", raw]], ["id", "code", "name"])
    if pft:
        return pft
    pft = sg.find_one("PublishedFileType", [["name", "is", raw]], ["id", "code", "name"])
    if pft:
        return pft
    raise ShotGridError(f"PublishedFileType 을 찾을 수 없습니다: {raw!r}")


def create_published_file(
    sg: Any,
    *,
    project_id: int,
    shot_id: int,
    task_id: int,
    published_file_type_id: int,
    path: str,
    name: str,
    code: str,
    description: str = "",
) -> Dict[str, Any]:
    path = (path or "").strip()
    if not path:
        raise ShotGridError("퍼블리시 경로가 비어 있습니다.")
    name = (name or "").strip() or Path(path.replace("\\", "/").split("/")[-1]).stem
    code = (code or "").strip() or re.sub(r"[^\w\-.]+", "_", name)[:80]
    data: Dict[str, Any] = {
        "project": {"type": "Project", "id": int(project_id)},
        "entity":  {"type": "Shot",    "id": int(shot_id)},
        "task":    {"type": "Task",    "id": int(task_id)},
        "published_file_type": {"type": "PublishedFileType", "id": int(published_file_type_id)},
        "name": name,
        "code": code,
        "description": (description or "").strip(),
    }
    path_val = path.replace("/", "\\") if os.name == "nt" else path
    try:
        data["path"] = path_val
        return sg.create("PublishedFile", data)
    except Exception as e_first:
        if "path" in str(e_first).lower() or "invalid" in str(e_first).lower():
            data["path"] = {"local_path": path}
            try:
                return sg.create("PublishedFile", data)
            except Exception as e2:
                raise ShotGridError(f"PublishedFile 생성 실패: {e2}") from e2
        raise ShotGridError(f"PublishedFile 생성 실패: {e_first}") from e_first


# ── Task 상태 ─────────────────────────────────────────────────────────

def update_task_status(
    sg: Any,
    task_id: int,
    status_value: str,
    field_name: Optional[str] = None,
) -> Dict[str, Any]:
    status_value = (status_value or "").strip()
    if not status_value:
        return {}
    fn = (field_name or "").strip() or "sg_status_list"
    return sg.update("Task", int(task_id), {fn: status_value})


def detect_task_status_field(sg: Any) -> Optional[str]:
    for candidate in ("sg_status_list", "sg_task_status"):
        try:
            sch = sg.schema_field_read("Task", candidate)
            if sch and isinstance(sch, dict):
                dt = (sch.get("data_type") or "").lower()
                if "status" in dt or sch.get("properties"):
                    return candidate
        except Exception:
            continue
    return None


def list_task_status_values(
    sg: Any, field_name: Optional[str] = None
) -> Tuple[str, List[str]]:
    fn = (field_name or "").strip() or detect_task_status_field(sg) or "sg_status_list"
    sch = sg.schema_field_read("Task", fn)
    if not sch or not isinstance(sch, dict):
        return fn, []
    props = sch.get("properties") or sch.get("data_type_properties") or {}
    if not isinstance(props, dict):
        props = {}
    for key in ("valid_values", "values", "enum_values", "display_values"):
        vals = props.get(key)
        if isinstance(vals, (list, tuple)) and vals:
            return fn, [str(v) for v in vals]
    nested = props.get("status_list") or {}
    if isinstance(nested, dict):
        vals = nested.get("values") or nested.get("valid_values")
        if isinstance(vals, (list, tuple)) and vals:
            return fn, [str(v) for v in vals]
    return fn, []


# ── My Shots: Comp Task by assignee + 썸네일 ───────────────────────────


def list_comp_tasks_for_assignee(
    sg: Any,
    human_user_id: int,
    *,
    task_content: str = "comp",
    status_filter: Optional[str] = None,
    status_field_name: Optional[str] = None,
    due_date_field: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """
    지정 HumanUser 에게 할당된 Task 중 entity 가 Shot 이고 content 가 comp(또는 설정값)인 항목만 조회.
    task_content 는 우선 정확 일치(is); 결과가 없으면 contains 로 한 번 더 시도합니다.
    due_date_field 가 비어 있지 않으면 해당 Task 필드를 납기(due_date 키)로 매핑합니다.
    UI 스레드에서 직접 호출하지 말 것.
    """
    uid = int(human_user_id)
    tc_raw = (task_content or "comp").strip()
    status_fn = (status_field_name or "").strip() or detect_task_status_field(sg) or "sg_status_list"
    due_fn_effective = (due_date_field or "").strip() or "due_date"
    st = (status_filter or "").strip()
    st_use = st and st not in ("(전체)", "(비움)", "(all)", "전체")
    order = [{"field_name": "id", "direction": "desc"}]
    lim = int(limit)

    def _task_fields_for_due(due_col: str) -> List[str]:
        return [
            "id",
            "content",
            due_col,
            "entity",
            "project",
            status_fn,
            "entity.Shot.code",
            "entity.Shot.description",
            "entity.Shot.image",
            "project.Project.code",
            "project.Project.name",
        ]

    fields: List[str] = _task_fields_for_due(due_fn_effective)

    def _filters(assignee: List[Any], content: Optional[List[Any]]) -> List[List[Any]]:
        fl: List[List[Any]] = [assignee, ["entity", "type_is", "Shot"]]
        if content:
            fl.append(content)
        if st_use:
            fl.append([status_fn, "is", st])
        return fl

    def _find(
        assignee: List[Any],
        content: Optional[List[Any]],
        field_list: List[str],
    ) -> List[Dict[str, Any]]:
        return sg.find(
            "Task",
            _filters(assignee, content),
            field_list,
            order=order,
            limit=lim,
        )

    assignee_is = ["task_assignees", "is", {"type": "HumanUser", "id": uid}]
    assignee_try = (
        assignee_is,
        ["task_assignees", "in", {"type": "HumanUser", "id": uid}],
        ["task_assignees", "contains", {"type": "HumanUser", "id": uid}],
    )
    content_is: Optional[List[Any]] = ["content", "is", tc_raw] if tc_raw else None
    content_has: Optional[List[Any]] = ["content", "contains", tc_raw] if tc_raw else None

    rows: List[Dict[str, Any]] = []
    due_read_col = due_fn_effective

    def _find_with_assignee_fallback(content: Optional[List[Any]]) -> None:
        nonlocal rows
        try:
            rows = _find(assignee_is, content, fields)
            return
        except Exception as e1:
            el = str(e1).lower()
            if due_fn_effective != "due_date" and due_fn_effective.lower() in el:
                raise
            if "task_assignees" not in el:
                raise
        last_exc: Optional[BaseException] = None
        for af in assignee_try[1:]:
            try:
                rows = _find(af, content, fields)
                return
            except Exception as e2:
                last_exc = e2
                rows = []
        if last_exc is not None:
            raise last_exc

    try:
        rows = _find(assignee_is, content_is, fields)
    except Exception as e1:
        el = str(e1).lower()
        if due_fn_effective != "due_date" and due_fn_effective.lower() in el:
            fields = _task_fields_for_due("due_date")
            due_read_col = "due_date"
            _find_with_assignee_fallback(content_is)
        elif "task_assignees" in el:
            _find_with_assignee_fallback(content_is)
        else:
            raise e1

    if not rows and content_has is not None:
        try:
            rows = _find(assignee_is, content_has, fields)
        except Exception as e1:
            logger.debug("list_comp_tasks_for_assignee content_has primary: %s", e1)
            try:
                _find_with_assignee_fallback(content_has)
            except Exception as e2:
                logger.warning(
                    "list_comp_tasks_for_assignee content_has fallback failed user=%s: %s",
                    uid,
                    e2,
                )
                rows = []

    out: List[Dict[str, Any]] = []
    for t in rows or []:
        ent = t.get("entity") or {}
        if (ent.get("type") or "").lower() != "shot":
            continue
        shot_id = ent.get("id")
        shot_code = (ent.get("code") or ent.get("name") or "").strip()
        desc = (ent.get("description") or "").strip()
        img = t.get("entity.Shot.image") or ent.get("image")
        proj = t.get("project") or {}
        proj_code = (proj.get("code") or "").strip()
        proj_name = (proj.get("name") or "").strip()
        due_val = t.get(due_read_col)

        folder = (proj_code or proj_name).strip()
        out.append(
            {
                "task_id": t.get("id"),
                "task_content": (t.get("content") or "").strip(),
                "task_status": (t.get(status_fn) or "").strip(),
                "status_field": status_fn,
                "due_date": due_val,
                "shot_id": shot_id,
                "shot_code": shot_code,
                "shot_description": desc,
                "shot_image": img,
                "project_id": proj.get("id"),
                "project_code": proj_code,
                "project_name": proj_name,
                "project_folder": folder,
                "latest_version_code": "",
            }
        )
    return out


def download_entity_thumbnail_to_path(
    sg: Any,
    entity_type: str,
    entity_id: int,
    dest_path: Path,
    *,
    timeout_sec: float = 60.0,
) -> bool:
    """
    Shot 등 엔티티 썸네일을 로컬 파일로 저장 (SG 데이터 변경 없음).
    """
    et = (entity_type or "Shot").strip() or "Shot"
    eid = int(entity_id)
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 로컬 캐시 파일이 이미 존재하면 다운로드 건너뜀
    if dest.is_file() and dest.stat().st_size > 0:
        return True

    def _fetch_url(url: str) -> bool:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BPE-Pipeline-Tool/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                content_type = (resp.headers.get("Content-Type") or "").lower()
                data = resp.read()
            if not data:
                return False
            # HTML 에러 페이지가 이미지로 저장되는 것을 방지
            if b"<!DOCTYPE" in data[:100] or b"<html" in data[:100]:
                logger.debug("thumbnail response is HTML, not image: %s", url[:120])
                return False
            # Content-Type 이 이미지가 아닌 경우도 방지
            if content_type and "image" not in content_type and "octet" not in content_type:
                logger.debug("thumbnail content-type not image: %s", content_type)
                return False
            dest.write_bytes(data)
            return dest.is_file() and dest.stat().st_size > 0
        except (urllib.error.URLError, OSError, ValueError) as e:
            logger.debug("thumbnail fetch failed for %s: %s", url[:120], e)
        return False

    try:
        getter = getattr(sg, "get_thumbnail_url", None)
        if callable(getter):
            url = getter(et, eid)
            if url and _fetch_url(str(url)):
                return True
    except Exception:
        pass

    try:
        ent = sg.find_one(et, [["id", "is", eid]], ["image"])
        img = ent.get("image") if ent else None
        if isinstance(img, str) and img.strip().startswith(("http://", "https://")):
            if _fetch_url(img.strip()):
                return True
        if isinstance(img, dict):
            u = img.get("url") or img.get("this_file")
            if isinstance(u, str) and u.strip().startswith(("http://", "https://")):
                if _fetch_url(u.strip()):
                    return True
            if img.get("id"):
                att = {"type": "Attachment", "id": int(img["id"])}
                sg.download_attachment(att, str(dest))
                if dest.is_file() and dest.stat().st_size > 0:
                    # 다운로드된 파일이 이미지인지 간이 검증
                    head = dest.read_bytes()[:100]
                    if b"<!DOCTYPE" in head or b"<html" in head:
                        logger.debug("download_attachment returned HTML, removing: %s", dest)
                        dest.unlink(missing_ok=True)
                        return False
                    return True
    except Exception:
        pass

    return False


def guess_human_user_for_me(sg: Any, *, limit: int = 8) -> Optional[Dict[str, Any]]:
    """
    Windows 로그인명 / USERNAME 으로 HumanUser 를 추정 (첫 일치).
    """
    candidates: List[str] = []
    try:
        candidates.append(os.getlogin().strip().lower())
    except Exception:
        pass
    env_u = (os.environ.get("USERNAME") or os.environ.get("USER") or "").strip().lower()
    if env_u:
        candidates.append(env_u)
    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        try:
            hits = sg.find(
                "HumanUser",
                [["login", "contains", c]],
                ["id", "name", "login", "email"],
                limit=int(limit),
            )
            if hits:
                return hits[0]
        except Exception:
            continue
        try:
            hits = sg.find(
                "HumanUser",
                [["email", "contains", c]],
                ["id", "name", "login", "email"],
                limit=int(limit),
            )
            if hits:
                return hits[0]
        except Exception:
            continue
    return None


# ─────────────────────────── My Shots Dashboard ─────────────────────────────

def list_active_projects(sg: Any, limit: int = 300) -> List[Dict[str, Any]]:
    """현재 활성(Active) 상태인 프로젝트 목록을 반환합니다."""
    try:
        return sg.find(
            "Project",
            [["sg_status", "is", "Active"]],
            ["id", "name", "code"],
            limit=limit,
        )
    except Exception:
        # sg_status 필드가 없는 스튜디오용 폴백: 전체 프로젝트 반환
        try:
            return sg.find("Project", [], ["id", "name", "code"], limit=limit)
        except Exception:
            return []


def list_comp_tasks_for_project_user(
    sg: Any,
    project_id: int,
    human_user_id: int,
    *,
    task_content: str = "comp",
    status_filter: Optional[str] = None,
    status_field_name: Optional[str] = None,
    due_date_field: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """특정 프로젝트 + 담당자 기반으로 Comp 태스크 목록을 반환합니다.
    project_id 가 None 이면 전체 프로젝트에서 조회합니다.
    """
    if project_id is None:
        return list_comp_tasks_for_assignee(
            sg,
            human_user_id,
            task_content=task_content,
            status_filter=status_filter,
            status_field_name=status_field_name,
            due_date_field=due_date_field,
            limit=limit,
        )

    # ── 상태 필드 결정 ──────────────────────────────────────────────
    if status_field_name:
        status_fn = status_field_name.strip()
    else:
        detected = detect_task_status_field(sg)
        status_fn = detected if detected else "sg_status_list"

    st: str = (status_filter or "").strip()
    st_use: bool = bool(st)
    due_fn_effective = (due_date_field or "").strip() or "due_date"

    def _fields() -> List[str]:
        base = [
            "id", "content", status_fn, due_fn_effective, "project",
            "entity", "entity.Shot.code", "entity.Shot.description",
            "entity.Shot.image", "project.Project.code", "project.Project.name",
        ]
        if due_fn_effective != "due_date":
            base.append("due_date")
        return base

    tc_raw = (task_content or "").strip()
    base_filters: List[Any] = [
        ["project", "is", {"type": "Project", "id": int(project_id)}],
        ["entity", "type_is", "Shot"],
        ["task_assignees", "is", {"type": "HumanUser", "id": int(human_user_id)}],
    ]
    if tc_raw:
        base_filters.append(["content", "contains", tc_raw])
    if st_use:
        base_filters.append([status_fn, "is", st])

    def _fields_with_version() -> List[str]:
        return _fields() + ["sg_latest_version", "sg_latest_version.Version.code"]

    rows: List[Dict[str, Any]] = []
    due_read_col = due_fn_effective
    try:
        rows = sg.find("Task", base_filters, _fields_with_version(), limit=limit)
    except Exception:
        try:
            rows = sg.find("Task", base_filters, _fields(), limit=limit)
        except Exception as e1:
            el = str(e1).lower()
            if due_fn_effective != "due_date" and due_fn_effective.lower() in el:
                due_read_col = "due_date"
                fb_filters = [f for f in base_filters]
                fb_fields = [
                    "id", "content", status_fn, "due_date", "project",
                    "entity", "entity.Shot.code", "entity.Shot.description",
                    "entity.Shot.image", "project.Project.code", "project.Project.name",
                ]
                try:
                    rows = sg.find("Task", fb_filters, fb_fields, limit=limit)
                except Exception as e3:
                    logger.warning(
                        "list_comp_tasks_for_project_user due_date fallback failed: %s", e3
                    )
                    rows = []
            else:
                rows = []

    out: List[Dict[str, Any]] = []
    for t in rows:
        ent = t.get("entity") or {}
        if (ent.get("type") or "").lower() != "shot":
            continue
        proj = t.get("project") or {}
        due_val = t.get(due_read_col)
        proj_code = (proj.get("code") or "").strip()
        proj_name = (proj.get("name") or "").strip()
        ver = t.get("sg_latest_version")
        latest_ver = ""
        if isinstance(ver, dict):
            latest_ver = (ver.get("code") or ver.get("name") or "").strip()
        out.append({
            "task_id": t.get("id"),
            "task_content": (t.get("content") or "").strip(),
            "task_status": (t.get(status_fn) or "").strip(),
            "status_field": status_fn,
            "due_date": due_val,
            "shot_id": ent.get("id"),
            "shot_code": (ent.get("code") or ent.get("name") or "").strip(),
            "shot_description": (ent.get("description") or "").strip(),
            "shot_image": t.get("entity.Shot.image") or ent.get("image"),
            "project_id": proj.get("id"),
            "project_code": proj_code,
            "project_name": proj_name,
            "project_folder": (proj_code or proj_name).strip(),
            "latest_version_code": latest_ver,
        })
    return out


def list_notes_for_shots(
    sg: Any,
    shot_ids: List[int],
    *,
    limit: int = 300,
    days_back: int = 14,
) -> List[Dict[str, Any]]:
    """주어진 샷 ID 목록과 연결된 Note 엔티티를 최신순으로 반환합니다.

    days_back: 생성일(created_at) 기준으로 이 일수 이내의 노트만 조회합니다.
    기본 14일(2주). 0 이하이면 날짜 제한 없이 조회합니다.
    """
    if not shot_ids:
        return []
    note_link_vals = [{"type": "Shot", "id": int(sid)} for sid in shot_ids]
    note_fields = [
        "id", "subject", "content", "created_at", "created_by",
        "note_links", "project",
    ]
    order = [{"field_name": "created_at", "direction": "desc"}]

    cutoff: Optional[datetime] = None
    if days_back > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(days_back))

    def _note_filters(link_clause: Any) -> List[Any]:
        if cutoff is None:
            return [link_clause] if isinstance(link_clause, list) else [link_clause]
        # ShotGrid: 여러 조건은 AND
        if isinstance(link_clause, list) and link_clause and isinstance(
            link_clause[0], list
        ):
            return [*link_clause, ["created_at", "greater_than", cutoff]]
        return [link_clause, ["created_at", "greater_than", cutoff]]

    raw: List[Dict[str, Any]] = []
    try:
        link_filter: List[Any] = ["note_links", "in", note_link_vals]
        raw = sg.find(
            "Note",
            _note_filters(link_filter),
            note_fields,
            limit=limit,
            order=order,
        )
    except Exception:
        # 구버전 API 폴백: OR 필터로 최대 10개 샷
        try:
            or_filters = [
                ["note_links", "is", {"type": "Shot", "id": int(sid)}]
                for sid in shot_ids[:10]
            ]
            or_clause = {"filter_operator": "any", "filters": or_filters}
            raw = sg.find(
                "Note",
                _note_filters(or_clause),
                note_fields,
                limit=limit,
                order=order,
            )
        except Exception:
            return []

    out: List[Dict[str, Any]] = []
    for n in raw or []:
        links = n.get("note_links") or []
        shot_names = [
            (lk.get("name") or lk.get("code") or "")
            for lk in links
            if (lk.get("type") or "").lower() == "shot"
        ]
        context = ", ".join(s for s in shot_names if s) or "—"
        proj = n.get("project") or {}
        proj_name = (proj.get("name") or "").strip() or "—"
        author = n.get("created_by") or {}
        author_name = (author.get("name") or "").strip() or "—"
        created_at = n.get("created_at")
        if hasattr(created_at, "strftime"):
            ts_str = created_at.strftime("%Y-%m-%d %H:%M")
        else:
            ts_str = str(created_at or "—")
        out.append({
            "note_id": n.get("id"),
            "subject": (n.get("subject") or "").strip(),
            "content": (n.get("content") or "").strip(),
            "timestamp": ts_str,
            "author": author_name,
            "context": context,
            "project_name": proj_name,
        })
    return out
