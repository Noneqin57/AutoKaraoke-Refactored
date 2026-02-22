# REATK - AutoKaraoke Refactored (Web 版)

**REATK** 是一个基于 OpenAI Whisper 和 `stable-ts` 的自动化卡拉OK逐字歌词生成器。本项目是其 Web UI 版本，提供了一个用户友好的图形界面，让歌词制作过程更加直观和高效。

[![LICENSE](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](https://github.com/your-repo/REATK-Web/blob/main/LICENSE)

## ✨ 功能特性

- **Web 用户界面**: 通过浏览器即可完成所有操作，无需命令行。
- **实时进度反馈**: 使用 WebSocket 实时显示任务状态和生成进度。
- **高精度时间轴**: 基于 `stable-ts` 对 Whisper 的输出进行对齐，生成逐字级别的时间戳。
- **多种模型支持**: 支持 `Whisper` 和 `faster-whisper` 两种推理后端，并可在多种模型尺寸（`tiny` 到 `large-v3`）之间切换。
- **模型管理**: 内置模型下载、删除和管理功能，支持从 Hugging Face 镜像源加速下载。
- **人声分离 (可选)**: 集成基础人声分离库，可在处理前自动分离人声，提高识别准确率。
- **参数可调**: 支持调整语言、提示词 (Prompt)、时间轴偏移等多种参数。
- **批量处理**: 支持一次性处理多个音频文件。
- **现代化的后端**: 基于 FastAPI 构建，采用多进程架构，将耗时的 AI 任务与 Web 服务分离，保证界面响应速度。

## 🛠️ 技术栈

- **后端**:
  - **Web 框架**: FastAPI
  - **AI 推理**: `openai-whisper`, `faster-whisper`, `stable-ts`
  - **深度学习框架**: PyTorch
  - **服务器**: Uvicorn
  - **异步通信**: WebSockets

- **前端**:
  - (从后端代码推断) 基于现代 JavaScript 框架（如 Vue.js 或 React）构建的单页应用 (SPA)。

## 🚀 快速开始

### 1. 环境准备

- Python 3.8 或更高版本
- `ffmpeg` 已安装并配置在系统 PATH 中。
- (可选, 推荐) NVIDIA 显卡及对应的 CUDA Toolkit。

### 2. 安装依赖

克隆本仓库，然后安装所需的 Python 包：

```bash
git clone https://github.com/your-repo/REATK-Web.git
cd REATK-Web
pip install -r requirements.txt
```

### 3. 下载模型

程序首次运行时会自动在项目根目录下创建 `models` 文件夹用于存放模型。你可以通过 Web 界面的 "模型管理" 页面来下载所需的 Whisper 模型。

### 4. 运行程序

直接运行 `main.py` 即可启动 Web 服务：

```bash
python main.py
```

程序启动后，会自动在默认浏览器中打开 `http://127.0.0.1:18632`。

### 5. 使用

1.  在 Web 界面上传你的音频文件（如 MP3, WAV）。
2.  上传或直接粘贴歌词文本。
3.  在 "设置" 页面调整模型、语言等参数。
4.  点击 "开始" 按钮，等待任务完成。
5.  在结果区域预览生成的 LRC 歌词，并下载文件。

## 📝 API 概览

应用后端提供了一套 RESTful API，前端通过这些 API 与后端进行交互。API 文档由 FastAPI 自动生成，启动服务后可访问 `http://127.0.0.1:18632/docs` 查看。

主要 API 端点包括：

- `/api/config`: 获取和更新应用配置。
- `/api/file`: 处理文件上传（音频、歌词）和下载（LRC）。
- `/api/model`: 列出、下载、删除 AI 模型。
- `/api/task`: 启动和停止歌词生成任务。
- `/api/audio/{file_id}`: 提供音频流，支持 HTTP Range 请求以实现拖动播放。
- `/ws/task`: WebSocket 端点，用于广播任务进度。
- `/ws/model`: WebSocket 端点，用于广播模型下载进度。

## 📄 许可证

本项目基于 [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html) 授权。
