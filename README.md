# Volc Proxy

Anthropic 协议兼容的火山引擎 API 本地转发代理。

## 功能

- 将 Anthropic 协议请求转换为火山引擎（OpenAI-compatible）格式
- 本地模型名统一为 `opus-4.7`，实际模型可自由选择
- 支持流式和非流式响应
- 支持运行时切换实际模型
- Thinking 模式切换（auto / enabled / disabled）
- Health check + Token 计数端点（兼容 Claude Code 探测）
- Web Dashboard 监控台（请求历史、统计、模型切换）
- 模型列表从火山引擎 API 动态获取

## 快速开始

```bash
git clone https://github.com/kaisonlau8/volc-proxy.git
cd volc-proxy
pip3 install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的火山引擎 API Key

# 创建日志目录
mkdir -p logs

python3 main.py
```

默认监听 `http://localhost:8000`。

## Docker 部署

```bash
# 构建镜像
docker build -t volc-proxy .

# 运行（通过环境变量传配置）
docker run -d --name volc-proxy \
  -p 8000:8000 \
  -e ARK_API_KEY=你的火山引擎API_KEY \
  volc-proxy

# 自定义端口和模型
docker run -d --name volc-proxy \
  -p 9000:9000 \
  -e ARK_API_KEY=xxx \
  -e ARK_PROXY_PORT=9000 \
  -e ARK_REAL_MODEL=doubao-seed-2-0-pro-260215 \
  volc-proxy

# 查看日志
docker logs -f volc-proxy

# 停止 / 重启
docker stop volc-proxy
docker restart volc-proxy

# 删除
docker rm -f volc-proxy
```

`.env` 文件不会打包进镜像，所有配置通过 `-e` 环境变量传入。

## 配置

通过 `.env` 文件配置（优先级：`.env` < 环境变量）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ARK_API_KEY` | （必填） | 火山引擎 API Key |
| `ARK_BASE_URL` | `https://ark.cn-beijing.volces.com/api/coding` | 火山引擎 API 地址 |
| `ARK_REAL_MODEL` | `glm-5.1` | `opus-4.7` 映射的实际模型 ID |
| `ARK_PROXY_PORT` | `8000` | 本地监听端口 |
| `ARK_THINKING_MODE` | `auto` | Thinking 模式：auto/enabled/disabled |

## 开机自启（macOS launchd）

```bash
# 1. 复制模板，修改路径
cp com.volc.proxy.plist.example ~/Library/LaunchAgents/com.volc.proxy.plist
# 编辑 plist，将 /path/to/volc-proxy 替换为实际路径，将 /usr/bin/python3 替换为实际 Python 路径

# 2. 安装服务（.env 文件会被自动加载）
launchctl load ~/Library/LaunchAgents/com.volc.proxy.plist

# 3. 验证
curl http://localhost:8000/
```

### 服务管理

```bash
# 查看状态
launchctl list | grep volc.proxy

# 停止
launchctl unload ~/Library/LaunchAgents/com.volc.proxy.plist

# 重启
launchctl unload ~/Library/LaunchAgents/com.volc.proxy.plist
launchctl load ~/Library/LaunchAgents/com.volc.proxy.plist

# 卸载
launchctl unload ~/Library/LaunchAgents/com.volc.proxy.plist
rm ~/Library/LaunchAgents/com.volc.proxy.plist

# 查看日志
tail -f logs/stderr.log   # 请求摘要 + 响应摘要
tail -f logs/stdout.log   # HTTP access log
```

## API 端点

### Anthropic 兼容端点

| 端点 | 说明 |
|------|------|
| `GET /` | Health check（`HEAD /` 也支持） |
| `GET /v1/models` | 返回模型列表（仅显示 `opus-4.7`） |
| `POST /v1/messages` | 核心消息端点，支持 `stream` 参数 |
| `POST /v1/messages/count_tokens` | Token 计数（近似值，兼容 Claude Code 探测） |

### Dashboard

| 端点 | 说明 |
|------|------|
| `GET /dashboard` | Web 监控台（浏览器打开 `http://localhost:8000/dashboard`） |
| `GET /_dashboard/api/stats` | Dashboard 数据 API |

Dashboard 功能：
- 实时统计：总请求数、错误数、输入/输出 token 数
- 模型映射 + 下拉选择切换模型（从火山引擎 API 动态获取）
- Thinking 模式切换按钮
- 最近 200 条请求历史（点击行弹出详情，完整 input/output）
- 自动 5 秒刷新

### 管理端点

| 端点 | 说明 |
|------|------|
| `POST /_admin/set_model` | 运行时切换模型映射 |
| `POST /_admin/set_thinking` | 运行时切换 thinking 模式 |
| `GET /_admin/models_map` | 查看当前映射和可用模型列表 |

### 切换模型

```bash
curl -X POST http://localhost:8000/_admin/set_model \
  -H "Content-Type: application/json" \
  -d '{"local_model":"opus-4.7","real_model":"doubao-seed-2-0-code-preview-260215"}'
```

### 切换 Thinking 模式

```bash
# 强制开启深度思考
curl -X POST http://localhost:8000/_admin/set_thinking \
  -H "Content-Type: application/json" \
  -d '{"mode":"enabled"}'

# 强制关闭（节省 token）
curl -X POST http://localhost:8000/_admin/set_thinking \
  -H "Content-Type: application/json" \
  -d '{"mode":"disabled"}'

# 跟随模型默认
curl -X POST http://localhost:8000/_admin/set_thinking \
  -H "Content-Type: application/json" \
  -d '{"mode":"auto"}'
```

## 在 Claude Code 中使用

```bash
export ANTHROPIC_BASE_URL=http://localhost:8000
export ANTHROPIC_API_KEY=sk-placeholder  # 代理不校验 key，随便填
```

## 项目结构

```
volc-proxy/
  main.py                      # FastAPI 服务入口
  config.py                    # 配置（从 .env 加载）
  converter.py                 # Anthropic ↔ OpenAI 协议转换
  Dockerfile                   # Docker 部署
  .dockerignore                # Docker 构建排除文件
  .env.example                 # 环境变量示例（不含 key）
  com.volc.proxy.plist.example # macOS launchd 配置示例
  .gitignore
  requirements.txt
  README.md
```

## Thinking 模式说明

这些模型均为 1M 上下文，thinking 不限制 token 数：

| 模型 | 默认 Thinking | 可切换 |
|------|--------------|--------|
| Doubao-Seed-2.0-Code | non-thinking | 可开启 |
| Doubao-Seed-2.0-pro | thinking | 可关闭 |
| Doubao-Seed-2.0-lite | thinking | 可关闭 |
| Doubao-Seed-Code | non-thinking | 可开启 |
| GLM-5.1 | thinking | 可关闭 |
| MiniMax-M2.7 | thinking | 可关闭 |
| Kimi-K2.6 | thinking | 可关闭 |
| MiniMax-M2.5 | thinking | 可关闭 |
| Kimi-K2.5 | non-thinking | 可开启 |
| GLM-4.7 | non-thinking | 可开启 |