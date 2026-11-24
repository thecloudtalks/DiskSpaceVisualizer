"""Disk Space Visualizer — entry point (Windows). Run:  python main.py"""
import tkinter as tk

from app import App


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
