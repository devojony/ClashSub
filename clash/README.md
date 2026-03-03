# Clash 订阅文件说明

## 文件说明

### 1. subs.yaml
完整的 Clash 配置文件，包含：
- DNS 配置
- 代理规则
- 代理组
- Proxy Providers
- 直接代理节点（来自 v2ray 订阅）

**用途**: 直接作为 Clash/Mihomo 的配置文件使用

### 2. proxies.yaml
仅包含代理节点的文件，格式：
```yaml
proxies:
  - name: xxx
    type: vmess
    ...
```

**用途**: 作为 Proxy Provider 被其他配置引用

## 使用方法

### 方式一：直接使用完整配置
```bash
mihomo -f subs.yaml
```

### 方式二：作为 Provider 引用

在你的 Clash 配置中添加：

```yaml
proxy-providers:
  my-subs:
    type: http
    url: https://your-domain.com/clash/proxies.yaml
    interval: 3600
    health-check:
      enable: true
      interval: 600
      url: http://www.gstatic.com/generate_204

proxy-groups:
  - name: 节点选择
    type: select
    use:
      - my-subs
    # 或使用 include-all-providers: true
```

如果使用本地文件：
```yaml
proxy-providers:
  my-subs:
    type: file
    path: ./proxies.yaml  # 相对于配置目录
    health-check:
      enable: true
      interval: 600
      url: http://www.gstatic.com/generate_204
```

## 节点来源

- **Proxy Providers**: 从机场订阅获取的节点
- **V2Ray 订阅**: 从公开 v2ray 订阅转换的节点

## 更新频率

建议每天运行一次 `python convert.py` 更新订阅。
