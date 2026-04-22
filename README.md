# Grok2API 管理工具

一键管理 [grok2api](https://github.com/chenyme/grok2api) 服务的 Windows 工具。

## 功能

| 功能 | 说明 |
|------|------|
| 🍪 刷新 Cookie | 自动通过 WARP 代理获取 cf_clearance 并更新服务器 |
| 🔄 检查更新 | 检测新版本 → 备份配置 → 拉取镜像 → 对比差异 |
| 💾 备份管理 | 创建/查看/对比/还原 config.toml 备份 |
| 📊 状态查看 | 一键查看容器状态、WARP IP、内存等 |

## 前置要求

- Windows 系统
- Python 3.8+
- Google Chrome 浏览器
- 服务器已部署 grok2api + WARP（Docker Compose）

## 使用方法

1. 下载本项目
2. 复制 `config.env.example` 为 `config.env`，填入你的服务器信息
3. 双击 `一键刷新Cookie.bat` 运行

## 配置文件

```env
# config.env
SERVER_HOST=你的服务器IP
SERVER_PORT=SSH端口
SERVER_USER=root
SERVER_PASS=你的密码
```

> ⚠️ `config.env` 包含敏感信息，已被 `.gitignore` 排除，不会上传到 GitHub。

## 原理

grok2api 访问 grok.com 需要通过 Cloudflare 验证。本工具通过 SSH 隧道将服务器的 WARP 代理转发到本地，用 Chrome 走相同 IP 访问 grok.com 获取 cf_clearance Cookie，确保 Cookie 绑定的 IP 与服务器请求 IP 一致。
