# CapsWriter-Offline

这是一个离线语音输入工具。本分支的默认入口会把本地服务端、麦克风客户端和
系统托盘作为一个应用统一启动和关闭。

## 使用方式

Windows 打包版：

1. 下载[语音识别模型](https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-zh-2023-09-14)
   和[标点模型](https://www.modelscope.cn/models/iic/punc_ct-transformer_cn-en-common-vocab471067-large-onnx)，
   按下面的目录结构放到程序旁：

   ```text
   models/
   ├─ paraformer-offline-zh/
   │  ├─ model.int8.onnx
   │  └─ tokens.txt
   └─ punc_ct-transformer_cn-en/
      ├─ model_quant.onnx
      └─ ...
   ```

2. 双击 `CapsWriter.exe`。不要再分别启动 `start_server.exe` 和
   `start_client.exe`。
3. 等待右下角通知从“正在加载模型”变为“已就绪”。
4. 按一下 `Caps Lock` 开始录音，再按一下结束，等待识别结果自动输入。
5. 从系统托盘菜单退出；客户端、服务端和模型进程会一并关闭。

托盘会显示并通知以下状态：

- 黄色：正在启动或加载模型
- 绿色：客户端与服务端均已就绪
- 红色：正在录音
- 蓝色：正在识别
- 橙色：服务断开，正在等待恢复
- 红色叉号：启动或运行异常

重复双击程序不会再启动第二套服务。服务端异常时，可以在托盘菜单选择
“重新启动服务”。托盘菜单会显示 `config.py` 的完整位置和当前月份的保存
目录，并显示实际使用的麦克风；点击路径菜单即可打开。客户端日志也可从托盘
菜单直接打开。

## 从源码运行

推荐 Python 3.10：

```shell
pip install -r requirements.txt
python start_capswriter.py
```

调试时仍可分别运行 `start_server.py` 和 `start_client.py`。

## 打包

```shell
pip install -r requirements.txt
pyinstaller build.spec
```

输出位于 `dist/CapsWriter-Offline`。模型超过 1 GB，因此不会被 PyInstaller
复制进发行包，需要按“使用方式”单独放入 `models`。

## 配置

编辑 `config.py` 可以修改服务地址、端口、快捷键、录音模式、热词和识别
格式。统一启动模式用于本地服务，默认地址为 `127.0.0.1:6016`。
默认采用单击切换模式；需要改成按住录音、松开结束时，可将
`ClientConfig.hold_mode` 设置为 `True`。默认使用 Windows 的默认输入设备；
需要指定麦克风时，可将
`ClientConfig.mic_device` 设置为设备编号或名称的一部分。

热词文件：

- `hot-zh.txt`：中文热词
- `hot-en.txt`：英文热词
- `hot-rule.txt`：自定义替换规则
- `keywords.txt`：日记关键词

上游项目与完整功能说明：
[HaujetZhao/CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline)。
