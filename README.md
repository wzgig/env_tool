# env_tool

用于一键安装并检查常用 Python 库，支持控制台版和图形版 EXE。

## 0. 当前项目结构（已精简）

- env_manager.py：核心逻辑（安装+检查）
- env_tool_gui.py：图形界面入口
- build_exe.py：一键打包脚本
- README.md：使用说明
- .gitignore：忽略构建产物

## 1. 功能

- 按分组安装常用库（支持自定义只安装指定包）
- 安装后自动检查包可用性
- 支持输出 JSON 报告
- 支持打包成 EnvTool.exe（控制台）与 EnvToolGUI.exe（图形）

## 2. 本地直接运行（源码方式）

在项目根目录执行：

- 安装+检查（默认分组）：`python env_manager.py`
- 仅安装：`python env_manager.py --mode install`
- 仅检查：`python env_manager.py --mode check`
- 导出环境快照：`python env_manager.py --mode snapshot --snapshot-file requirements_snapshot.txt`
- 从快照恢复：`python env_manager.py --mode restore --snapshot-file requirements_snapshot.txt`
- 离线安装：`python env_manager.py --mode offline --wheel-dir D:\\wheels`
- 创建虚拟环境：`python env_manager.py --mode venv --venv-path .envtool_venv`
- 生成诊断报告：`python env_manager.py --mode diagnose --diag-output diagnostic_report.json`
- 检查更新：`python env_manager.py --mode update-check --repo-owner wzgig --repo-name env_tool`
- 指定包：`python env_manager.py --only numpy pandas`

## 3. 打包 EXE

在项目根目录执行：

`python build_exe.py`

可选参数：

- `python build_exe.py --target all`（默认，两个都打）
- `python build_exe.py --target console`（只打控制台版）
- `python build_exe.py --target gui`（只打图形版）

打包完成后输出文件：

- [dist/EnvTool.exe](dist/EnvTool.exe)
- [dist/EnvToolGUI.exe](dist/EnvToolGUI.exe)

## 4. 其他人如何使用 EXE

目标机器准备：

1. 安装 Python（建议 3.10+，3.10/3.11/3.12/3.13 均可）
2. 推荐双击运行 [dist/EnvToolGUI.exe](dist/EnvToolGUI.exe)
3. 如需命令行方式，运行 [dist/EnvTool.exe](dist/EnvTool.exe)

说明：

- 工具会自动探测可用 Python（`py -3`、`python`、常见安装目录），不要求与打包机同版本。
- 自动探测会先验证目标解释器能正常导入 `urllib.request` 和 `socket`；如果某个 Python 安装损坏或 DLL 冲突，它会被跳过。
- 若自动探测失败，可在 GUI 中手动选择 `python.exe`，或在命令行使用 `--python` 指定。
- 如果 `py -3` 指到了异常的 Python 安装，请直接显式指定目标解释器，或设置 `ENV_TOOL_RUNNER_PYTHON`。

推荐双击参数（防止窗口自动关闭）：

`EnvTool.exe --pause-on-exit`

如需指定目标解释器：

`EnvTool.exe --python C:\\Python313\\python.exe --pause-on-exit`

也可以设置环境变量：

`ENV_TOOL_PYTHON=C:\\Python313\\python.exe`

## 5. 常用参数

- `--mode all|install|check|snapshot|restore|offline|venv|diagnose|update-check`
- `--groups daily_common scientific_research`
- `--include-optional-ai`
- `--only numpy pandas scipy`
- `--skip-pip-upgrade`
- `--skip-installed`
- `--dry-run`
- `--json-report report.json`
- `--snapshot-file requirements_snapshot.txt`
- `--wheel-dir D:\\wheels`
- `--venv-path .envtool_venv`
- `--diag-output diagnostic_report.json`
- `--repo-owner wzgig`
- `--repo-name env_tool`
- `--index-url https://pypi.tuna.tsinghua.edu.cn/simple`
- `--extra-index-url https://pypi.org/simple`
- `--trusted-host pypi.tuna.tsinghua.edu.cn`
- `--pip-timeout 120`
- `--pip-retries 3`
- `--python C:\\Python313\\python.exe`
- `--pause-on-exit`

## 6. 安全与可维护建议

- 建议在干净虚拟环境中运行，避免污染系统环境
- 内网环境可配置企业镜像源（如清华/阿里/公司私有镜像）
- 给 `EXE` 做版本号管理（如 `EnvTool_v1.0.0.exe`）并附带 SHA256 校验值

## 7. 图形版说明

- 图形版会调用 env_manager.py 执行同样的安装/检查逻辑
- 新版界面采用现代化轻量视觉风格（Apple-inspired），层级更清晰、按钮更统一
- 第二轮 UI 升级：新增左侧导航栏（快速模式/快捷操作）+ 右侧双工作区（配置中心 / 运行与日志）
- 新增欢迎页与配置记忆：会自动保存上次使用的页面、模式、路径与参数
- 新增说明书页面：解释每个功能的作用和使用方式
- 新增关于页面：查看作者、版本与 GitHub 链接
- 首页新增作者信息：Zicheng Wang (@wzgig), Tiany Huo (@titih258) <3377386900@qq.com>
- 组织：MuFeng；联系邮箱：[qqiuqiuhua@gmail.com](mailto:qqiuqiuhua@gmail.com)
- 新增模板中心：数据分析 / 科研 / 办公 / 离线部署 / 诊断模板
- 新增更新检查：自动读取 GitHub Releases 最新版本与资产下载地址
- 支持浅色/深色主题切换
- 支持：模式选择、分组勾选、`--only` 包输入、目标 Python 路径、JSON 报告路径
- 支持实时日志和中止任务
- 支持命令预览、恢复默认、打开报告、进度条状态
- 支持“配置预设”（默认推荐 / 最小安装 / 科研增强 / AI 全量 / 仅检查）
- 支持“全选分组 / 清空分组”快捷操作
- 支持日志颜色高亮（成功/警告/失败）
- 支持报告摘要读取与“失败包一键重试”
- 支持日志导出（便于提交排障）
- 支持自动更新检查与 Release 资产打开
- 快捷键：`Ctrl+R` 开始执行，`Ctrl+L` 清空日志

## 8. 建议的产品化发布流程

1. 先本地执行一次 `python env_tool_gui.py` 验证 UI 交互
2. 打包 GUI：`python build_exe.py --target gui`
3. 验证 [dist/EnvToolGUI.exe](dist/EnvToolGUI.exe) 双击可运行
4. 同步发布 SHA256 与版本号（例如 `EnvToolGUI_v1.2.0.exe`）

### 7.1 打包后 GUI 运行提示

- 如果 GUI 无法自动找到“运行器 Python”，可设置环境变量：
  - `ENV_TOOL_RUNNER_PYTHON=C:\\Python313\\python.exe`
- 新版 GUI 已增强关闭流程，避免关闭窗口时因异步回调导致重复异常弹窗。
- 新增说明书页，可从首页或左侧导航直接打开。


