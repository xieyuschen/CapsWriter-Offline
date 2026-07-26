from config import ModelPaths
from util.server_cosmic import console


def check_model(*, interactive: bool = True) -> None:
    missing = [
        path
        for key, path in ModelPaths.__dict__.items()
        if not key.startswith("_") and not path.exists()
    ]
    if not missing:
        return

    missing_text = "、".join(str(path) for path in missing)
    message = (
        f"未找到模型文件：{missing_text}。"
        f"请将模型放入 {ModelPaths.model_dir}。"
    )
    console.print(message, style="bright_red")
    if interactive:
        input("按回车退出")
    raise FileNotFoundError(message)
