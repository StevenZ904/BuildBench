#!/bin/bash

# Compiler Wrapper
# Usage:
# 1. 将此脚本链接到 PATH 中，例如 ln -s /home/user1/wrapper.sh /usr/local/bin/gcc
# 2. 移走原始编译器：查看路径 which gcc ；然后 mv /usr/bin/gcc /usr/bin/gcc-real
# 3. 将此脚本中的 real_gcc/real_gxx/real_clang/real_clangxx 设置为实际的编译器路径
# 3. 此时调用编译器时将自动执行此脚本，可以通过环境变量 ENABLE_COMPILER_WRAPPER=True 或者设置 WRAPPER_OPTI 来启用编译参数的替换
# Tips: 一旦启用该脚本，关于调试信息和剥离符号信息的参数首先被删除
#       如果 WRAPPER_OPTI 中存在有关优化选项的参数，则替换原始命令中的优化选项，
#       最后， WRAPPER_OPTI 中的其他参数也会被加入到编译命令中
# Example: WRAPPER_OPTI="-O2 -gdwarf-4" gcc -O3 -Wall -o test.elf test.c

# 检查是否有足够的参数
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 [source files and options]"
  echo "This is a wrapper for the compiler 'gcc, g++, clang, clang++'."
  echo "It modifies the compilation options and ignores certain flags."
  exit 1
fi

real_gcc="gcc-real"
real_gxx="g++-real"
real_clang="clang-real"
real_clangxx="clang++-real"
real_cc="gcc-real"
real_cxx="g++-real"

# 如果环境变量 ENABLE_COMPILER_WRAPPER=True 或者设置了 WRAPPER_OPTI，则执行参数替换，否则执行原始命令
if [ -z "$ENABLE_COMPILER_WRAPPER" ] && [ -z "$WRAPPER_OPTI" ]; then
  # 确定要使用的编译器
  compiler=""
  case $(basename "$0") in
    gcc)
      compiler=$real_gcc
      ;;
    clang)
      compiler=$real_clang
      ;;
    g++)
      compiler=$real_gxx
      ;;
    clang++)
      compiler=$real_clangxx
      ;;
    cc)
      compiler=$real_cc
      ;;
    c++)
      compiler=$real_cxx
      ;;
    *)
      echo "Error: Unknown compiler '$0'."
      exit 1
      ;;
  esac
  # 直接执行原始命令
  exec "$compiler" "$@"
fi

# 函数：检查并跳过无效或指定的参数
skip_base_arg() {
  local arg="$1"
  case "$arg" in
    -s|-DNDEBUG|-g|-gdwarf-*|-gdwarf|--debug|--debug=*|--optimize|--optimize=*)
      return 0 # 跳过这些参数
      ;;
    *)
      return 1 # 不跳过
      ;;
  esac
}
skip_opti_arg() {
  local arg="$1"
  case "$arg" in
    -O|-O0|-O1|-O2|-O3|-Os|-Ofast|-Og|-Oz)
      return 0 # 跳过这些参数
      ;;
    *)
      return 1 # 不跳过
      ;;
  esac
}

# 确定要使用的编译器
compiler=""
case $(basename "$0") in
  gcc)
    compiler=${WRAPPER_GCC:-$real_gcc}
    ;;
  clang)
    compiler=${WRAPPER_CLANG:-$real_clang}
    ;;
  g++)
    compiler=${WRAPPER_GXX:-$real_gxx}
    ;;
  clang++)
    compiler=${WRAPPER_CLANGXX:-$real_clangxx}
    ;;
  cc)
    compiler=${WRAPPER_CC:-$real_cc}
    ;;
  c++)
    compiler=${WRAPPER_CXX:-$real_cxx}
    ;;
  *)
    echo "Error: Unknown compiler '$0'."
    exit 1
    ;;
esac

# 判断 WRAPPER_OPTI 中是否包含优化选项 "-O|-O0|-O1|-O2|-O3|-Os|-Ofast|-Og|-Oz"，如果包含则将变量 IS_WRAP_OPTI 设置为 true
IS_WRAP_OPTI=false
if [[ "$WRAPPER_OPTI" =~ -O[0-3sfastgz]* ]]; then
  IS_WRAP_OPTI=true
fi

# 初始化参数数组
params=()

# 遍历所有传入的参数
for arg in "$@"; do
  if skip_base_arg "$arg"; then
    continue # 跳过必须跳过的参数
  fi
  # 如果 IS_WRAP_OPTI 为 true，则使用 skip_opti_arg 跳过原始的优化选项
  if $IS_WRAP_OPTI && skip_opti_arg "$arg"; then
    continue # 跳过原始的优化选项
  fi

  params+=("$arg") # 添加参数到数组
done

# 修改环境变量指定的优化选项处理部分以支持空格分隔
if [ -n "$WRAPPER_OPTI" ]; then
  # 将环境变量中的逗号替换为空格，以统一分隔符
  WRAPPER_OPTI_MODIFIED="${WRAPPER_OPTI//,/ }"
  # 读取并分割优化选项
  read -ra OPTI_ARR <<< "$WRAPPER_OPTI_MODIFIED"
  for opt in "${OPTI_ARR[@]}"; do
    opt_trimmed=$(echo $opt | xargs)  # Trim whitespace
    params+=("$opt_trimmed")
  done
fi

# 执行编译器
# echo "[-] DEBUG | Executing: $compiler ${params[@]}"
"$compiler" "${params[@]}"
