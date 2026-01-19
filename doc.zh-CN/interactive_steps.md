# CLI/GUI交互逻辑

## 导入数据和得到Figure对象
1. 选择数据导入器（对应一种仪器设备）
2. 选择作图场景 （对应一种测试项目）
3. 选择原始数据文件
4. 点击导入，计算得到Figure对象。
> 导入同名的原始数据可能会在保存时覆盖以前的图像

## 预览Figure图像
- 选中一个Figure，用户能看到由matplotlib生成的预览图像
- 用户可以删除任一个Figure
- 用户可以修改任一个Figure的归档信息（opju文件名/opju下Floder名）
- 可以为当前所有Figure指定统一的归档信息
  - 指定opju文件名，可选择附加或覆盖
  - 指定Floder名，只能覆盖

## 保存到OPJU
- 输入保存到的OPJU文件的目标路径
- 选择保存模式（默认为附加模式，可改成覆盖模式）
- 点击保存，得到写入后的OPJU

# GUI设计
只需要一个界面就能展示所有功能：
## 最左边的数据导入区
- 选择数据导入器（Importer）的选框，选项依据`domain.importers/`下的内容生成
- 选择作图场景(Scenario)的选框，选项依据`domain.scenarios/[current_selected_importer]/`下的内容生成
- 导入原始数据的按钮，按下后弹出文件管理器，供用户选择原始数据文件，用户确定后选定的文件会调用相应的Importer和Scenario进行处理，得到Figure对象
- 原始数据导入历史列表：可以看到当前App实例启动以来用户导入过的所有原始数据文件名
## 中间的Figure预览区
这又分为左右（3:7）两个子区域：
- 左边的是当前的Figure列表，右边的是当前选中的Figure的Matplotlib预览图，预览图在选中某个Figure项时生成，会缓存5张
- 在左边的Figure列表中，可以点击任意一个Figure，弹出一个操作框，有以下组件：
  - 删除按钮：点击后删除这个Figure
  - `proj_name:floder_path`的键值对编辑框，和对应保存按钮，proj名以及Figure在proj中的子Floder路径本来是Scenario处理流程默认生成的，但用户可以修改。
  - 单独保存按钮，按下后弹出文件管理器选择单独保存的路径（文件夹），会依据当前`proj_name:floder_path`配置进行保存。
## 右边的OPJU保存区
- 一个proj_name输入框
- 一个floder_path输入框
- 一个将输入框的proj_name:floder_path对应用到所有Figure的配置的按钮
- 一个将输入框的proj_name:floder_path对覆盖应用所有Figure的配置的按钮
- OPJU文件路径（一个文件夹）指定按钮和对应路径文本显示框。用户点击这个按钮会弹出文件管理器以选择一个合适的路径
- 保存模式选框，用户可选择附加保存（会附加到当前路径下对应OPJU文件的对应Floder中）或覆盖保存（如果同名OPJU文件存在会直接清空再写入）。 按钮按下后保存全部Figure到OPJU。保存时会应用每个Figure各自的`proj_name:floder_path`配置。