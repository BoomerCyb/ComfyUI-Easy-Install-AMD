"""Experimental ROCm INT4 linear backend. Not a complete Nunchaku replacement."""
import torch


def unpack_weight(packed):
    n, half_k = packed.shape
    k = half_k * 2
    if packed.dtype != torch.int8 or n % 128 or k % 128:
        raise ValueError('Expected Nunchaku INT4 int8 weights with N%128=K%128=0')
    words = packed.contiguous().view(torch.int32)
    shifts = torch.arange(8, device=packed.device, dtype=torch.int32) * 4
    values = ((words[..., None] >> shifts) & 15)
    values = torch.where(values >= 8, values - 16, values)
    values = values.reshape(n // 128, k // 64, 1, 8, 8, 4, 2, 2, 1, 8)
    return values.permute(0, 3, 6, 4, 8, 1, 2, 7, 5, 9).reshape(n, k)


def unpack_scales(packed, n, k):
    if packed.numel() != n * (k // 64):
        raise ValueError('Only group-size-64 INT4 scales are supported')
    return packed.reshape(n // 128, k // 64, 1, 8, 4, 2, 2).permute(0, 2, 3, 5, 4, 6, 1).reshape(n, k // 64)


def unpack_lowrank(packed, down):
    c, r = packed.shape
    if c % 16 or r % 16:
        raise ValueError('Packed low-rank dimensions must be multiples of 16')
    value = packed.reshape(c // 16, r // 16, 8, 4, 2, 2, 1, 2)
    value = value.permute(0, 1, 4, 2, 6, 5, 3, 7).contiguous().reshape(c // 16, r // 16, 16, 16)
    return (value.permute(1, 2, 0, 3).reshape(r, c) if down else
            value.permute(0, 2, 1, 3).reshape(c, r))


def quantize_activation(x, unsigned=False):
    grouped = x.float().reshape(*x.shape[:-1], -1, 64)
    scales = (grouped.clamp_min(0).amax(-1, keepdim=True) / 15 if unsigned else grouped.abs().amax(-1, keepdim=True) / 7)
    safe = torch.where(scales == 0, torch.ones_like(scales), scales)
    values = torch.round(grouped / safe).clamp(0, 15) if unsigned else torch.round(grouped / safe).clamp(-7, 7)
    return (values * scales.to(x.dtype).float()).reshape_as(x).to(x.dtype)


@torch.inference_mode()
def linear(x, qweight, wscales, *, proj_down=None, proj_up=None,
           bias=None, activation_bits=4, backend='torch'):
    """Signed INT4/SVD branch prototype; expects upstream packed weights/scales.

    Smoothing, unsigned activations, NVFP4, fused attention and full-model APIs
    are deliberately unsupported. Input is already in the quantization domain.
    """
    n, half_k = qweight.shape
    k = half_k * 2
    if qweight.dtype != torch.int8 or n % 128 or k % 128:
        raise ValueError('Expected aligned signed INT4 Nunchaku weights')
    if wscales.dtype not in (torch.float16, torch.bfloat16):
        raise ValueError('Only FP16/BF16 group-size-64 INT4 scales are supported')
    if x.shape[-1] != k or x.dtype not in (torch.float16, torch.bfloat16):
        raise ValueError('Input must be FP16/BF16 with the weight input width')
    if activation_bits not in (4, 16):
        raise ValueError('activation_bits must be 4 or 16')
    if backend not in ('torch', 'triton'):
        raise ValueError('backend must be torch or triton')
    if (proj_down is None) != (proj_up is None):
        raise ValueError('Both low-rank projections are required')
    if any(t.device != x.device for t in (qweight, wscales, proj_down, proj_up, bias) if t is not None):
        raise ValueError('All tensors must be on the same device')
    xq = quantize_activation(x) if activation_bits == 4 else x
    if backend == 'triton':
        if __package__:
            from .packed_kernel import packed_linear
        else:
            from packed_kernel import packed_linear
        result = packed_linear(xq, qweight, wscales)
    else:
        if wscales.numel() != n * (k // 64):
            raise ValueError('Expected group-size-64 weight scales')
        # Decode 128 output channels at a time; do not expand the whole model.
        result = torch.empty((*x.shape[:-1], n), dtype=x.dtype, device=x.device)
        flat_scales = wscales.reshape(n // 128, -1)
        for start in range(0, n, 128):
            qw = unpack_weight(qweight[start:start + 128])
            ws = unpack_scales(flat_scales[start // 128], 128, k)
            dense = (qw.reshape(128, k // 64, 64).float() * ws.float().unsqueeze(-1)).reshape(128, k).to(x.dtype)
            result[..., start:start + 128] = xq @ dense.T
    if proj_down is not None:
        down = unpack_lowrank(proj_down, True)
        up = unpack_lowrank(proj_up, False)
        result = (result.float() + (x.float() @ down.float().T) @ up.float().T).to(x.dtype)
    if bias is not None:
        result = result + bias
    return result


class AMDInt4Linear(torch.nn.Module):
    """Standalone layer accepting an upstream signed-INT4 layer state dict.

    This does not implement Nunchaku's native-extension or model-loader API.
    Packed parameters stay compressed; BF16/FP16 dot products handle compute.
    """
    def __init__(self, state, *, backend='triton', activation_bits=4, unsigned=False, activation_shift=0.0):
        super().__init__()
        if 'wcscales' in state or 'wtscale' in state:
            raise ValueError('NVFP4 checkpoints are unsupported; use signed INT4')
        for key in ('qweight', 'wscales', 'proj_down', 'proj_up', 'smooth_factor', 'bias'):
            if key in state:
                self.register_buffer(key, state[key])
            else:
                setattr(self, key, None)
        if self.qweight is None or self.wscales is None:
            raise ValueError('qweight and wscales are required')
        self.backend = backend
        self.activation_bits = activation_bits
        self.unsigned = unsigned
        self.activation_shift = activation_shift
        self._runtime_key = None
        self._runtime_cache = None

    def clear_runtime_cache(self):
        self._runtime_key = None
        self._runtime_cache = None

    def _apply(self, fn, recurse=True):
        self.clear_runtime_cache()
        return super()._apply(fn, recurse=recurse)

    def _load_from_state_dict(self, *args, **kwargs):
        self.clear_runtime_cache()
        return super()._load_from_state_dict(*args, **kwargs)

    def _prepare_runtime(self):
        def stamp(value):
            if value is None:
                return None
            try:
                version = value._version
            except RuntimeError:  # immutable inference tensors have no version counter
                version = None
            return (id(value), version, value.device, value.dtype)
        key = tuple(stamp(value) for value in (self.smooth_factor, self.proj_down, self.proj_up, self.bias))
        if key != self._runtime_key:
            factor = None
            if self.smooth_factor is not None:
                factor = unpack_scales(self.smooth_factor, self.qweight.shape[1]*2, 64).reshape(-1).float()
                if not torch.isfinite(factor).all() or (factor == 0).any():
                    raise ValueError('Smoothing factors must be finite and nonzero')
            if (self.proj_down is None) != (self.proj_up is None):
                raise ValueError('Both low-rank projections are required')
            down = unpack_lowrank(self.proj_down, True).float() if self.proj_down is not None else None
            up = unpack_lowrank(self.proj_up, False).float() if self.proj_up is not None else None
            bias = unpack_scales(self.bias, self.qweight.shape[0], 64).reshape(-1) if self.bias is not None else None
            self._runtime_cache = (factor, down, up, bias)
            self._runtime_key = key
        return self._runtime_cache

    @torch.inference_mode()
    def forward(self, x):
        # Upstream computes the low-rank branch on unsmoothed input.
        original = x
        factor, down, up, bias = self._prepare_runtime()
        if self.activation_shift:
            x = x + self.activation_shift
        if self.smooth_factor is not None:
            x = (x.float() / factor).to(x.dtype)
        if self.activation_bits == 4:
            x = quantize_activation(x, unsigned=self.unsigned)
        result = linear(x, self.qweight, self.wscales, bias=None,
                        activation_bits=16, backend=self.backend)
        if down is not None:
            result = (result.float() + (original.float() @ down.T) @ up.T).to(x.dtype)
        return result if bias is None else result + bias
