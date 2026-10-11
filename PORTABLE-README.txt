Musicdl App 0.1.0 - Windows x64 便携版

1. 解压整个 Musicdl 文件夹，然后双击 Musicdl.exe。不要只复制 EXE。
2. 需要 Windows 10/11 x64 和 Microsoft Edge WebView2 运行时。
   官方下载：https://developer.microsoft.com/microsoft-edge/webview2/
3. 音乐、歌词、播放列表与桌面播放记录保存在本文件夹的 data 目录。
   将整个文件夹移动到其他可写目录后，数据仍保留。升级时保留 data 目录。
4. 搜索、下载和在线歌词查询需要联网，本地播放与已有歌词可离线使用。
5. 应用与 D:\musicdl-test 本地网站独立，不会自动修改或迁移原网站数据。
6. 关闭应用会关闭后台服务。有任务进行时会提示；中断任务可重新搜索下载。
7. 启动错误日志位于 data\.musicdl-app\app.log。
8. 保留 portable.flag 使用便携模式；移除后数据改用 %LOCALAPPDATA%\MusicdlApp。
9. 本应用未进行代码签名；请从自己的可信仓库获取。公司设备的应用策略可能限制运行。

项目：https://github.com/bilinili1416/musicdl-app
网页版本：https://github.com/bilinili1416/musicdl-web
后端原项目：https://github.com/CharlesPikachu/musicdl
