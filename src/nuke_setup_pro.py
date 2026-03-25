"""
Nuke side integration for setup_pro.

How to use:
1) Place this file where Nuke can import it (for example your .nuke folder).
2) In menu.py, call add_setup_pro_menu().
"""

import os
import re

import nuke
import nukescripts

from setup_pro_common import (
    APP_DIR,
    load_presets,
    load_nuke_formats_cache,
    load_colorspaces_cache,
    load_datatypes_cache,
    save_nuke_formats_cache,
    save_colorspaces_cache,
    save_datatypes_cache,
    get_tools_settings,
)


def _set_knob_if_exists(node, knob_name: str, value):
    knob = node.knob(knob_name)
    if knob is None:
        return False
    try:
        knob.setValue(value)
        applied = knob.value()
        if applied != value:
            nuke.tprint(f"[setup_pro] 경고: {knob_name} 값 불일치 — 기대={value!r}, 실제={applied!r}")
    except Exception as e:
        nuke.tprint(f"[setup_pro] {knob_name} setValue 실패: {e}")
        return False
    return True


def _ensure_format(width: int, height: int) -> str:
    # 다른 작업환경 포맷과 충돌을 줄이기 위해 prefix를 길게 둡니다.
    fmt_name = f"VFX_SP_root_{width}x{height}"
    for fmt in nuke.formats():
        if fmt.name() == fmt_name:
            return fmt_name
    nuke.addFormat(f"{width} {height} 0 0 {width} {height} 1 {fmt_name}")
    return fmt_name


def _apply_root_settings(preset_name: str, data: dict) -> None:
    root = nuke.root()

    fps_value = data.get("fps", "").strip()
    if fps_value:
        try:
            _set_knob_if_exists(root, "fps", float(fps_value))
        except ValueError:
            nuke.message(f"[setup_pro] Invalid fps value: {fps_value}")

    plate_format_name = (data.get("plate_format_name") or "").strip()
    formats = {fmt.name(): fmt for fmt in nuke.formats()}
    # 1) 저장된 포맷 이름이 있으면 그대로 root.format에 적용
    if plate_format_name and plate_format_name in formats:
        _set_knob_if_exists(root, "format", plate_format_name)
        # return 하지 않고 아래 OCIO 설정까지 계속 진행
    else:
        # 2) 없으면 width/height로 임시 포맷을 만들어 적용(레거시/특수 사이즈 대응)
        w = data.get("plate_width", "").strip()
        h = data.get("plate_height", "").strip()
        if w and h:
            try:
                width = int(float(w))
                height = int(float(h))
                format_name = _ensure_format(width, height)
                _set_knob_if_exists(root, "format", format_name)
            except ValueError:
                nuke.message(f"[setup_pro] Invalid plate size: {w} x {h}")

    # OCIO 설정: 포맷 처리 경로와 무관하게 항상 적용
    ocio_path = data.get("ocio_path", "").strip()
    if ocio_path:
        if not os.path.exists(ocio_path):
            nuke.message(f"[setup_pro] OCIO path does not exist:\n{ocio_path}")
        else:
            # Depending on Nuke version and color management mode, these knobs differ.
            _set_knob_if_exists(root, "colorManagement", "OCIO")
            if not _set_knob_if_exists(root, "OCIO_config", ocio_path):
                _set_knob_if_exists(root, "customOCIOConfigPath", ocio_path)


def _try_set_node_knob_enum(node, knob_candidates, value: str) -> bool:
    """
    Enumeration knob 값에 맞게 setValue 시도.
    실패하면 False를 리턴합니다.
    """
    if not value:
        return False
    for knob_name in knob_candidates:
        knob = node.knob(knob_name)
        if knob is None:
            continue
        try:
            # If enumeration, prefer only when the value exists.
            if hasattr(knob, "values"):
                vals = []
                try:
                    vals = list(knob.values())
                except Exception:
                    vals = []
                if vals and value not in vals:
                    continue
            knob.setValue(value)
            return True
        except Exception:
            continue
    return False


def _best_enum_match(values, required_substrings):
    """
    values: knob.values() 형태의 문자열 리스트
    required_substrings: 매칭에 필요한 키워드들(전부 포함해야 함)
    """
    req = [s.lower() for s in required_substrings if s]
    for v in values:
        vl = str(v).lower()
        if all(r in vl for r in req):
            return v
    # fallback: 첫 번째에서 부분 키워드만 매칭
    for v in values:
        vl = str(v).lower()
        if any(r in vl for r in req):
            return v
    return None


