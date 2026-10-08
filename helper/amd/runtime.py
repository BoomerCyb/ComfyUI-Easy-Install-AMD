"""ROCm environment shared by EZi Desktop and the command-line launcher."""
import os
from pathlib import Path
import subprocess
import sys


def architecture(root):
    result = subprocess.run([sys.executable, str(Path(root) / 'amd/detect_gpu.py')],
                            capture_output=True, text=True, check=True)
    arch = result.stdout.strip()
    if not arch.startswith('gfx') or not arch[3:].isalnum():
        raise RuntimeError('AMD GPU detection returned an invalid architecture')
    return arch


def configure(root, env=None):
    root = Path(root)
    env = dict(os.environ if env is None else env)
    py = root / 'python_embeded'
    env['PATH'] = str(py) + os.pathsep + str(py / 'Scripts') + os.pathsep + env.get('PATH', '')
    env['PATH'] = str(root / 'amd/sox-14.4.2') + os.pathsep + env['PATH']
    env['PIP_CONSTRAINT'] = str(root / 'amd/amd-constraints.txt')
    env['UV_CONSTRAINT'] = env['PIP_CONSTRAINT']
    env['PYTHONNOUSERSITE'] = '1'
    env['PYTHONUTF8'] = '1'
    sdk = [str(py / 'python.exe'), str(root / 'amd/sdk.py')]
    subprocess.run(sdk + ['init'], env=env, check=True)
    sdk_root = subprocess.check_output(sdk + ['path', '--root'], env=env, text=True).strip()
    env['HIP_PATH'] = env['ROCM_PATH'] = sdk_root
    arch = architecture(root)
    if arch.startswith(('gfx101', 'gfx103')):
        env.update(TORCH_BACKENDS_CUDA_FLASH_SDP_ENABLED='0',
                   TORCH_BACKENDS_CUDA_MEM_EFF_SDP_ENABLED='0',
                   TORCH_BACKENDS_CUDA_MATH_SDP_ENABLED='1')
    else:
        env['TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL'] = '1'
    for key, directory in [('TRITON_CACHE_DIR', 'triton-cache'),
                           ('PYTORCH_TUNABLEOP_CACHE_DIR', 'tunableop-cache')]:
        cache = root / directory / arch
        cache.mkdir(parents=True, exist_ok=True)
        env[key] = str(cache)
    if arch != 'gfx1100':
        bin_dir = py / 'Lib/site-packages/_rocm_sdk_devel/bin'
        env['MIOPEN_SYSTEM_DB_PATH'] = str(bin_dir)
        env['ROCBLAS_TENSILE_DB_PATH'] = str(bin_dir / 'rocblas')
        env['ROCBLAS_TENSILE_LIBPATH'] = str(bin_dir / 'rocblas/library')
    env.update(COMFYUI_ENABLE_MIOPEN='0', FLASH_ATTENTION_TRITON_AMD_ENABLE='TRUE',
               MIOPEN_FIND_ENFORCE='1', MIOPEN_FIND_MODE='2', MIOPEN_DEBUG_DISABLE_FIND_DB='0',
               MIOPEN_SEARCH_CUTOFF='1', MIOPEN_ENABLE_LOGGING='0', MIOPEN_LOG_LEVEL='0',
               MIOPEN_ENABLE_LOGGING_CMD='0', TRITON_PRINT_AUTOTUNING='0', TRITON_CACHE_AUTOTUNING='0')
    return env, arch


def startup_args(arch, args):
    args = list(args)
    attention = any(a.startswith('--use-') and 'attention' in a for a in args)
    if not attention:
        args.append('--use-pytorch-cross-attention')
    return args


if __name__ == '__main__':
    install_root = Path(__file__).resolve().parent.parent
    run_env, gpu_arch = configure(install_root)
    print('AMD GPU architecture:', gpu_arch, flush=True)
    raise SystemExit(subprocess.call([sys.executable, str(install_root / 'ComfyUI/main.py')]
                                    + startup_args(gpu_arch, sys.argv[1:]),
                                    cwd=install_root, env=run_env))
