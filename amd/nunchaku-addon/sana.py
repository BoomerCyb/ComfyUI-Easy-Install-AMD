"""Nunchaku SANA-1.6B packed INT4 blocks with ROCm PyTorch attention."""
import json
import torch
import torch.nn.functional as F
from safetensors import safe_open
if __package__:
    from .nunchaku_amd import AMDInt4Linear,unpack_scales
else:
    from nunchaku_amd import AMDInt4Linear,unpack_scales


class PaddedProjection(torch.nn.Module):
    def __init__(self, layer, output_dim=None):
        super().__init__()
        self.layer,self.output_dim = layer,output_dim

    def forward(self,x):
        width = self.layer.qweight.shape[1]*2
        if x.shape[-1] > width:
            raise ValueError('SANA projection input is too wide')
        result = self.layer(F.pad(x,(0,width-x.shape[-1])))
        return result if self.output_dim is None else result[...,:self.output_dim]


class Pointwise(torch.nn.Module):
    def __init__(self,original):
        super().__init__()
        self.weight,self.bias = original.weight,original.bias

    def forward(self,x):
        return F.linear(x.movedim(1,-1),self.weight[:,:,0,0],self.bias).movedim(-1,1)


class SanaBlock(torch.nn.Module):
    def __init__(self,state,*,backend='triton',activation_bits=4,dim=2240):
        super().__init__()
        self.dim = dim
        aliases = dict(lora_down='proj_down',lora_up='proj_up',smooth='smooth_factor',smooth_orig='smooth_factor_orig')
        self.projections = torch.nn.ModuleDict()
        consumed = set()
        for prefix in sorted(key[:-8] for key in state if key.endswith('.qweight')):
            names = {key for key in state if key.startswith(prefix+'.')}
            tensors = {aliases.get(key[len(prefix)+1:],key[len(prefix)+1:]):state[key] for key in names}
            required = {'qweight','wscales','proj_down','proj_up','smooth_factor'}
            if not required <= tensors.keys() or tensors.keys()-required-{'smooth_factor_orig','bias'}:
                raise ValueError(f'Unexpected SANA fields: {prefix}')
            input_width = tensors['qweight'].shape[1]*2
            valid_width = int(dim*2.5) if prefix == 'ff.point_conv' else dim
            factor = unpack_scales(tensors['smooth_factor'],input_width,64).reshape(-1)
            if (factor[:valid_width] == 0).any():
                raise ValueError(f'Zero smoothing in active SANA channels: {prefix}')
            # Published weights pad input channels with zero smoothing. Those
            # channels are identically zero; dividing them by one preserves zero.
            tensors['smooth_factor'] = tensors['smooth_factor'].masked_fill(tensors['smooth_factor']==0,1)
            self.projections[prefix.replace('.','_')] = AMDInt4Linear(tensors,backend=backend,activation_bits=activation_bits)
            consumed.update(names)
        expected = {'scale_shift_table','cross_attn.kv_linear.weight','cross_attn.kv_linear.bias',
                    'ff.depth_conv.weight','ff.depth_conv.bias'}
        if state.keys()-consumed != expected:
            raise ValueError(f'Unexpected SANA block tensors: {state.keys()-consumed-expected}')
        self.register_buffer('scale_shift_table',state['scale_shift_table'])
        self.register_buffer('kv_weight',state['cross_attn.kv_linear.weight'])
        self.register_buffer('kv_bias',state['cross_attn.kv_linear.bias'])
        self.register_buffer('depth_weight',state['ff.depth_conv.weight'].permute(0,3,1,2).contiguous())
        self.register_buffer('depth_bias',state['ff.depth_conv.bias'])

    def project(self,prefix,x,output_dim=None):
        layer = self.projections[prefix.replace('.','_')]
        width = layer.qweight.shape[1]*2
        result = layer(F.pad(x,(0,width-x.shape[-1])))
        return result if output_dim is None else result[...,:output_dim]

    def forward(self,hidden_states,attention_mask=None,encoder_hidden_states=None,
                encoder_attention_mask=None,timestep=None,height=None,width=None):
        batch,tokens,_ = hidden_states.shape
        shift,scale,gate,shift_ff,scale_ff,gate_ff = (self.scale_shift_table[None]+timestep.reshape(batch,6,self.dim)).chunk(6,dim=1)
        x = F.layer_norm(hidden_states,(self.dim,),eps=1e-6)*(1+scale)+shift
        qkv = self.project('attn.qkv_proj',x)
        q = qkv[...,:qkv.shape[-1]//3]
        padded_dim = q.shape[-1]
        # CUDA LiteLA stores Q followed by [K_head, V_head] for each head.
        kv = qkv[...,padded_dim:].reshape(batch,tokens,padded_dim//32,2,32)
        k,v = kv[:,:,:,0].flatten(-2),kv[:,:,:,1].flatten(-2)
        q,k,v = [t.reshape(batch,tokens,padded_dim//32,32).permute(0,2,3,1).float() for t in (q,k,v)]
        q,k = F.relu(q),F.relu(k)
        v = F.pad(v,(0,0,0,1),value=1)
        out = (v@k.transpose(-1,-2))@q
        out = (out[:,:,:-1]/(out[:,:,-1:]+1e-15)).flatten(1,2).transpose(1,2).to(hidden_states.dtype)
        hidden_states = hidden_states+gate*self.project('attn.out_proj',out,self.dim)
        q = self.project('cross_attn.q_linear',hidden_states,self.dim)
        k,v = F.linear(encoder_hidden_states,self.kv_weight,self.kv_bias).chunk(2,dim=-1)
        q,k,v = [t.reshape(batch,-1,20,self.dim//20).transpose(1,2) for t in (q,k,v)]
        mask = encoder_attention_mask
        if mask is not None:
            mask = mask.reshape(batch,1,1,-1)
        out = F.scaled_dot_product_attention(q,k,v,attn_mask=mask).transpose(1,2).reshape(batch,tokens,self.dim)
        hidden_states = hidden_states+self.project('cross_attn.out_proj',out,self.dim)
        x = F.layer_norm(hidden_states,(self.dim,),eps=1e-6)*(1+scale_ff)+shift_ff
        x = F.silu(self.project('ff.inverted_conv',x))
        channels = x.shape[-1]
        x = x.transpose(1,2).reshape(batch,channels,height,width)
        # MIOpen on Windows rejects these large BF16 depthwise group counts.
        padded = F.pad(x,(1,1,1,1))
        acc = self.depth_bias.float()[None,:,None,None].expand(batch,channels,height,width).clone()
        for row in range(3):
            for col in range(3):
                acc += padded[:,:,row:row+height,col:col+width].float()*self.depth_weight[:,0,row,col].float()[None,:,None,None]
        x = acc.to(x.dtype)
        x = x.flatten(2).transpose(1,2)
        # Upstream fused GLU consumes adjacent value/gate channel pairs.
        x,gate = x[...,0::2],x[...,1::2]
        out = self.project('ff.point_conv',x*F.silu(gate),self.dim)
        return hidden_states+gate_ff*out


def load_sana(path,*,backend='triton',activation_bits=4):
    from diffusers import SanaTransformer2DModel
    with safe_open(str(path),framework='pt',device='cpu') as checkpoint:
        metadata = checkpoint.metadata() or {}
        config = json.loads(metadata.get('config','{}'))
        if metadata.get('model_class') != 'NunchakuSanaTransformer2DModel':
            raise ValueError('Expected Nunchaku SANA weights')
        if (config.get('num_attention_heads'),config.get('attention_head_dim'),config.get('num_layers')) != (70,32,20):
            raise ValueError('Only the published SANA-1.6B architecture is supported')
        with torch.device('meta'):
            model = SanaTransformer2DModel.from_config(config)
        keys = list(checkpoint.keys())
        backbone = {key:checkpoint.get_tensor(key) for key in keys if not key.startswith('transformer_blocks.')}
        blocks = []
        for index in range(config['num_layers']):
            prefix = f'transformer_blocks.{index}.'
            state = {key[len(prefix):]:checkpoint.get_tensor(key) for key in keys if key.startswith(prefix)}
            blocks.append(SanaBlock(state,backend=backend,activation_bits=activation_bits))
        model.transformer_blocks = torch.nn.ModuleList(blocks)
        missing,unexpected = model.load_state_dict(backbone,strict=False,assign=True)
        expected = {name for name in model.state_dict() if name.startswith('transformer_blocks.')}
        if set(missing) != expected or unexpected:
            raise ValueError(f'SANA backbone mismatch: {set(missing)^expected}, {unexpected}')
        model = model.to(dtype=torch.bfloat16)
        model.patch_embed.proj = Pointwise(model.patch_embed.proj)
        if any(t.is_meta for t in (*model.parameters(),*model.buffers())):
            raise ValueError('Uninitialized SANA tensor')
        model.eval().requires_grad_(False)
        model.nunchaku_amd_info = dict(architecture='sana-1.6b',blocks=len(blocks),
                                      quantized_projections=sum(len(b.projections) for b in blocks),backend=backend,
                                      activation_bits=activation_bits,experimental=True)
        return model
