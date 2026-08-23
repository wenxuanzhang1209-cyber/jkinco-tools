<p align="center">
  <a href="https://github.com/wenxuanzhang1209-cyber/jkinco-tools/actions/workflows/ci.yml"><img src="https://github.com/wenxuanzhang1209-cyber/jkinco-tools/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <img src="https://img.shields.io/github/license/wenxuanzhang1209-cyber/jkinco-tools?style=flat-square" alt="License" />
  <img src="https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/tests-9%20passing-3fb950?style=flat-square" alt="Tests" />
  <img src="https://img.shields.io/badge/dependencies-none-3fb950?style=flat-square" alt="No dependencies" />
</p>

# JKinco Tools

**Small automation scripts that verify their own work.**

<sub>轻量自动化脚本——每一步都自己校验结果。</sub>

---

## `import-upstream.py`

Mirrors a GitHub repository tree through the jsDelivr CDN, **verifying every blob against its
Git SHA-1 before writing it to disk.**

The verification is the point. Bulk-fetching thousands of files over a CDN produces occasional
truncated or stale responses, and a silently corrupted file in a mirrored tree is very hard to
notice later — it looks like a normal file until something downstream breaks in a confusing
way. So each blob is hashed with Git's own object format (`blob <size>\0<content>`) and
compared to the SHA the tree API reported. A mismatch is a failure, not a warning.

Last run: **6,407 files, zero failures** (`import-logs/`).

<sub>通过 jsDelivr CDN 镜像 GitHub 仓库树，**每个 blob 落盘前都用 Git 的 SHA-1 校验**。
校验才是重点：批量拉取上千个文件时，CDN 偶尔会给出截断或过期的响应，而镜像树里一个
静默损坏的文件极难被发现——它看起来就是个正常文件，直到下游以某种莫名其妙的方式出错。
最近一次运行：6407 个文件，零失败。</sub>

### Design notes

- **No third-party dependencies.** Standard library only — `urllib`, `hashlib`,
  `concurrent.futures`. A tool that mirrors code should not itself need a dependency tree.
- **Parallel with retry and jitter.** CDN rate limits are handled with backoff rather than by
  slowing everything down.
- **Failures are recorded, not swallowed.** `import-logs/import-failures.txt` exists so an
  empty file is a meaningful result.

### Usage

```bash
python3 import-upstream.py
```

Edit `OWNER` / `REPO` / `BRANCH` at the top of the file to point it somewhere else.

## Status

One script, 166 lines, CI on every push. Deliberately small — this repository is for tools
that are too small to deserve their own home but too useful to keep re-writing.

<sub>一个脚本，166 行，每次推送跑 CI。刻意保持小：这个仓库收的是那些
「小到不值得单独开仓库、又实用到不想每次重写」的工具。</sub>

## License

[MIT](LICENSE) © 2026 JKinco

---

<sub>
<b>JKinco</b> — local-first tools for work whose data cannot leave the building ·
<a href="https://github.com/wenxuanzhang1209-cyber/jkinco-listen-open">Listen</a> ·
<a href="https://github.com/wenxuanzhang1209-cyber/jkinco-slides">Slides</a> ·
<a href="https://github.com/wenxuanzhang1209-cyber/JKinco-Skills-Lab">Skills Lab</a> ·
<a href="https://github.com/wenxuanzhang1209-cyber/personal-life-hub">Life Hub</a> ·
<a href="https://github.com/wenxuanzhang1209-cyber/jkinco-tools">Tools</a>
</sub>
