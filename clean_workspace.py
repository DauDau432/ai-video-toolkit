"""Dọn dẹp thư mục dự án để bắt đầu video mới.

Không xóa gì cả: mọi file/thư mục của video cũ được CHUYỂN vào
_archive/<thời gian>[_<tên video cũ>]/ để có thể lấy lại khi cần.
Sau đó tạo lại cấu trúc thư mục trống theo mục 9 của Template.md.

Cách dùng: double-click file này, hoặc chạy `python clean_workspace.py`, rồi chọn trong menu.
"""
import os
import shutil
import sys
from datetime import datetime

# Khi đóng gói bằng PyInstaller, __file__ nằm trong thư mục tạm, nên lấy vị trí file .exe
SELF = os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
ROOT = os.path.dirname(SELF)
ARCHIVE_DIR = "_archive"
KEEP = {"Template.md", "clean_workspace.py", "clean_workspace.exe", ARCHIVE_DIR, "_models", "_tools"}

NEW_DIRS = [
    "scripts",
    "docs",
    "assets/images", "assets/video", "assets/sfx", "assets/bgm",
    "assets/voice", "assets/fonts", "assets/icons",
    "output/preview", "output/frames", "output/final",
    "tmp",
]


def list_items():
    items = sorted(i for i in os.listdir(ROOT) if i not in KEEP)
    if not items:
        print("\nKhông có gì để dọn.")
    else:
        print(f"\nCó {len(items)} mục sẽ được chuyển vào {ARCHIVE_DIR}/:")
        for item in items:
            print("  -", item + ("/" if os.path.isdir(os.path.join(ROOT, item)) else ""))
    return items


def clean():
    items = list_items()
    if items:
        name = input("\nTên video cũ để dễ tìm lại sau này (Enter để bỏ qua): ").strip()
        if input("Xác nhận dọn dẹp? (Y/n, Enter = đồng ý): ").strip().lower() not in ("", "y"):
            print("Đã hủy.")
            return
        dest = os.path.join(ROOT, ARCHIVE_DIR, f"{datetime.now():%Y%m%d-%H%M%S}" + (f"_{name}" if name else ""))
        os.makedirs(dest)
        for item in items:
            shutil.move(os.path.join(ROOT, item), os.path.join(dest, item))
        print(f"\nĐã chuyển {len(items)} mục vào {os.path.relpath(dest, ROOT)}")

    for d in NEW_DIRS:
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    print("Đã tạo cấu trúc thư mục mới cho video tiếp theo.")
    print("Giữ lại:", ", ".join(sorted(KEEP - {ARCHIVE_DIR})))


while True:
    print("\n===== DỌN DẸP DỰ ÁN VIDEO =====")
    print("1. Xem trước những gì sẽ được dọn")
    print("2. Dọn dẹp (chuyển vào _archive + tạo thư mục mới)")
    print("0. Thoát")
    choice = input("Chọn: ").strip()
    if choice == "1":
        list_items()
    elif choice == "2":
        clean()
    elif choice == "0":
        break
    else:
        print("Lựa chọn không hợp lệ.")
