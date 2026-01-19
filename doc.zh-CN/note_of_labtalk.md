# Labtalk指令笔记
虽然很不情愿，但我还是学习了这个古老的、古怪特性非常多的系统。

以下笔记主要基于ChatGPT的对话和在OriginLab中的实测。

## 开始
- 启动Origin，点击菜单栏的Window - Script Window （Shift + Alt + 3），打开Labtalk 窗口
- 输入`type Hello World`回车，得到输出。
> 在不是分号结尾的行上按Enter会运行该行的命令
> origin命令和变量名不区分大小写
> type后的内容可以是纯字符串、用""括起来的字符串、类型为字符串的变量。
## 注释
- `\\`或`#`开头的行为注释，用`\**\`包裹的行也为注释。
## [获取帮助](https://www.originlab.com/doc/en/LabTalk)
- 使用`help`加上关键字获得x-function相关帮助
- 关键字+`-h`获得x-function的简短帮助
但不如直接在官网搜
## 变量
- Labtalk变量在第一次赋值时被声明，从这时起其类型就固定不变。
- 通过`del -v`（v = variable）删除变量。
- labtalk变量能在Variables窗口查看，可以通过这个窗口发现： String变量能和其它类型变量“同名”。实际上`$`后缀是String变量真实名称的一部分，只是变量窗口不显示，所以并没有真的同名。

- 不同的变量类型：
  - 可以用`a = 123`的方式赋值Double类型变量
  - 可以用`b$ = 123`的方式赋值String类型变量，调用String变量时也要加`$`后缀
  - `int a = 123`赋值整数变量
  - 数组`a[1] = 123`编号从1开始
  - 字符串数组`a$[1] = 123`


- 字符串与数值之间的转换函数
  - `$()` to String
  
- 如何把命令的运行结果赋值给变量

## Project Explorer Folder
文件路径操作基于`pe_cd`,`pe_mkdir`等类shell命令：
```labtalk

\\ 跳转到根文件夹，根文件夹名字在GUI显示与OPJU文件同名，但在Labtalk中用`/`表示它即可。
pe_cd
\\ 或
pe_cd /
\\ 或
pe_cd path:="/"

\\ 查看当前目录
pe_path
\\ 列出当前目录下的项目
pe_dir

\\ 新建目录（如果存在会加数字后缀）
pe_mkdir miaomiao
\\ 新建目录（如果存在则无输出）
pe_mkdir miaomiao chk:=1
\\ 新建目录然后立即cd进去
pe_mkdir miaomiao chk:=1 cd:=1

\\ 删除Floder 无论空还是非空都会弹出提示框
pe_rmdir miaomiao

\\ 删除page
win -cd Book1
\\ 或
win -close Book1

\\ 移动Floder或Page
pe_move move:="MT" path:="/miaomiao2";

\\ 重命名Floder或Page
pe_rename name1 name2

\\ 重命名page
win -rename name1 name2
```

