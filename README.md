# lerobot-web-viz

`lerobot-web-viz` 是一个面向本地 LeRobot 数据集的 Web 可视化平台。后端使用 FastAPI 按需读取数据集帧并返回 JPEG，前端使用 React + Vite 实现多摄像头同步回放、时间轴拖动、播放控制以及 action/state/timestamp 曲线联动。

## 目录结构

```txt
lerobot-web-viz/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── dataset_loader.py
│   │   ├── frame_cache.py
│   │   ├── video_stream.py
│   │   ├── schemas.py
│   │   └── routers/
│   ├── requirements.txt
│   └── README.md
├── frontend/
│   ├── package.json
│   ├── index.html
│   ├── vite.config.js
│   └── src/
├── deploy/
│   ├── nginx.conf
│   ├── systemd-backend.service
│   └── docker-compose.yml
└── README.md
```

## 一键启动

开发或内网部署时可以直接使用根目录脚本：

```bash
cd lerobot-web-viz
./start.sh
```

打开前端后，可以在页面顶部输入服务器本地 LeRobot 数据集路径，也可以点击 `Browse` 浏览服务器允许范围内的目录，然后点击 `Load`。也可以启动时直接传入路径：

```bash
./start.sh /home/ghr/datasets/pullthedoor4/
```

可选环境变量：

```bash
BACKEND_PORT=8000 FRONTEND_PORT=5173 HOST=0.0.0.0 ./start.sh /path/to/dataset
```

## 安装依赖

后端：

```bash
cd lerobot-web-viz/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

前端：

```bash
cd lerobot-web-viz/frontend
npm install
```

## 指定 LeRobot 数据集路径

后端通过环境变量读取本地数据集：

```bash
export LEROBOT_DATASET_PATH=/path/to/dataset
```

如果本地目录名不是 LeRobot 的 repo id，可以额外指定：

```bash
export LEROBOT_REPO_ID=lerobot/pusht
```

## 启动后端

```bash
cd lerobot-web-viz/backend
export LEROBOT_DATASET_PATH=/path/to/dataset
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://localhost:8000/api/health
```

## 启动前端

开发模式：

```bash
cd lerobot-web-viz/frontend
npm run dev
```

浏览器访问：

```txt
http://localhost:5173
```

局域网访问时使用服务器 IP，例如 `http://192.168.1.10:5173`。

## 服务器目录选择

浏览器不能像 Windows 文件选择器一样直接打开服务器文件系统。`lerobot-web-viz` 的做法是由后端提供受限目录浏览接口，前端显示服务器目录列表。

默认可浏览范围来自 `LEROBOT_BROWSE_ROOTS`，没有设置时使用数据集路径、`/data`、`/home` 和服务当前目录中存在的目录。生产环境建议显式限制：

```bash
export LEROBOT_BROWSE_ROOTS=/data/lerobot:/mnt/datasets
./start.sh
```

多个根目录用冒号分隔。前端只能浏览这些根目录内部的子目录。

## API

主要接口：

```txt
GET /api/health
GET /api/dataset/info
POST /api/dataset/load
GET /api/dataset/browse
GET /api/episodes
GET /api/episodes/{episode_id}
GET /api/episodes/{episode_id}/frames/{frame_id}
GET /api/episodes/{episode_id}/frames/{frame_id}/{camera_name}?quality=80
GET /api/episodes/{episode_id}/actions
GET /api/episodes/{episode_id}/states
GET /api/episodes/{episode_id}/timestamps
GET /api/episodes/{episode_id}/warnings
GET /api/episodes/{episode_id}/videos
GET /api/episodes/{episode_id}/videos/file/{camera_name}
```

## 快速加载策略

`Load` 按钮只加载 LeRobot metadata，不会立即初始化完整 `LeRobotDataset` reader，也不会读取 action/state/timestamp 大表。因此页面会先显示 episode 列表和 mp4 视频。

action/state/timestamp/warnings 改为按需加载：进入 episode 后点击 `Load trajectories` 才会读取轨迹数据并绘制曲线。这样可以避免大数据集在初次加载时被 parquet 扫描拖慢。

## 原生 MP4 播放模式

