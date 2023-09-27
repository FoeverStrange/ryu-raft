#!/bin/bash

# 启动第一个实例
python3 counter.py 3000 3001 3002 &

# 启动第二个实例
python3 counter.py 3001 3000 3002 &

# 启动第三个实例
python3 counter.py 3002 3000 3001 &

# 等待所有后台进程完成
wait
