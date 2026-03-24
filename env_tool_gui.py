"""EnvTool 图形界面入口。

设计目标：
1) 让非技术用户也能一眼看懂并完成常用操作；
2) 提供完整可追踪日志；
3) 兼容源码运行与 PyInstaller 打包运行。
"""

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List


class EnvToolGUI:
    """EnvTool 主界面类。"""

    POLL_MS = 120

    # 内部“任务分组名” -> 界面显示名
    GROUP_LABELS = {
        "daily_common": "日常常用",
        "scientific_research": "科研分析",
        "visualization": "可视化",
        "data_processing": "数据处理",
    }

    # 常用预设：帮助非技术用户快速上手
    PRESETS: Dict[str, Dict] = {
        "默认推荐": {
            "mode": "all",
            "groups": ["daily_common", "scientific_research", "visualization", "data_processing"],
            "include_ai": False,
            "skip_pip": False,
            "skip_installed": True,
            "dry_run": False,
            "only": "",
        },
        "最小安装": {
            "mode": "install",
            "groups": ["daily_common"],
            "include_ai": False,
            "skip_pip": True,
            "skip_installed": True,
            "dry_run": False,
            "only": "",
        },
        "科研增强": {
            "mode": "all",
            "groups": ["daily_common", "scientific_research", "visualization", "data_processing"],
            "include_ai": False,
            "skip_pip": False,
            "skip_installed": True,
            "dry_run": False,
            "only": "",
        },
        "AI 全量": {
            "mode": "all",
            "groups": ["daily_common", "scientific_research", "visualization", "data_processing"],
            "include_ai": True,
            "skip_pip": False,
            "skip_installed": True,
            "dry_run": False,
            "only": "",
        },
        "仅检查": {
            "mode": "check",
            "groups": ["daily_common", "scientific_research", "visualization", "data_processing"],
            "include_ai": False,
            "skip_pip": True,
            "skip_installed": True,
            "dry_run": False,
            "only": "",
        },
    }

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("EnvTool · Python 库安装与检查")
        self.root.geometry("1080x760")
        self.root.minsize(980, 680)

        self.project_root = Path(__file__).resolve().parent
        self.entry_script = self._resolve_entry_script()

        # 当前子进程（执行 env_manager.py）
        self.proc: subprocess.Popen | None = None
        # 后台线程 -> 主线程的日志队列
        self.log_queue: queue.Queue[str] = queue.Queue()

        # ------- 业务状态变量 -------
        self.mode_var = tk.StringVar(value="all")
        self.python_var = tk.StringVar(value="")
        self.only_var = tk.StringVar(value="")
        self.json_var = tk.StringVar(value="report.json")

        self.include_ai_var = tk.BooleanVar(value=False)
        self.skip_pip_var = tk.BooleanVar(value=False)
        self.skip_installed_var = tk.BooleanVar(value=True)
        self.dry_run_var = tk.BooleanVar(value=False)

        self.group_vars = {
            "daily_common": tk.BooleanVar(value=True),
            "scientific_research": tk.BooleanVar(value=True),
            "visualization": tk.BooleanVar(value=True),
            "data_processing": tk.BooleanVar(value=True),
        }

        self.status_var = tk.StringVar(value="就绪")
        self.preview_var = tk.StringVar(value="")
        self.preset_var = tk.StringVar(value="默认推荐")
        self.summary_var = tk.StringVar(value="结果摘要：尚未执行")

        self._configure_style()
        self._build_ui()
        self._bind_events()
        self._apply_preset(self.preset_var.get())
        self._refresh_cmd_preview()

        # 持续轮询后台日志
        self.root.after(self.POLL_MS, self._poll_log)

    def _resolve_entry_script(self) -> Path:
        """定位 env_manager.py。

        - 源码运行：就在当前目录
        - 打包运行：可能在 _MEIPASS 目录
        """
        local_candidate = Path(__file__).resolve().parent / "env_manager.py"
        if local_candidate.exists():
            return local_candidate

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled_candidate = Path(meipass) / "env_manager.py"
            if bundled_candidate.exists():
                return bundled_candidate

        return local_candidate

    def _configure_style(self) -> None:
        """统一界面风格。"""
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 14, "bold"))
        style.configure("Hint.TLabel", foreground="#606060")

    def _build_ui(self) -> None:
        """创建界面组件。"""
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        # 顶部标题区
        header = ttk.Frame(container)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="EnvTool 图形化安装器", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            header,
            text="推荐流程：选择模式 → 勾选分组/包 → 点击“开始执行” → 查看日志与报告",
            style="Hint.TLabel",
        ).pack(anchor=tk.W, pady=(2, 0))

        # 预设区：一键套用参数
        preset_frame = ttk.Frame(container)
        preset_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(preset_frame, text="配置预设").pack(side=tk.LEFT)
        self.preset_box = ttk.Combobox(
            preset_frame,
            textvariable=self.preset_var,
            values=list(self.PRESETS.keys()),
            state="readonly",
            width=18,
        )
        self.preset_box.pack(side=tk.LEFT, padx=(8, 8))
        ttk.Button(preset_frame, text="应用预设", command=self._on_apply_preset).pack(side=tk.LEFT)
        ttk.Label(preset_frame, text="（预设不会覆盖 Python 路径与报告路径）", style="Hint.TLabel").pack(side=tk.LEFT, padx=(12, 0))

        # 基础配置
        basic = ttk.LabelFrame(container, text="基础配置", padding=10)
        basic.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(basic, text="运行模式").grid(row=0, column=0, sticky=tk.W)
        mode_box = ttk.Combobox(
            basic,
            textvariable=self.mode_var,
            values=["all", "install", "check"],
            width=12,
            state="readonly",
        )
        mode_box.grid(row=0, column=1, sticky=tk.W, padx=(8, 24))

        ttk.Label(basic, text="目标 Python（可选）").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(basic, textvariable=self.python_var).grid(row=0, column=3, sticky=tk.EW, padx=8)
        ttk.Button(basic, text="浏览", command=self._choose_python).grid(row=0, column=4, sticky=tk.W)

        ttk.Label(basic, text="JSON 报告路径").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(basic, textvariable=self.json_var).grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=(8, 8), pady=(8, 0))
        ttk.Button(basic, text="选择", command=self._choose_report_path).grid(row=1, column=4, sticky=tk.W, pady=(8, 0))

        basic.columnconfigure(3, weight=1)

        # 任务与选项
        option_wrap = ttk.Frame(container)
        option_wrap.pack(fill=tk.X, pady=(0, 8))

        groups = ttk.LabelFrame(option_wrap, text="任务分组", padding=10)
        groups.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        col = 0
        for group_key, var in self.group_vars.items():
            label = f"{self.GROUP_LABELS[group_key]} ({group_key})"
            ttk.Checkbutton(groups, text=label, variable=var).grid(row=0, column=col, sticky=tk.W, padx=6)
            col += 1
        ttk.Checkbutton(groups, text="包含 AI 可选组（optional_ai）", variable=self.include_ai_var).grid(
            row=1, column=0, columnspan=4, sticky=tk.W, padx=6, pady=(8, 0)
        )
        ttk.Button(groups, text="全选分组", command=self._select_all_groups).grid(row=2, column=0, sticky=tk.W, padx=6, pady=(8, 0))
        ttk.Button(groups, text="清空分组", command=self._clear_all_groups).grid(row=2, column=1, sticky=tk.W, padx=6, pady=(8, 0))

        advanced = ttk.LabelFrame(option_wrap, text="高级参数", padding=10)
        advanced.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        ttk.Label(advanced, text="仅处理包（--only，空格分隔）").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(advanced, textvariable=self.only_var).grid(row=0, column=1, sticky=tk.EW, padx=(8, 0))

        ttk.Checkbutton(advanced, text="跳过 pip 升级", variable=self.skip_pip_var).grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Checkbutton(advanced, text="跳过已安装包", variable=self.skip_installed_var).grid(row=1, column=1, sticky=tk.W, pady=(8, 0))
        ttk.Checkbutton(advanced, text="仅预演（dry-run）", variable=self.dry_run_var).grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        advanced.columnconfigure(1, weight=1)

        # 命令预览
        preview = ttk.LabelFrame(container, text="命令预览（执行前可确认）", padding=8)
        preview.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(preview, textvariable=self.preview_var, state="readonly").pack(fill=tk.X)

        # 操作区
        actions = ttk.Frame(container)
        actions.pack(fill=tk.X, pady=(0, 8))

        self.run_btn = ttk.Button(actions, text="开始执行", command=self._run)
        self.run_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(actions, text="停止", command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=8)

        ttk.Button(actions, text="恢复默认", command=self._reset_defaults).pack(side=tk.LEFT)
        ttk.Button(actions, text="打开报告", command=self._open_report).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="刷新摘要", command=self._refresh_report_summary).pack(side=tk.LEFT)
        ttk.Button(actions, text="失败包重试", command=self._retry_failed_from_report).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="导出日志", command=self._export_log).pack(side=tk.LEFT)
        ttk.Button(actions, text="清空日志", command=self._clear_log).pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=180)
        self.progress.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Label(actions, textvariable=self.status_var).pack(side=tk.RIGHT)

        # 摘要栏
        summary_frame = ttk.Frame(container)
        summary_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(summary_frame, textvariable=self.summary_var, style="Hint.TLabel").pack(side=tk.LEFT)

        # 日志区
        log_frame = ttk.LabelFrame(container, text="执行日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, wrap=tk.WORD, height=24, font=("Consolas", 10))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.log_text.tag_configure("ok", foreground="#1B8F3A")
        self.log_text.tag_configure("warn", foreground="#B36B00")
        self.log_text.tag_configure("err", foreground="#C62828")
        self.log_text.tag_configure("title", foreground="#1F4E79", font=("Consolas", 10, "bold"))

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _bind_events(self) -> None:
        """绑定变量变化与快捷键。"""
        tracked = [
            self.mode_var,
            self.python_var,
            self.only_var,
            self.json_var,
            self.include_ai_var,
            self.skip_pip_var,
            self.skip_installed_var,
            self.dry_run_var,
            *self.group_vars.values(),
        ]
        for var in tracked:
            var.trace_add("write", self._on_option_changed)

        self.root.bind("<Control-r>", lambda _e: self._run())
        self.root.bind("<Control-l>", lambda _e: self._clear_log())
        self.root.bind("<Control-s>", lambda _e: self._export_log())

    def _on_apply_preset(self) -> None:
        self._apply_preset(self.preset_var.get())

    def _apply_preset(self, name: str) -> None:
        """应用某个预设到当前界面。"""
        preset = self.PRESETS.get(name)
        if not preset:
            return

        self.mode_var.set(preset["mode"])
        self.include_ai_var.set(preset["include_ai"])
        self.skip_pip_var.set(preset["skip_pip"])
        self.skip_installed_var.set(preset["skip_installed"])
        self.dry_run_var.set(preset["dry_run"])
        self.only_var.set(preset["only"])

        group_set = set(preset["groups"])
        for key, var in self.group_vars.items():
            var.set(key in group_set)

        self._append_log(f"[配置] 已应用预设：{name}")

    def _select_all_groups(self) -> None:
        for var in self.group_vars.values():
            var.set(True)

    def _clear_all_groups(self) -> None:
        for var in self.group_vars.values():
            var.set(False)

    def _on_option_changed(self, *_args) -> None:
        self._refresh_cmd_preview()

    def _can_run_python(self, candidate: str) -> bool:
        """判断某个 Python 命令是否可执行。"""
        try:
            result = subprocess.run(
                [candidate, "-c", "import sys;print(sys.executable)"],
                check=False,
                capture_output=True,
                text=True,
                timeout=8,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _resolve_runner_python(self) -> str:
        """选择用于启动 env_manager.py 的 Python 解释器。"""
        if not getattr(sys, "frozen", False):
            return sys.executable

        env_runner = os.environ.get("ENV_TOOL_RUNNER_PYTHON", "").strip()
        if env_runner and self._can_run_python(env_runner):
            return env_runner

        env_target = os.environ.get("ENV_TOOL_PYTHON", "").strip()
        if env_target and self._can_run_python(env_target):
            return env_target

        if shutil.which("py") and self._can_run_python("py"):
            return "py"
        if shutil.which("python") and self._can_run_python("python"):
            return "python"

        raise RuntimeError("未找到可用 Python 解释器。请安装 Python 或设置 ENV_TOOL_RUNNER_PYTHON。")

    def _choose_python(self) -> None:
        """选择目标 Python（用于 pip 安装/检查目标环境）。"""
        selected = filedialog.askopenfilename(
            title="选择 python.exe",
            filetypes=[("Python", "python.exe"), ("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if selected:
            self.python_var.set(selected)

    def _choose_report_path(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="选择 JSON 报告路径",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
            initialfile=self.json_var.get().strip() or "report.json",
        )
        if selected:
            self.json_var.set(selected)

    def _validate_inputs(self) -> None:
        """执行前参数校验，提前给出友好提示。"""
        python_path = self.python_var.get().strip()
        if python_path and not Path(python_path).exists():
            raise ValueError("目标 Python 路径不存在，请重新选择。")

        only_text = self.only_var.get().strip()
        if not only_text:
            selected_groups = [name for name, var in self.group_vars.items() if var.get()]
            if not selected_groups:
                raise ValueError("请至少勾选一个分组，或在 --only 中指定包名。")

    def _build_cmd(self) -> List[str]:
        """把当前界面状态转换为命令行参数。"""
        if not self.entry_script.exists():
            raise FileNotFoundError(f"未找到入口脚本: {self.entry_script}")

        self._validate_inputs()
        runner = self._resolve_runner_python()
        cmd: List[str] = [runner, str(self.entry_script), "--mode", self.mode_var.get()]

        selected_groups = [name for name, var in self.group_vars.items() if var.get()]
        only_text = self.only_var.get().strip()

        if only_text:
            cmd.extend(["--only", *only_text.split()])
        else:
            cmd.extend(["--groups", *selected_groups])

        if self.include_ai_var.get():
            cmd.append("--include-optional-ai")
        if self.skip_pip_var.get():
            cmd.append("--skip-pip-upgrade")
        if self.skip_installed_var.get():
            cmd.append("--skip-installed")
        if self.dry_run_var.get():
            cmd.append("--dry-run")

        python_path = self.python_var.get().strip()
        if python_path:
            cmd.extend(["--python", python_path])

        json_path = self.json_var.get().strip()
        if json_path:
            cmd.extend(["--json-report", json_path])

        return cmd

    def _refresh_cmd_preview(self) -> None:
        """实时刷新“命令预览”行。"""
        try:
            cmd = self._build_cmd()
            self.preview_var.set(" ".join(cmd))
        except Exception as e:
            self.preview_var.set(f"参数待完善：{e}")

    def _set_running_state(self, running: bool) -> None:
        """统一切换按钮状态与进度条状态。"""
        self.run_btn.config(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)
        self.status_var.set("运行中..." if running else "已完成")
        if running:
            self.progress.start(10)
        else:
            self.progress.stop()

    def _run(self) -> None:
        """点击“开始执行”后触发。"""
        if self.proc is not None:
            messagebox.showinfo("提示", "任务正在运行中")
            return

        try:
            cmd = self._build_cmd()
        except Exception as e:
            messagebox.showerror("参数错误", str(e))
            return

        self.summary_var.set("结果摘要：任务执行中...")
        self._append_log("\n" + "=" * 88)
        self._append_log("启动命令: " + " ".join(cmd))
        self._append_log("=" * 88 + "\n")

        self._set_running_state(True)
        threading.Thread(target=self._worker, args=(cmd,), daemon=True).start()

    def _worker(self, cmd: List[str]) -> None:
        """后台线程：执行命令并把输出塞到队列。"""
        try:
            # 关键：强制子进程统一使用 UTF-8，避免 Windows 下出现中文乱码。
            # 常见乱码原因是：子进程按 cp936/gbk 输出，而父进程按 utf-8 解码。
            run_env = os.environ.copy()
            run_env.setdefault("PYTHONIOENCODING", "utf-8")
            run_env.setdefault("PYTHONUTF8", "1")

            self.proc = subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                env=run_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                self.log_queue.put(line.rstrip("\n"))

            code = self.proc.wait()
            self.log_queue.put(f"\n[结束] 退出码: {code}")
        except Exception as e:
            self.log_queue.put(f"\n[异常] {type(e).__name__}: {e}")
        finally:
            self.proc = None
            self.log_queue.put("__TASK_DONE__")

    def _stop(self) -> None:
        """尝试停止当前任务。"""
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self._append_log("\n[操作] 已发送停止信号")
        except Exception as e:
            self._append_log(f"\n[异常] 停止失败: {e}")

    def _open_report(self) -> None:
        """打开当前 JSON 报告文件。"""
        path = self.json_var.get().strip()
        if not path:
            messagebox.showinfo("提示", "请先设置 JSON 报告路径")
            return

        report_path = Path(path)
        if not report_path.is_absolute():
            report_path = self.project_root / report_path

        if not report_path.exists():
            messagebox.showwarning("提示", f"报告不存在：{report_path}")
            return

        os.startfile(str(report_path))  # type: ignore[attr-defined]

    def _resolve_report_path(self) -> Path:
        path = self.json_var.get().strip() or "report.json"
        report_path = Path(path)
        if not report_path.is_absolute():
            report_path = self.project_root / report_path
        return report_path

    def _refresh_report_summary(self) -> None:
        """读取 JSON 报告并展示简要摘要。"""
        report_path = self._resolve_report_path()
        if not report_path.exists():
            self.summary_var.set(f"结果摘要：未找到报告 {report_path.name}")
            return

        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as e:
            self.summary_var.set(f"结果摘要：报告读取失败（{type(e).__name__}）")
            return

        install = data.get("install") or {}
        check = data.get("check") or {}

        install_ok = int(install.get("success_count", 0) or 0)
        install_fail = int(install.get("failed_count", 0) or 0)
        install_skip = int(install.get("skipped_count", 0) or 0)

        check_ok = int(check.get("passed_count", 0) or 0)
        check_fail = int(check.get("failed_count", 0) or 0)

        summary_text = (
            f"结果摘要：安装 成功 {install_ok} / 失败 {install_fail} / 跳过 {install_skip}；"
            f"检查 通过 {check_ok} / 失败 {check_fail}"
        )
        self.summary_var.set(summary_text)
        self._append_log("[摘要] " + summary_text)

    def _get_failed_packages_from_report(self) -> List[str]:
        """从报告中提取失败包，用于一键重试。"""
        report_path = self._resolve_report_path()
        if not report_path.exists():
            return []

        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        failed: List[str] = []
        for item in (data.get("install") or {}).get("failed") or []:
            pkg = str(item.get("package", "")).strip()
            if pkg:
                failed.append(pkg)
        for item in (data.get("check") or {}).get("failed") or []:
            pkg = str(item.get("package", "")).strip()
            if pkg:
                failed.append(pkg)

        # 去重并保持顺序
        seen = set()
        result: List[str] = []
        for pkg in failed:
            key = pkg.lower()
            if key not in seen:
                seen.add(key)
                result.append(pkg)
        return result

    def _retry_failed_from_report(self) -> None:
        """把报告中的失败包写入 --only，实现快速重试。"""
        if self.proc is not None:
            messagebox.showinfo("提示", "请先停止当前任务")
            return

        failed = self._get_failed_packages_from_report()
        if not failed:
            messagebox.showinfo("提示", "报告中未找到失败包。")
            return

        self.mode_var.set("all")
        self.only_var.set(" ".join(failed))
        self.skip_installed_var.set(False)
        self._append_log(f"[重试] 已加载失败包：{' '.join(failed)}")
        messagebox.showinfo("已准备", "失败包已填入 --only，可直接点击“开始执行”。")

    def _export_log(self) -> None:
        """导出当前日志到文本文件，便于排障提交。"""
        default_name = f"envtool_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path = filedialog.asksaveasfilename(
            title="导出日志",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile=default_name,
        )
        if not path:
            return

        try:
            content = self.log_text.get("1.0", tk.END)
            Path(path).write_text(content, encoding="utf-8")
            self._append_log(f"[导出] 日志已保存：{path}")
        except Exception as e:
            messagebox.showerror("导出失败", f"{type(e).__name__}: {e}")

    def _append_log(self, text: str) -> None:
        """向日志区域追加一行文本。"""
        tag = None
        up = text.upper()
        if "FAILED" in up or "ERROR" in up or "异常" in text:
            tag = "err"
        elif "WARNING" in up or "警告" in text or "跳过" in text:
            tag = "warn"
        elif "[OK]" in up or "成功" in text:
            tag = "ok"
        elif text.startswith("===") or text.startswith("启动命令"):
            tag = "title"

        if tag:
            self.log_text.insert(tk.END, text + "\n", tag)
        else:
            self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def _reset_defaults(self) -> None:
        """恢复默认参数。"""
        if self.proc is not None:
            messagebox.showinfo("提示", "请先停止当前任务")
            return

        self.mode_var.set("all")
        self.python_var.set("")
        self.only_var.set("")
        self.json_var.set("report.json")
        self.include_ai_var.set(False)
        self.skip_pip_var.set(False)
        self.skip_installed_var.set(True)
        self.dry_run_var.set(False)

        for key, var in self.group_vars.items():
            var.set(key in {"daily_common", "scientific_research", "visualization", "data_processing"})

        self._append_log("[操作] 已恢复默认参数")

    def _poll_log(self) -> None:
        """主线程轮询日志队列。"""
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if item == "__TASK_DONE__":
                self._set_running_state(False)
                self._refresh_report_summary()
                continue

            self._append_log(item)

        self.root.after(self.POLL_MS, self._poll_log)


def main() -> int:
    root = tk.Tk()
    EnvToolGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