def _apply_delivery_format_to_write(write, delivery_format: str) -> str:
    """
    Nuke Write 노드에 납품 포맷(EXR/ProRes/DNx/H264)을 반영합니다.
    knob 이름/enum 값은 Nuke 버전/설정에 따라 다를 수 있어:
    - 후보 knob 이름 여러 개를 시도
    - knob.values()가 있으면 키워드 기반으로 "실제로 존재하는 값"을 골라 setValue
    """
    delivery_format = (delivery_format or "").strip()
    if not delivery_format:
        return "[setup_pro] 납품 포맷이 비어 있어 Write 파일 포맷 설정을 건너뛰었습니다."

    result_lines = ["[setup_pro] 납품 포맷 적용"]

    fmt_lower = delivery_format.lower()
    is_exr = fmt_lower.startswith("exr")
    is_prores = "prores" in fmt_lower
    is_dnx = "dnx" in fmt_lower or "dnxhr" in fmt_lower
    is_h264 = "h264" in fmt_lower

    # file_type 후보들
    file_type_candidates = [
        "file_type",
        "fileType",
        "file_format",
        "fileFormat",
    ]

    codec_candidates = [
        "mov64_codec",
        "mov_codec",
        "mov64Codec",
        "codec",
        "h264_codec",
        "h264Codec",
        "avc_codec",
        "avcCodec",
        "mp4_codec",
        "mp4Codec",
        "video_codec",
        "videoCodec",
    ]

    applied_any = False

    # EXR: file_type을 exr로
    if is_exr:
        # 어떤 enum이 있을지 몰라서, values에 'exr'가 포함되는 걸 우선 선택
        for knob_name in file_type_candidates:
            knob = write.knob(knob_name)
            if knob is None:
                continue
            try:
                if hasattr(knob, "values"):
                    vals = list(knob.values())
                    if vals:
                        match = _best_enum_match(vals, ["exr"])
                        if match is not None:
                            knob.setValue(match)
                            applied_any = True
                            result_lines.append(f"- {knob_name} = {match}")
                            break
                else:
                    # enumeration이 아니면 그냥 exr로 시도
                    knob.setValue("exr")
                    applied_any = True
                    result_lines.append(f"- {knob_name} = exr")
                    break
            except Exception:
                continue

        if not applied_any:
            result_lines.append("- EXR용 file_type을 찾지 못했습니다(또는 값 set 실패).")

        return "\n".join(result_lines)

    # MOV/MP4 계열: file_type과 codec을 같이 맞추기
    if is_prores:
        # file_type은 mov 형태가 흔함
        preferred_file_substrings = ["mov"]
        required_codec = ["prores", "422", "hq"]
    elif is_dnx:
        preferred_file_substrings = ["mov"]
        required_codec = ["dnxhr", "hq"]
    elif is_h264:
        # mp4/h264는 파일 타입명이 다양할 수 있음
        preferred_file_substrings = ["mp4", "mov"]
        required_codec = ["h264"]
    else:
        preferred_file_substrings = []
        required_codec = []

    # file_type set
    for knob_name in file_type_candidates:
        knob = write.knob(knob_name)
        if knob is None:
            continue
        try:
            if hasattr(knob, "values"):
                vals = list(knob.values())
                if not vals:
                    continue
                match = None
                if preferred_file_substrings:
                    match = _best_enum_match(vals, preferred_file_substrings)
                if match is None and required_codec:
                    match = _best_enum_match(vals, required_codec)
                if match is not None:
                    knob.setValue(match)
                    applied_any = True
                    result_lines.append(f"- {knob_name} = {match}")
                    break
            else:
                # enumeration이 아니면 대략 시도
                knob.setValue("mov")
                applied_any = True
                result_lines.append(f"- {knob_name} = mov")
                break
        except Exception:
            continue

    # codec set
    codec_applied = False
    if required_codec:
        for knob_name in codec_candidates:
            knob = write.knob(knob_name)
            if knob is None:
                continue
            try:
                if hasattr(knob, "values"):
                    vals = list(knob.values())
                    if not vals:
                        continue
                    match = _best_enum_match(vals, required_codec)
                    if match is None:
                        continue
                    knob.setValue(match)
                    codec_applied = True
                    applied_any = True
                    result_lines.append(f"- {knob_name} = {match}")
                    break
            except Exception:
                continue

    if not applied_any:
        result_lines.append("- file_type/codec 적용을 실패했습니다(또는 knob을 찾지 못했습니다).")

    if required_codec and not codec_applied:
        result_lines.append("- codec 후보 knob에서 매칭되는 값을 못 찾았습니다.")

    return "\n".join(result_lines)


def _find_or_create_setup_pro_write() -> tuple:
    """
    setup_pro 전용 Write 노드를 재사용하고, 없으면 새로 만듭니다.
    """
    for n in nuke.allNodes("Write"):
        try:
            if n.name() == "setup_pro_write":
                return n, False
        except Exception:
            continue

    # 없으면 새로 생성
    sel = nuke.selectedNodes()
    x, y = 200, 200
    if sel:
        try:
            x = sel[0].xpos() + 250
            y = sel[0].ypos()
        except Exception:
            pass
    write = nuke.nodes.Write(xpos=x, ypos=y)
    try:
        write.setName("setup_pro_write", uncollide=True)
    except Exception:
        try:
            write["name"].setValue("setup_pro_write")
        except Exception:
            pass
    return write, True


def _set_enum_with_aliases(node, knob_candidates, selected_value: str, alias_map=None):
    """
    enum/string knob에 대해 selected_value를 최대한 유사 매칭으로 안전하게 setValue 합니다.
    return: (ok, knob_name, applied_value)
    """
    alias_map = alias_map or {}
    selected_value = (selected_value or "").strip()
    if not selected_value:
        return False, "", ""

    candidates = [selected_value] + list(alias_map.get(selected_value, []))
    candidates = [str(c).strip() for c in candidates if str(c).strip()]

    for knob_name in knob_candidates:
        k = node.knob(knob_name)
        if not k:
            continue
        try:
            if hasattr(k, "values"):
                vals = list(k.values())
                if vals:
                    # 1) exact(ignore-case)
                    for c in candidates:
                        cl = c.lower()
                        for v in vals:
                            if str(v).strip().lower() == cl:
                                k.setValue(v)
                                return True, knob_name, str(v)
                    # 2) substring
                    for c in candidates:
                        cl = c.lower()
                        for v in vals:
                            vl = str(v).strip().lower()
                            if cl in vl or vl in cl:
                                k.setValue(v)
                                return True, knob_name, str(v)
                    continue
            # enum이 아니거나 values 비어있으면 문자열 직접 시도
            k.setValue(selected_value)
            return True, knob_name, selected_value
        except Exception:
            continue

    return False, "", ""


def _force_write_file_type_exr(write) -> str:
    ok, knob_name, applied = _set_enum_with_aliases(
        write,
        ["file_type", "fileType", "file_format", "fileFormat"],
        "exr",
        {"exr": ["openexr"]},
    )
    if ok:
        return f"- EXR 고정: {knob_name} = {applied}"
    return "- EXR 고정 실패(file_type 계열 knob을 찾지 못했거나 set 실패)"


