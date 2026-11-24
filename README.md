# KuroCat Custom Avatar

为 Windows 版 KuroCat 加入自定义桌宠。可以导入透明图片，也可以把一张已分层的人像或插画绑定成会转头、眨眼、握鼠和敲键的角色。手臂分为上臂、前臂和手掌，双手分别跟随鼠标和按键位置。

## 构建

此仓库以源码补丁分发，基于 [KuroCat v5.0.2](https://github.com/qianyiai/kurocat/tree/v5.0.2)。在 Windows 上准备 Node.js、Rust、MSVC C++ 构建工具和 WebView2。以下 PowerShell 命令从本仓库根目录运行。

```powershell
$patch = (Resolve-Path ./kurocat-avatar.patch).Path
git clone --branch v5.0.2 --depth 1 https://github.com/qianyiai/kurocat.git desktop
Set-Location desktop
git rev-parse HEAD
git apply --check $patch
git apply $patch
npm ci
npm run build
cargo build --manifest-path src-tauri/Cargo.toml --release --features tauri/custom-protocol
```

上游提交为 `48e27fd4ac4e921b96f2018f7a5c11987f998a02`。默认 Cargo 输出为 `src-tauri/target/release/KuroCatCustom.exe`。把程序放在可写目录，运行后右键桌宠，打开「自定义形象」。角色选择保存在程序旁的 `data/`。

## 用自己的图绑定双手

准备一张透明背景上半身立绘，最好能看到肩、肘、腕和指尖。复制 `examples/` 的两份坐标模板，在图片的原始像素坐标系内调整。模板按 240 像素宽的示意比例编写。坐标原点在左上角，两个手臂按画面从左到右排列。

- `landmarks.json` 的 `neck`、`faceEnd`、`collar` 控制头部跟随到衣领的渐变。`waist` 是角色与键盘的相对高度。每只眼按瞳孔中心、椭圆半径、眼裂边界矩形填写。
- `arms.json` 的 `j` 依次是肩、肘、腕、指尖。`p` 是三个部件各自的轮廓多边形，`radii` 控制上臂和前臂两端的半径。`edge` 各行依次给出纵坐标、躯干左边缘和右边缘。交叉手臂移开后，遮挡区域通过局部修补重建。
- 在本仓库根目录运行下列命令，把输出文件放入程序旁的 `data/`，重新打开「自定义形象」选择相应槽位。当前三个兼容槽位分别为 `luffy-rig.json`、`nami-rig.json`、`naruto-rig.json`，文件名对应菜单按钮。仓库只提供坐标模板和代码，立绘由使用者自行准备。

```powershell
python -m pip install numpy pillow opencv-python scipy
python tools/make_atlas.py my-art.png examples/landmarks.json atlas.json
python tools/bind_arms.py my-art.png atlas.json examples/arms.json luffy-rig.json
```

普通透明 PNG/WebP 可以直接导入。可选的 Windows 自动抠图后端寻找当前用户按标准路径安装的 Python 3.10、Pillow、rembg、CPU 版 ONNX Runtime，以及程序旁的 `models/isnet-general-use.onnx`。绘制动态人物时请在桌宠尺寸下检查手掌可见性、衣服遮挡和颈部接缝。

## 验证

在 Windows 定制版的三个本地角色上检查了握鼠、双手组合键、按住与释放、A/L 两个不同落点、眼球跟随、闭眼和衣领固定。原图中被遮住的衣服和肢体需要逐角色校正。公开仓库不含测试人员的照片、角色图集、模型权重或桌面截图。

本项目保留上游 MIT 许可与版权声明。第三方角色美术不随源码分发。
