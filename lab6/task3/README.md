# Lab 6 Task 3: ESP32 + ADXL345 + Gemini + OLED

流程：电脑交互命令 `classify_HAR` → ESP32 采样 → 电脑调用 Gemini → 返回标签到 OLED。
代码扩展了 Lab 5 的命令服务器，保留时间、闹钟、显示等原有命令。
Task 1、Task 2 和 Lab 5 的原文件没有修改。

## 文件

```text
task3/
  client.py                      电脑端交互、Gemini、记录与汇总
  requirements.txt               电脑端依赖
  esp32/
    main.py                      ESP32 启动程序和 Lab 5 命令服务器
    har_sensor.py                ADXL345 SPI 驱动与 50 Hz 采样
    ssd1306.py                   OLED I2C 驱动
    board_config.example.py      接线、Wi-Fi 配置模板
  tests/test_task3.py             离线测试，不访问真实 API 或硬件
```

## 1. 核对接线和配置

将 `esp32/board_config.example.py` 复制为 **ESP32 上的 `board_config.py`**，填写
SSID、PASSWORD，并核对 GPIO。模板的引脚来自当前文件夹的 Lab 4 和 Lab 5：

无密码的开放校园 Wi-Fi 使用 `PASSWORD = ""`，SSID 填写电脑上显示的实际网络名称；
固件会在密码为空时调用 `wifi.connect(ssid)`。

| 功能 | ESP32 GPIO 默认值 |
| --- | --- |
| ADXL345 SCK | 5 |
| ADXL345 MOSI / SDA / SDI | 19 |
| ADXL345 MISO / SDO | 21 |
| ADXL345 CS | 4 |
| OLED SDA | 22 |
| OLED SCL | 20 |

外设按现有模块要求接 3.3 V 和 GND，电脑与 ESP32 在能互相访问的同一网络上。
**GPIO 编号以你的板型和实际接线为准。**例如经典 ESP32 没有 GPIO20；旧 Lab 5
配置若不适用于你的开发板，应在配置文件里修改 OLED_SCL，而不是照抄接线。
OLED 驱动默认适用于 SSD1306、128×32、I2C 地址 0x3C。

## 2. 将固件上传到 ESP32

先在电脑备份开发板已有的 `main.py`，然后用 Thonny 上传下面四个文件到开发板根目录：

- `main.py`
- `har_sensor.py`
- `ssd1306.py`（如果板上已有可用的同名驱动，也可以保留现有驱动）
- `board_config.py`（由配置模板复制、改名并填写）

重启或运行 `main.py`，串口应出现：

```text
WiFi connected: (...)
Server ready: <ESP32_IP>:8080
```

记下这里的实际 IP；电脑端不要运行 `esp32/main.py`。
原 Lab 5 的位置和天气功能额外依赖板上的 `urequests`，天气功能还需配置 WEATHER_API。
Task 3 本身不需要这两个功能，也不需要在 ESP32 上安装 google-genai。

## 3. 安装电脑端依赖

在 PowerShell 中执行：

```powershell
Set-Location 'C:\Users\Lenovo\Desktop\Columbia\AIoT\Lab6\task3'
python -m pip install -r requirements.txt
$env:GEMINI_API_KEY = '填写你在 Task 2 使用的 Gemini API key'
```

API key 只放在电脑端环境变量中。本代码不自动导入 Task 2 文件，因而无需安装
PyTorch，也不会意外运行 Task 2 的数据集评估。
模型默认沿用 Task 2 的 `gemini-3.5-flash-lite`；如果你的账号需要其他模型，可加
`--model 实际可用的模型名`，并在报告中注明。

## 4. 先验证一次采样

以下示例把板子固定在腰部。如果你实际绑在其他位置，修改 `--location`，并保持
所有正式样本佩戴位置和朝向一致。将命令中的 `ESP32_IP` 换成串口打印的实际地址。

```powershell
python client.py capture --host ESP32_IP --location Waist --true-label STANDING
```

倒计时结束后，会采集 128 个新的三轴加速度测量值，约 2.56 秒。输出 Sampling QA：

- `effective_rate_hz` 应接近 50。
- `max_gap_ms` 应接近 20。
- 静止时 `mean_vector_magnitude_g` 通常应接近 1；运动时不能用 1 g 作为判定标准。

程序使用 ADXL345 的 50 Hz 输出速率并轮询 DATA_READY，保留重力、不做标准化。
完整窗口是 `[3,128]`，通道顺序 X、Y、Z；全分辨率、±4 g，按 256 LSB/g 转换。
样本首末读数间隔约 2.54 秒，而 128 点窗口的名义时长是 2.56 秒。
时间戳是电脑可检查的传感器**读取时间**，不是外部仪器测得的精确转换时间。
如果有效速率不在 45–55 Hz、最大间隔超过 35 ms 或检测到 overrun，程序保存原始数据
并报错，要求重新采集，避免把明显丢样的窗口交给模型。

## 5. 完成一次分类和 OLED 演示

```powershell
python client.py classify_HAR --host ESP32_IP --location Waist --true-label WALKING
```