优先使用 LeRobot 数据集中的 mp4 文件进行浏览器原生播放。即使多个 episode 被压缩在同一个 mp4 文件中，后端也会读取 metadata 中的 `videos/{camera}/from_timestamp` 和 `videos/{camera}/to_timestamp`，只播放当前 episode 对应的时间片段。

多摄像头同步由前端统一控制：第一个 camera 作为 master video，其它 camera 按相同 episode 相对时间 seek；如果漂移超过阈值，会自动校正。action/state/timestamp 曲线继续通过 JSON 接口读取，并和当前播放 frame 联动。

如果某个数据集没有可用 mp4，前端会退回 JPEG 帧接口。

## 回放优化

后端使用 LRU 缓存保存最近访问的 JPEG 帧，按需解码图像，避免一次性把大数据集载入内存。每次请求当前帧后，会在后台预加载后续少量帧，数量由 `LEROBOT_PRELOAD_FRAMES` 控制，默认 1，避免大 episode 播放时后台解码过载。

前端使用 `requestAnimationFrame` 控制播放节奏，并用 `Image` 对象预加载后续帧。播放时如果网络或解码没有跟上，播放器会按时间推进，允许短暂跳帧，避免主线程阻塞。

## Docker 部署

```bash
cd lerobot-web-viz/deploy
export LEROBOT_DATASET_PATH=/absolute/path/to/dataset
docker compose up
```

访问：

```txt
http://localhost:8080
```

说明：Compose 示例使用官方 Python/Node/Nginx 镜像，启动时安装依赖并构建前端。生产环境建议改成自定义镜像以缩短启动时间。

## Nginx 部署

`deploy/nginx.conf` 会让 Nginx 提供前端静态资源，并把 `/api` 反向代理到 FastAPI 后端。典型流程：

```bash
cd lerobot-web-viz/frontend
npm install
npm run build
sudo cp -r dist/* /usr/share/nginx/html/
sudo cp ../deploy/nginx.conf /etc/nginx/conf.d/lerobot-web-viz.conf
sudo nginx -t
sudo systemctl reload nginx
```

## systemd 后端服务

编辑 `deploy/systemd-backend.service`，修改：

- `WorkingDirectory`
- `LEROBOT_DATASET_PATH`
- `ExecStart`
- `User` 和 `Group`

安装并启动：

```bash
sudo cp deploy/systemd-backend.service /etc/systemd/system/lerobot-web-viz-backend.service
sudo systemctl daemon-reload
sudo systemctl enable --now lerobot-web-viz-backend
```

## 数据质量 warning

后端会检查：

- timestamp 是否存在异常间隔或倒退；
- action 是否存在突变；
- episode 是否过短；
- 图像字段是否缺失；
- 多摄像头同步所需字段是否可用。

## 如何扩展新的可视化指标

1. 在 `backend/app/dataset_loader.py` 中新增字段识别逻辑，例如 `reward`、`done` 或自定义传感器字段。
2. 在 `backend/app/schemas.py` 中增加响应模型。
3. 在 `backend/app/routers/episodes.py` 中增加 API 路由。
4. 在 `frontend/src/api/client.js` 中封装新接口。
5. 在 `frontend/src/components/` 中增加新的图表组件，并在 `App.jsx` 中加载数据。

## 常见问题

### 后端提示无法 import LeRobotDataset

确认后端环境已安装 `lerobot`，或者在本仓库开发环境中运行后端，并把 LeRobot 源码路径加入 `PYTHONPATH`。

### 数据集路径存在但加载失败

尝试设置 `LEROBOT_REPO_ID`。部分 LeRobot 本地数据集仍需要 repo id 和 root 组合才能正确初始化。

### 图像接口 404

确认 camera 名称来自 `/api/dataset/info` 的 `camera_keys`。如果 camera key 中包含特殊字符，前端会自动编码 URL。

### 播放不流畅

可以降低 JPEG 质量、增大 `LEROBOT_FRAME_CACHE_SIZE` 和 `LEROBOT_PRELOAD_FRAMES`，并确认浏览器和后端部署在同一局域网内。
No native file dialog available. Install zenity, kdialog, or use the server Browse button instead.# lerobot-web-viz
