[English](https://github.com/ponyofshadows/majoplot/blob/master/README.md) | 中文文档

# majoplot

Majoplot旨在尽量自动化凝聚态物理实验室的数据处理过程中的重复操作。Origin图像可携带绘图数据粘贴到PowerPoint幻灯片中，是一个不错的数据展示工具，因此Majoplot使用OriginLab作为主要的绘图后端。

## 主要功能：
- 在同一个界面预览VSM, PPMS, XRD等仪器产生的原始数据
- 批量绘制图像，自动归档到OPJU的合适Floder中


## 注意
本程序不包含OriginLab，如果要使用OriginLab后端作图，需要自行获取OriginLab许可证和安装它到自己的系统中。

## 安装
首先需要在系统中安装Python（包括pip）。
```bash
#（不推荐）通过pip安装到全局
#pip install majoplot

# (推荐) 通过uv安装
uv tool install majoplot
## 如果uv启动脚本所在路径没被添加到环境变量/Path，则需要运行：
## python -m uv tool install majoplot
```

# 使用方法
1. 在任意路径启打开一个命令行窗口，运行以下命令以启动图形界面
```bash
# 如果是通过pip安装到全局
# python -m majoplot

# 如果是通过uv安装
uv run majoplot
## 如果uv启动脚本所在路径没被添加到环境变量/Path，则需要运行：
## python -m uv run majoplot
```
然后跟着图形界面的指引走就行。