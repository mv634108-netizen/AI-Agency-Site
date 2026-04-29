@echo off
chcp 65001 > nul
echo Попытка запуска скрипта через различные команды Python...

echo Проверка команды 'python'...
python vk_real_estate_scraper.py
if %errorlevel% equ 0 goto end

echo.
echo Проверка команды 'py'...
py vk_real_estate_scraper.py
if %errorlevel% equ 0 goto end

echo.
echo Проверка команды 'python3'...
python3 vk_real_estate_scraper.py
if %errorlevel% equ 0 goto end

echo.
echo ОШИБКА: Не удалось запустить Python. Убедитесь, что Python установлен.
pause

:end
echo.
echo Работа завершена.
pause
