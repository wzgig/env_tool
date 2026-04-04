"""EnvTool 图形界面入口。

设计目标：
1) 让非技术用户也能一眼看懂并完成常用操作；
2) 提供完整可追踪日志；
3) 兼容源码运行与 PyInstaller 打包运行。
"""

import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Dict, List



class CardFrame(ctk.CTkFrame):
    def __init__(self, master, title=None, **kwargs):
        kwargs.pop("padding", None)
        kwargs.pop("style", None)
        kwargs.setdefault("corner_radius", 10)
        super().__init__(master, **kwargs)
        self._content_frame = self
        if title:
            label = ctk.CTkLabel(self, text=title, font=ctk.CTkFont(family="Helvetica Neue", size=14, weight="bold"))
            label.pack(anchor="w", padx=12, pady=(10, 4))
            self._content_frame = ctk.CTkFrame(self, fg_color="transparent")
            self._content_frame.pack(fill="both", expand=True, padx=4, pady=(0, 8))
            self._content_frame.pack = self.pack
            self._content_frame.grid = self.grid
            self._content_frame.pack_forget = self.pack_forget
            self._content_frame.grid_forget = self.grid_forget
            
    def pack(self, **kwargs):
        super().pack(**kwargs)
        
    def grid(self, **kwargs):
        super().grid(**kwargs)