def _create_write_node_with_settings(data: dict) -> str:
    write_enabled = data.get("write_enabled", True)
    if not write_enabled:
        return "[setup_pro] Write 세팅 토글이 꺼져있어 Write 노드를 생성하지 않았습니다."

    write, created = _find_or_create_setup_pro_write()

    lines = ["[setup_pro] Write 노드 적용"]
    if created:
        lines.append("- setup_pro_write 노드를 새로 생성했습니다.")
    else:
        lines.append("- 기존 setup_pro_write 노드를 재사용했습니다.")

    # delivery_format에 따라 file_type/codec 적용 (EXR/ProRes/DNx/H264)
    delivery_format = str(data.get("delivery_format", "") or "").strip()
    if not delivery_format:
        delivery_format = "EXR 16bit"  # 레거시 프리셋 호환
    lines.append(_apply_delivery_format_to_write(write, delivery_format))

    channels_value = str(data.get("write_channels", "") or "").strip()
    datatype_value = str(data.get("write_datatype", "") or "").strip()
    compression_value = str(data.get("write_compression", "") or "").strip()
    metadata_value = str(data.get("write_metadata", "") or "").strip()

    ok, kname, applied = _set_enum_with_aliases(
        write,
        ["channels", "channel"],
        channels_value,
        {},
    )
    lines.append(f"- channels: {kname} = {applied}" if ok else f"- channels 적용 실패: {channels_value}")

    datatype_alias = {
        "16 bit half": ["half", "16-bit half"],
        "32 bit float": ["float", "32-bit float"],
        "integer": ["int", "32 bit int", "32-bit int"],
    }
    ok, kname, applied = _set_enum_with_aliases(
        write,
        ["datatype", "dataType", "data_type", "bitdepth", "bitDepth", "bit_depth"],
        datatype_value,
        datatype_alias,
    )
    lines.append(f"- datatype: {kname} = {applied}" if ok else f"- datatype 적용 실패: {datatype_value}")

    compression_alias = {
        "none": ["none"],
        "ZIP (single line)": ["zip", "zip (1 scanline)", "zip (single line)"],
        "ZIP (block of 16 scanlines)": ["zip16", "zips", "zip (16 scanlines)"],
        "RLE": ["rle"],
        "PIZ Wavelet (32 scanlines)": ["piz", "piz wavelet"],
        "PXR24 (lossy)": ["pxr24"],
        "B44 (lossy)": ["b44"],
        "B44A (lossy)": ["b44a"],
        "DWAA (lossy)": ["dwaa"],
        "DWAB (lossy)": ["dwab"],
    }
    ok, kname, applied = _set_enum_with_aliases(
        write,
        ["compression", "compress"],
        compression_value,
        compression_alias,
    )
    lines.append(f"- compression: {kname} = {applied}" if ok else f"- compression 적용 실패: {compression_value}")

    metadata_alias = {
        "all metadata": ["all metadata"],
        "no metadata": ["no metadata"],
        "all metadata except input/time": ["all metadata except input/time"],
        "no metadata except input/time": ["no metadata except input/time"],
    }
    ok, kname, applied = _set_enum_with_aliases(
        write,
        ["metadata"],
        metadata_value,
        metadata_alias,
    )
    lines.append(f"- metadata: {kname} = {applied}" if ok else f"- metadata 적용 실패: {metadata_value}")

    transform_type = str(
        data.get("write_transform_type", data.get("colorspace_transform", "")) or ""
    ).strip()
    out_colorspace = str(
        data.get("write_out_colorspace", data.get("write_colorspace", data.get("out_colorspace", ""))) or ""
    ).strip()
    output_display = str(data.get("write_output_display", data.get("output_display", "")) or "").strip()
    output_view = str(data.get("write_output_view", data.get("output_view", "")) or "").strip()

    transform_alias = {
        "off": ["off", "none", "disabled"],
        "display/view": ["display/view", "display view", "display"],
        "input": ["input"],
        "colorspace": ["colorspace", "color space"],
    }
    ok_t, k_t, v_t = _set_enum_with_aliases(
        write,
        ["colorspace_transform", "transform_type", "transformType"],
        transform_type,
        transform_alias,
    )
    if transform_type:
        lines.append(f"- transform type: {k_t} = {v_t}" if ok_t else f"- transform type 적용 실패: {transform_type}")

    t_norm = transform_type.lower()
    if t_norm == "colorspace":
        ok_c, k_c, v_c = _set_enum_with_aliases(
            write,
            ["out_colorspace", "output_transform", "output_colorspace", "colorspace", "OCIO_colorspace", "ocio_colorspace"],
            out_colorspace,
            {},
        )
        lines.append(f"- output transform: {k_c} = {v_c}" if ok_c else f"- output transform 적용 실패: {out_colorspace}")
    elif t_norm == "display/view":
        ok_d, k_d, v_d = _set_enum_with_aliases(
            write,
            ["output_display", "display"],
            output_display,
            {},
        )
        ok_v, k_v, v_v = _set_enum_with_aliases(
            write,
            ["output_view", "view"],
            output_view,
            {},
        )
        lines.append(f"- display: {k_d} = {v_d}" if ok_d else f"- display 적용 실패: {output_display}")
        lines.append(f"- view: {k_v} = {v_v}" if ok_v else f"- view 적용 실패: {output_view}")

    return "\n".join(lines)


def apply_preset(preset_name: str) -> None:
    presets = load_presets()
    data = presets.get(preset_name)
    if not data:
        nuke.message(f"[setup_pro] Preset not found: {preset_name}")
        return

    _apply_root_settings(preset_name, data)
    write_msg = _create_write_node_with_settings(data)

    project_type = data.get("project_type", "-")
    project_code = data.get("project_code", "-")
    nuke.message(
        f"[setup_pro] 적용 완료: {preset_name}\n"
        f"Type: {project_type} / Code: {project_code}\n\n"
        f"{write_msg}"
    )


def refresh_setup_pro_caches() -> None:
    """
    Nuke 내부에서 실제로 가능한 목록을 긁어서 EXE가 사용할 캐시에 저장합니다.
    """
    # formats 캐시
    formats_dict = {}
    for fmt in nuke.formats():
        try:
            formats_dict[fmt.name()] = {"width": int(fmt.width()), "height": int(fmt.height())}
        except Exception:
            continue
    save_nuke_formats_cache(formats_dict)

    # colorspace/datatype 캐시 (Write 노드에서 enum 값을 읽음)
    # finally로 임시 노드가 반드시 삭제되도록 보장
    write = nuke.nodes.Write()
    colorspaces = []
    datatypes = []
    try:
        colorspace_candidates = [
            "colorspace",
            "colorSpace",
            "OCIO_colorspace",
            "ocio_colorspace",
            "ocioColorSpace",
        ]
        datatype_candidates = [
            "datatype",
            "dataType",
            "data_type",
            "bitdepth",
            "bitDepth",
            "bit_depth",
        ]

        for knob_name in colorspace_candidates:
            k = write.knob(knob_name)
            if not k:
                continue
            try:
                if hasattr(k, "values"):
                    colorspaces = list(k.values())
                    if colorspaces:
                        break
            except Exception:
                pass

        for knob_name in datatype_candidates:
            k = write.knob(knob_name)
            if not k:
                continue
            try:
                if hasattr(k, "values"):
                    datatypes = list(k.values())
                    if datatypes:
                        break
            except Exception:
                pass

        # 마지막 안전장치: "datatype/bit" 계열 knob 전체를 훑어서 값 수집
        if not datatypes:
            try:
                knobs_obj = write.knobs()
                all_knobs = list(knobs_obj.values()) if isinstance(knobs_obj, dict) else list(knobs_obj)
                for k in all_knobs:
                    try:
                        kn = k.name()
                    except Exception:
                        kn = str(k)
                    knl = str(kn).lower()
                    if any(s in knl for s in ["datatype", "data_type", "bitdepth", "bit_depth", "bit", "depth"]):
                        if hasattr(k, "values"):
                            vals = list(k.values())
                            if vals:
                                datatypes = vals
                                break
            except Exception:
                pass
    finally:
        try:
            nuke.delete(write)
        except Exception:
            pass

    # 빈 리스트로 캐시를 덮어쓰면 UI 목록이 사라질 수 있으니, 값이 있을 때만 저장합니다.
    if colorspaces:
        save_colorspaces_cache(colorspaces)
    else:
        nuke.tprint(f"[setup_pro] colorspaces 캐시 갱신 실패/비어 있음({len(colorspaces)}). 기존 캐시를 유지합니다.")

    if datatypes:
        save_datatypes_cache(datatypes)
    else:
        nuke.tprint(f"[setup_pro] datatypes 캐시 갱신 실패/비어 있음({len(datatypes)}). 기존 캐시를 유지합니다.")

    # 팝업 대신 로그로만 남깁니다. (요청: 패널 열 때 안내 팝업 제거)
    if not colorspaces or not datatypes:
        nuke.tprint(
            "[setup_pro] 캐시 갱신 중 일부 목록을 못 읽었습니다.\n"
            f"- colorspaces: {len(colorspaces)}\n"
            f"- datatypes: {len(datatypes)}\n"
            "해결: Nuke에서 Write 노드에 보이는 컬러스페이스/데이터타입 knob 이름을 알려주세요."
        )
        return

    nuke.tprint(
        "[setup_pro] 캐시 갱신 완료\n"
        f"- formats: {len(formats_dict)}\n"
        f"- colorspaces: {len(colorspaces)}\n"
        f"- datatypes: {len(datatypes)}"
    )


