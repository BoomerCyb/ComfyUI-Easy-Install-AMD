"""Experimental complete original Qwen-Image block for Nunchaku INT4 weights."""
import torch
import torch.nn.functional as F
if __package__:
    from .nunchaku_amd import AMDInt4Linear
    from .awq import AMDAWQLinear
else:
    from nunchaku_amd import AMDInt4Linear
    from awq import AMDAWQLinear


def rms_norm(x, weight, eps=1e-6):
    normalized = (x.float() * torch.rsqrt(x.float().square().mean(-1, keepdim=True) + eps)).to(x.dtype)
    return normalized * weight


def apply_rope(x, pe):
    if pe is None:
        return x
    pairs = x.float().reshape(*x.shape[:-1], -1, 2)
    return (pe[..., 0] * pairs[..., 0, None] + pe[..., 1] * pairs[..., 1, None]).reshape_as(x).to(x.dtype)


class AMDQwenBlock(torch.nn.Module):
    def __init__(self, state, *, backend='triton', activation_bits=4, heads=24):
        super().__init__()
        self.heads = heads
        self.dim = state['attn.to_add_out.qweight'].shape[0]
        self.layers = torch.nn.ModuleDict()
        prefixes = sorted(key[:-8] for key in state if key.endswith('.qweight'))
        for prefix in prefixes:
            tensors = {key[len(prefix) + 1:]: value for key, value in state.items() if key.startswith(prefix + '.')}
            if prefix in ('img_mod.1', 'txt_mod.1'):
                layer = AMDAWQLinear(tensors, modulation=True, backend=backend)
            else:
                fc2 = prefix in ('img_mlp.net.2', 'txt_mlp.net.2')
                layer = AMDInt4Linear(tensors, backend=backend, activation_bits=activation_bits,
                                     unsigned=fc2, activation_shift=0.171875 if fc2 else 0.0)
            self.layers[prefix.replace('.', '_')] = layer
        for name in ('norm_q', 'norm_k', 'norm_added_q', 'norm_added_k'):
            self.register_buffer(name, state[f'attn.{name}.weight'])

    def project(self, name, x):
        return self.layers[name.replace('.', '_')](x)

    @staticmethod
    def modulate(x, params):
        shift, scale, gate = params.chunk(3, dim=-1)
        # +1 is already folded into the checkpoint's AWQ modulation biases.
        return x * scale[:, None] + shift[:, None], gate[:, None]

    def attention(self, image, text, mask, pe):
        b, ni, d = image.shape
        nt = text.shape[1]
        iq, ik, iv = self.project('attn.to_qkv', image).chunk(3, dim=-1)
        tq, tk, tv = self.project('attn.add_qkv_proj', text).chunk(3, dim=-1)
        reshape = lambda x: x.reshape(b, -1, self.heads, d // self.heads).transpose(1, 2)
        iq, ik, iv, tq, tk, tv = map(reshape, (iq, ik, iv, tq, tk, tv))
        q = torch.cat((rms_norm(tq, self.norm_added_q), rms_norm(iq, self.norm_q)), dim=2)
        k = torch.cat((rms_norm(tk, self.norm_added_k), rms_norm(ik, self.norm_k)), dim=2)
        v = torch.cat((tv, iv), dim=2)
        q, k = apply_rope(q, pe), apply_rope(k, pe)
        if mask is not None:
            text_mask = mask.to(device=image.device, dtype=torch.bool).reshape(b, nt)
            joint_mask = torch.cat((text_mask, torch.ones((b, ni), device=image.device, dtype=torch.bool)), dim=1)[:, None, None, :]
        else:
            joint_mask = None
        value = F.scaled_dot_product_attention(q, k, v, attn_mask=joint_mask, dropout_p=0.0)
        value = value.transpose(1, 2).reshape(b, nt + ni, d)
        return self.project('attn.to_out.0', value[:, nt:]), self.project('attn.to_add_out', value[:, :nt])

    def mlp(self, stream, x):
        value = self.project(f'{stream}_mlp.net.0.proj', x)
        value = F.gelu(value, approximate='tanh')
        return self.project(f'{stream}_mlp.net.2', value)

    @torch.inference_mode()
    def forward(self, hidden_states, encoder_hidden_states, encoder_hidden_states_mask, temb,
                image_rotary_emb=None, timestep_zero_index=None, transformer_options=None):
        if timestep_zero_index is not None:
            raise ValueError('Qwen Edit timestep-zero mode is not implemented; use original Qwen-Image T2I')
        options = transformer_options or {}
        if options.get('patches'):
            raise ValueError('Attention patches are not implemented in the experimental AMD backend')
        img1, img2 = self.project('img_mod.1', F.silu(temb)).chunk(2, dim=-1)
        txt1, txt2 = self.project('txt_mod.1', F.silu(temb)).chunk(2, dim=-1)
        ni = F.layer_norm(hidden_states, (self.dim,), eps=1e-6)
        nt = F.layer_norm(encoder_hidden_states, (self.dim,), eps=1e-6)
        xi, gi = self.modulate(ni, img1)
        xt, gt = self.modulate(nt, txt1)
        ai, at = self.attention(xi, xt, encoder_hidden_states_mask, image_rotary_emb)
        hidden_states = hidden_states + gi * ai
        encoder_hidden_states = encoder_hidden_states + gt * at
        xi, gi = self.modulate(F.layer_norm(hidden_states, (self.dim,), eps=1e-6), img2)
        xt, gt = self.modulate(F.layer_norm(encoder_hidden_states, (self.dim,), eps=1e-6), txt2)
        return encoder_hidden_states + gt * self.mlp('txt', xt), hidden_states + gi * self.mlp('img', xi)
