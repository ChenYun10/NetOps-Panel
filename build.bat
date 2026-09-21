@echo off
chcp 65001 >nul
REM ============================================
REM  NetOps Panel 打包脚本（单文件 exe）
REM ============================================

echo [1/3] 安装依赖...
pip install -r requirements.txt pyinstaller || goto :err

echo [2/3] 清理旧构建产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist NetOpsPanel.spec del /q NetOpsPanel.spec

echo [3/3] 打包为单文件 exe（内嵌 iperf3）...
pyinstaller --onefile --windowed --name NetOpsPanel ^
    --add-binary "bin/iperf3.exe;." ^
    --add-binary "bin/cygwin1.dll;." ^
    main.py || goto :err

echo.
echo ============================================
echo  打包完成！可执行文件在 dist\NetOpsPanel.exe
echo ============================================
pause
exit /b 0

:err
echo.
echo 打包失败，请检查上面的错误信息。
pause
exit /b 1