def open_setup_pro_panel() -> None:
    # 캐시가 비어있으면 패널 열 때 자동으로 1회 갱신
    try:
        fmts = load_nuke_formats_cache()
        cspaces = load_colorspaces_cache()
        dtypes = load_datatypes_cache()
        if not fmts or not cspaces or not dtypes:
            refresh_setup_pro_caches()
    except Exception:
        # 캐시 로딩 실패여도 패널은 열리게 한다
        pass

    presets = load_presets()
    names = sorted(presets.keys())
    if not names:
        nuke.message("[setup_pro] No presets found. Save presets in setup_pro_manager first.")
        return

    display_to_real = {}
    display_names = []
    for name in names:
        data = presets.get(name, {})
        p_type = data.get("project_type", "미지정")
        # 프리셋 이름(=프로젝트 코드)을 한 번만 표시
        display = f"[{p_type}]  {name}"
        display_to_real[display] = name
        display_names.append(display)

    panel = nukescripts.PythonPanel("BPE — 프리셋 적용")
    hint_top = nuke.Text_Knob("_hint_top", "",
        "적용할 프로젝트 프리셋을 선택하고 OK를 누르세요.\n"
        "선택하면 Nuke Root 설정(FPS·해상도·OCIO)과 Write 노드가 자동으로 세팅됩니다."
    )
    panel.addKnob(hint_top)
    knob = nuke.Enumeration_Knob("preset_name", "프리셋", display_names)
    panel.addKnob(knob)

    if not panel.showModalDialog():
        return

    selected_display = knob.value()
    preset_name = display_to_real.get(selected_display, "")
    if not preset_name:
        nuke.message("[BPE] 프리셋을 찾을 수 없습니다.")
        return
    apply_preset(preset_name)


def show_bpe_tools_status() -> None:
    """
    BPE 앱 Tools 패널에서 저장한 설정(~/.setup_pro/settings.json)과
    현재 Nuke에 등록된 Before/After Render 훅 상태를 안내합니다.
    (별도 'Tools' 메뉴는 없으며, QC/Post-Render는 훅으로만 동작합니다.)
    """
    try:
        cfg = get_tools_settings()
    except Exception as e:
        nuke.message(f"[BPE] settings.json 을 읽지 못했습니다:\n{e}")
        return
    qc_file = cfg.get("qc_checker", {}).get("enabled", False)
    pr_file = cfg.get("post_render_viewer", {}).get("enabled", False)
    settings_path = APP_DIR / "settings.json"
    msg = (
        "BPE Tools 상태\n"
        "────────────────────────\n"
        f"설정 파일:\n  {settings_path}\n\n"
        f"파일에 저장된 옵션:\n"
        f"  • QC Checker (렌더 전):     {'켜짐' if qc_file else '꺼짐'}\n"
        f"  • Post-Render Viewer:       {'켜짐' if pr_file else '꺼짐'}\n\n"
        "Nuke에는 'Tools'라는 메뉴가 없습니다.\n"
        "BPE 데스크톱 앱에서 스위치를 바꾼 뒤,\n"
        "아래 메뉴로 훅을 다시 읽어와야 적용됩니다.\n\n"
        "  setup_pro → BPE Tools → Reload Tool Hooks\n\n"
        "스크립트 에디터에서 확인:\n"
        "  nuke_setup_pro.reload_tool_hooks()"
    )
    nuke.message(msg)


def add_setup_pro_menu() -> None:
    """Nuke 메인 메뉴에 setup_pro 를 한 번만 등록 (중복 호출·재로드 시에도 TD 메뉴와 충돌 없음)."""
    menu = nuke.menu("Nuke")
    try:
        if menu.findItem("setup_pro") is not None:
            return
    except Exception:
        pass
    setup_menu = menu.addMenu("setup_pro")
    setup_menu.addCommand(
        "프리셋 적용  (FPS · 해상도 · OCIO · Write 세팅)",
        "nuke_setup_pro.open_setup_pro_panel()",
    )
    setup_menu.addCommand(
        "캐시 새로 고침  (Write / 포맷 목록 갱신)",
        "nuke_setup_pro.refresh_setup_pro_caches()",
    )
    tools_menu = setup_menu.addMenu("BPE Tools")
    tools_menu.addCommand(
        "QC · Post-Render 상태 확인",
        "nuke_setup_pro.show_bpe_tools_status()",
    )
    tools_menu.addCommand(
        "Tool Hooks 다시 불러오기  (BPE 앱 설정 적용)",
        "nuke_setup_pro.reload_tool_hooks()",
    )
    # 상위 메뉴에도 단축 접근용으로 유지
    setup_menu.addCommand(
        "Tool Hooks 다시 불러오기",
        "nuke_setup_pro.reload_tool_hooks()",
    )


# ══════════════════════════════════════════════════════════════════════
# QC CHECKER
# ══════════════════════════════════════════════════════════════════════

# QC 승인 후 재실행되는 렌더를 식별하는 전역 상태
# {write_node_name} 에 포함된 경우 QC 다이얼로그를 건너뜁니다.
_bpe_qc_approved: set = set()


