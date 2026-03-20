#!/bin/bash

# 原始strip命令的路径
STRIP_REAL="strip-real"

# 如果没有参数，则执行原始的strip命令
if [ $# -eq 0 ]; then
    exec $STRIP_REAL "$@"
fi

# 遍历所有参数，检查是否存在 -o 选项
OUTPUT_SPECIFIED=false
OUTPUT_FILE=""
INPUT_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -o)
            OUTPUT_SPECIFIED=true
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -*)
            shift
            ;;
        *)
            INPUT_FILE="$1"
            shift
            ;;
    esac
done

# 如果没有指定输出文件（即在原始文件上执行strip），则不进行任何操作
if [ "$OUTPUT_SPECIFIED" = false ]; then
    echo "Skipping strip operation on original file: $INPUT_FILE"
    exit 0
fi

# 如果指定了输出文件，则执行复制操作
if [ "$OUTPUT_SPECIFIED" = true ]; then
    cp "$INPUT_FILE" "$OUTPUT_FILE"
    echo "Copied $INPUT_FILE to $OUTPUT_FILE instead of stripping"
fi
