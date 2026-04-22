# Grok2API Windows 管理助手 (一键刷新 Cookie & 维护工具)

本工具专为 [grok2api](https://github.com/chenyme/grok2api) 用户设计，解决 Cloudflare 403 报错问题，并提供一键更新和备份功能。

---

## 📖 为什么需要这个工具？

Grok.com 使用了 Cloudflare 高级防护。当你使用 WARP 代理时，必须保证你浏览器获取 Cookie 时的 IP 和服务器请求时的 IP **完全一致**。

本工具通过 SSH 隧道技术，让你的本地 Chrome 浏览器“伪装”成服务器的 IP 去访问 Grok，从而获取 100% 兼容的有效 Cookie。

---

## 🚀 快速上手 (小白必看)

### 第一步：准备环境
1. **安装 Python**:
   - 前往 [Python 官网](https://www.python.org/downloads/) 下载并安装。
   - **非常重要**: 安装时一定要勾选 **"Add Python to PATH"** (如下图所示)。
     ![安装示意图](https://www.python.org/static/community_logos/python-logo.png)
2. **安装 Chrome**: 确保电脑上安装了谷歌浏览器 (Google Chrome)。

### 第二步：下载与配置
1. 点击 GitHub 页面右上角的 `Code` -> `Download ZIP` 下载并解压。
2. 在文件夹里找到 `config.env.example` 文件，将其重命名为 **`config.env`**。
3. 右键点击 `config.env`，选择“记事本”打开，填写你的信息：
   ```env
   # 服务器 IP 地址
   SERVER_HOST=1.2.3.4
   # SSH 端口 (默认是 22，如果是搬瓦工或其他可能不同)
   SERVER_PORT=22
   # SSH 用户名 (通常是 root)
   SERVER_USER=root
   # SSH 密码
   SERVER_PASS=你的服务器密码
   ```

### 第三步：运行
1. 双击 **`一键刷新Cookie.bat`**。
2. 第一次运行会自动安装必要的插件，请耐心等待。
3. 弹出菜单后，输入数字 `1` 并回车，脚本会自动打开 Chrome 帮你获取 Cookie。
4. **看到 "✅ Cookie 刷新成功"** 即可关闭，你的 API 现在满血复活了！

---

## 🛠️ 功能介绍

| 功能编号 | 名称 | 详细说明 |
| :--- | :--- | :--- |
| **1** | **刷新 Cookie** | **最常用功能**。当 API 报 403 错误时使用。自动同步 IP 并获取新 Cookie，重启容器。 |
| **2** | **检查更新** | 自动检查作者是否有新版镜像。如果有，会自动备份你的配置并安全更新，防止更新后配置丢失。 |
| **3** | **备份管理** | 手动备份当前的 `config.toml`。如果配置改乱了，可以随时一键还原到之前的版本。 |
| **4** | **状态查看** | 快速看一眼服务器：容器在不在跑？WARP 现在是什么 IP？内存还剩多少？ |

---

## ❓ 常见问题

**Q: 运行脚本时 Chrome 为什么会被关闭？**
A: 脚本需要独占模式启动 Chrome 来提取加密的 Cookie，所以必须先关闭正在运行的实例。建议运行脚本前保存好网页内容。

**Q: 提示 "Authentication failed" 怎么办？**
A: 请检查 `config.env` 里的密码和端口是否填写正确。

**Q: 获取 Cookie 成功但还是 403？**
A: 请确保你的服务器 `docker-compose.yml` 里的 `grok2api` 容器是通过 `network_mode: "service:warp"` 运行的。

---

## 📜 免责声明
本工具仅供学习交流使用，请勿用于任何非法用途。

---

## ☕ 喝杯咖啡

如果你觉得这个工具有帮到你，可以请作者喝杯咖啡支持一下，你的支持是我更新的最大动力！

<img src="coffee_qr.jpg" width="250" alt="微信打赏二维码">

---

## 📈 Star 趋势

[![Star History Chart](https://api.star-history.com/svg?repos=mjj0001/grok2api-cookie-refresher&type=Date)](https://star-history.com/#mjj0001/grok2api-cookie-refresher&Date)

---
*喜欢的话给个 Star ⭐ 吧！*