def _find_upstream_reads(node, visited=None):
    """Write 노드에서 upstream을 역추적해 모든 Read 노드를 반환합니다.
    재귀 대신 명시적 스택을 사용해 깊은 노드 그래프에서의 RecursionError를 방지합니다.
    """
    results = []
    seen: set = set()
    stack = [node]
    while stack:
        current = stack.pop()
        try:
            name = current.name()
        except Exception:
            continue
        if name in seen:
            continue
        seen.add(name)
        if current.Class() == "Read":
            results.append(current)
        try:
            deps = current.dependencies(nuke.INPUTS)
        except Exception:
            deps = []
        for dep in deps:
            stack.append(dep)
    return results


def _knob_value_safe(node, *knob_candidates):
    """여러 후보 knob 이름 중 첫 번째로 값을 가진 것을 반환합니다."""
    for kname in knob_candidates:
        k = node.knob(kname)
        if k is not None:
            try:
                return str(k.value()).strip()
            except Exception:
                pass
    return ""


def _guess_preset_from_script():
    """
    현재 열린 NK 의 Write 파일 경로나 Root 설정으로 프리셋을 추론합니다.
    프리셋 코드(project_code)가 Write 경로에 포함되면 해당 프리셋을 반환.
    """
    try:
        presets = load_presets()
        write_nodes = nuke.allNodes("Write")
        for write in write_nodes:
            file_path = _knob_value_safe(write, "file")
            for name, data in presets.items():
                code = (data.get("project_code") or "").strip().upper()
                if code and code in file_path.upper():
                    return name, data
    except Exception:
        pass
    return None, None


def collect_qc_data(write_node):
    """
    렌더 대상 Write 노드에서 QC 에 필요한 정보를 수집합니다.
    반환: dict
    """
    root = nuke.root()
    data = {}

    # ── Root 정보 ────────────────────────────────────────────────────
    try:
        data["fps"] = str(root["fps"].value())
    except Exception:
        data["fps"] = "?"

    try:
        fmt = root.format()
        data["width"] = str(int(fmt.width()))
        data["height"] = str(int(fmt.height()))
        data["format_name"] = fmt.name()
    except Exception:
        data["width"] = "?"
        data["height"] = "?"
        data["format_name"] = "?"

    data["ocio_path"] = _knob_value_safe(
        root, "customOCIOConfigPath", "OCIO_config", "ocioConfigPath")

    # ── Write 정보 ───────────────────────────────────────────────────
    data["write_name"] = write_node.name()
    data["write_file"] = _knob_value_safe(write_node, "file")
    data["write_colorspace"] = _knob_value_safe(
        write_node, "ocioColorspace", "colorspace", "colorSpace")
    data["write_file_type"] = _knob_value_safe(write_node, "file_type", "fileType", "file_format")

    try:
        data["write_first"] = int(write_node["first"].value())
        data["write_last"] = int(write_node["last"].value())
    except Exception:
        data["write_first"] = None
        data["write_last"] = None

    # ── Upstream Read 분류 ───────────────────────────────────────────
    all_reads = _find_upstream_reads(write_node)

    plate_reads = [
        r for r in all_reads
        if any(k in _knob_value_safe(r, "file").lower() for k in ("plate", "/org/", "\\org\\"))
    ]
    edit_reads = [
        r for r in all_reads
        if any(k in _knob_value_safe(r, "file").lower() for k in ("edit", "/edit/", "\\edit\\"))
    ]

    if plate_reads:
        pr = plate_reads[0]
        data["plate_colorspace"] = _knob_value_safe(pr, "colorspace", "colorSpace")
        data["plate_file"] = _knob_value_safe(pr, "file")
        try:
            data["plate_first"] = int(pr["first"].value())
            data["plate_last"] = int(pr["last"].value())
            data["plate_frames"] = data["plate_last"] - data["plate_first"] + 1
        except Exception:
            data["plate_first"] = None
            data["plate_last"] = None
            data["plate_frames"] = None
    else:
        data["plate_colorspace"] = None
        data["plate_file"] = None
        data["plate_frames"] = None

    if edit_reads:
        er = edit_reads[0]
        data["edit_file"] = _knob_value_safe(er, "file")
        try:
            data["edit_first"] = int(er["first"].value())
            data["edit_last"] = int(er["last"].value())
            data["edit_frames"] = data["edit_last"] - data["edit_first"] + 1
        except Exception:
            data["edit_first"] = None
            data["edit_last"] = None
            data["edit_frames"] = None
    else:
        data["edit_file"] = None
        data["edit_frames"] = None

    # ── 프리셋 매칭 ──────────────────────────────────────────────────
    preset_name, preset_data = _guess_preset_from_script()
    data["preset_name"] = preset_name
    data["preset_data"] = preset_data or {}

    return data


def _qc_status_line(label, current, expected=None, ok_if_none=False):
    """
    체크 한 줄을 (status_char, label, current, note) 튜플로 반환합니다.
    status: "ok" | "warn" | "error"
    """
    if current is None or current == "":
        if ok_if_none:
            return ("ok", label, "(없음)", "")
        return ("warn", label, "(감지 안됨)", "")

    if expected is None:
        return ("ok", label, current, "")

    current_s = str(current).strip()
    expected_s = str(expected).strip()
    if current_s.lower() == expected_s.lower():
        return ("ok", label, current_s, "프리셋 일치")
    else:
        return ("warn", label, current_s, f"프리셋: {expected_s}  ← 불일치!")


