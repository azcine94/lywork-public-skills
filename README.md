# LYWork Public Skills

LYWork 随安装包提供、并可通过 GitHub Releases 持续更新的公共 Skill 仓库。

## 当前包含

| Skill | 用途 |
| --- | --- |
| `az-extract-frame-img` | 按用户点名提取首帧、尾帧或具体帧号，并按需生成参考图与 Seedance 工作流提示词 |
| `lywork-document-reader` | 读取与分析本地 PDF、DOCX、XLSX、PPTX |
| `image-context-orchestrator` | 连续图片生成与编辑时的上下文编排 |
| `imagegen` | 识别图片生成/编辑意图并调用 LYWork 图片工具 |
| `quill-image-prompt-director-pro` | 专业图片提示词生成与修改 |
| `lywork-video-director` | 视频创作与导演工作流 |
| `image-multi-angle-prompter` | 多角度机位图片提示词 |

`0.6.7` 移除 `chinese-thinking`，保留以上 7 个公共 Skill。内部 `lywork-canvas-director`
不进入公共包。保留本仓库已发布的指定帧抽取修复，并同步 LYWork 随包的其他最新内容。

## 安装约定

Release 中的 `lywork-public-skills.zip` 解压后，应将内容原子替换到：

```text
~/.pi/agent/public-skills
```

该目录由 LYWork 管理。用户自己的 Skill 应放在：

```text
~/.pi/agent/skills
```

更新公共 Skill 时不得删除或覆盖个人 Skill 目录。若个人目录存在同名 Skill，LYWork 应以个人版本优先，并提示公共版本被覆盖。

## 仓库结构

```text
skills/                 # 发布到用户机器的 Skill
manifest.json           # 包版本和 Skill 清单
scripts/build-release.mjs
.github/workflows/release.yml
```

`az-extract-frame-img` 依赖 Python、FFmpeg 和 FFprobe。图片相关 Skill 依赖 LYWork 提供的 `ly_image` 工具。

## 发布新版本

日常可以直接在本仓库的 `skills/<skill-name>/` 新增、修改或删除公共 Skill，
同步维护 `manifest.json` 的完整清单并提升包版本。删除时同时移除目录和清单条目。
公共包可以独立发布，不需要等待 LYWork 应用发版；客户端检查更新后会应用新内容。

公共包发布后，将清单中的完整目录集合及版本同步回 LYWork 仓库的
`resources/builtin-skills/` 和 `.lywork-public-skills.json`，供下一次应用发版使用。
同步前比较两边文件和提交历史，保留两边独立修复；不能仅凭包版本号判断内容新旧，
也不能把单个 Skill 当作完整更新包发布。内部 `lywork-canvas-director` 不参与公共同步。

如果 Skill 依赖尚未发布的应用工具或协议，需要等待支持它的应用版本，或先提供兼容处理。
退役 Skill 的旧目录迁移修复属于应用代码，公共包本身无法更新主进程。
应用侧验证和迁移细节见 LYWork 仓库 `docs/public-skills-maintenance.md`。

1. 修改或新增 `skills/<skill-name>/`。
2. 同步更新 `manifest.json` 中的版本与 Skill 清单。
3. 本地运行校验：

   ```text
   node scripts/build-release.mjs vX.Y.Z --validate-only
   ```

4. 提交后创建与清单版本一致的标签，例如 `v0.1.0`。
5. GitHub Actions 自动生成 Release，并附加：
   - `lywork-public-skills.zip`
   - `lywork-public-skills.zip.sha256`
   - `release-manifest.json`

客户端只需检查最新 Release 的版本。版本未变化时不下载；发现新版本后校验 SHA-256，并通过临时目录和原子替换完成更新。
