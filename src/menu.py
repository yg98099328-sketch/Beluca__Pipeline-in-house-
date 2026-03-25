# 신규 .nuke 설치 시 템플릿용입니다.
# 이미 menu.py 가 있으면 install_to_nuke.bat 가 이 파일을 덮어쓰지 않고
# 기존 파일 끝에 hook 만 추가합니다 (TD 파이프라인 메뉴 유지).
import nuke_setup_pro

nuke_setup_pro.add_setup_pro_menu()

# Tools 훅 초기화: settings.json 에 저장된 on/off 상태에 맞게 훅을 등록합니다.
try:
    nuke_setup_pro.reload_tool_hooks()
except Exception:
    pass
