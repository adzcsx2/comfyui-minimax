# ComfyUI MiniMax H3：Ref2VA + Fun ControlNet Union 2.0

用于 AutoDL 云端安装、运行和保存自用镜像的部署工程。支持四张身份/尺度/场景参考图与逐帧深度控制共同进入一次 H3 生成；默认不将角色分层生成后贴回。

**已在 AutoDL RTX 6000D 84GB 实例完成四图＋Union 2.0 深度控制的完整推理测试。** 输出为 1024×576、124 帧、24fps，40 步约 538 秒；2 秒采样的最高显存占用为 47,660MiB。实际证据与尚未完成项见[验证记录](docs/验证记录.md)。这是软件链路验证，角色尺寸和成片质量仍需另验；结构控制不能保证数学意义上的固定 3D 体积。本项目不要求在个人电脑安装或运行 Docker。

## 组成

- 固定 ComfyUI 提交 `c5751c81abe131202eea9e4c66d000589013dd0b`，包含原生 H3 Union 2.0 支持。
- H3 Ref2VA INT8 主模型、NVFP4 文本编码器、视频/音频 VAE，以及匹配的 Union 2.0 INT8 控制权重。
- 模型的版本、真实字节数与 SHA-256 在 [`config/models.lock.json`](config/models.lock.json) 锁定。五个文件合计约 44.6 GB；不包含在 Git 仓库或 Docker 构建中。
- 独立 Python 3.12 虚拟环境、PyTorch `2.13.0+cu130`，不修改底座应用原有 ComfyUI。上传前依赖审计发现旧版已知问题后，已将自建环境更新到修复版本；云端兼容性仍需实测。
- [`workflows/h3-depth-ref2va.json`](workflows/h3-depth-ref2va.json)：可导入 ComfyUI 的工作流；对应 API 图为同目录 `h3-depth-ref2va-api.json`。
- 一个轻量控制视频检查节点，拒绝错误帧率、尺寸、帧数；它不改变模型算法，也不保证成片尺寸。

## 全部下载入口使用镜像源

镜像入口见 [`config/mirrors.env`](config/mirrors.env)，PyTorch 主包的固定镜像直链及哈希见 [`config/requirements-pytorch.txt`](config/requirements-pytorch.txt)。其 CUDA/Python 依赖从 PyPI 镜像解析，不再同时查询较慢的 PyTorch 索引。默认不会在失败时偷偷切回源站。

| 内容 | 默认镜像入口 |
|---|---|
| Docker 基础镜像 | `m.daocloud.io/docker.io/library/python`，已锁 digest |
| Debian / Ubuntu 系统包 | 清华 TUNA |
| Python 包 | 清华 PyPI；缺少的固定模板素材包通过显式阿里云镜像直链获取 |
| PyTorch CUDA 13.0 包 | 南京大学 PyTorch 镜像 |
| ComfyUI 源码归档 | `gh-proxy.com`，固定提交并验证归档 SHA-256 |
| 模型文件 | `hf-mirror.com`，固定仓库提交并验证文件 SHA-256 |

模型镜像可能将文件请求重定向到上游对象存储 CDN；这是镜像返回的下载地址，不是脚本启用官方源兜底。GitHub 的代码推送和 GHCR 的镜像发布是发布目的地，不属于容器依赖下载源。

## AutoDL 云端安装：推荐路径

### 1. 准备云实例