开始前固定好传感器，在倒计时结束前进入目标活动，并在整个采样窗口保持该活动。
采样完成后可停下，等待电脑调用 Gemini。结果会显示在终端和 OLED 上；例如长标签
WALKING_DOWNSTAIRS 会分行显示。`--true-label` 只用于实验记录和准确率计算，
**不会进入发给模型的 prompt**。

默认使用直接回答。若选择 `--style cot`，会使用与 Task 2 相同的 CoT 输出格式。
Task 3 的 prompt 保留 Task 2 的结构、六类候选活动、四位小数及输出指令，修改设备、
佩戴位置、环境，并明确声明只有三轴加速度，没有陀螺仪。

也可以从交互界面连续操作：

```powershell
python client.py --host ESP32_IP --location Waist --style direct
```

随后逐行输入：

```text
capture STANDING
classify_HAR WALKING
classify_HAR WALKING_UPSTAIRS
classify_HAR WALKING_DOWNSTAIRS
classify_HAR SITTING
classify_HAR STANDING
classify_HAR LAYING
summary
q
```

这些命令需要你逐次进行相应的真实活动；示例本身只列出了六个正式分类样本，
还需补采到 **至少 10 个窗口，六种活动每种至少一个**。建议正式实验固定一种 prompt
策略，例如 direct，便于汇总和与 Task 2 对照。

已有 Lab 5 JSON 命令也可在交互界面使用，例如：

```json
{"name":"display_text","args":["Hello"]}
```

ESP32 收到的采样命令名是 `capture_HAR`；电脑端的 `classify_HAR` 会协调采样、
Gemini 和显示三个步骤，Gemini 不在 ESP32 上运行。

## 6. 结果和报告

每次操作建立一个独立的 `results/samples/<sample_id>/`：

- `metadata.json`：真实标签、位置、环境、模型、prompt 策略。
- `window.json`：完整原始窗口和实际采样时间戳。
- `quality.json`：采样速率和间隔检查结果。
- `prompt.txt`、`response.txt`：实际发出的 prompt 和模型原始回复。
- `result.json`：预测、是否正确、推理耗时、OLED 是否显示成功。

仅采样模式不会生成 prompt 或回复。API 出错时保留已采集的数据；OLED 更新失败时
保留已获得的预测，`display_ok` 为 false。错误不会被伪装成成功。

导出 CSV 和准确率：

```powershell
python client.py summary
```

产生 `results/summary.csv` 和 `results/summary.json`，按 direct/cot 分别汇总已标注
分类记录，非法输出算错误。`captured` 和 API 失败的记录不计入分类准确率。
`at_least_10_and_all_6_classes` 检查的是该策略的分类记录数量与类别覆盖；你还应检查
每次记录对应独立的真实窗口，并确认 OLED 演示成功。

报告包括：10 个样本的真实标签与预测表、实验准确率、OLED 照片，以及与 Task 2 的
UCI 结果对比。当前保存的那轮 UCI 实验是 CoT 4/10、direct 3/10；这些是已有实验记录，
不是这份 Task 3 代码新测出来的硬件结果。说明 UCI 有六通道，而 ADXL345 只有三通道，
佩戴位置、轴方向和采样环境也可能影响结果。

可重新分类已保存的窗口，避免 API 失败后重新做动作：

```powershell
python client.py classify_HAR --host ESP32_IP --location Waist --true-label WALKING --window 'results\samples\实际样本ID\window.json'
```

这会生成新的分类记录，并记录 `source_window`；**对同一窗口重复调用，不算新的独立
硬件样本**，整理正式的 10 样本表时需要去重。请选定一个正式结果目录，避免把调试和
重复分类的记录一起当成正式实验。

## 7. 测试与问题排查

```powershell
python -m unittest discover -s tests -v
```

这组测试只检查数据契约、SPI 配置/有符号转换、分片长回复、标签解析和记录保存。
没有调用 Gemini，也没有连接开发板；物理接线、实际采样和 OLED 显示需要在板上验证。

- `ADXL345 not found`：核对 SPI 接线、GPIO 编号、供电和 CS；设备 ID 应为 0xE5。
- `Invalid pin`：核对开发板型号和 board_config.py，尤其是继承的 OLED_SCL=20。
- 无法连接：检查串口 IP、同一网络、客户端隔离和端口 8080；板子需持续运行 main.py。
- `DATA_READY timeout`：检查传感器供电和 SPI 通信。
- `MemoryError` 出现在发送采样结果时：重新上传当前 `esp32/main.py`。新版以 512 字节缓冲
  分段编码/发送 JSON，避免同时生成完整 JSON 字符串和字节副本，并在每次请求结束后
  释放采样结果、执行垃圾回收；单个请求内存不足也会关闭该连接而保留服务器。
- `Sampling timing failed QA`：原始数据已保存，排查板上负载/通信后重新采集。
- API 报错：检查 key、配额和实际可用模型；修复后可用 `--window` 重试。
- OLED 报错：确认 SSD1306 型号、128×32、0x3C 地址及 I2C 接线。

## 技术依据

- [ADXL345 官方数据手册](https://www.analog.com/media/en/technical-documentation/data-sheets/ADXL345.pdf)：50 Hz 速率码 0x09、全分辨率量程、SPI 多字节读取和 DATA_READY。
- [Google Gen AI Python SDK 官方文档](https://googleapis.github.io/python-genai/)：Client、generate_content 和请求配置。
