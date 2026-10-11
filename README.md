# Musicdl App

独立的 Windows 桌面音乐应用，基于 [Musicdl Web](https://github.com/bilinili1416/musicdl-web) 与 [CharlesPikachu/musicdl](https://github.com/CharlesPikachu/musicdl)。网页界面由 pywebview / WebView2 显示，Python 后端随程序打包，用户无需自行安装 Python。

此仓库与 D:\musicdl-test 完全独立。源码从网页版本复制，后续修改不会自动同步。包含最新的快速搜索、播放列表、音频导入、逐句双语歌词、日语振假名、静态歌词鉴赏和萌娘百科查询。

## 使用便携版

解压 dist/Musicdl-App-0.1.0-win-x64.zip 中的完整 Musicdl 文件夹，双击 Musicdl.exe。需要 Windows 10/11 x64 和 Microsoft Edge WebView2 Runtime；缺少时从[微软官方页面](https://developer.microsoft.com/microsoft-edge/webview2/)安装。

便携包包含 portable.flag，音频与状态保存在程序旁的 data 目录，WebView2 浏览数据独立保存。更换程序目录时连同整个 data 目录移动；升级时保留它。应用文件夹必须可写。移除 portable.flag 后使用 %LOCALAPPDATA%\MusicdlApp，两个模式的数据不会自动互相移动。

启动会使用上次保存的本地端口；端口被其他程序占用时重新分配，不停止其他服务。播放位置、搜索历史、收藏与偏好额外保存到 data/.musicdl-app/preferences.json，换端口仍可恢复。默认不读取、复制或改动网页版本的音乐和记录。

关闭应用会保存播放位置并结束其后台服务；有进行中的下载或导入歌词任务时先提示。Windows Job Object 负责在退出或崩溃时结束本应用的后端及工作进程，其他本地服务保持运行。

搜索、下载、在线歌词和百科查询需要联网。已保存音频、歌词及振假名可离线使用。打包不保证第三方平台一直可用；音频格式兼容性由 WebView2 决定。

## 从源码启动

安装 Python 3.12 x64：

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe desktop.py
~~~

也可运行 start.ps1。--data-dir 指定独立数据目录。源码目录含 portable.flag，开发默认使用 ./data。

## 打包

在 Windows x64 上执行：

~~~powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
~~~

输出 dist/Musicdl/Musicdl.exe 和便携 ZIP。采用 PyInstaller 目录模式，完整包含 UniDic Lite 字典、fugashi 扩展、musicdl 平台模块、Node.js 工具及 WebView2 桥接组件。首次安装依赖或打包可能较慢。WebView2 Runtime 由系统提供，未内嵌完整浏览器。不需要 Node.js 前端构建；随包的 Node.js 为 musicdl 的内部依赖。

## 验证

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/test_memory.cjs tests/test_queue.cjs
.\dist\Musicdl\Musicdl.exe --self-test --data-dir .\test-data\frozen
~~~

无窗口诊断会写出 test-data/frozen/.musicdl-app/self-test.json，检查打包资源、真实 spawn 工作进程、六个平台客户端初始化、词典读音和 GUI 模块导入，不访问音乐平台或下载音频。它不替代人工测试 Windows 文件选择器、音频解码或实际平台网络情况。

已有网站音乐可通过桌面「导入音乐」复制到播放列表，不会删除原文件。同名外部 LRC 需要另行导入；网站浏览器的播放记录不会自动进入新应用。

打包产物、音频、状态、浏览器数据与账号凭据均被 Git 忽略。项目目前没有签名证书和自动更新服务。第三方组件许可见 THIRD-PARTY-NOTICES.md。
