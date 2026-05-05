# Prompt 模板安全隔离机制

## 概述

本文档描述了 AIFriends 项目中实施的 Prompt 模板安全隔离机制，用于防止 Prompt 注入攻击，确保用户输入不会被误认为系统指令。

## 风险背景

### 原有实现的风险

原有实现直接将用户输入拼接到系统提示词中：

```python
# 危险的直接拼接
prompt = f'\n【角色性格】\n{friend.character.profile}\n'
prompt += f'【长期记忆】\n{friend.memory}\n'
```

这种做法存在以下安全风险：
1. **Prompt 注入**：用户输入可能包含 `IGNORE PREVIOUS INSTRUCTIONS` 等指令
2. **指令混淆**：用户输入可能被误认为是系统指令
3. **系统控制**：恶意用户可能尝试控制 AI 的行为

## 安全解决方案

### 1. 架构设计

#### 1.1 数据/指令分离

```
系统提示词 = 固定指令部分 + 结构化数据部分
```

- **固定指令部分**：存储在 SystemPrompt 表中的系统指令
- **结构化数据部分**：经过验证和转义的用户数据

#### 1.2 模板引擎

使用模板语法替代字符串拼接：

```python
# 模板格式
template = """你是一个 AI 助手。
【角色性格】
{{character_profile}}

【长期记忆】
{{memory}}

请根据以上信息回答用户的问题。"""

# 渲染后
rendered = engine.render_template(template, context)
```

### 2. 核心组件

#### 2.1 PromptTemplateEngine

安全模板渲染引擎，提供以下功能：

- **上下文验证**：只允许预定义的字段
- **危险模式检测**：识别潜在的注入攻击
- **HTML 转义**：防止 XSS 攻击
- **安全转义**：对特殊字符进行编码

```python
from web.utils.prompt_template import PromptTemplateEngine

# 验证上下文数据
context = {
    'character_profile': 'AI 助手',
    'memory': '用户的历史记忆',
    'user_message': '用户当前消息'
}

# 安全渲染
rendered = PromptTemplateEngine.render_template(template, context)
```

#### 2.2 PromptTemplateManager

模板管理器，提供预定义的创建方法：

```python
from web.utils.prompt_template import PromptTemplateManager

# 创建系统提示词
prompt_data = PromptTemplateManager.create_system_prompt(friend, user_message)

# 创建记忆更新提示词
memory_prompt = PromptTemplateManager.create_memory_update_prompt(friend)
```

### 3. 实现细节

#### 3.1 危险模式检测

系统自动检测以下危险模式：

```python
DANGEROUS_PATTERNS = [
    r'IGNORE\s+PREVIOUS\s+INSTRUCTIONS',
    r'DISREGARD\s+ALL\s+PRIOR\s+COMMANDS',
    r'OVERRIDE\s+SYSTEM\s+PROMPT',
    r'SET\s+SYSTEM\s+ROLE\s+TO',
    r'YOU\s+ARE\s+NOW',
    r'PROMPT\s+INJECTION',
    # ... 更多模式
]
```

#### 3.2 字段白名单

只允许以下字段出现在上下文中：

```python
ALLOWED_CONTEXT_FIELDS = {
    'character_profile',    # 角色性格
    'memory',               # 长期记忆
    'recent_messages',      # 最近消息
    'user_message',        # 用户消息
    'image_analysis',       # 图片分析
}
```

#### 3.3 转义规则

- **HTML 转义**：`<` → `&lt;`，`>` → `&gt;`
- **特殊字符**：`{` → `&#123;`，`}` → `&#125;`
- **长度限制**：单个字段最大 10000 字符

### 4. 使用示例

#### 4.1 基础用法

```python
# 定义模板
template = """你是一个 {{character_role}}。
你的长期记忆：
{{memory}}

用户说：{{user_message}}
请根据你的角色和记忆回答。"""

# 准备上下文
context = {
    'character_role': '专业心理咨询师',
    'memory': '用户有焦虑倾向',
    'user_message': '我最近总是睡不着'
}

# 渲染
result = PromptTemplateEngine.render_template(template, context)
```

#### 4.2 多模态支持

```python
# 支持图片分析
template = """角色信息：
{{character_profile}}

长期记忆：
{{memory}}

图片分析结果：
{{image_analysis}}

用户问题：{{user_message}}
"""

context = {
    'character_profile': 'AI 助手',
    'memory': '对话历史',
    'image_analysis': '这是一张风景照',
    'user_message': '这是什么地方？'
}
```

### 5. 安全检查清单

#### 5.1 开发阶段

- [ ] 使用模板引擎替代字符串拼接
- [ ] 验证所有上下文字段
- [ ] 检查输出结果是否包含未替换的占位符
- [ ] 测试包含特殊字符的输入

#### 5.2 测试阶段

- [ ] Prompt 注入测试
- [ ] 越权访问测试
- [ ] 长度限制测试
- [ ] 特殊字符测试

#### 5.3 部署阶段

- [ ] 启用安全日志
- [ ] 监控异常模式
- [ ] 定期更新危险模式列表
- [ ] 审计模板使用

### 6. 配置选项

#### 6.1 SystemPrompt 模型增强

新增字段：
- `is_template`：是否使用模板格式
- `template_version`：模板版本控制

```python
# 迁移后创建新的系统提示词
SystemPrompt.objects.create(
    title='回复',
    is_template=True,  # 启用模板模式
    template_version='v3',  # 使用高级模板
    prompt='''你是一个 {{character_role}}。
【角色性格】
{{character_profile}}

【长期记忆】
{{memory}}
'''
)
```

#### 6.2 性能考虑

- 模板渲染在内存中进行，无额外 I/O 开销
- 危险模式使用正则表达式，性能影响最小
- 缓存常用模板以提高性能

### 7. 故障排查

#### 7.1 常见错误

```python
# 错误：包含未定义的字段
ValidationError: 不允许的上下文字段: undefined_field

# 解决：检查 ALLOWED_CONTEXT_FIELDS

# 错误：包含危险模式
ValidationError: 字段 'memory' 包含潜在的危险模式

# 解决：清理输入内容
```

#### 7.2 调试模式

启用调试日志：

```python
import logging
logging.getLogger('web.utils.prompt_template').setLevel(logging.DEBUG)
```

### 8. 最佳实践

1. **永远不要**直接拼接用户输入到系统提示词
2. **总是使用**模板引擎的验证功能
3. **定期更新**危险模式列表
4. **监控异常**的模板使用行为
5. **测试边界**情况（超长输入、特殊字符等）

## 总结

通过实施模板隔离机制，我们成功防止了 Prompt 注入攻击，同时保持了系统的灵活性和功能性。这个方案：

- **安全性**：多层防护，防止各种注入攻击
- **灵活性**：支持复杂的模板和变量替换
- **可维护性**：清晰的架构和完善的文档
- **可扩展性**：易于添加新的安全规则和模板功能

建议在生产环境中启用所有安全功能，并定期进行安全审计。

---
**文档版本**: 1.0  
**更新日期**: 2026-04-20  
**作者**: Claude Code Assistant