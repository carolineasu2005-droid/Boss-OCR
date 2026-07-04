#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SPEC_FILE="${PROJECT_ROOT}/BossOCR-macos.spec"
BUILD_DIR="${PROJECT_ROOT}/build/macos"
DIST_DIR="${PROJECT_ROOT}/dist"
OUTPUT_DIR="${DIST_DIR}/BossOCR"
OUTPUT_BIN="${OUTPUT_DIR}/BossOCR"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: macOS beta packaging 只能在 macOS (Darwin) 上运行。" >&2
    exit 1
fi

if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
    echo "Using active virtual environment: ${VIRTUAL_ENV}"
elif [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
    echo "NOTICE: 当前未激活 virtualenv；将显式使用 .venv/bin/python。"
    echo "        也可以先运行: source .venv/bin/activate"
else
    echo "ERROR: 未检测到已激活的 virtualenv 或 .venv/bin/python。" >&2
    echo "请先创建并安装项目依赖，然后重新运行本脚本。" >&2
    exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "ERROR: Python 不可执行: ${PYTHON_BIN}" >&2
    exit 1
fi

PYTHON_VERSION="$(${PYTHON_BIN} -c 'import platform; print(platform.python_version())')"
PYTHON_MAJOR_MINOR="$(${PYTHON_BIN} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "Python: ${PYTHON_VERSION} (${PYTHON_BIN})"
if [[ "${PYTHON_MAJOR_MINOR}" != "3.11" ]]; then
    echo "WARNING: macOS beta packaging 建议使用 Python 3.11；当前为 ${PYTHON_MAJOR_MINOR}。" >&2
fi

if ! "${PYTHON_BIN}" -c 'import PyInstaller' >/dev/null 2>&1; then
    echo "ERROR: 当前环境未安装 PyInstaller；脚本不会静默或全局安装依赖。" >&2
    echo "请运行:" >&2
    echo "  ${PYTHON_BIN} -m pip install -r requirements-build.txt" >&2
    exit 1
fi

REQUIRED_MODULES=(
    tkinter
    pyautogui
    pynput
    mss
    rapidocr
    onnxruntime
    cv2
    numpy
    PIL
)

MISSING_MODULES=()
for module_name in "${REQUIRED_MODULES[@]}"; do
    if ! "${PYTHON_BIN}" -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('${module_name}') else 1)"; then
        MISSING_MODULES+=("${module_name}")
    fi
done

if (( ${#MISSING_MODULES[@]} > 0 )); then
    echo "ERROR: 缺少打包所需模块: ${MISSING_MODULES[*]}" >&2
    echo "请先安装 requirements.txt 与 requirements-ocr.txt。" >&2
    exit 1
fi

if [[ ! -f "${SPEC_FILE}" ]]; then
    echo "ERROR: 找不到 PyInstaller spec: ${SPEC_FILE}" >&2
    exit 1
fi

echo "Cleaning macOS packaging artifacts:"
echo "  ${BUILD_DIR}"
echo "  ${OUTPUT_DIR}"
rm -rf "${BUILD_DIR}" "${OUTPUT_DIR}"

cd "${PROJECT_ROOT}"
"${PYTHON_BIN}" -m PyInstaller \
    --clean \
    --noconfirm \
    --workpath "${BUILD_DIR}" \
    --distpath "${DIST_DIR}" \
    "${SPEC_FILE}"

if [[ ! -x "${OUTPUT_BIN}" ]]; then
    echo "ERROR: PyInstaller 已结束，但未找到预期可执行文件: ${OUTPUT_BIN}" >&2
    exit 1
fi

echo
echo "macOS beta onedir build completed."
echo "Run from Terminal:"
echo "  dist/BossOCR/BossOCR"
echo
echo "另一台 Mac 需要为实际运行主体重新授权："
echo "  辅助功能、屏幕录制、输入监控"
echo
echo "本产物未签名、未公证。GitHub 下载后可能需要右键打开，"
echo "或在确认来源可信后解除 quarantine 属性。"

