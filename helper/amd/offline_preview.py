from pathlib import Path

SOURCE = 'from aiohttp import web\nfrom server import PromptServer\n\nNODE_CLASS_MAPPINGS = {}\n\n\n@web.middleware\nasync def offline_texture_preview(request, handler):\n    response = await handler(request)\n    policy = response.headers.get(\'Content-Security-Policy\')\n    if policy:\n        directives = policy.split(\';\')\n        for index, directive in enumerate(directives):\n            sources = directive.split()\n            if sources and sources[0] == \'connect-src\' and "\'none\'" not in sources:\n                if \'blob:\' not in sources:\n                    directives[index] = directive.rstrip() + \' blob:\'\n                    response.headers[\'Content-Security-Policy\'] = \';\'.join(directives)\n                break\n    return response\n\n\n# Run outside ComfyUI\'s offline middleware so its response policy is available.\nPromptServer.instance.app.middlewares.insert(0, offline_texture_preview)\n'


def install(comfy):
    destination = Path(comfy) / 'custom_nodes/ComfyUI-Offline-Textures/__init__.py'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(SOURCE, encoding='utf-8')
    print('Offline GLB texture previews enabled.', flush=True)
