#!/usr/bin/env bash
# Скрипт для исправления окончаний строк в shell скриптах
# Запустите: bash fix_line_endings.sh

# Проверяем наличие dos2unix, если нет - используем sed
if command -v dos2unix &> /dev/null; then
    dos2unix start.sh start_background.sh
else
    # Используем sed для замены CRLF на LF
    sed -i 's/\r$//' start.sh
    sed -i 's/\r$//' start_background.sh
fi

# Делаем файлы исполняемыми
chmod +x start.sh start_background.sh

echo "✅ Файлы исправлены и сделаны исполняемыми"
