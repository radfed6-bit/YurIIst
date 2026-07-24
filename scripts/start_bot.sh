#!/data/data/com.termux/files/usr/bin/bash
# Автозапуск юридического бота при загрузке телефона
# Положи этот файл в ~/.termux/boot/start-bot.sh
# Предварительно: pkg install termux-boot

CHROOT_DIR=/data/local/debian  # или где у тебя развёрнут chroot
exec chroot "$CHROOT_DIR" /root/legal-bot/.venv/bin/python -m src.bot.main
