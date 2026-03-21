"""
Nuke side integration for setup_pro.

How to use:
1) Place this file where Nuke can import it (for example your .nuke folder).
2) In menu.py, call add_setup_pro_menu().
"""

import os

import nuke
import nukescripts

from setup_pro_common import (
    load_presets,
    load_nuke_formats_cache,
    load_colorspaces_cache,
    load_datatypes_cache,
    save_nuke_formats_cache,
    save_colorspaces_cache,
    save_datatypes_cache,
)


def _set_knob_if_exists(node, knob_name: str, value):
    knob = node.knob(knob_name)
    if knob is None:
        return False
    knob.setValue(value)
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
        return

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
        "fileType",
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
        required_codec = ["dnx", "hq", "x"]
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
    write = nuke.nodes.Write()

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

    colorspaces = []
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

    datatypes = []
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

    # 후보 knob 이름 매칭이 실패할 수 있어서, 마지막 안전장치로 "datatype/bit" 계열 knob을 전체 훑어서 값을 수집합니다.
    if not datatypes:
        try:
            knobs_obj = write.knobs()
            if isinstance(knobs_obj, dict):
                all_knobs = list(knobs_obj.values())
            else:
                all_knobs = list(knobs_obj)

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

    # 임시 노드 제거
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
        p_code = data.get("project_code", "NO_CODE")
        display = f"{p_type} | {p_code} | {name}"
        display_to_real[display] = name
        display_names.append(display)

    panel = nukescripts.PythonPanel("setup_pro")
    knob = nuke.Enumeration_Knob("preset_name", "Preset", display_names)
    panel.addKnob(knob)

    if not panel.showModalDialog():
        return

    selected_display = knob.value()
    preset_name = display_to_real.get(selected_display, "")
    if not preset_name:
        nuke.message("[setup_pro] Invalid preset selection.")
        return
    apply_preset(preset_name)


def add_setup_pro_menu() -> None:
    menu = nuke.menu("Nuke")
    setup_menu = menu.addMenu("setup_pro")
    setup_menu.addCommand("Open setup_pro panel", "nuke_setup_pro.open_setup_pro_panel()")
    setup_menu.addCommand("Refresh setup_pro lists (Write/Formats)", "nuke_setup_pro.refresh_setup_pro_caches()")