本次底座选 [MINIMAX-H3提速500高画质](https://www.autodl.art/app/market/252)，应用 ID **`spcwDDc6XW:v9.49`**。它只是创建实例的起始环境；本仓库会安装自己固定的控制链，不自动采用底座里的 U30 或其他封装工作流。

先完成代码准备，再创建实例，避免等待代码时占用 GPU。建议首次验证使用单张 NVIDIA GPU、48GB 以上显存并留足内存；这不是已经实测的最低配置。必须核对驱动与 CUDA 13.0 兼容。不要选择 AMD、昇腾等不同后端套用本配置。

保存基础实例的原有启动命令和端口信息。新增环境安装到本项目 `runtime/`，不覆盖底座原工作流。公共模型优先按文件名寻找并验证哈希，匹配后创建只读使用的软链接。缺失文件才下载到 `MODEL_DIR`；公共仓未提供模型时，准备至少约 50GB 可用模型空间，系统环境另计。

### 2. 在云端取回代码

在 AutoDL 的 JupyterLab 终端或 SSH 终端执行，**不是在个人电脑运行**：

```bash
cd /root
curl --fail --location --retry 3 \
  'https://gh-proxy.com/https://github.com/adzcsx2/comfyui-minimax/archive/refs/heads/main.tar.gz' \
  --output comfyui-minimax-main.tar.gz
tar -xzf comfyui-minimax-main.tar.gz
mv comfyui-minimax-main comfyui-minimax
cd /root/comfyui-minimax
cp .env.example .env
```

上述命令用于首次安装，目标目录已存在时不要重复执行 `mv`。正式复现时，应将本仓库的 `main` 换成已确认的提交或版本归档；ComfyUI 和模型本身已由仓库锁定。

### 3. 配置持久化路径

编辑 `.env`：

```dotenv
COMFYUI_DIR=/root/comfyui-minimax/runtime/ComfyUI
VENV_DIR=/root/comfyui-minimax/runtime/venv
PYTHON_BIN=/root/miniconda3/bin/python3.12
MODEL_DIR=/root/autodl-tmp/minimax-h3-models
PUBLIC_MODEL_ROOTS=/.autodl:/root/autodl-pub:/root/ComfyUI/models
COMFYUI_LISTEN=127.0.0.1
COMFYUI_PORT=6010
AUTO_DOWNLOAD_MODELS=0
```

先确认云实例是否实际提供 `/root/autodl-tmp` 数据盘。应用实例可能只有系统盘，应根据实际容量改 `MODEL_DIR`，不能把 44.6GB 权重塞进剩余空间不足的系统盘。公共仓挂载路径也以实际实例为准。

```bash
bash scripts/install_autodl.sh --download-models
```

如果缺少 `ffmpeg`、系统库或 Python venv 支持，增加 `--install-system`。安装器要求已有 Python 3.12；底座应用的 Python/CUDA 版本与本文一致时仍会进行实际核对。下载中断后可重新执行同一安装命令，已有且校验通过的文件不会重复下载。

本次 6000D 实例已验证 AutoDL 内置网络加速能访问清华 PyPI 和模型镜像。若直连超时，可在云端 `.env` 明确设置 `AUTODL_NETWORK_TURBO=1` 后执行安装；安装器在自身进程中加载平台 `/etc/network_turbo`，不修改镜像地址或关闭证书校验，也不修改系统全局网络设置。参见 [平台网络加速说明](https://www.autodl.com/docs/network_turbo/)。公共 VAE 的 `-v2` 文件名也可复用，但必须通过同一锁定字节数及 SHA-256；同名不同版本不会混用。

遇到模型大文件单连接停滞时，可在云端安装阶段启用平台加速，再使用有界分块下载。它逐块核对 HTTP Range 和长度，拼接后验证完整 SHA-256，验证失败保留诊断文件，不发布模型：

```bash
source /etc/network_turbo
runtime/venv/bin/python scripts/download_model_ranges.py --role controlnet --connections 8
runtime/venv/bin/python scripts/download_models.py --link-only
```

实际安装时清华镜像尚未提供 `comfyui-workflow-templates-media-assets-02==0.1.31`，阿里云镜像已提供。[兼容依赖文件](config/requirements-mirror-overrides.txt)只为该包提供固定镜像直链，并锁定官方 PyPI 发布的 SHA-256；其余包继续从清华镜像获取，不回退到官方源，也不删除该依赖或更换 ComfyUI 版本。

### 4. 检查并启动

```bash
runtime/venv/bin/python scripts/doctor.py --require-cuda --require-models
bash scripts/start.sh
```

启动脚本先检查或重建模型链接，不默认联网补下载。首次缺模型时回到安装命令，或明确设置 `AUTO_DOWNLOAD_MODELS=1`。本次底座已占用6006/6008，因此原生云端示例使用6010；若该端口也被占用，选择其他空闲端口并同步隧道和检查命令。

默认仅监听云机器回环地址。可从个人电脑建立 SSH 隧道访问，不需要个人电脑运行模型或 Docker：

```bash
ssh -N -L 16010:127.0.0.1:6010 -p <云实例SSH端口> root@<云实例SSH主机>
```

然后打开 `http://127.0.0.1:16010`。若使用 AutoDL 的 WebUI 服务代理，按平台实际端口映射配置监听地址和访问控制，不直接暴露无认证的 ComfyUI 到公网。

本次实际独立服务使用云端 `127.0.0.1:6010`，本地 SSH 隧道使用 `127.0.0.1:16010`。从外站跳转本地页面可能触发 ComfyUI 的跨站保护；应从浏览器地址栏直接输入地址后验证，不关闭该保护。本次自动浏览器请求返回 403，原生导航被工具安全机制中止，因此未把网页加载或原速审片记为通过。

服务运行后，在云端另一个终端执行：

```bash
runtime/venv/bin/python scripts/doctor.py --server http://127.0.0.1:6010 \
  --require-cuda --require-models --output .local/live-doctor.json
```

`doctor` 分别记录固定源码、CUDA、模型大小/控制头信息、实际服务节点；即使全部通过，也只代表部署检查通过，不代表已经完成推理或画面验收。

安装并验证后，把实例的自定义开机命令设为 `bash /root/comfyui-minimax/scripts/boot_autodl.sh`，并保存原底座的启动命令。此入口保留本次核实的底座面板启动，再启动独立环境；底座已有 6006/6008 服务时，新服务应使用 6010 等空闲端口。需低显存模式时，可在命令末尾加 `--lowvram`；启动器会原样传递给 ComfyUI。低显存模式仍需实际测试，不代表 32GB 显卡已验证可完整推理。若其他底座需要先挂载公共模型，应先核对其启动脚本行为。不要只保存一个尚未检查模型挂载的空软链接；重启后再次执行 `doctor` 核验。

## 深度控制工作流

```text
角色 A / 角色 B / 尺度图 / 场景图 ──→ Ref2VA 条件 ──┐
                                                    ├→ 同一次 H3 采样 → 完整视频
深度视频 → 帧率/尺寸检查 → Union 2.0 → 主模型 ──────┘
```

默认参考顺序：①角色 A，②角色 B，③身高/尺度图，④场景图。图序、图内人物对应及模型正文必须一致；可在原生 Ref2VA 节点继续增加参考槽。

将已经准备好的深度视频和四张图片放入新 ComfyUI 的 `input/`，在工作流里选择实际文件。API 图中的 `depth.mp4`、`character-a.png` 等只是占位名称，**必须替换**。

默认 1024×576、24fps、124 帧，即 **5.167 秒**；不是精确的 5.000 秒。H3 使用 `17*n+5` 帧网格。输入控制片需与生成尺寸、帧数、帧率一致；不要把 120 帧强行拉伸到 124 帧或放慢动作来凑时长。

```bash
runtime/venv/bin/python scripts/preflight.py --control /绝对路径/depth.mp4
```

默认 40 步、不加载 Turbo LoRA、不将参考视频音轨接入输出，样例输出静音。结构节点的 `strength`、起止采样范围与简化几何会影响遵循及自然度，必须依据实际结果检查。仅把深度视频放进普通参考视频槽不等于经过 ControlNet；本图明确把控制分支返回的 MODEL 接入采样。

首次推理须记录实际输入、seed、节点、权重、耗时与输出。检查动作中间状态的体量、深度、速度、接触及环境形变；首尾一致不能证明全程一致。先验证具体动作，再决定是否用于正式作品。

## 两小时使用与保存镜像

用完选择**关机并保留实例**，不要误点释放；下次开机可继续使用已保存的系统环境。关机停止 GPU 计费，保留的磁盘仍按平台规则收费，可在平台设置两小时定时关机。

云端安装和推理验证后，将实例关机，再用平台“保存镜像”保存自己的定制系统环境。镜像获得自己的标识，不会修改 `spcwDDc6XW:v9.49`。应用实例如果没有保存镜像功能，应按平台实际支持的实例/镜像流程处理，不能声称已经保存。

镜像通常只保存系统盘，不自动包含数据盘、公共模型、软链接目标或输出备份。必须保留本仓库版本、模型清单及重要输出，并在从新镜像创建的实例上验证重新挂载与启动。连续关机后的保留期限、磁盘计费及发布流程以 [AutoDL 规则](https://www.autodl.art/docs/app/) 为准。

## Docker：仅供云端构建

AutoDL 当前公共云文档不支持直接导入外部 Docker 镜像，因此本次 AutoDL 部署使用上面的实例内安装路径。Dockerfile 用于支持 Docker 的其他云主机或 GitHub Actions 构建；不会要求在个人电脑启动 Docker。

在具备 NVIDIA Container Toolkit 的云端 Docker 主机，可以使用 `compose.yaml`。首次显式设置 `AUTO_DOWNLOAD_MODELS=1` 安装模型，之后关闭；数据和输出通过卷保留。GitHub Actions 的 **Build container on GitHub** 手动工作流可以构建，默认不发布；选择发布时推送到 GHCR。CPU 构建和导入检查不能代替 GPU 推理。

## 验证与开发

不安装模型、不调用 Docker即可执行的检查：

```bash
python -m unittest discover -s tests -v
python scripts/preflight.py
python -m compileall -q scripts custom_nodes
```

源码、工作流/模型文件以各自上游许可为准，见 [NOTICE](NOTICE)。本仓库不包含密钥、角色私人素材、模型权重或生成视频。
