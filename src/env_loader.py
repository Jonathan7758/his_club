"""
环境变量加载器
在模块导入链最前端调用，从 .env 文件加载环境变量
"""
import os


def load_env(env_path: str = None):
    """从 .env 文件加载环境变量（不覆盖已存在的）"""
    if env_path is None:
        # 尝试多个位置: 开发环境(src/../.env), 生产环境(同目录/.env)
        candidates = []
        my_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.normpath(os.path.join(my_dir, "..", ".env")))
        candidates.append(os.path.normpath(os.path.join(my_dir, ".env")))
        candidates.append(os.path.normpath(os.path.join(my_dir, "..", "..", ".env")))
        for p in candidates:
            if os.path.isfile(p):
                env_path = p
                break
        if env_path is None:
            return False

    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if key and key not in os.environ:
                os.environ[key] = val
    return True
