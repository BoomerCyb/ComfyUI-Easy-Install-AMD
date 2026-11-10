"""ROCm environment shared by EZi Desktop and the command-line launcher."""
import importlib.util
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


def discrete_devices(sdk_root, env):
    """HIP device indexes of the discrete GPUs when the system also has an integrated one, else None.

    comfy-kitchen enables its matrix-core kernels only when every visible device has them, so a
    Ryzen iGPU (gfx1036 has none) switches them off for the Radeon card as well. amdgpu-arch lists
    the devices in HIP order without loading PyTorch.
    """
    tool = Path(sdk_root) / 'lib/llvm/bin/amdgpu-arch.exe'
    if not tool.exists():
        return None
    try:
        result = subprocess.run([str(tool)], capture_output=True, text=True, timeout=30, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    arches = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    integrated = set(_detect_gpu().INTEGRATED_GFX)
    discrete = [i for i, arch in enumerate(arches) if arch not in integrated]
    if result.returncode != 0 or not discrete or len(discrete) == len(arches):
        return None
    return discrete


def _detect_gpu():
    spec = importlib.util.spec_from_file_location('detect_gpu', Path(__file__).with_name('detect_gpu.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    # a device choice the user made (variable or --cuda-device) wins: main.py applies it after this
    if not env.get('HIP_VISIBLE_DEVICES') and not env.get('CUDA_VISIBLE_DEVICES'):
        discrete = discrete_devices(sdk_root, env)
        if discrete:
            env['HIP_VISIBLE_DEVICES'] = ','.join(map(str, discrete))
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
    if arch.startswith('gfx120'):
        # On RDNA4, hipBLASLt rejects some bf16 GEMM layouts (HIPBLAS_STATUS_NOT_SUPPORTED) and
        # PyTorch falls back to hipBLAS, warning ~170 times per 3D workflow. Using hipBLAS
        # directly removes the warnings and was not slower (PixelArtistry 2K workflow, RX 9070 XT).
        env.setdefault('TORCH_BLAS_PREFER_HIPBLASLT', '0')
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
    if 'HIP_VISIBLE_DEVICES' in run_env and 'HIP_VISIBLE_DEVICES' not in os.environ:
        print('Integrated GPU hidden from ComfyUI: HIP_VISIBLE_DEVICES =', run_env['HIP_VISIBLE_DEVICES'], flush=True)
    raise SystemExit(subprocess.call([sys.executable, str(install_root / 'ComfyUI/main.py')]
                                    + startup_args(gpu_arch, sys.argv[1:]),
                                    cwd=install_root, env=run_env))
