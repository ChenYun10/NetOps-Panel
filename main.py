# -*- coding: utf-8 -*-
"""
NetOps Panel 程序入口。

运行：python main.py
打包：pyinstaller --onefile --windowed --name NetOpsPanel main.py
"""
import tkinter as tk

from app import theme
from app.ui.main_window import MainWindow


def main():
    # 主窗口
    root = tk.Tk()
    root.title("NetOps Panel 网络运维检测面板")
    root.geometry("1280x800")
    root.minsize(1080, 680)
    root.configure(bg=theme.BG)

    # 实例化主窗口（侧边栏 + 工作台）
    MainWindow(root)

    root.mainloop()


if __name__ == "__main__":
    main()