class EnvToolGUI:
    """EnvTool 主界面类。"""

    APP_NAME = "EnvTool"
    APP_VERSION = "1.2.0"
    AUTHOR_NAME = "Zicheng Wang, Tiany Huo"
    AUTHOR_EMAIL = "qqiuqiuhua@gmail.com, 3377386900@qq.com"
    AUTHOR_GITHUB = "https://github.com/wzgig"
    ORGANIZATION = "MuFeng"
    COPYRIGHT_TEXT = "© 2026 MuFeng · Zicheng Wang, Tiany Huo. All rights reserved."
    REPO_OWNER = "wzgig"
    REPO_NAME = "env_tool"
    SETTINGS_FILE_NAME = "settings.json"
    POLL_MS = 120
    SAVE_SETTINGS_DELAY_MS = 500

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
        "环境快照": {
            "mode": "snapshot",
            "groups": ["daily_common", "scientific_research", "visualization", "data_processing"],
            "include_ai": False,
            "skip_pip": True,
            "skip_installed": True,
            "dry_run": False,
            "only": "",
        },
    }

    TEMPLATES: Dict[str, Dict] = {
        "data_analysis": {
            "title": "数据分析模板",
            "preset": "默认推荐",
            "description": "适合 pandas / numpy / matplotlib / notebook 组合。",
        },
        "research": {
            "title": "科研模板",
            "preset": "科研增强",
            "description": "适合科学计算、统计分析与可视化。",
        },
        "office": {
            "title": "办公模板",
            "preset": "最小安装",
            "description": "适合轻量办公、文档与表格场景。",
        },
        "offline": {
            "title": "离线部署模板",
            "preset": "默认推荐",
            "description": "适合内网/无外网安装，配合 wheel 仓库目录使用。",
        },
        "diagnose": {
            "title": "诊断模板",
            "preset": "仅检查",
            "description": "自动收集环境、网络与包状态，输出诊断报告。",
        },
    }

    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self.root.title("EnvTool · Python 库安装与检查")
        self.root.geometry("1080x760")
        self.root.minsize(980, 680)
        self.root.configure(bg="#F5F5F7")
        self.colors = {"text": "black", "bg": "#F5F5F7", "card": "#FFFFFF", "primary": "#007AFF", "muted_btn": "#E5E5EA", "subtext": "#6E6E73"}


        # 确定真正的绝对工作目录，避免把由于 PyInstaller 的 _MEIPASS 引入的 DLL 污染传递给子系统
        if getattr(sys, "frozen", False):
            self.project_root = Path(sys.executable).resolve().parent
        else:
            self.project_root = Path(__file__).resolve().parent

        self.entry_script = self._resolve_entry_script()

        # 当前子进程（执行 env_manager.py）
        self.proc: subprocess.Popen | None = None
        self.last_exit_code: int | None = None
        # 后台线程 -> 主线程的日志队列
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.poll_job_id: str | None = None
        self.settings_job_id: str | None = None
        self.running_anim_job_id: str | None = None
        self.running_anim_phase = 0
        self.is_closing = False
        self._exception_dialog_shown = False
        self._loading_settings = False

        # ------- 业务状态变量 -------
        self.mode_var = tk.StringVar(value="all")
        self.python_var = tk.StringVar(value="")
        self.only_var = tk.StringVar(value="")
        self.json_var = tk.StringVar(value="report.json")
        self.snapshot_var = tk.StringVar(value="requirements_snapshot.txt")
        self.wheel_dir_var = tk.StringVar(value="")
        self.venv_path_var = tk.StringVar(value=str((Path(__file__).resolve().parent / ".envtool_venv").resolve()))
        self.diag_output_var = tk.StringVar(value="diagnostic_report.json")
        self.repo_owner_var = tk.StringVar(value=self.REPO_OWNER)
        self.repo_name_var = tk.StringVar(value=self.REPO_NAME)
        self.dark_mode_var = tk.BooleanVar(value=False)
        self.index_url_var = tk.StringVar(value="")
        self.extra_index_var = tk.StringVar(value="")
        self.trusted_host_var = tk.StringVar(value="")
        self.pip_timeout_var = tk.StringVar(value="")
        self.pip_retries_var = tk.StringVar(value="")

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
        self.update_status_var = tk.StringVar(value="更新：未检查")
        self.badge_mode_var = tk.StringVar(value="模式: all")
        self.badge_theme_var = tk.StringVar(value="主题: 浅色")
        self.badge_state_var = tk.StringVar(value="状态: 空闲")
        self.active_page_var = tk.StringVar(value="welcome")
        self.nav_buttons: Dict[str, ctk.CTkButton] = {}
        self.page_frames: Dict[str, ctk.CTkFrame] = {}

        # #  - Removed for CustomTkinter - Removed for CustomTkinter
        self._build_ui()
        self._set_window_icon()
        self._bind_events()
        self._loading_settings = True
        self._apply_preset(self.preset_var.get())
        self._load_settings()
        # #  - Removed for CustomTkinter - Removed for CustomTkinter
        self._refresh_cmd_preview()
        self._sync_nav_state()
        self._show_page(self.active_page_var.get())

        # 启动后做一次静默更新检查，不打断用户操作
        self.root.after(1200, self._start_silent_update_check)

        # 统一异常与关闭行为，避免窗口关闭时反复弹窗
        self.root.report_callback_exception = self._report_callback_exception
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 持续轮询后台日志
        self.poll_job_id = self.root.after(self.POLL_MS, self._poll_log)

    def _resolve_entry_script(self) -> Path:
        """定位 env_manager.py。

        - 源码运行：就在当前目录
        - 打包运行：由于 sys.path[0] 会导致目标 Python 错误加载 _MEIPASS 下的 pyd，必须提取到 TEMP 目录再运行。
        """
        local_candidate = Path(__file__).resolve().parent / "env_manager.py"
        if not getattr(sys, "frozen", False) and local_candidate.exists():
            return local_candidate

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled_candidate = Path(meipass) / "env_manager.py"
            if bundled_candidate.exists():
                import tempfile
                # 创一个临时目录，避免与其他进程冲突，或者复用固定的隔离目录
                temp_dir = Path(tempfile.gettempdir()) / "EnvTool_Extracted"
                temp_dir.mkdir(parents=True, exist_ok=True)
                extracted_script = temp_dir / "env_manager.py"
                
                # 覆盖写入，保证最新
                shutil.copy2(bundled_candidate, extracted_script)
                return extracted_script

        return local_candidate

    def _set_window_icon(self) -> None:
        """设置窗口图标（内置像素图标，避免外部依赖）。"""
        try:
            icon = tk.PhotoImage(width=16, height=16)
            icon.put("#0071E3", to=(0, 0, 16, 16))
            icon.put("#FFFFFF", to=(4, 4, 12, 12))
            icon.put("#0071E3", to=(6, 6, 10, 10))
            self.window_icon = icon
            self.root.iconphoto(True, self.window_icon)
        except Exception:
            pass

    def _update_top_badges(self) -> None:
        self.badge_mode_var.set(f"模式: {self.mode_var.get()}")
        self.badge_theme_var.set(f"主题: {'深色' if self.dark_mode_var.get() else '浅色'}")

    def _animate_running_badge(self) -> None:
        if self.proc is None or self.is_closing:
            self.running_anim_job_id = None
            return

        dots = "." * ((self.running_anim_phase % 3) + 1)
        self.badge_state_var.set(f"状态: 运行中{dots}")
        self.running_anim_phase += 1
        self.running_anim_job_id = self.root.after(420, self._animate_running_badge)

    def _stop_running_badge_animation(self) -> None:
        if self.running_anim_job_id:
            try:
                self.root.after_cancel(self.running_anim_job_id)
            except tk.TclError:
                pass
            self.running_anim_job_id = None

    def _build_ui(self) -> None:
        """创建界面组件（第二轮：侧边栏 + 工作区分栏）。"""
        container = ctk.CTkFrame(self.root)
        container.pack(fill=tk.BOTH, expand=True)

        shell = ctk.CTkFrame(container)
        shell.pack(fill=tk.BOTH, expand=True)

        # 左侧导航外层容器
        sidebar_container = ctk.CTkFrame(shell, width=230)
        sidebar_container.pack(side=tk.LEFT, fill=tk.Y)
        sidebar_container.pack_propagate(False)

        self.sidebar_canvas = None
        sidebar = ctk.CTkScrollableFrame(sidebar_container, fg_color="transparent")
        sidebar.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ctk.CTkLabel(sidebar, text="EnvTool").pack(anchor=tk.W)
        ctk.CTkLabel(sidebar, text="Python 环境助手").pack(anchor=tk.W, pady=(2, 12))

        ctk.CTkLabel(sidebar, text="页面导航").pack(anchor=tk.W)
        for page_id, text in [
            ("welcome", "欢迎"),
            ("config", "配置中心"),
            ("run", "运行与日志"),
            ("help", "说明书"),
            ("about", "关于"),
        ]:
            self.nav_buttons[page_id] = ctk.CTkButton(
                sidebar,
                text=text,
                command=lambda p=page_id: self._show_page(p),
                corner_radius=8
            )
            self.nav_buttons[page_id].pack(fill=tk.X, pady=(6, 0))

        ctk.CTkFrame(sidebar, height=1, fg_color="#C7C7CC").pack(fill=tk.X, pady=14)
        ctk.CTkLabel(sidebar, text="快速模式").pack(anchor=tk.W)
        for text, mode in [
            ("一键安装+检查", "all"),
            ("仅安装", "install"),
            ("仅检查", "check"),
            ("环境快照", "snapshot"),
            ("从快照恢复", "restore"),
            ("离线安装", "offline"),
            ("创建虚拟环境", "venv"),
            ("生成诊断", "diagnose"),
            ("检查更新", "update-check"),
        ]:
            ctk.CTkButton(
                sidebar,
                text=text,
                command=lambda m=mode: self._quick_set_mode(m),
                corner_radius=8
            ).pack(fill=tk.X, pady=(6, 0))

        ctk.CTkFrame(sidebar, height=1, fg_color="#C7C7CC").pack(fill=tk.X, pady=14)
        ctk.CTkLabel(sidebar, text="快捷操作").pack(anchor=tk.W)
        ctk.CTkButton(sidebar, text="开始执行", command=self._run, corner_radius=8).pack(fill=tk.X, pady=(6, 0))
        ctk.CTkButton(sidebar, text="停止任务", command=self._stop, corner_radius=8).pack(fill=tk.X, pady=(6, 0))
        ctk.CTkButton(sidebar, text="打开报告", command=self._open_report, corner_radius=8).pack(fill=tk.X, pady=(6, 0))
        ctk.CTkButton(sidebar, text="导出日志", command=self._export_log, corner_radius=8).pack(fill=tk.X, pady=(6, 0))
        ctk.CTkButton(sidebar, text="切换深色模式", command=self._toggle_theme, corner_radius=8).pack(fill=tk.X, pady=(6, 0))

        ctk.CTkFrame(sidebar, height=1, fg_color="#C7C7CC").pack(fill=tk.X, pady=14)
        ctk.CTkLabel(sidebar, text="快捷键").pack(anchor=tk.W)
        ctk.CTkLabel(sidebar, text="Ctrl+R 运行").pack(anchor=tk.W, pady=(4, 0))
        ctk.CTkLabel(sidebar, text="Ctrl+L 清空日志").pack(anchor=tk.W, pady=(2, 0))
        ctk.CTkLabel(sidebar, text="Ctrl+S 导出日志").pack(anchor=tk.W, pady=(2, 0))

        # 右侧主工作区
        main = ctk.CTkFrame(shell)
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        header = ctk.CTkFrame(main)
        header.pack(fill=tk.X, pady=(0, 10))
        ctk.CTkLabel(header, text="EnvTool 图形化安装器").pack(anchor=tk.W)
        ctk.CTkLabel(
            header,
            text="选择配置并执行任务，实时查看日志与结果摘要",
        ).pack(anchor=tk.W, pady=(2, 0))
        ctk.CTkLabel(
            header,
            text=f"作者：{self.AUTHOR_NAME} · 组织：{self.ORGANIZATION} · 版本：{self.APP_VERSION}",
        ).pack(anchor=tk.W, pady=(2, 0))

        badge_wrap = tk.Frame(header, bg=self.colors["bg"])
        badge_wrap.pack(anchor=tk.W, pady=(8, 0))
        self.badge_wrap = badge_wrap
        self.badge_mode_label = tk.Label(
            badge_wrap,
            textvariable=self.badge_mode_var,
            bg=self.colors["muted_btn"],
            fg=self.colors["text"],
            padx=10,
            pady=4,
            font=(("Helvetica Neue", "Segoe UI", "Arial"), 9, "bold"),
        )
        self.badge_mode_label.pack(side=tk.LEFT)
        self.badge_theme_label = tk.Label(
            badge_wrap,
            textvariable=self.badge_theme_var,
            bg=self.colors["muted_btn"],
            fg=self.colors["text"],
            padx=10,
            pady=4,
            font=(("Helvetica Neue", "Segoe UI", "Arial"), 9, "bold"),
        )
        self.badge_theme_label.pack(side=tk.LEFT, padx=(8, 0))
        self.badge_state_label = tk.Label(
            badge_wrap,
            textvariable=self.badge_state_var,
            bg=self.colors["primary"],
            fg="#FFFFFF",
            padx=10,
            pady=4,
            font=(("Helvetica Neue", "Segoe UI", "Arial"), 9, "bold"),
        )
        self.badge_state_label.pack(side=tk.LEFT, padx=(8, 0))

        cards = ctk.CTkFrame(main)
        cards.pack(fill=tk.X, pady=(0, 8))
        status_card = CardFrame(cards, title="运行状态")._content_frame
        status_card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ctk.CTkLabel(status_card, textvariable=self.status_var).pack(anchor=tk.W)
        summary_card = CardFrame(cards, title="结果摘要")._content_frame
        summary_card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        ctk.CTkLabel(summary_card, textvariable=self.summary_var).pack(anchor=tk.W)
        update_card = CardFrame(cards, title="更新")._content_frame
        update_card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        ctk.CTkLabel(update_card, textvariable=self.update_status_var).pack(anchor=tk.W)
        ctk.CTkButton(update_card, text="检查更新", command=self._check_update_ui, corner_radius=8).pack(anchor=tk.W, pady=(6, 0))

        self.page_hint = ctk.CTkLabel(main, text="")
        self.page_hint.pack(fill=tk.X, pady=(0, 8))

        workspace = ctk.CTkTabview(main)
        workspace.pack(fill=tk.BOTH, expand=True)
        self.workspace = workspace

        welcome_tab = workspace.add("欢迎")
        config_tab = workspace.add("配置中心")
        run_tab = workspace.add("运行与日志")
        help_tab = workspace.add("说明书")
        about_tab = workspace.add("关于")

        welcome_body = ctk.CTkScrollableFrame(welcome_tab, fg_color="transparent")
        welcome_body.pack(fill="both", expand=True)
        config_body = ctk.CTkScrollableFrame(config_tab, fg_color="transparent")
        config_body.pack(fill="both", expand=True)
        about_body = ctk.CTkScrollableFrame(about_tab, fg_color="transparent")
        about_body.pack(fill="both", expand=True)
        
        welcome_canvas = config_canvas = about_canvas = None

        self.scroll_canvases = {}

        self.page_frames = {"welcome": welcome_tab, "config": config_tab, "run": run_tab, "help": help_tab, "about": about_tab}

        # 欢迎页
        welcome_cards = ctk.CTkFrame(welcome_body)
        welcome_cards.pack(fill=tk.BOTH, expand=True)

        intro = CardFrame(welcome_cards, title="快速开始")._content_frame
        intro.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkLabel(
            intro,
            text="1. 选择左侧页面或预设\n2. 配置目标 Python / 分组 / 镜像源\n3. 点击开始执行\n4. 在运行页查看日志与结果",
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        features = CardFrame(welcome_cards, title="功能亮点")._content_frame
        features.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkLabel(
            features,
            text="• 自动探测多个 Python 解释器\n• 记住上次配置\n• 支持环境快照\n• 支持镜像源与超时重试\n• 支持日志导出与失败包重试",
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        quick_actions = CardFrame(welcome_cards, title="常用操作")._content_frame
        quick_actions.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkButton(quick_actions, text="前往配置中心", command=lambda: self._show_page("config"), corner_radius=8).pack(side=tk.LEFT)
        ctk.CTkButton(quick_actions, text="前往运行页", command=lambda: self._show_page("run"), corner_radius=8).pack(side=tk.LEFT, padx=8)
        ctk.CTkButton(quick_actions, text="恢复默认", command=self._reset_defaults, corner_radius=8).pack(side=tk.LEFT)
        ctk.CTkButton(quick_actions, text="说明书", command=lambda: self._show_page("help"), corner_radius=8).pack(side=tk.LEFT, padx=8)
        ctk.CTkButton(quick_actions, text="检查更新", command=self._check_update_ui, corner_radius=8).pack(side=tk.LEFT)

        author_card = CardFrame(welcome_cards, title="作者与信息")._content_frame
        author_card.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkLabel(
            author_card,
            text=(
                f"作者：{self.AUTHOR_NAME}\n"
                f"组织：{self.ORGANIZATION}\n"
                f"邮箱：{self.AUTHOR_EMAIL}\n"
                f"GitHub：{self.AUTHOR_GITHUB}\n"
                "适用版本：Python 3.10 - 3.13\n"
                "项目定位：一站式 Python 环境装配、诊断与发布工具"
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        template_card = CardFrame(welcome_cards, title="推荐模板")._content_frame
        template_card.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkButton(template_card, text="数据分析模板", command=lambda: self._apply_template("data_analysis"), corner_radius=8).pack(side=tk.LEFT)
        ctk.CTkButton(template_card, text="科研模板", command=lambda: self._apply_template("research"), corner_radius=8).pack(side=tk.LEFT, padx=8)
        ctk.CTkButton(template_card, text="办公模板", command=lambda: self._apply_template("office"), corner_radius=8).pack(side=tk.LEFT)
        ctk.CTkButton(template_card, text="离线部署模板", command=lambda: self._apply_template("offline"), corner_radius=8).pack(side=tk.LEFT, padx=8)
        ctk.CTkButton(template_card, text="诊断模板", command=lambda: self._apply_template("diagnose"), corner_radius=8).pack(side=tk.LEFT)

        # 说明书页
        help_wrap = ctk.CTkFrame(help_tab)
        help_wrap.pack(fill=tk.BOTH, expand=True)
        help_text = ctk.CTkTextbox(help_wrap, wrap=tk.WORD, font=ctk.CTkFont("Helvetica Neue", 13))
        help_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        help_text.insert(tk.END, self._build_manual_text())
        help_text.configure(state="disabled")
        self.help_text = help_text

        # 关于页
        about_card = CardFrame(about_body, title="关于 EnvTool")._content_frame
        about_card.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkLabel(
            about_card,
            text=(
                f"EnvTool v{self.APP_VERSION}\n"
                f"作者：{self.AUTHOR_NAME}\n"
                f"组织：{self.ORGANIZATION}\n"
                f"邮箱：{self.AUTHOR_EMAIL}\n"
                f"GitHub：{self.AUTHOR_GITHUB}\n"
                "定位：Python 环境安装、恢复、离线部署、诊断与更新检查\n"
                f"{self.COPYRIGHT_TEXT}"
            ),
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        links_card = CardFrame(about_body, title="相关链接")._content_frame
        links_card.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkButton(links_card, text="作者主页", command=self._open_author_home, corner_radius=8).pack(side=tk.LEFT)
        ctk.CTkButton(links_card, text="打开 GitHub 仓库", command=self._open_repo_home, corner_radius=8).pack(side=tk.LEFT)
        ctk.CTkButton(links_card, text="打开 Releases", command=self._open_repo_releases, corner_radius=8).pack(side=tk.LEFT, padx=8)

        # 配置中心
        preset_frame = CardFrame(config_body, title="快捷预设")._content_frame
        preset_frame.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkLabel(preset_frame, text="配置预设").pack(side=tk.LEFT)
        self.preset_box = ctk.CTkComboBox(
            preset_frame,
            variable=self.preset_var,
            values=list(self.PRESETS.keys()),
            state="disabled",
            width=180,
        )
        self.preset_box.pack(side=tk.LEFT, padx=(8, 8))
        ctk.CTkButton(preset_frame, text="应用预设", command=self._on_apply_preset, corner_radius=8).pack(side=tk.LEFT)
        ctk.CTkLabel(preset_frame, text="（预设不会覆盖 Python 路径与报告路径）").pack(side=tk.LEFT, padx=(12, 0))

        basic = CardFrame(config_body, title="基础配置")._content_frame
        basic.pack(fill=tk.X, pady=(0, 8))

        ctk.CTkLabel(basic, text="运行模式").grid(row=0, column=0, sticky=tk.W)
        mode_box = ctk.CTkComboBox(
            basic,
            variable=self.mode_var,
            values=["all", "install", "check", "snapshot", "restore", "offline", "venv", "diagnose", "update-check"],
            width=120,
            state="normal",
        )
        mode_box.grid(row=0, column=1, sticky=tk.W, padx=(8, 24))

        ctk.CTkLabel(basic, text="目标 Python（可选）").grid(row=0, column=2, sticky=tk.W)
        ctk.CTkEntry(basic, textvariable=self.python_var).grid(row=0, column=3, sticky=tk.EW, padx=8)
        ctk.CTkButton(basic, text="浏览", command=self._choose_python, corner_radius=8).grid(row=0, column=4, sticky=tk.W)

        ctk.CTkLabel(basic, text="JSON 报告路径").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ctk.CTkEntry(basic, textvariable=self.json_var).grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=(8, 8), pady=(8, 0))
        ctk.CTkButton(basic, text="选择", command=self._choose_report_path, corner_radius=8).grid(row=1, column=4, sticky=tk.W, pady=(8, 0))

        ctk.CTkLabel(basic, text="快照文件路径（snapshot）").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ctk.CTkEntry(basic, textvariable=self.snapshot_var).grid(row=2, column=1, columnspan=3, sticky=tk.EW, padx=(8, 8), pady=(8, 0))
        ctk.CTkButton(basic, text="选择", command=self._choose_snapshot_path, corner_radius=8).grid(row=2, column=4, sticky=tk.W, pady=(8, 0))
        basic.columnconfigure(3, weight=1)

        advanced_ext = CardFrame(config_body, title="扩展功能")._content_frame
        advanced_ext.pack(fill=tk.X, pady=(0, 8))

        ctk.CTkLabel(advanced_ext, text="wheel 仓库目录（offline）").grid(row=0, column=0, sticky=tk.W)
        ctk.CTkEntry(advanced_ext, textvariable=self.wheel_dir_var).grid(row=0, column=1, sticky=tk.EW, padx=(8, 0))
        ctk.CTkButton(advanced_ext, text="选择", command=self._choose_wheel_dir, corner_radius=8).grid(row=0, column=2, padx=(8, 0))

        ctk.CTkLabel(advanced_ext, text="虚拟环境目录（venv）").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ctk.CTkEntry(advanced_ext, textvariable=self.venv_path_var).grid(row=1, column=1, sticky=tk.EW, padx=(8, 0), pady=(8, 0))
        ctk.CTkButton(advanced_ext, text="选择", command=self._choose_venv_dir, corner_radius=8).grid(row=1, column=2, padx=(8, 0), pady=(8, 0))

        ctk.CTkLabel(advanced_ext, text="诊断报告路径（diagnose）").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ctk.CTkEntry(advanced_ext, textvariable=self.diag_output_var).grid(row=2, column=1, sticky=tk.EW, padx=(8, 0), pady=(8, 0))

        ctk.CTkLabel(advanced_ext, text="GitHub 仓库 owner / name（update-check）").grid(row=3, column=0, sticky=tk.W, pady=(8, 0))
        owner_repo = ctk.CTkFrame(advanced_ext)
        owner_repo.grid(row=3, column=1, sticky=tk.EW, padx=(8, 0), pady=(8, 0))
        ctk.CTkEntry(owner_repo, textvariable=self.repo_owner_var, width=120).pack(side=tk.LEFT)
        ctk.CTkLabel(owner_repo, text=" /").pack(side=tk.LEFT)
        ctk.CTkEntry(owner_repo, textvariable=self.repo_name_var, width=120).pack(side=tk.LEFT, padx=(4, 0))

        advanced_ext.columnconfigure(1, weight=1)

        option_wrap = ctk.CTkFrame(config_body)
        option_wrap.pack(fill=tk.X, pady=(0, 8))

        groups = CardFrame(option_wrap, title="任务分组")._content_frame
        groups.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        col = 0
        for group_key, var in self.group_vars.items():
            label = f"{self.GROUP_LABELS[group_key]} ({group_key})"
            ctk.CTkCheckBox(groups, text=label, variable=var).grid(row=0, column=col, sticky=tk.W, padx=6)
            col += 1
        ctk.CTkCheckBox(groups, text="包含 AI 可选组（optional_ai）", variable=self.include_ai_var).grid(
            row=1, column=0, columnspan=4, sticky=tk.W, padx=6, pady=(8, 0)
        )
        ctk.CTkButton(groups, text="全选分组", command=self._select_all_groups, corner_radius=8).grid(row=2, column=0, sticky=tk.W, padx=6, pady=(8, 0))
        ctk.CTkButton(groups, text="清空分组", command=self._clear_all_groups, corner_radius=8).grid(row=2, column=1, sticky=tk.W, padx=6, pady=(8, 0))

        advanced = CardFrame(option_wrap, title="高级参数")._content_frame
        advanced.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        ctk.CTkLabel(advanced, text="仅处理包（--only，空格分隔）").grid(row=0, column=0, sticky=tk.W)
        ctk.CTkEntry(advanced, textvariable=self.only_var).grid(row=0, column=1, sticky=tk.EW, padx=(8, 0))

        ctk.CTkCheckBox(advanced, text="跳过 pip 升级", variable=self.skip_pip_var).grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ctk.CTkCheckBox(advanced, text="跳过已安装包", variable=self.skip_installed_var).grid(row=1, column=1, sticky=tk.W, pady=(8, 0))
        ctk.CTkCheckBox(advanced, text="仅预演（dry-run）", variable=self.dry_run_var).grid(row=2, column=0, sticky=tk.W, pady=(8, 0))

        ctk.CTkLabel(advanced, text="镜像源（--index-url）").grid(row=3, column=0, sticky=tk.W, pady=(8, 0))
        ctk.CTkEntry(advanced, textvariable=self.index_url_var).grid(row=3, column=1, sticky=tk.EW, padx=(8, 0), pady=(8, 0))

        ctk.CTkLabel(advanced, text="额外源（空格分隔）").grid(row=4, column=0, sticky=tk.W, pady=(8, 0))
        ctk.CTkEntry(advanced, textvariable=self.extra_index_var).grid(row=4, column=1, sticky=tk.EW, padx=(8, 0), pady=(8, 0))

        ctk.CTkLabel(advanced, text="信任域名（空格分隔）").grid(row=5, column=0, sticky=tk.W, pady=(8, 0))
        ctk.CTkEntry(advanced, textvariable=self.trusted_host_var).grid(row=5, column=1, sticky=tk.EW, padx=(8, 0), pady=(8, 0))

        ctk.CTkLabel(advanced, text="pip 超时/重试").grid(row=6, column=0, sticky=tk.W, pady=(8, 0))
        timeout_retry = ctk.CTkFrame(advanced)
        timeout_retry.grid(row=6, column=1, sticky=tk.EW, padx=(8, 0), pady=(8, 0))
        ctk.CTkEntry(timeout_retry, textvariable=self.pip_timeout_var, width=10).pack(side=tk.LEFT)
        ctk.CTkLabel(timeout_retry, text=" 秒  ").pack(side=tk.LEFT)
        ctk.CTkEntry(timeout_retry, textvariable=self.pip_retries_var, width=10).pack(side=tk.LEFT)
        ctk.CTkLabel(timeout_retry, text=" 次").pack(side=tk.LEFT)
        advanced.columnconfigure(1, weight=1)

        preview = CardFrame(config_body, title="命令预览（执行前可确认）")._content_frame
        preview.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkEntry(preview, textvariable=self.preview_var, state="disabled").pack(fill=tk.X)

        # 运行与日志
        actions = CardFrame(run_tab, title="操作")._content_frame
        actions.pack(fill=tk.X, pady=(0, 8))

        self.run_btn = ctk.CTkButton(actions, text="开始执行", command=self._run, corner_radius=8)
        self.run_btn.pack(side=tk.LEFT)

        self.stop_btn = ctk.CTkButton(actions, text="停止", command=self._stop, state=tk.DISABLED, corner_radius=8)
        self.stop_btn.pack(side=tk.LEFT, padx=8)

        ctk.CTkButton(actions, text="恢复默认", command=self._reset_defaults, corner_radius=8).pack(side=tk.LEFT)
        ctk.CTkButton(actions, text="打开报告", command=self._open_report, corner_radius=8).pack(side=tk.LEFT, padx=8)
        ctk.CTkButton(actions, text="刷新摘要", command=self._refresh_report_summary, corner_radius=8).pack(side=tk.LEFT)
        ctk.CTkButton(actions, text="失败包重试", command=self._retry_failed_from_report, corner_radius=8).pack(side=tk.LEFT, padx=8)
        ctk.CTkButton(actions, text="导出日志", command=self._export_log, corner_radius=8).pack(side=tk.LEFT)
        ctk.CTkButton(actions, text="清空日志", command=self._clear_log, corner_radius=8).pack(side=tk.LEFT)

        self.progress = ctk.CTkProgressBar(actions, mode="indeterminate", width=180)
        self.progress.pack(side=tk.RIGHT, padx=(8, 0))
        ctk.CTkLabel(actions, textvariable=self.status_var).pack(side=tk.RIGHT)

        summary_frame = ctk.CTkFrame(run_tab)
        summary_frame.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkLabel(summary_frame, textvariable=self.summary_var).pack(side=tk.LEFT)

        log_frame = CardFrame(run_tab, title="执行日志")._content_frame
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = ctk.CTkTextbox(log_frame, wrap=tk.WORD, height=400, font=ctk.CTkFont("Cascadia Code", 12),
            fg_color="#FCFCFD",
            text_color="#1D1D1F"
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.log_text.tag_config("ok", foreground="#248A3D")
        self.log_text.tag_config("warn", foreground="#B26A00")
        self.log_text.tag_config("err", foreground="#D70015")
        self.log_text.tag_config("title", foreground="#0A84FF")

        workspace.configure(command=self._on_tab_changed)

    
    def _bind_events(self) -> None:
        """绑定变量变化与快捷键。"""
        tracked = [
            self.mode_var,
            self.python_var,
            self.only_var,
            self.json_var,
            self.snapshot_var,
            self.wheel_dir_var,
            self.venv_path_var,
            self.diag_output_var,
            self.repo_owner_var,
            self.repo_name_var,
            self.dark_mode_var,
            self.index_url_var,
            self.extra_index_var,
            self.trusted_host_var,
            self.pip_timeout_var,
            self.pip_retries_var,
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

    def _settings_path(self) -> Path:
        """返回用户配置保存路径。"""
        if os.name == "nt":
            base = os.environ.get("APPDATA") or str(Path.home())
            return Path(base) / self.APP_NAME / self.SETTINGS_FILE_NAME
        return Path.home() / ".config" / self.APP_NAME / self.SETTINGS_FILE_NAME

    def _collect_settings(self) -> Dict:
        return {
            "mode": self.mode_var.get(),
            "python": self.python_var.get(),
            "only": self.only_var.get(),
            "json": self.json_var.get(),
            "snapshot": self.snapshot_var.get(),
            "index_url": self.index_url_var.get(),
            "extra_index": self.extra_index_var.get(),
            "trusted_host": self.trusted_host_var.get(),
            "wheel_dir": self.wheel_dir_var.get(),
            "venv_path": self.venv_path_var.get(),
            "diag_output": self.diag_output_var.get(),
            "repo_owner": self.repo_owner_var.get(),
            "repo_name": self.repo_name_var.get(),
            "dark_mode": self.dark_mode_var.get(),
            "pip_timeout": self.pip_timeout_var.get(),
            "pip_retries": self.pip_retries_var.get(),
            "include_ai": self.include_ai_var.get(),
            "skip_pip": self.skip_pip_var.get(),
            "skip_installed": self.skip_installed_var.get(),
            "dry_run": self.dry_run_var.get(),
            "groups": {key: var.get() for key, var in self.group_vars.items()},
            "preset": self.preset_var.get(),
            "page": self.active_page_var.get(),
        }

    def _schedule_settings_save(self) -> None:
        if self.is_closing or self._loading_settings:
            return
        if self.settings_job_id:
            try:
                self.root.after_cancel(self.settings_job_id)
            except tk.TclError:
                pass
        self.settings_job_id = self.root.after(self.SAVE_SETTINGS_DELAY_MS, self._save_settings)

    def _save_settings(self) -> None:
        self.settings_job_id = None
        if self.is_closing:
            return

        path = self._settings_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._collect_settings(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            self._append_log(f"[警告] 保存配置失败：{type(e).__name__}: {e}")

    def _load_settings(self) -> None:
        self._loading_settings = True
        try:
            path = self._settings_path()
            if not path.exists():
                return

            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return

            self.mode_var.set(str(data.get("mode", self.mode_var.get())))
            self.python_var.set(str(data.get("python", self.python_var.get())))
            self.only_var.set(str(data.get("only", self.only_var.get())))
            self.json_var.set(str(data.get("json", self.json_var.get())))
            self.snapshot_var.set(str(data.get("snapshot", self.snapshot_var.get())))
            self.wheel_dir_var.set(str(data.get("wheel_dir", self.wheel_dir_var.get())))
            self.venv_path_var.set(str(data.get("venv_path", self.venv_path_var.get())))
            self.diag_output_var.set(str(data.get("diag_output", self.diag_output_var.get())))
            self.repo_owner_var.set(str(data.get("repo_owner", self.repo_owner_var.get())))
            self.repo_name_var.set(str(data.get("repo_name", self.repo_name_var.get())))
            self.dark_mode_var.set(bool(data.get("dark_mode", self.dark_mode_var.get())))
            self.index_url_var.set(str(data.get("index_url", self.index_url_var.get())))
            self.extra_index_var.set(str(data.get("extra_index", self.extra_index_var.get())))
            self.trusted_host_var.set(str(data.get("trusted_host", self.trusted_host_var.get())))
            self.pip_timeout_var.set(str(data.get("pip_timeout", self.pip_timeout_var.get())))
            self.pip_retries_var.set(str(data.get("pip_retries", self.pip_retries_var.get())))
            self.include_ai_var.set(bool(data.get("include_ai", self.include_ai_var.get())))
            self.skip_pip_var.set(bool(data.get("skip_pip", self.skip_pip_var.get())))
            self.skip_installed_var.set(bool(data.get("skip_installed", self.skip_installed_var.get())))
            self.dry_run_var.set(bool(data.get("dry_run", self.dry_run_var.get())))

            groups = data.get("groups") or {}
            if isinstance(groups, dict):
                for key, var in self.group_vars.items():
                    if key in groups:
                        var.set(bool(groups.get(key)))

            preset = str(data.get("preset", self.preset_var.get()))
            if preset in self.PRESETS:
                self.preset_var.set(preset)

            page = str(data.get("page", self.active_page_var.get()))
            if page in self.page_frames:
                self.active_page_var.set(page)
        finally:
            self._loading_settings = False

    def _show_page(self, page_id: str, **kwargs) -> None:
        if page_id not in self.page_frames:
            return
        self.active_page_var.set(page_id)
        mapping = {"welcome": "欢迎", "config": "配置中心", "run": "运行与日志", "help": "说明书", "about": "关于"}
        if mapping.get(page_id):
            try:
                self.workspace.set(mapping[page_id])
            except Exception:
                pass
        self._sync_nav_state()
        self._update_page_hint(page_id)
        self._play_page_transition_animation()
        self._schedule_settings_save()

    def _play_page_transition_animation(self) -> None:
        if self.proc is not None:
            return
        self.badge_state_var.set("状态: 切换中.")

        def step2() -> None:
            if self.proc is None and not self.is_closing:
                self.badge_state_var.set("状态: 切换中..")

        def step3() -> None:
            if self.proc is None and not self.is_closing:
                self.badge_state_var.set("状态: 空闲")

        self.root.after(80, step2)
        self.root.after(180, step3)

    def _update_page_hint(self, page_id: str) -> None:
        hint_map = {
            "welcome": "欢迎页：快速了解功能、进入配置或直接开始执行。",
            "config": "配置中心：适合调整预设、Python 路径、分组和镜像参数。",
            "run": "运行与日志：查看执行进度、结果摘要和详细日志。",
            "help": "说明书：解释每个功能的用途与推荐使用方式。",
            "about": "关于：查看作者信息、版本与项目链接。",
        }
        self.page_hint.configure(text=hint_map.get(page_id, ""))
        self._update_top_badges()

    def _sync_nav_state(self) -> None:
        active = self.active_page_var.get()
        for page_id, button in self.nav_buttons.items():
            try:
                pass # removed style config
            except tk.TclError:
                pass

    def _on_tab_changed(self, _event=None) -> None:
        try:
            tab_name = self.workspace.get()
        except Exception:
            return
        mapping = {"欢迎": "welcome", "配置中心": "config", "运行与日志": "run", "说明书": "help", "关于": "about"}
        page_id = mapping.get(tab_name)
        if page_id:
            self.active_page_var.set(page_id)
            self._sync_nav_state()
            self._update_page_hint(page_id)
            self._schedule_settings_save()

    def _mark_settings_dirty(self) -> None:
        self._schedule_settings_save()

    def _toggle_theme(self) -> None:
        self.dark_mode_var.set(not self.dark_mode_var.get())
        # #  - Removed for CustomTkinter - Removed for CustomTkinter
        self._sync_nav_state()
        self._update_top_badges()
        self._schedule_settings_save()
        self._append_log(f"[主题] 已切换为{'深色' if self.dark_mode_var.get() else '浅色'}模式")

    def _open_repo_home(self) -> None:
        webbrowser.open(f"https://github.com/{self.repo_owner_var.get().strip() or self.REPO_OWNER}/{self.repo_name_var.get().strip() or self.REPO_NAME}")

    def _open_repo_releases(self) -> None:
        webbrowser.open(f"https://github.com/{self.repo_owner_var.get().strip() or self.REPO_OWNER}/{self.repo_name_var.get().strip() or self.REPO_NAME}/releases")

    def _open_author_home(self) -> None:
        webbrowser.open(self.AUTHOR_GITHUB)

    def _quick_set_mode(self, mode: str) -> None:
        if mode not in {"all", "install", "check", "snapshot", "restore", "offline", "venv", "diagnose", "update-check"}:
            return
        self.mode_var.set(mode)
        self._show_page("config")
        self._update_top_badges()
        self._append_log(f"[快捷] 已切换到模式：{mode}")

    def _on_apply_preset(self) -> None:
        self._apply_preset(self.preset_var.get())

    def _apply_template(self, template_key: str) -> None:
        template = self.TEMPLATES.get(template_key)
        if not template:
            return
        preset_name = template.get("preset")
        if preset_name in self.PRESETS:
            self._apply_preset(preset_name)
        mode_map = {
            "data_analysis": "all",
            "research": "all",
            "office": "install",
            "offline": "offline",
            "diagnose": "diagnose",
        }
        if template_key in mode_map:
            self.mode_var.set(mode_map[template_key])
        self._append_log(f"[模板] 已应用：{template.get('title')} - {template.get('description')}")
        self._show_page("config")

    def _build_manual_text(self) -> str:
        return (
            "EnvTool 说明书\n"
            "\n"
            "1. 主要功能\n"
            "- 安装/检查：按分组安装常用 Python 包，并在完成后检查是否可导入。\n"
            "- 环境快照：导出当前 Python 环境的版本清单。\n"
            "- 从快照恢复：按快照文件中的锁定版本重新安装。\n"
            "- 离线安装：使用本地 wheel 仓库目录完成安装，适合无外网环境。\n"
            "- 创建虚拟环境：一键创建 venv，避免污染系统 Python。\n"
            "- 诊断报告：自动收集 Python、pip、网络、包检查结果。\n"
            "- 检查更新：访问 GitHub Releases，提示是否有新版本与下载地址。\n"
            "\n"
            "2. 推荐使用流程\n"
            "- 首次使用：在欢迎页查看作者、模板和快速开始。\n"
            "- 日常操作：在配置中心选择模板，修改路径与参数，再执行。\n"
            "- 排障：使用诊断报告页生成可分享给维护者的报告。\n"
            "\n"
            "3. 模板中心\n"
            "- 数据分析模板：面向 pandas / numpy / matplotlib 场景。\n"
            "- 科研模板：面向科学计算、统计分析与可视化。\n"
            "- 办公模板：面向轻量办公与文档处理。\n"
            "- 离线部署模板：面向无外网安装。\n"
            "- 诊断模板：面向排障和环境核查。\n"
            "\n"
            "4. 说明\n"
            "- 本工具会自动探测可用 Python，也可手动指定目标解释器。\n"
            "- 建议在虚拟环境中执行，以减少对系统环境的影响。\n"
            "- 如需更新检查，请确保网络可访问 GitHub。\n"
            f"- 作者：{self.AUTHOR_NAME} ({self.AUTHOR_EMAIL})\n"
            f"- 组织：{self.ORGANIZATION}\n"
        )

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

    def _check_update_ui(self) -> None:
        self.update_status_var.set("更新：检查中...")

        def worker() -> None:
            try:
                info = self._run_update_check()
                self.root.after(0, lambda: self._present_update_info(info, interactive=True))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("检查更新失败", f"{type(e).__name__}: {e}"))
                self.root.after(0, lambda: self.update_status_var.set("更新：检查失败"))

        threading.Thread(target=worker, daemon=True).start()

    def _present_update_info(self, info: Dict, interactive: bool = False) -> None:
        if not info.get("ok"):
            self.update_status_var.set("更新：检查失败")
            if interactive:
                messagebox.showwarning("检查更新", "暂时无法获取最新版本信息。")
            return

        latest_version = info.get("latest_version") or "未知"
        if info.get("update_available"):
            self.update_status_var.set(f"更新：发现新版本 {latest_version}")
            assets = info.get("assets") or []
            asset_lines = "\n".join(f"- {a.get('name')}: {a.get('browser_download_url')}" for a in assets if isinstance(a, dict))
            msg = f"发现新版本：{latest_version}\n\nRelease：{info.get('html_url', '')}\n\n资产：\n{asset_lines or '无'}"
            if interactive and messagebox.askyesno("发现更新", "已发现新版本，是否打开 Release 页面？"):
                url = info.get("html_url")
                if url:
                    webbrowser.open(str(url))
            if interactive:
                messagebox.showinfo("更新信息", msg)
        else:
            self.update_status_var.set(f"更新：已是最新 {latest_version}")
            if interactive:
                messagebox.showinfo("检查更新", f"当前已是最新版本：{latest_version}")

    def _start_silent_update_check(self) -> None:
        if self.is_closing:
            return

        def worker() -> None:
            try:
                info = self._run_update_check()
                if info.get("ok") and info.get("update_available"):
                    latest = info.get("latest_version") or "未知"
                    self.log_queue.put(f"[更新] 发现新版本：{latest}")
                    self.log_queue.put(f"[更新] Release：{info.get('html_url', '')}")
                    self.log_queue.put("[更新] 可在欢迎页点击“检查更新”查看资产下载地址。")
                self.root.after(0, lambda: self._present_update_info(info, interactive=False))
            except Exception:
                # 静默失败，不打扰用户
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _run_update_check(self) -> Dict:
        from urllib.request import Request, urlopen

        owner = self.repo_owner_var.get().strip() or self.REPO_OWNER
        name = self.repo_name_var.get().strip() or self.REPO_NAME
        url = f"https://api.github.com/repos/{owner}/{name}/releases/latest"
        req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"EnvTool/{self.APP_VERSION}"})
        with urlopen(req, timeout=8) as resp:
            latest = json.loads(resp.read().decode("utf-8"))

        latest_tag = str(latest.get("tag_name", "")).strip()
        return {
            "ok": True,
            "current_version": self.APP_VERSION,
            "latest_version": latest_tag or None,
            "update_available": bool(latest_tag and latest_tag.lstrip("vV") != self.APP_VERSION.lstrip("vV")),
            "release_name": latest.get("name"),
            "html_url": latest.get("html_url"),
            "assets": [
                {
                    "name": asset.get("name"),
                    "browser_download_url": asset.get("browser_download_url"),
                    "size": asset.get("size"),
                }
                for asset in latest.get("assets", [])
                if isinstance(asset, dict)
            ],
        }

    def _select_all_groups(self) -> None:
        for var in self.group_vars.values():
            var.set(True)

    def _clear_all_groups(self) -> None:
        for var in self.group_vars.values():
            var.set(False)

    def _on_option_changed(self, *_args) -> None:
        self._refresh_cmd_preview()
        self._update_top_badges()
        self._schedule_settings_save()

    def _report_callback_exception(self, exc, val, tb) -> None:  # type: ignore[no-untyped-def]
        """拦截 Tk 回调异常，避免重复弹窗。"""
        details = "".join(traceback.format_exception(exc, val, tb))
        self._append_log("[异常] GUI 回调异常：\n" + details.strip())

        if not self._exception_dialog_shown and not self.is_closing:
            self._exception_dialog_shown = True
            messagebox.showerror(
                "EnvTool GUI 异常",
                "发生了未处理异常，详情已写入日志。\n请导出日志并反馈给开发者。",
            )

    @staticmethod
    def _split_cmd(text: str) -> List[str]:
        raw = (text or "").strip()
        if not raw:
            return []
        try:
            return shlex.split(raw, posix=False)
        except Exception:
            return [raw]

    @staticmethod
    def _subprocess_env() -> Dict[str, str]:
        """准备干净的子进程环境变量，避免 PyInstaller 环境污染其他 Python。"""
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            meipass_norm = os.path.normcase(os.path.abspath(meipass))
            paths = env.get("PATH", "").split(os.pathsep)
            clean_paths = [p for p in paths if p.strip() and os.path.normcase(os.path.abspath(p)) != meipass_norm]
            env["PATH"] = os.pathsep.join(clean_paths)
            
        return env

    @staticmethod
    def _subprocess_hidden_kwargs() -> Dict:
        """尽量隐藏 Windows 下的控制台窗口，避免闪烁。"""
        kwargs: Dict = {}
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return kwargs

    def _can_run_python(self, candidate: List[str]) -> bool:
        """判断某个 Python 命令是否可执行。"""
        if not candidate:
            return False
        try:
            result = subprocess.run(
                candidate + ["-c", "import socket, urllib.request, sys;print(sys.executable)"],
                check=False,
                capture_output=True,
                env=self._subprocess_env(),
                text=True,
                timeout=8,
                **self._subprocess_hidden_kwargs(),
            )
            return result.returncode == 0
        except Exception:
            return False

    def _discover_py_launcher_paths(self) -> List[List[str]]:
        if not shutil.which("py"):
            return []

        try:
            result = subprocess.run(
                ["py", "-0p"],
                check=False,
                text=True,
                capture_output=True,
                env=self._subprocess_env(),
                timeout=8,
                **self._subprocess_hidden_kwargs(),
            )
        except Exception:
            return []

        text = (result.stdout or "") + "\n" + (result.stderr or "")
        cmds: List[List[str]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.search(r"([A-Za-z]:\\[^\s]+python\.exe)", line, re.IGNORECASE)
            if match:
                cmds.append([match.group(1)])
        return cmds

    def _discover_common_python_paths(self) -> List[List[str]]:
        roots: List[Path] = []
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            roots.append(Path(local_app) / "Programs" / "Python")

        pf = os.environ.get("ProgramFiles")
        if pf:
            roots.append(Path(pf) / "Python")

        pf86 = os.environ.get("ProgramFiles(x86)")
        if pf86:
            roots.append(Path(pf86) / "Python")

        candidates: List[List[str]] = []
        for root in roots:
            if not root.exists():
                continue
            for exe in root.glob("Python*/python.exe"):
                candidates.append([str(exe)])
        return candidates

    def _resolve_runner_python(self) -> List[str]:
        """选择用于启动 env_manager.py 的 Python 解释器。"""
        if not getattr(sys, "frozen", False):
            return [sys.executable]

        candidates: List[List[str]] = []

        env_runner = self._split_cmd(os.environ.get("ENV_TOOL_RUNNER_PYTHON", ""))
        if env_runner:
            candidates.append(env_runner)

        env_target = self._split_cmd(os.environ.get("ENV_TOOL_PYTHON", ""))
        if env_target:
            candidates.append(env_target)

        if shutil.which("py"):
            candidates.append(["py", "-3"])
        if shutil.which("python"):
            candidates.append(["python"])
        if shutil.which("python3"):
            candidates.append(["python3"])

        candidates.extend(self._discover_py_launcher_paths())
        candidates.extend(self._discover_common_python_paths())

        deduped: List[List[str]] = []
        seen = set()
        for cmd in candidates:
            key = "\u0000".join(part.lower() for part in cmd)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(cmd)

        for cmd in deduped:
            if self._can_run_python(cmd):
                return cmd

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

    def _choose_snapshot_path(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="选择快照输出路径",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile=self.snapshot_var.get().strip() or "requirements_snapshot.txt",
        )
        if selected:
            self.snapshot_var.set(selected)

    def _choose_wheel_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择 wheel 仓库目录")
        if selected:
            self.wheel_dir_var.set(selected)

    def _choose_venv_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择虚拟环境目录")
        if selected:
            self.venv_path_var.set(selected)

    def _validate_inputs(self) -> None:
        """执行前参数校验，提前给出友好提示。"""
        python_path = self.python_var.get().strip()
        if python_path and not Path(python_path).exists():
            raise ValueError("目标 Python 路径不存在，请重新选择。")

        mode = self.mode_var.get()
        if mode in {"snapshot", "restore"} and not self.snapshot_var.get().strip():
            raise ValueError("快照模式需要填写输出文件路径。")

        if mode == "offline" and not self.wheel_dir_var.get().strip():
            raise ValueError("离线安装需要填写 wheel 仓库目录。")

        if mode == "venv" and not self.venv_path_var.get().strip():
            raise ValueError("虚拟环境模式需要填写 venv 目录。")

        if mode == "diagnose" and not self.diag_output_var.get().strip():
            raise ValueError("诊断模式需要填写诊断报告路径。")

        if mode == "update-check":
            if not self.repo_owner_var.get().strip() or not self.repo_name_var.get().strip():
                raise ValueError("检查更新需要填写 GitHub 仓库 owner 和 name。")

        only_text = self.only_var.get().strip()
        if mode not in {"snapshot", "restore", "update-check"} and not only_text:
            selected_groups = [name for name, var in self.group_vars.items() if var.get()]
            if not selected_groups:
                raise ValueError("请至少勾选一个分组，或在 --only 中指定包名。")

        for text, name in [
            (self.pip_timeout_var.get().strip(), "pip 超时"),
            (self.pip_retries_var.get().strip(), "pip 重试"),
        ]:
            if text and (not text.isdigit() or int(text) < 0):
                raise ValueError(f"{name} 需为非负整数。")

    def _build_cmd(self, strict_runner: bool = True) -> List[str]:
        """把当前界面状态转换为命令行参数。"""
        if not self.entry_script.exists():
            raise FileNotFoundError(f"未找到入口脚本: {self.entry_script}")

        self._validate_inputs()
        if strict_runner:
            runner = self._resolve_runner_python()
        else:
            runner = self._preview_runner_text()

        cmd: List[str] = [*runner, str(self.entry_script), "--mode", self.mode_var.get()]

        selected_groups = [name for name, var in self.group_vars.items() if var.get()]
        only_text = self.only_var.get().strip()

        if self.mode_var.get() not in {"snapshot", "restore", "update-check"}:
            if only_text:
                cmd.extend(["--only", *only_text.split()])
            else:
                cmd.extend(["--groups", *selected_groups])

        if self.include_ai_var.get() and self.mode_var.get() not in {"restore", "update-check"}:
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
        if json_path and self.mode_var.get() != "diagnose":
            cmd.extend(["--json-report", json_path])

        snapshot_path = self.snapshot_var.get().strip()
        if snapshot_path and self.mode_var.get() in {"snapshot", "restore"}:
            cmd.extend(["--snapshot-file", snapshot_path])

        wheel_dir = self.wheel_dir_var.get().strip()
        if wheel_dir and self.mode_var.get() == "offline":
            cmd.extend(["--wheel-dir", wheel_dir])

        venv_path = self.venv_path_var.get().strip()
        if venv_path and self.mode_var.get() == "venv":
            cmd.extend(["--venv-path", venv_path])

        diag_output = self.diag_output_var.get().strip()
        if diag_output and self.mode_var.get() == "diagnose":
            cmd.extend(["--diag-output", diag_output])

        if self.mode_var.get() == "update-check":
            cmd.extend(["--repo-owner", self.repo_owner_var.get().strip(), "--repo-name", self.repo_name_var.get().strip()])

        index_url = self.index_url_var.get().strip()
        if index_url:
            cmd.extend(["--index-url", index_url])

        extra_index = self.extra_index_var.get().strip()
        if extra_index:
            cmd.extend(["--extra-index-url", *extra_index.split()])

        trusted_host = self.trusted_host_var.get().strip()
        if trusted_host:
            cmd.extend(["--trusted-host", *trusted_host.split()])

        pip_timeout = self.pip_timeout_var.get().strip()
        if pip_timeout:
            cmd.extend(["--pip-timeout", pip_timeout])

        pip_retries = self.pip_retries_var.get().strip()
        if pip_retries:
            cmd.extend(["--pip-retries", pip_retries])

        return cmd

    def _preview_runner_text(self) -> List[str]:
        """仅用于命令预览，不执行任何探测。"""
        env_runner = self._split_cmd(os.environ.get("ENV_TOOL_RUNNER_PYTHON", ""))
        if env_runner:
            return env_runner

        env_target = self._split_cmd(os.environ.get("ENV_TOOL_PYTHON", ""))
        if env_target:
            return env_target

        if getattr(sys, "frozen", False):
            return ["python"]
        return [sys.executable]

    def _refresh_cmd_preview(self) -> None:
        """实时刷新“命令预览”行。"""
        try:
            cmd = self._build_cmd(strict_runner=False)
            self.preview_var.set(" ".join(cmd))
        except Exception as e:
            self.preview_var.set(f"参数待完善：{e}")

    def _set_running_state(self, running: bool) -> None:
        """统一切换按钮状态与进度条状态。"""
        self.run_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        self.status_var.set("运行中..." if running else "已完成")
        self._update_top_badges()
        if running:
            self.running_anim_phase = 0
            self._stop_running_badge_animation()
            self._animate_running_badge()
            self.progress.start()
        else:
            self._stop_running_badge_animation()
            self.badge_state_var.set("状态: 空闲")
            self.progress.stop()

    def _run(self) -> None:
        """点击“开始执行”后触发。"""
        if self.proc is not None:
            messagebox.showinfo("提示", "任务正在运行中")
            return

        try:
            cmd = self._build_cmd(strict_runner=True)
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
            run_env = self._subprocess_env()
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
                **self._subprocess_hidden_kwargs(),
            )

            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                self.log_queue.put(line.rstrip("\n"))

            code = self.proc.wait()
            self.log_queue.put(f"__TASK_EXIT__:{code}")
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
            self.log_text.configure(state="normal")
            self.log_text.configure(state='normal')
            self.log_text.insert(tk.END, text + "\n", tag)
            self.log_text.configure(state='disabled')
            self.log_text.configure(state="disabled")
        else:
            self.log_text.configure(state="normal")
            self.log_text.configure(state='normal')
            self.log_text.insert(tk.END, text + "\n")
            self.log_text.configure(state='disabled')
            self.log_text.configure(state="disabled")
        self.log_text.see(tk.END)

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.configure(state='normal')
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state='disabled')
        self.log_text.configure(state="disabled")

    def _reset_defaults(self) -> None:
        """恢复默认参数。"""
        if self.proc is not None:
            messagebox.showinfo("提示", "请先停止当前任务")
            return

        self.mode_var.set("all")
        self.python_var.set("")
        self.only_var.set("")
        self.json_var.set("report.json")
        self.snapshot_var.set("requirements_snapshot.txt")
        self.index_url_var.set("")
        self.extra_index_var.set("")
        self.trusted_host_var.set("")
        self.pip_timeout_var.set("")
        self.pip_retries_var.set("")
        self.include_ai_var.set(False)
        self.skip_pip_var.set(False)
        self.skip_installed_var.set(True)
        self.dry_run_var.set(False)

        for key, var in self.group_vars.items():
            var.set(key in {"daily_common", "scientific_research", "visualization", "data_processing"})

        self._append_log("[操作] 已恢复默认参数")

    def _poll_log(self) -> None:
        """主线程轮询日志队列。"""
        if self.is_closing:
            return

        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break

            if item == "__TASK_DONE__":
                self._set_running_state(False)
                if self._resolve_report_path().exists():
                    self._refresh_report_summary()
                elif self.last_exit_code not in (None, 0):
                    self.summary_var.set(f"结果摘要：任务失败，退出码 {self.last_exit_code}")
                else:
                    self.summary_var.set("结果摘要：任务已结束，未生成报告")
                continue

            if item.startswith("__TASK_EXIT__:"):
                try:
                    self.last_exit_code = int(item.split(":", 1)[1])
                except Exception:
                    self.last_exit_code = None
                continue

            self._append_log(item)

        try:
            self.poll_job_id = self.root.after(self.POLL_MS, self._poll_log)
        except tk.TclError:
            self.poll_job_id = None

    def _on_close(self) -> None:
        """统一关闭流程，避免关闭时 Tk 回调抛异常导致重复弹窗。"""
        if self.is_closing:
            return
        self.is_closing = True

        self._stop_running_badge_animation()

        if self.poll_job_id:
            try:
                self.root.after_cancel(self.poll_job_id)
            except tk.TclError:
                pass
            self.poll_job_id = None

        if self.settings_job_id:
            try:
                self.root.after_cancel(self.settings_job_id)
            except tk.TclError:
                pass
            self.settings_job_id = None

        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass

        try:
            self.root.destroy()
        except tk.TclError:
            pass


def main() -> int:
    root = ctk.CTk()
    EnvToolGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
