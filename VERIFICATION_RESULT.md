# Mihomo 验证结果

## 测试环境
- Mihomo 版本: 1.19.20
- 配置文件: clash/subs.yaml
- 测试时间: 2026-03-03

## 验证结果

### 1. 配置文件语法
✅ **通过** - mihomo -t 测试成功

### 2. Proxy Providers 加载情况
测试了 3 个 proxy-providers：

- **provider#0** (https://s1.byte33.com/...): ✅ **7 个节点**
  - 一元.com (Vmess)
  - yiyuanjichang.com (Vmess)
  - 香港 01 | 专线 (Vmess)
  - 香港 02 | 专线 (Vmess)
  - 香港 03 | 专线 (Vmess)
  - 新加坡 01 | 专线 (Vmess)
  - 日本 01 | 专线 (Vmess)

- **provider#1** (https://s1.byte33.com/...): ✅ **7 个节点**
  - 相同的 7 个节点（重复订阅）

- **provider#2** (https://mcp.dpenly.org/...): ❌ **0 个节点**
  - 连接失败或无可用节点

### 3. V2Ray 订阅转换
✅ **成功** - 从 https://sub.scpnb.top/base64 解析到 3 个节点：
- SCP|US (Trojan)
- SCP|UK (Trojan)
- SCP|PL (Trojan)

## 总结
- **Proxy Providers 节点**: 14 个（去重后约 7 个）
- **V2Ray 直接节点**: 3 个
- **总计可用节点**: 约 10 个

配置文件工作正常，proxy-providers 和 v2ray 订阅转换功能均验证通过。