def _show_qc_dialog(qc_data: dict) -> bool:
    """
    QC 결과를 Nuke PythonPanel 팝업으로 표시합니다.
    True → 렌더 진행, False → 취소.
    """
    preset_data = qc_data.get("preset_data", {})
    shot_name = ""
    write_file = qc_data.get("write_file", "")
    # 파일 경로에서 샷 이름 추출 시도
    m = re.search(r"([A-Z]\d{3}_[A-Z]\d{3}_\d{4})", write_file, re.IGNORECASE)
    if m:
        shot_name = m.group(1)

    lines = []

    def _add(label, current, expected=None, ok_if_none=False):
        st, lbl, cur, note = _qc_status_line(label, current, expected, ok_if_none)
        icon = {"ok": "✅", "warn": "⚠️", "error": "❌"}[st]
        note_str = f"  ({note})" if note else ""
        lines.append((st, f"{icon}  {lbl:<22} {cur}{note_str}"))

    # FPS
    _add("FPS", qc_data.get("fps"),
         expected=preset_data.get("fps") if preset_data else None)

    # 해상도
    w = qc_data.get("width", "?")
    h = qc_data.get("height", "?")
    cur_res = f"{w}×{h}"
    if preset_data:
        exp_res = f"{preset_data.get('plate_width','?')}×{preset_data.get('plate_height','?')}"
        _add("해상도", cur_res, expected=exp_res)
    else:
        _add("해상도", cur_res)

    # OCIO 경로
    ocio = qc_data.get("ocio_path", "")
    if ocio:
        ocio_exists = os.path.exists(ocio)
        if preset_data and preset_data.get("ocio_path"):
            _add("OCIO 경로", ocio, expected=preset_data.get("ocio_path"))
        else:
            st = "ok" if ocio_exists else "warn"
            icon = "✅" if ocio_exists else "⚠️"
            note = "" if ocio_exists else "  (경로 없음!)"
            lines.append((st, f"{icon}  {'OCIO 경로':<22} {ocio}{note}"))
    else:
        lines.append(("warn", "⚠️  OCIO 경로           (설정 없음)"))

    # Write colorspace
    _add("Write 컬러스페이스", qc_data.get("write_colorspace"),
         expected=preset_data.get("write_out_colorspace") if preset_data else None)

    # Write 파일 타입
    _add("Write 파일 포맷", qc_data.get("write_file_type"))

    # 플레이트 colorspace
    if qc_data.get("plate_colorspace") is not None:
        _add("플레이트 컬러스페이스", qc_data.get("plate_colorspace"),
             expected=preset_data.get("read_input_transform") if preset_data else None)
    else:
        lines.append(("warn", "⚠️  플레이트 컬러스페이스  (플레이트 Read 감지 안됨)"))

    # 프레임 수 비교
    plate_f = qc_data.get("plate_frames")
    edit_f = qc_data.get("edit_frames")
    if plate_f is not None and edit_f is not None:
        match = (plate_f == edit_f)
        icon = "✅" if match else "⚠️"
        note = "일치" if match else f"  ← 불일치! (편집본 {edit_f}f)"
        lines.append(
            ("ok" if match else "warn",
             f"{icon}  {'플레이트 길이':<22} {plate_f}f{note}")
        )
    elif plate_f is not None:
        lines.append(("ok", f"✅  {'플레이트 길이':<22} {plate_f}f"))
    else:
        lines.append(("warn", "⚠️  플레이트 길이         (Read 감지 안됨)"))

    if edit_f is not None and plate_f is None:
        lines.append(("ok", f"✅  {'편집본 길이':<22} {edit_f}f"))

    # ── 요약 판정 ────────────────────────────────────────────────────
    has_warn = any(st in ("warn", "error") for st, _ in lines)
    separator = "─" * 52

    title_shot = f"  {shot_name}" if shot_name else ""
    header = (
        f"BPE QC Checker{title_shot}\n"
        f"{separator}\n"
    )
    body_text = "\n".join(txt for _, txt in lines)
    footer = (
        f"\n{separator}\n"
        + ("⚠️  불일치 항목이 있습니다. 그대로 렌더하시겠습니까?" if has_warn
           else "✅  모든 항목이 프리셋과 일치합니다.")
    )

    full_text = header + body_text + footer
    # 이 함수는 항상 nuke.executeDeferred 컨텍스트에서 호출되므로
    # Nuke가 executing 상태가 아닙니다. 직접 모달을 표시합니다.
    return _show_qc_panel_modal(full_text)


def _show_qc_panel_modal(full_text: str) -> bool:
    """PythonPanel을 띄워 True(OK) / False(Cancel)를 반환합니다."""
    panel = nukescripts.PythonPanel(
        "BPE QC Checker",
        "com.beluca.bpe.qc_checker",
    )
    try:
        panel.setMinimumSize(960, 780)
    except Exception:
        pass

    spacer_knob = nuke.Text_Knob("_spacer", "", " " * 118)
    panel.addKnob(spacer_knob)

    text_knob = nuke.Multiline_Eval_String_Knob("report", "", full_text)
    text_knob.setFlag(nuke.NO_ANIMATION)
    try:
        if hasattr(text_knob, "setHeight"):
            text_knob.setHeight(520)
    except Exception:
        pass
    panel.addKnob(text_knob)

    hint_knob = nuke.Text_Knob("_hint", "", "<b>OK</b> → 렌더 진행   /   <b>Cancel</b> → 취소")
    panel.addKnob(hint_knob)

    return bool(panel.showModalDialog())


def bpe_qc_before_render():
    """
    nuke.addBeforeRender 에 등록되는 콜백.

    addBeforeRender/addAfterRender 콜백은 nuke.execute() 컨텍스트 내부에서
    실행됩니다. 이 상태에서 showModalDialog() 나 노드 생성을 시도하면
    "I'm already executing something else" 오류가 발생합니다.

    해결책:
      1. QC 데이터를 수집 (read-only 조작 — 안전)
      2. RuntimeError 로 현재 렌더를 즉시 중단
      3. nuke.executeDeferred 로 Nuke가 idle 상태가 된 뒤 QC 다이얼로그 표시
      4. OK 면 _bpe_qc_approved 에 노드 이름을 추가하고 nuke.execute 재호출
         — beforeRender 가 다시 실행되지만 approved set 에서 즉시 통과
      5. Cancel 이면 렌더 없이 종료
    """
    write = nuke.thisNode()
    write_name = write.name()

    # QC 승인 후 재실행된 렌더 — 다이얼로그 없이 통과
    if write_name in _bpe_qc_approved:
        _bpe_qc_approved.discard(write_name)
        return

    # QC 데이터 수집 (노드 읽기 전용 — execute 컨텍스트에서도 안전)
    try:
        qc_data = collect_qc_data(write)
    except Exception as e:
        nuke.tprint(f"[BPE QC Checker] QC 데이터 수집 오류 (렌더 계속): {e}")
        return

    # 렌더 범위 캡처 (thisNode 컨텍스트가 끝나기 전에 저장)
    try:
        first = int(write["first"].value())
        last = int(write["last"].value())
    except Exception:
        try:
            first = int(nuke.root().firstFrame())
            last = int(nuke.root().lastFrame())
        except Exception:
            first, last = 1, 1

    def _deferred_qc_and_render():
        """Nuke idle 상태에서 QC 다이얼로그를 표시하고, 승인 시 렌더를 재실행합니다."""
        try:
            proceed = _show_qc_dialog(qc_data)
        except Exception as e:
            nuke.tprint(f"[BPE QC Checker] 다이얼로그 오류: {e}")
            return

        if not proceed:
            nuke.tprint("[BPE QC Checker] 사용자가 렌더를 취소했습니다.")
            return

        w = nuke.toNode(write_name)
        if w is None:
            nuke.tprint(f"[BPE QC Checker] Write 노드 '{write_name}'를 찾을 수 없습니다.")
            return

        # 재실행 시 beforeRender 가 다시 호출되지 않도록 approved 등록
        _bpe_qc_approved.add(write_name)
        try:
            nuke.execute(w, first, last, 1)
        except Exception as e:
            _bpe_qc_approved.discard(write_name)
            nuke.tprint(f"[BPE QC Checker] 렌더 실행 오류: {e}")

    # Nuke가 execute 컨텍스트에서 빠져나온 뒤 실행하도록 예약
    nuke.executeDeferred(_deferred_qc_and_render)

    # 현재 렌더를 중단 — RuntimeError 는 try/except 밖에서 raise
    raise RuntimeError(
        "[BPE] QC Checker 다이얼로그를 표시합니다. 확인 후 렌더가 재시작됩니다."
    )


