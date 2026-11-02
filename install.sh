#!/usr/bin/env bash
# 安装 mapconv (及兼容命令 xmind2pdf / map2md) 到 ~/.local/bin, 软链保留包结构
set -e
cd "$(dirname "$0")"
mkdir -p ~/.local/bin
chmod +x bin/mapconv bin/xmind2pdf bin/map2md
for cmd in mapconv xmind2pdf map2md; do
    ln -sf "$(pwd)/bin/$cmd" ~/.local/bin/$cmd
done
echo "已安装: mapconv, xmind2pdf, map2md -> ~/.local/bin/"
