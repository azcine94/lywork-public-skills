---
name: image-context-orchestrator
description: 连续图片会话的前置路由 Skill。只要当前请求或最近上下文涉及图片提示词、参考图、已生成图片、出图或改图，并且需要判断本轮应输出文字提示词还是实际图片，就必须先使用本 Skill，再决定是否调用 imagegen。尤其当上一轮由任意提示词、摄影、设计或其他主要 Skill 输出了文字，用户下一轮只说“猫不要”“去掉耳环”“换成笑脸”等内容变化而没有明确要求出图或直接编辑图片时，必须继续修改提示词，不得直接调用 imagegen。只有用户明确要求实际出图或直接编辑当前图片时才转交 imagegen。负责维护输出模式、主要 Skill、原始参考图和活动图片，并使用 PiDeck 注入的 sessionId 与 assetId；适用于所有主要 Skill，不绑定 Quill，不用于与图片无关的任务。
---

# 图片上下文编排

在连续图片工作流中先判断“本轮交付文字还是图片”以及“哪些图片扮演什么角色”，再把任务交给当前主要提示词 Skill 或 `imagegen` 工作流。不要绑定任何特定提示词 Skill。

## 职责边界

- 把本 Skill 作为会话编排层，不要替代当前主要提示词 Skill 的专业规则。
- 在 `prompt_only` 模式下，让当前主要提示词 Skill 生成或修改完整提示词；不要调用 `ly_image`。
- 在 `render_image` 模式下，应用 `imagegen` 规则并调用 `ly_image`；不要仅输出一段提示词冒充已经出图。
- 把一次 `ly_image` 调用视为一次性的执行步骤。出图完成后结束本轮 imagegen 子流程，不要让 imagegen 自动接管后续普通反馈。
- 不要要求用户提供应用没有暴露的本地路径，不要猜测路径，不要从缩略图、文件名或消息顺序编造图片引用。

## 每轮维护的工作状态

结合当前请求、会话历史、宿主图片上下文和工具结果，在内部维护：

- `output_mode`：本轮为 `prompt_only` 或 `render_image`。
- `primary_skill`：当前负责提示词、摄影、设计或其他文字产出的主要 Skill；它可能随用户显式引用而变化。
- `source_image`：本轮创作链路最初采用的原始图片资产，使用稳定 `assetId` 表示。
- `active_image`：最近一次成功生成、编辑，或被用户明确指定继续修改的图片资产，使用稳定 `assetId` 表示。

不要向用户机械输出这份状态，除非用户要求查看判断过程。

按以下优先级更新状态：

1. 用户当前轮的明确指令。
2. 宿主随新图片注入的 `<ly-image-context>`；结构化界面选项由宿主在工具执行时应用，不进入对话正文。
3. 最近一次 `ly_image` 结果中的 `assetId`、`parentAssetId` 和任务类型。
4. 当前主要 Skill、最近相关对话和图片语义。

新上传的第一批相关图片可以建立 `source_image`，但不要因为后来出现了生成图就覆盖它。每次成功生成或编辑的新资源更新 `active_image`，同时保留 `source_image`。

## 判断本轮输出模式

### 选择 `prompt_only`

用户明确要求以下结果时，只交付文字：

- 出提示词、只要提示词、不要出图。
- 编写、改写、优化、翻译或分析图片提示词。
- 要求当前主要 Skill 修改上一版文字方案。
- 询问“你会怎么做”“如果这样改会怎样”等解释性或假设性问题。

在提示词链路中，用户只描述内容变化但没有明确要求操作实际图片时，继续 `prompt_only`。例如主要提示词 Skill 刚输出提示词，之后即使执行过一次出图，用户只说“猫不要”“耳环去掉”，也先修改并返回完整提示词，不要自动再次出图。

### 选择 `render_image`

只有用户当前轮明确需要实际图片时，进入图片执行：

- 出图、生成图片、直接做图、开始渲染。
- 使用刚才的提示词生成图片。
- 明确要求直接修改、编辑当前图片。
- 明确指向实际图片，例如“直接把刚生成的这张图改掉”“继续编辑当前版本”。

`render_image` 是本轮执行授权，不是永久粘连状态。成功出图后，下一轮普通内容反馈不自动触发 `ly_image`；只有新的明确出图或直接改图意图才能再次进入图片执行。

如果语义确实无法判断，而且误判会触发实际出图，先简短确认，不要默认调用付费或耗时的图片工具。

## 选择图片资产

### 回到原始创作起点

用户表达以下意图时选择 `source_image`：