# ══════════════════════════════════════════════════════════════════════
# POST-RENDER VIEWER
# ══════════════════════════════════════════════════════════════════════

def _bpe_output_media_kind(out_path: str, write) -> str:
    """렌더 출력이 EXR 시퀀스 / 무비 / 기타인지 추정합니다."""
    p = (out_path or "").lower().replace("\\", "/")
    ft = _knob_value_safe(write, "file_type", "fileType", "file_format").lower()
    if "exr" in ft or p.endswith(".exr") or ".exr" in p:
        return "exr"
    if any(ext in p for ext in (".mov", ".mp4", ".mxf", ".avi", ".mkv")):
        return "movie"
    if any(x in ft for x in ("mov", "mp4", "prores", "h264", "dnx", "mpeg")):
        return "movie"
    return "other"


def _bpe_safe_set_read_enum(read, knob_names: tuple, preferred_values: list) -> bool:
    """
    Read 노드 enum 계열 knob에 대해, knob.values()에 실제로 있는 값만 setValue.
    잘못된 문자열을 넣어 Nuke가 에러 다이얼로그를 띄우는 것을 막습니다.
    """
    preferred_values = [str(v).strip() for v in preferred_values if str(v).strip()]
    # 중복 제거(순서 유지)
    seen = set()
    prefs = []
    for v in preferred_values:
        if v not in seen:
            seen.add(v)
            prefs.append(v)

    for kname in knob_names:
        k = read.knob(kname)
        if k is None:
            continue
        vals = []
        try:
            if hasattr(k, "values"):
                vals = list(k.values())
        except Exception:
            vals = []
        if not vals:
            for pref in prefs:
                try:
                    k.setValue(pref)
                    return True
                except Exception:
                    continue
            continue
        for pref in prefs:
            if pref in vals:
                try:
                    k.setValue(pref)
                    return True
                except Exception:
                    continue
            pl = pref.lower()
            for v in vals:
                try:
                    if str(v).strip().lower() == pl:
                        k.setValue(v)
                        return True
                except Exception:
                    continue
            for v in vals:
                try:
                    vs = str(v).lower()
                    if pl and (pl in vs or vs in pl):
                        k.setValue(v)
                        return True
                except Exception:
                    continue
    return False


def _bpe_plate_colorspace_from_write(write) -> str:
    """
    Write 업스트림에서 플레이트 Read(경로에 plate / org 등)를 찾아 그 colorspace 문자열을 반환.
    QC Checker와 동일한 분류 규칙을 사용합니다.
    """
    try:
        all_reads = _find_upstream_reads(write)
    except Exception:
        return ""
    plate_reads = [
        r for r in all_reads
        if any(k in _knob_value_safe(r, "file").lower() for k in ("plate", "/org/", "\\org\\"))
    ]
    if not plate_reads:
        return ""
    return _knob_value_safe(
        plate_reads[0], "colorspace", "colorSpace", "OCIO_colorspace", "ocio_colorspace"
    )


def _bpe_configure_read_from_write(read, write, out_file: str, plate_colorspace: str = "") -> None:
    """
    Write 출력 형식(EXR / MOV 등)에 맞춰 Read의 file_type을 설정하고,
    colorspace는 플레이트 Read와 동일하게 맞춥니다(없을 때만 Write·기본값 후보).
    """
    kind = _bpe_output_media_kind(out_file, write)
    p = out_file.lower()

    # --- file_type (무비/EXR 명시 시 로드 오류 감소) ---
    if kind == "exr":
        _bpe_safe_set_read_enum(read, ("file_type", "fileType"), ["exr", "openexr", "EXR", "OpenEXR"])
    elif kind == "movie":
        if ".mp4" in p:
            _bpe_safe_set_read_enum(read, ("file_type", "fileType"), ["mp4", "mpeg4", "MP4"])
        else:
            _bpe_safe_set_read_enum(read, ("file_type", "fileType"), ["mov", "quicktime", "MOV", "mp4"])

    # --- colorspace: 플레이트 Read와 동일하게 (뷰어에서 플레이트와 톤이 맞도록) ---
    plate_cs = (plate_colorspace or "").strip()
    w_ocio = _knob_value_safe(write, "ocioColorspace", "OCIO_colorspace", "ocio_colorspace")
    w_cs = _knob_value_safe(write, "colorspace", "colorSpace")
    tt = _knob_value_safe(write, "colorspace_transform", "transform_type", "transformType").lower()

    candidates = []
    if plate_cs:
        candidates.append(plate_cs)
    if w_ocio and w_ocio not in candidates:
        candidates.append(w_ocio)
    if w_cs and w_cs not in candidates:
        candidates.append(w_cs)

    if kind == "exr":
        candidates.extend(
            ["default", "scene_linear", "compositing_linear", "linear", "data", "raw"]
        )
    else:
        candidates.extend(
            ["default", "Output - Rec.709", "Output - sRGB", "sRGB", "rec709", "scene_linear"]
        )

    if "display" in tt or "view" in tt:
        extra = [
            plate_cs, w_ocio, w_cs,
            "default", "Output - Rec.709", "sRGB", "rec709",
            "scene_linear", "compositing_linear",
        ]
        seen = set()
        candidates = [c for c in extra if c and (c not in seen and not seen.add(c))]

    ok = _bpe_safe_set_read_enum(
        read,
        ("colorspace", "colorSpace", "OCIO_colorspace", "ocio_colorspace"),
        candidates,
    )
    if not ok:
        nuke.tprint(
            "[BPE Post-Render Viewer] Read colorspace: 플레이트/Write 값이 Read 목록에 없어 Nuke 기본값 유지"
        )


def _bpe_read_reload_safe(read) -> None:
    try:
        rk = read.knob("reload")
        if rk is not None:
            rk.execute()
    except Exception:
        pass


