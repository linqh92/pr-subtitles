"""Cross-platform Python entry point with a project-local dependency environment."""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def environment_python(directory: Path, platform: str | None = None) -> Path:
    return directory / ('Scripts/python.exe' if (platform or sys.platform) == 'win32' else 'bin/python')


def prepare(root: Path = ROOT) -> Path:
    if sys.version_info < (3, 10):
        raise ValueError('需要 Python 3.10 或更新版本，推荐 Python 3.12。')
    requirements = root / 'requirements.txt'
    if not requirements.is_file():
        raise ValueError('找不到 requirements.txt，请保留完整工具文件夹。')
    environment = root / '.venv'
    python = environment_python(environment)
    if not python.is_file():
        print('正在准备本地 Python 环境……', flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = environment / 'requirements.sha256'
    installed = marker.read_text(encoding='ascii').strip().lower() if marker.is_file() else ''
    if installed != digest:
        print('正在安装字幕组件，首次运行需要联网……', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], check=True)
        marker.write_text(digest, encoding='ascii')
    return python


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--setup-only', action='store_true')
    options, caption_args = parser.parse_known_args(args)
    try:
        if '--help' in caption_args or '-h' in caption_args:
            print('通用启动：python run.py [字幕选项]\n仅安装组件：python run.py --setup-only', flush=True)
            return subprocess.run([sys.executable, '-X', 'utf8', str(ROOT / 'subtitle.py'), '--help']).returncode
        python = prepare()
        if options.setup_only:
            print('组件安装完成。首次处理音频时会下载模型。')
            return 0
        environment = os.environ.copy()
        environment['PYTHONUTF8'] = '1'
        return subprocess.run([str(python), '-X', 'utf8', str(ROOT / 'subtitle.py'), *caption_args],
                              env=environment).returncode
    except KeyboardInterrupt:
        print('\n已取消。', file=sys.stderr)
        return 130
    except Exception as error:
        print(f'启动失败：{error}\n请确认 Python 已安装、工具目录可写，首次安装时网络可用。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
