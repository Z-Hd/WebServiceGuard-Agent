---
id: demo-service-owner
service: demo-service
services:
  - demo-service
  - demo-web-service
display_name: wmlu
language: zh-CN
tone: lively
verbosity: short
opening_style: direct-friendly
emoji_level: medium
format_preferences:
  - summary-first
  - root-cause
  - files-changed
  - verification
  - pr-link
preferred_sections:
  - greeting
  - conclusion
  - root-cause
  - files-changed
  - verification
  - action-item
  - pr-link
action_style: explicit
avoid:
  - vague-language
  - excessive-apology
---

通知偏好：
先给出修复结论，再说明错误根因、修改的文件、验证结果和 PR 链接。

措辞可以稍微活泼一点，但仍然要清楚、直接、可靠。
通知要像发给 wmlu 本人，不要写成群发公告口吻。
如果需要开发者进一步处理，请明确写出下一步动作。
