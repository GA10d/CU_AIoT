# HUZZAH Control Deck

一个仅在 Mac 本机运行的 HUZZAH ESP32 / MicroPython 网页控制台。

## 启动

首次使用时，确保 `aiot` 环境中已安装依赖：

```bash
conda activate aiot
python -m pip install -r requirements.txt
```

之后双击 `start.command`，或在终端运行：

```bash
./start.command
```

浏览器会自动打开 <http://127.0.0.1:8765>。终端窗口必须保持开启；按 `Control-C` 停止服务。

## 工作方式

- **烧录程序**：选择包含 `main.py` 的目录。服务优先使用 `mpremote`；若未安装，则使用内置的 MicroPython 串口上传器，不依赖旧版 `mpfshell`。
- **查看输出**：用 PySerial 以所选波特率读取串口，并把内容实时显示到页面日志。
- **释放串口**：关闭本程序持有的串口，之后即可再次烧录。

服务只监听 `127.0.0.1`，不会对局域网开放。上传前会检查串口是否被 `screen`、Thonny 或其他程序占用；本程序不会擅自结束其他进程。