def _bpe_set_read_frame_range_values(read, first: int, last: int) -> None:
    """first/last 값을 직접 받아 Read 노드에 설정합니다."""
    for knob_name, val in (("first", first), ("last", last)):
        try:
            k = read.knob(knob_name)
            if k is not None:
                k.setValue(val)
        except Exception:
            pass
    for knob_name, val in (("origfirst", first), ("origlast", last)):
        k = read.knob(knob_name)
        if k is not None:
            try:
                k.setValue(val)
            except Exception:
                pass


def _bpe_set_read_frame_range(read, write) -> None:
    try:
        first = int(write["first"].value())
        last = int(write["last"].value())
    except Exception:
        return
    _bpe_set_read_frame_range_values(read, first, last)


def _bpe_defer_connect_viewer(read_name: str) -> None:
    """AfterRender 직후 Viewer 연결이 Nuke 내부 상태와 충돌할 수 있어 한 틱 미룸."""

    def _go():
        n = nuke.toNode(read_name)
        if n:
            _bpe_connect_read_to_viewer(n)

    try:
        nuke.executeDeferred(_go)
    except Exception:
        _go()


def bpe_post_render_load():
    """
    nuke.addAfterRender 에 등록되는 콜백.
    렌더 완료 후 출력 시퀀스를 Read 노드로 자동 생성/갱신하고 Viewer에 연결합니다.

    addAfterRender 콜백은 nuke.execute() 컨텍스트 내부에서 실행됩니다.
    이 상태에서 노드를 생성/수정하면 "I'm already executing something else"
    오류가 발생하고 Read 노드가 ERROR 상태로 남습니다.

    해결책: 콜백 안에서는 읽기 전용 데이터만 수집하고,
    실제 노드 생성/수정은 nuke.executeDeferred 로 idle 상태에서 실행합니다.
    """
    try:
        write = nuke.thisNode()
        out_file = _knob_value_safe(write, "file")
        if not out_file:
            nuke.tprint("[BPE Post-Render Viewer] Write 파일 경로가 비어 있어 Read 생성을 건너뜁니다.")
            return

        # execute 컨텍스트 안에서 안전한 읽기 전용 조작만 수행
        write_name = write.name()
        plate_cs = _bpe_plate_colorspace_from_write(write)
        wx = write.xpos()
        wy = write.ypos()
        try:
            write_first = int(write["first"].value())
            write_last = int(write["last"].value())
        except Exception:
            write_first = None
            write_last = None

        def _deferred(_wname=write_name, _out=out_file, _pcs=plate_cs,
                      _wx=wx, _wy=wy, _wf=write_first, _wl=write_last):
            """Nuke idle 상태에서 Read 노드를 생성/갱신하고 Viewer에 연결합니다."""
            try:
                w = nuke.toNode(_wname)
                read_name = "bpe_render_preview"
                existing = nuke.toNode(read_name)

                if existing and existing.Class() == "Read":
                    try:
                        existing["file"].setValue(_out)
                    except Exception as e:
                        nuke.tprint(f"[BPE Post-Render Viewer] 기존 Read 경로 설정 실패: {e}")
                        return
                    if w is not None:
                        if _wf is not None and _wl is not None:
                            _bpe_set_read_frame_range_values(existing, _wf, _wl)
                        _bpe_configure_read_from_write(existing, w, _out, _pcs)
                    _bpe_read_reload_safe(existing)
                    nuke.tprint(f"[BPE Post-Render Viewer] 기존 '{read_name}' 갱신: {_out}")
                    _bpe_connect_read_to_viewer(existing)
                    return

                try:
                    read = nuke.nodes.Read(file=_out, xpos=_wx + 160, ypos=_wy)
                except Exception as e:
                    nuke.tprint(f"[BPE Post-Render Viewer] Read 노드 생성 실패: {e}")
                    return

                try:
                    read.setName(read_name, uncollide=True)
                except Exception:
                    try:
                        read["name"].setValue(read_name)
                    except Exception:
                        pass

                if w is not None:
                    if _wf is not None and _wl is not None:
                        _bpe_set_read_frame_range_values(read, _wf, _wl)
                    _bpe_configure_read_from_write(read, w, _out, _pcs)
                _bpe_read_reload_safe(read)
                nuke.tprint(f"[BPE Post-Render Viewer] Read '{read.name()}' 생성: {_out}")
                _bpe_connect_read_to_viewer(read)

            except Exception as e:
                nuke.tprint(f"[BPE Post-Render Viewer] deferred 오류: {e}")

        nuke.executeDeferred(_deferred)

    except Exception as e:
        nuke.tprint(f"[BPE Post-Render Viewer] 오류: {e}")


def _bpe_connect_read_to_viewer(read_node) -> None:
    """Read 노드를 Viewer의 입력 0번에 연결합니다."""
    try:
        viewer = next((n for n in nuke.allNodes("Viewer")), None)
        if viewer:
            viewer.setInput(0, read_node)
            nuke.tprint(f"[BPE Post-Render Viewer] Viewer → {read_node.name()}")
    except Exception as e:
        nuke.tprint(f"[BPE Post-Render Viewer] Viewer 연결 실패: {e}")


# ══════════════════════════════════════════════════════════════════════
# TOOL HOOKS 관리
# ══════════════════════════════════════════════════════════════════════

def reload_tool_hooks() -> None:
    """
    settings.json 의 tools 섹션을 읽어 훅을 등록/해제합니다.
    BPE 앱의 Tools 패널에서 설정 변경 후 이 함수를 호출하거나,
    Nuke 메뉴 setup_pro > BPE Tools > Reload Tool Hooks 를 실행하세요.
    """
    try:
        cfg = get_tools_settings()
    except Exception as e:
        nuke.tprint(f"[BPE Tools] settings 로드 실패: {e}")
        return

    # ── QC Checker ───────────────────────────────────────────────────
    qc_enabled = cfg.get("qc_checker", {}).get("enabled", False)
    try:
        nuke.removeBeforeRender(bpe_qc_before_render)
    except Exception:
        pass
    if qc_enabled:
        nuke.addBeforeRender(bpe_qc_before_render)

    # ── Post-Render Viewer ────────────────────────────────────────────
    prv_enabled = cfg.get("post_render_viewer", {}).get("enabled", False)
    try:
        nuke.removeAfterRender(bpe_post_render_load)
    except Exception:
        pass
    if prv_enabled:
        nuke.addAfterRender(bpe_post_render_load)

    nuke.tprint(
        "[BPE Tools] Reload 완료 — "
        f"QC Checker: {'ON' if qc_enabled else 'OFF'}  |  "
        f"Post-Render Viewer: {'ON' if prv_enabled else 'OFF'}  |  "
        f"settings: {APP_DIR / 'settings.json'}"
    )