- 根据最开始的图片重新生成。
- 还是以原图为准。
- 从第一张重新做。
- 恢复原始人物、构图或其他初始特征。

不要把“第一张图片”机械解释为会话中时间最早的所有图片；选择当前创作链路的原始相关资产。

### 继续修改当前结果

用户明确要求编辑已经生成的当前结果时选择 `active_image`：

- 直接修改刚才生成的图片。
- 继续编辑当前版本。
- 把这张图的背景、服装或表情改掉。

把 `active_image` 设为唯一 `edit-target`。不要自动回到 `source_image`。

### 仅作为参考

只借鉴身份、风格或构图时，不要设为编辑目标。根据语义选择：

- `character`：人物或主体身份参考。
- `style`：风格、材质、色彩或灯光参考。
- `composition`：构图、布局或镜头参考。

一次编辑必须且只能有一个 `edit-target`。其他图片只能使用参考角色。

## 使用 PiDeck 图片资产协议

优先读取宿主提供的：

```xml
<ly-image-context precedence="host">
{"sessionId":"...","references":[{"slot":1,"assetId":"...","source":"upload"}]}
</ly-image-context>
```

遵守以下规则：

- 原样传递 `sessionId`，不要改写或另造会话 ID。
- 使用清单中的 `assetId` 作为 `ly_image.references` 输入。
- 保留 `slot` 对应的用户从左到右图片顺序，再根据可见图片和完整语义分配角色。
- 有 `assetId` 时不要改用本地路径、Base64 或临时远程 URL。
- 不要因为当前宿主清单只显示最新活动图片，就丢失会话历史中已经确定的 `source_image`；需要回到原图时使用此前记录的同会话 `assetId`。
- 只有宿主或用户明确提供了可用 URL 且没有 `assetId` 时，才考虑 URL 引用；绝不虚构 URL。

本地路径属于图片工具的输出展示信息，不属于输入引用协议。不要把一个猜测的 `referenced_image_paths` 或 `localPath` 传给 `ly_image`。

## 构造 `ly_image` 请求

### 纯文本生成新图

使用：

```json
{
  "taskType": "generate",
  "references": []
}
```

实际调用时省略 `references` 字段，不要附带历史图片。

### 根据参考图生成新图

使用：

```json
{
  "taskType": "reference-generate",
  "sessionId": "<宿主提供的 sessionId>",
  "references": [
    {"assetId": "<已有 assetId>", "role": "character"}
  ]
}
```

根据真实目的把角色改为 `style` 或 `composition`，不要默认全部设为同一种角色。

### 编辑现有图片

使用：

```json
{
  "taskType": "edit",
  "sessionId": "<宿主提供的 sessionId>",
  "references": [
    {"assetId": "<active_image assetId>", "role": "edit-target"}
  ]
}
```

需要额外参考图时追加 `character`、`style` 或 `composition`，但始终只保留一个 `edit-target`。

## 模型和参数

- 结构化界面选项由宿主在 `ly_image` 真正执行时注入并覆盖推断值，不会出现在对话正文。
- 不要向用户索要或猜测 `providerId`、`model`、`sessionId`；调用工具时可以省略这些宿主管理字段。
- 界面字段为 `Auto` 或省略时，交给已发布模型默认值或 Provider 默认值，不要伪造显式值。
- 把用户在自然语言中明确提出的比例、分辨率、数量、格式和模型专属参数放入结构化字段；宿主显式界面值仍具有更高优先级。

## 处理图片工具结果

`ly_image` 成功后：

1. 把返回的新 `assetId` 设为 `active_image`。
2. 编辑任务保留返回的 `parentAssetId` 血缘，不覆盖输入资产。
3. 使用工具返回的真实 `localPath` 展示结果。
4. 不把 Base64 正文写入回复或后续提示。
5. 不使用 APIMart 临时 URL 作为最终图片。
6. 结束本轮 imagegen 子流程，等待用户下一轮决定修改提示词、直接改图或再次出图。

工具失败时保留原有 `source_image` 和 `active_image`，报告真实错误；不要假装生成成功，也不要用另一个未获授权的图片模型静默重试。

## 典型连续链路

```text
主要 Skill 输出第一版提示词
→ 用户明确“出图”
→ imagegen + ly_image 生成图片，结果成为 active_image
→ 用户只说“猫不要”
→ 回到主要 Skill，输出去掉猫的完整提示词
→ 用户再次明确“出图”
→ 使用新提示词再次生成，结果更新 active_image
```

如果用户改为“直接把刚才生成的图片里的猫删掉”，则进入 `render_image`，使用当前 `active_image` 作为唯一 `edit-target`。
