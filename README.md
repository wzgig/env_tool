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

1. 安装 Python（建议 3.10+，并勾选 Add Python to PATH）
2. 推荐双击运行 [dist/EnvToolGUI.exe](dist/EnvToolGUI.exe)
3. 如需命令行方式，运行 [dist/EnvTool.exe](dist/EnvTool.exe)

推荐双击参数（防止窗口自动关闭）：

`EnvTool.exe --pause-on-exit`

如需指定目标解释器：

`EnvTool.exe --python C:\\Python313\\python.exe --pause-on-exit`

也可以设置环境变量：

`ENV_TOOL_PYTHON=C:\\Python313\\python.exe`

## 5. 常用参数

- `--mode all|install|check`
- `--groups daily_common scientific_research`
- `--include-optional-ai`
- `--only numpy pandas scipy`
- `--skip-pip-upgrade`
- `--skip-installed`
- `--dry-run`
- `--json-report report.json`
- `--python C:\\Python313\\python.exe`
- `--pause-on-exit`

## 6. 安全与可维护建议

- 建议在干净虚拟环境中运行，避免污染系统环境
- 内网环境可配置企业镜像源（如清华/阿里/公司私有镜像）
- 给 `EXE` 做版本号管理（如 `EnvTool_v1.0.0.exe`）并附带 SHA256 校验值

## 7. 图形版说明

- 图形版会调用 env_manager.py 执行同样的安装/检查逻辑
- 支持：模式选择、分组勾选、`--only` 包输入、目标 Python 路径、JSON 报告路径
- 支持实时日志和中止任务
- 支持命令预览、恢复默认、打开报告、进度条状态
- 支持“配置预设”（默认推荐 / 最小安装 / 科研增强 / AI 全量 / 仅检查）
- 支持“全选分组 / 清空分组”快捷操作
- 支持日志颜色高亮（成功/警告/失败）
- 支持报告摘要读取与“失败包一键重试”
- 支持日志导出（便于提交排障）
- 快捷键：`Ctrl+R` 开始执行，`Ctrl+L` 清空日志

## 8. 建议的产品化发布流程

1. 先本地执行一次 `python env_tool_gui.py` 验证 UI 交互
2. 打包 GUI：`python build_exe.py --target gui`
3. 验证 [dist/EnvToolGUI.exe](dist/EnvToolGUI.exe) 双击可运行
4. 同步发布 SHA256 与版本号（例如 `EnvToolGUI_v1.1.0.exe`）

### 7.1 打包后 GUI 运行提示

- 如果 GUI 无法自动找到“运行器 Python”，可设置环境变量：
  - `ENV_TOOL_RUNNER_PYTHON=C:\\Python313\\python.exe`
