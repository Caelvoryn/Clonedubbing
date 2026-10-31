# Clonedubbing 综合声线配音

整合10组现有声线：李羽希、夏炎、王玮琳、五组诗词声线和两组英文声音。支持中文、英文及长文自动分段；没有固定总字数上限，实际容量受服务器资源约束。

## Windows 下载与安装

在本仓库 Releases 下载 **ClonedubbingSetup.exe**，双击安装。桌面入口打开地址配置窗口，填写配音服务器 URL 后，通过系统浏览器使用工作台。安装包不含模型，也不会自动提供在线服务器。

[下载最新安装包](https://github.com/Caelvoryn/Clonedubbing/releases/tag/installer-latest)

## 服务器部署

需要 Python 3.12、可用模型文件和参考音频。NVIDIA GPU 可加速；安装与驱动兼容的 PyTorch。安装依赖：`pip install -r requirements.txt`。

1. 将基础模型放入 `models/Qwen3-TTS-12Hz-1.7B-Base`，专属微调模型放入 `models/李羽希` 与 `models/王玮琳`。
2. 复制 `profiles.example.json` 为 `voices/profiles.json`，按配置放置每组参考音频。模型和真人参考录音不随源码公开发布，需要部署者自行提供已有文件。
3. 设置 `VOICE_HOST=0.0.0.0`、`VOICE_USER`、`VOICE_PASSWORD`，运行 `python server.py`。默认端口7865。对外服务必须配置账号密码；公网使用 HTTPS 反向代理。
4. 客户端填入实际服务器地址。GitHub仅托管代码和安装包，不托管持续运行的GPU配音服务。

可用环境变量：`VOICE_MODEL` 基础模型目录、`VOICE_PROFILES` 声线配置路径、`VOICE_HOST`、`VOICE_PORT`、`VOICE_DEVICE=cpu`。模型路径和参考音频的相对路径以程序目录为基准。

长文逐段写入 WAV，不将全部音频堆入内存。若任务中断，已生成的部分仍在 outputs 目录；下一次生成会建立新的文件。更换专属模型会释放旧模型，首次切换需要加载时间。音色自然程度需要实际试听判断。

## 构建安装包

Windows PowerShell 运行 `./build-client.ps1`，结果在 dist。GitHub Actions 在主分支更新时构建，并发布到 installer-latest。安装器将客户端放到当前用户 LocalAppData/UnifiedVoice，并创建桌面入口。卸载时删除该目录和桌面入口即可。EXE尚未代码签名。

## 验证范围

已在本机检查配置读取、10组声线界面、长文分段及客户端/安装器编译。未完成远程服务器部署或全部10组声线的端到端回归；服务器启用前应逐组试听。
