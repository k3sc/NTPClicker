import tkinter as tk
from datetime import datetime
import threading
import time
import socket
import struct
import ctypes
import sys, os


def resource_path(relative_path):
    """获取 PyInstaller 打包后的资源路径"""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)  # 修改：从当前目录读取，而非上级目录


class NTPClickerUI:
    # ===== 配色方案 =====
    COLORS = {
        "bg_main": "#F0F2F5",
        "title_bar": "#FFFFFF",
        "title_bar_shadow": "#E6E9ED",
        "text_primary": "#2C3E50",
        "text_secondary": "#95A5A6",
        "accent": "#3498DB",
        "accent_hover": "#2980B9",
        "accent_pressed": "#1F618D",
        "success": "#27AE60",
        "success_pressed": "#1E8449",
        "error": "#E74C3C",
        "error_pressed": "#C0392B",
        "btn_close_hover": "#E74C3C",
        "btn_close_pressed": "#C0392B",
        "border": "#DFE6E9",
        "card_bg": "#FFFFFF",
        "card_shadow": "#E0E6ED",
        "window_border": "#CCCCCC"  # 新增窗口边框颜色
    }

    def __init__(self, root):
        self.root = root
        self.root.title("NTP同步点击器")  # 任务栏显示的名称

        # ========== 关键1：设置窗口图标 ==========
        try:
            # 优先尝试ICO格式（任务栏显示效果更好），也支持PNG
            icon_path = resource_path("sjz16.ico")  # 建议用ico格式，尺寸推荐32x32/64x64
            if not os.path.exists(icon_path):
                icon_path = resource_path("sjz16.png")  # 备用PNG路径

            # 设置窗口图标（同时影响标题栏和任务栏）
            self.app_icon = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, tk.PhotoImage(file= resource_path("sjz.ico")))  # True表示设置为应用程序默认图标

            # 兼容处理：设置任务栏图标句柄（针对overrideredirect窗口）
            hwnd = self.root.winfo_id()
            # 加载图标文件到系统
            icon_handle = ctypes.windll.user32.LoadImageW(
                0, icon_path, 1, 0, 0, 0x10  # 1=ICON, 0x10=LR_LOADFROMFILE
            )
            if icon_handle:
                ctypes.windll.user32.SendMessageW(
                    hwnd, 0x80, 0, icon_handle  # 0x80=WM_SETICON
                )
                ctypes.windll.user32.SendMessageW(
                    hwnd, 0x80, 1, icon_handle  # 同时设置大图标和小图标
                )

        except Exception as e:
            print(f"图标加载失败: {e}")  # 仅打印错误，不影响程序运行

        # ========== 关键：让任务栏正常显示 ==========
        self.root.overrideredirect(True)
        self.root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        style = style & ~0x80  # 移除 TOOLWINDOW
        style = style | 0x40000  # 添加 APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        self.root.withdraw()
        self.root.after(10, self.root.deiconify)

        # ========== 窗口大小与位置 ==========
        self.width = 400
        self.height = 200
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - self.width) // 2
        y = (screen_height - self.height) // 2
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

        # ===== 还原窗口背景 =====
        self.root.configure(bg=self.COLORS["bg_main"])

        self.root.attributes('-alpha', 1.0)

        # 状态变量
        self.offset = 0
        self.target_second = None
        self.triggered = False
        self.last_sync = 0
        self.is_topmost = False
        self.drag_start_x = 0
        self.drag_start_y = 0

        # 新增：记录上一次的秒数，防止同一秒重复触发
        self.last_second = -1

        # 字体
        self.font_time = ("Consolas", 28, "bold")
        self.font_title = ("Microsoft YaHei UI", 9, "bold")
        self.font_icon = ("Microsoft YaHei UI", 10)
        self.font_btn = ("Microsoft YaHei UI", 9, "bold")

        self._create_custom_titlebar()
        self._create_content()

        # 初始化
        self.sync_ntp()
        self.update_clock()

        # 默认置顶
        self.toggle_topmost()

    # ===== 自定义标题栏 =====
    def _create_custom_titlebar(self):
        self.title_bar = tk.Frame(
            self.root, bg=self.COLORS["title_bar"], height=32, relief=tk.FLAT, borderwidth=0
        )
        self.title_bar.pack(fill=tk.X, side=tk.TOP)
        tk.Frame(self.title_bar, bg=self.COLORS["title_bar_shadow"], height=1).pack(side=tk.BOTTOM, fill=tk.X)

        # 标题
        title_frame = tk.Frame(self.title_bar, bg=self.COLORS["title_bar"])
        title_frame.pack(side=tk.LEFT, padx=3, fill=tk.Y)
        # 使用加载好的图标
        tk.Label(title_frame, image=self.app_icon, bg=self.COLORS["title_bar"]).pack(side=tk.LEFT, padx=(0, 0))
        tk.Label(title_frame, text="NTP同步点击器    by:七月", font=self.font_title,
                 fg=self.COLORS["text_primary"], bg=self.COLORS["title_bar"]).pack(side=tk.LEFT)

        # 控制按钮 - 修改：移除右侧padx，调整布局使其紧贴边缘
        controls_frame = tk.Frame(self.title_bar, bg=self.COLORS["title_bar"])
        # 关键修改：padx改为0，添加东对齐
        controls_frame.pack(side=tk.RIGHT, padx=0, fill=tk.Y, anchor=tk.E)
        self.btn_pin = self._create_title_btn(
            controls_frame, "📌", self.toggle_topmost,
            self.COLORS["text_secondary"], self.COLORS["accent"], self.COLORS["accent_pressed"]
        )
        # 关键修改：移除padx，让按钮紧挨
        self.btn_pin.pack(side=tk.LEFT, padx=0)
        self.btn_close = self._create_title_btn(
            controls_frame, "✕", self.close_window,
            self.COLORS["text_secondary"], self.COLORS["btn_close_hover"], self.COLORS["btn_close_pressed"],
            is_close=True
        )
        # 关键修改：移除padx，让按钮紧挨
        self.btn_close.pack(side=tk.LEFT, padx=0)

        # 拖拽绑定
        self.title_bar.bind("<ButtonPress-1>", self.start_drag)
        self.title_bar.bind("<B1-Motion>", self.do_drag)
        for w in self.title_bar.winfo_children():
            w.bind("<ButtonPress-1>", self.start_drag)
            w.bind("<B1-Motion>", self.do_drag)

    def _create_title_btn(self, parent, text, command, n, h, p, is_close=False):
        # 关键修改：调整按钮宽度为2，移除内边距，使其更紧凑
        btn = tk.Button(parent, text=text, font=self.font_icon, bg=self.COLORS["title_bar"], fg=n,
                        relief="flat", cursor="hand2", width=2, height=1, borderwidth=0, highlightthickness=0,
                        command=command)

        def on_enter(e):
            if is_close:
                btn.config(fg="#fff", bg=h)
            else:
                btn.config(fg=h if text != "📌" or not self.is_topmost else self.COLORS["accent"])

        def on_leave(e):
            if is_close:
                btn.config(fg=n, bg=self.COLORS["title_bar"])
            else:
                btn.config(fg=self.COLORS["accent"] if text == "📌" and self.is_topmost else n)

        def on_press(e):
            if is_close:
                btn.config(bg=p)
            else:
                btn.config(fg=p)

        def on_release(e):
            on_enter(e)

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        btn.bind("<ButtonPress-1>", on_press)
        btn.bind("<ButtonRelease-1>", on_release)
        return btn

    def _create_custom_button(self, parent, text, command, bg, h, p, fg="white"):
        btn = tk.Button(parent, text=text, font=self.font_btn, bg=bg, fg=fg, relief="flat", cursor="hand2",
                        padx=12, pady=3, borderwidth=0, highlightthickness=0, command=command)

        def on_enter(e): btn.config(bg=h)

        def on_leave(e): btn.config(bg=bg)

        def on_press(e): btn.config(bg=p)

        def on_release(e): btn.config(bg=h)

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        btn.bind("<ButtonPress-1>", on_press)
        btn.bind("<ButtonRelease-1>", on_release)
        return btn

    # ===== 主界面内容 =====
    def _create_content(self):
        content = tk.Frame(self.root, bg=self.COLORS["bg_main"])
        content.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        # 时间卡片
        time_card = tk.Frame(content, bg=self.COLORS["card_bg"], relief=tk.FLAT, borderwidth=1,
                             highlightbackground=self.COLORS["card_shadow"],
                             highlightcolor=self.COLORS["card_shadow"],
                             highlightthickness=1)
        time_card.pack(pady=(5, 10), padx=5, fill=tk.X)
        time_inner = tk.Frame(time_card, bg=self.COLORS["card_bg"])
        time_inner.pack(padx=15, pady=8)
        self.time_label = tk.Label(time_inner, text="--:--:--.---", font=self.font_time,
                                   fg=self.COLORS["text_primary"], bg=self.COLORS["card_bg"])
        self.time_label.pack()

        # 输入区
        input_row = tk.Frame(content, bg=self.COLORS["bg_main"])
        input_row.pack(pady=5)
        tk.Label(input_row, text="触发秒:",
                 font=("Microsoft YaHei UI", 9),
                 fg=self.COLORS["text_secondary"], bg=self.COLORS["bg_main"]
                 ).pack(side=tk.LEFT, padx=(0, 5))

        entry_frame = tk.Frame(input_row, bg=self.COLORS["border"])
        entry_frame.pack(side=tk.LEFT, ipady=1)
        self.entry = tk.Entry(
            entry_frame, width=4, justify="center", font=("Consolas", 16),
            bg="#fff", fg=self.COLORS["text_primary"],
            insertbackground=self.COLORS["accent"], relief="flat",
            selectbackground=self.COLORS["accent"], selectforeground="white",
            borderwidth=0, highlightthickness=0
        )
        self.entry.pack(ipady=2, padx=1)
        self.set_btn = self._create_custom_button(input_row, "设定", self.set_target,
                                                  self.COLORS["accent"], self.COLORS["accent_hover"],
                                                  self.COLORS["accent_pressed"])
        self.set_btn.pack(side=tk.LEFT, padx=10)

        # 状态栏
        self.info = tk.Label(content, text="正在同步...", font=("Microsoft YaHei UI", 8),
                             fg=self.COLORS["text_secondary"], bg=self.COLORS["bg_main"], anchor="w")
        self.info.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

    # ===== 窗口控制 =====
    def start_drag(self, e):
        self.drag_start_x = e.x
        self.drag_start_y = e.y

    def do_drag(self, e):
        dx = e.x - self.drag_start_x
        dy = e.y - self.drag_start_y
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")

    def close_window(self):
        self.root.destroy()

    def toggle_topmost(self):
        self.is_topmost = not self.is_topmost
        self.root.attributes('-topmost', self.is_topmost)
        if self.is_topmost:
            self.btn_pin.config(fg=self.COLORS["accent"])
            self.info.config(text="✓ 已置顶", fg=self.COLORS["accent"])
        else:
            self.btn_pin.config(fg=self.COLORS["text_secondary"])
            self.info.config(text="已取消置顶", fg=self.COLORS["text_secondary"])
        self.root.after(2000, self._update_status_text)

    def _update_status_text(self):
        if self.last_sync > 0:
            self.info.config(text=f"上次同步: {int(time.time() - self.last_sync)}s 前",
                             fg=self.COLORS["text_secondary"])
        else:
            self.info.config(text="等待同步...", fg=self.COLORS["text_secondary"])

    # ===== 业务逻辑 =====
    def sync_ntp(self):
        def run():
            # NTP时间戳基准：1970-01-01 距离 1900-01-01 的秒数
            NTP_EPOCH = 2208988800
            s = None  # 初始化套接字变量，确保finally能访问
            try:
                # 记录客户端发送时间
                t0 = time.time()
                host = "ntp.aliyun.com"  # 阿里云主NTP服务器
                port = 123
                msg = b'\x1b' + 47 * b'\0'
                addr = (host, port)

                # 创建UDP套接字并设置超时
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(5)  # 延长超时时间，提升稳定性

                # 发送NTP请求并接收响应
                s.sendto(msg, addr)
                msg, _ = s.recvfrom(1024)
                # 记录客户端接收时间
                t1 = time.time()

                # 解析NTP响应包，提取服务器端时间戳
                unpacked = struct.unpack("!12I", msg)
                t_server_recv = unpacked[8] - NTP_EPOCH  # 服务器接收请求的时间
                t_server_send = unpacked[10] - NTP_EPOCH  # 服务器发送响应的时间

                # 计算标准NTP延迟（RTT）和时间偏移
                rtt = (t1 - t0) - (t_server_send - t_server_recv)  # 纯网络延迟
                self.offset = ((t_server_recv - t0) + (t_server_send - t1)) / 2  # 准确的时间偏移
                self.last_sync = time.time()

                # 更新UI显示（保留原有格式，仅优化数值精度）
                self.root.after(0, lambda: self.info.config(
                    text=f"同步成功 ({round(rtt * 1000, 1)}ms)",
                    fg=self.COLORS["success"]
                ))

            except socket.timeout:
                self.root.after(0, lambda: self.info.config(
                    text="同步失败：连接超时", fg=self.COLORS["error"]
                ))
            except socket.gaierror:
                self.root.after(0, lambda: self.info.config(
                    text="同步失败：域名解析错误", fg=self.COLORS["error"]
                ))
            except Exception as e:
                self.root.after(0, lambda: self.info.config(
                    text=f"同步失败：{str(e)}", fg=self.COLORS["error"]
                ))
            finally:
                # 确保套接字关闭，避免资源泄漏
                if s:
                    try:
                        s.close()
                    except:
                        pass

        # 启动后台线程执行同步
        threading.Thread(target=run, daemon=True).start()

    def set_target(self):
        try:
            s = int(self.entry.get())
            if 0 <= s <= 59:
                self.target_second = s
                self.triggered = False  # 重置触发状态
                self.last_second = -1  # 重置上一次秒数记录
                self.info.config(text=f"将在 {s} 秒触发", fg=self.COLORS["accent"])
            else:
                raise ValueError
        except:
            self.info.config(text="请输入 0-59 的整数", fg=self.COLORS["error"])

    def do_click(self):
        try:
            # 模拟鼠标左键点击（按下+释放）
            ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0)  # 按下
            ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0)  # 释放
            self.info.config(text=f"✓ {self.target_second}秒触发点击!", fg=self.COLORS["success"])
        except Exception as e:
            self.info.config(text=f"点击失败: {str(e)}", fg=self.COLORS["error"])

    def update_clock(self):
        now = time.time() + self.offset
        dt = datetime.fromtimestamp(now)
        current_second = dt.second
        ms = int((now % 1) * 1000)
        self.time_label.config(text=f"{dt:%H:%M:%S}.{ms:03d}")

        # 每5分钟重新同步一次NTP
        if time.time() - self.last_sync > 300:
            self.sync_ntp()

        # 触发逻辑：目标秒数且未触发，且不是上一次的秒数（防止重复触发）
        if self.target_second is not None and not self.triggered:
            if current_second == self.target_second and current_second != self.last_second:
                self.triggered = True
                self.last_second = current_second  # 记录当前秒数，防止重复触发
                self.root.after(10, self.do_click)  # 立即触发点击（延迟10ms避免UI卡顿）

        # 每20ms更新一次时钟（50帧/秒，兼顾精度和性能）
        self.root.after(20, self.update_clock)


if __name__ == "__main__":
    root = tk.Tk()
    app = NTPClickerUI(root)
    root.mainloop()