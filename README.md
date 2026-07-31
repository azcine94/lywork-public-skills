# LYWork Public Skills

LYWork/PiDeck 随安装包提供、并可通过 GitHub Releases 持续更新的公共 Skill 仓库。

## 当前包含

| Skill | 用途 |
| --- | --- |
| `az-extract-frame-img` | 提取视频首尾帧并生成图片、Seedance 工作流提示词 |
| `chinese-thinking` | 中文思考和中文输出约束 |
| `image-context-orchestrator` | 连续图片生成与编辑时的上下文编排 |
| `imagegen` | 识别图片生成/编辑意图并调用 LYWork 图片工具 |
| `quill-image-prompt-director-pro` | 专业图片提示词生成与修改 |

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
