#!/bin/bash

# 启动第一个实例
python3 kvstorage.py localhost:3000 localhost:3001 localhost:3002 &

# 启动第二个实例
python3 kvstorage.py localhost:3001 localhost:3000 localhost:3002 &

# 启动第三个实例
python3 kvstorage.py localhost:3002 localhost:3000 localhost:3001 &

# 等待所有后台进程完成
wait
