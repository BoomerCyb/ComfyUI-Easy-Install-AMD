import ast
import io
import json
from pathlib import Path
import sys
import unittest
import tempfile
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'amd'))
import bundles
import runtime
import bundle_switch
import shortcuts
import setup
import install_nunchaku


class ConversionTests(unittest.TestCase):
    def test_pixaroma_sync_adds_missing_workflows_and_preserves_existing(self):
        import download_pixaroma
        payload = io.BytesIO()
        with zipfile.ZipFile(payload,'w') as archive:
            archive.writestr('old.json',json.dumps({'nodes':[],'links':[]}))
            archive.writestr('new.json',json.dumps({'nodes':[],'links':[]}))
            archive.writestr('resource.json','{"not_a_workflow":true}')
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)/'Pixaroma'
            destination.mkdir()
            (destination/'old.json').write_text('my edited workflow')
            stats = {'added':0,'existing':0}
            count = download_pixaroma.install_archive(payload.getvalue(),destination,Path(directory)/'backup',stats)
            self.assertEqual(count,2)
            self.assertEqual(stats,{'added':1,'existing':1})
            self.assertEqual((destination/'old.json').read_text(),'my edited workflow')
            self.assertTrue((destination/'new.json').exists())
            self.assertFalse((destination/'resource.json').exists())

    def test_pixaroma_rejects_archive_path_traversal(self):
        import download_pixaroma
        payload = io.BytesIO()
        with zipfile.ZipFile(payload,'w') as archive:
            archive.writestr('../escape.json','{"nodes":[]}')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                download_pixaroma.install_archive(payload.getvalue(),Path(directory)/'Pixaroma',Path(directory)/'backup')
    def test_node_requirements_keep_one_augmentation_provider(self):
        import node_requirements
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'requirements.txt'
            original = 'torch\nalbumentationsx\n-r extra.txt\n'
            source.write_text(original)
            captured = []
            def inspect(py,*arguments):
                adjusted = Path(arguments[-1])
                captured.append(adjusted.read_text())
                self.assertEqual(adjusted.parent,source.parent)
            with patch.object(node_requirements,'pip',side_effect=inspect):
                node_requirements.install_requirements(Path('python.exe'),source)
            self.assertIn('albumentations==2.0.8',captured[0])
            self.assertIn('albucore==0.0.24',captured[0])
            self.assertNotIn('albumentationsx',captured[0])
            self.assertIn('-r extra.txt',captured[0])
            self.assertEqual(source.read_text(),original)
            self.assertEqual(list(source.parent.glob('.amd-requirements-*')),[])
    def test_stable_presets_use_matched_published_versions(self):
        presets = json.loads((ROOT/'amd/bundle-presets.json').read_text())
        for preset in presets[1:]:
            specs,index = bundles.package_specs('gfx1201',preset['versions'])
            self.assertEqual(index,bundles.STABLE)
            self.assertTrue(all('==' in item for item in specs))
            self.assertIn('rocm-sdk-devel==10.0.0',specs)
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(bundles,'pip',side_effect=lambda *args,**kwargs:calls.append(args)),patch.object(bundles.subprocess,'run'):
                bundles.install_gpu(Path(directory)/'python.exe','gfx1201',presets[1]['versions'])
        self.assertNotIn('--pre',calls[1])
        self.assertFalse(any(bundles.SAGE_RDNA4 in call or bundles.BNB in call for call in calls))

    def test_working_preset_reuses_active_environment(self):
        preset = json.loads((ROOT/'amd/bundle-presets.json').read_text())[0]
        packages = [{'name':key,'version':value} for key,value in preset['versions'].items()
                    if key in ('torch','torchvision','torchaudio')]
        packages.append({'name':'rocm-sdk-devel','version':preset['versions']['rocm']})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'amd').mkdir()
            (root/'amd/active-bundle.json').write_text(json.dumps({'architecture':'gfx1201','packages':packages}))
            with patch.object(bundles,'architecture',return_value='gfx1201'),patch.object(bundles,'prepare') as prepare:
                bundles.select_preset(root,preset)
                prepare.assert_not_called()
            self.assertFalse((root/'amd/pending-bundle.txt').exists())

    def test_addon_status_uses_installation_files_and_packages(self):
        source = ROOT/'helper-source/ComfyUI-Easy-Install/Add-Ons/Tools/Helper-CEI/ComfyUI-EZi.py'
        api = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(node,ast.ClassDef) and node.name=='Api')
        method = next(node for node in api.body if isinstance(node,ast.FunctionDef) and node.name=='get_addon_status')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            namespace = {'ROOT_DIR':str(root),'json':json}
            exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),namespace)
            status = namespace['get_addon_status'](None)
            self.assertFalse(any(status.values()))
            addon = root/'ComfyUI/custom_nodes/ComfyUI-Nunchaku-AMD'
            addon.mkdir(parents=True)
            for name in ('__init__.py','nunchaku_amd.py','packed_kernel.py'):
                (addon/name).touch()
            for name in ('sageattention','flash_attn','amd_aiter','insightface','facexlib','onnxruntime'):
                metadata = root/f'python_embeded/Lib/site-packages/{name}-1.0.dist-info'
                metadata.mkdir(parents=True)
                (metadata/'METADATA').write_text(f'Name: {name}\nVersion: 1.0\n')
            # The AITER distribution is named amd-aiter in this Windows bundle.
            status = namespace['get_addon_status'](None)
            self.assertTrue(status['nunchaku.bat'])
            self.assertTrue(status['sageattention-multi (v2.2.0 and v3).bat'])
            self.assertTrue(status['insightface.bat'])
            groups = json.loads((ROOT/'amd/wtivo-node-groups.json').read_text())
            (root/'amd').mkdir()
            (root/'amd/wtivo-node-groups.json').write_text(json.dumps(groups))
            status = namespace['get_addon_status'](None)
            self.assertFalse(status['boomercyb wtivo amd nodes.bat'])
            self.assertFalse(status['mostaadtech wtivo nodes.bat'])
            for group in groups.values():
                for name in group['nodes']:
                    directory = root/'ComfyUI/custom_nodes'/name
                    directory.mkdir(parents=True)
                    (directory/'__init__.py').touch()
            status = namespace['get_addon_status'](None)
            self.assertTrue(status['boomercyb wtivo amd nodes.bat'])
            self.assertTrue(status['mostaadtech wtivo nodes.bat'])

    def test_family_download_catalog_is_pinned_and_confined(self):
        from pathlib import PurePosixPath
        import re
        catalog = json.loads((ROOT/'amd/nunchaku-families-downloads.json').read_text())
        self.assertEqual(set(catalog),{'flux2','sdxl','sana','t5','ltx2'})
        for family,entries in catalog.items():
            self.assertTrue(entries,family)
            self.assertEqual(len({item['path'] for item in entries}),len(entries),family)
            for item in entries:
                path = PurePosixPath(item['path'])
                self.assertFalse(path.is_absolute())
                self.assertNotIn('..',path.parts)
                self.assertNotIn('\\',item['path'])
                self.assertGreater(item['size'],0)
                self.assertRegex(item['url'],r'^https://huggingface\.co/[^/]+/[^/]+/resolve/[0-9a-f]{40}/')

    def test_nunchaku_addon_install_preserves_other_nodes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'ComfyUI/custom_nodes/another-node').mkdir(parents=True)
            (root / 'ComfyUI/main.py').write_text('existing ComfyUI')
            (root / 'ComfyUI/custom_nodes/another-node/user.py').write_text('user content')
            def download(command, **kwargs):
                if command[1] == 'clone':
                    source = Path(command[-1])
                    for name in ('__init__.py', 'nunchaku_amd.py', 'packed_kernel.py', 'NOTICE.txt', 'LICENSE',
                                 'Nunchaku-AMD-Qwen-Image-2.1-Viggle-Turbo.json', 'Nunchaku-AMD-Qwen-Layer-Test.json',
                                 'web/report.js', 'fixtures/qwen-int4-layer.safetensors', '.git/config'):
                        path = source / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text('downloaded test file')
            with patch.object(install_nunchaku.subprocess, 'run', side_effect=download), patch.object(install_nunchaku.subprocess, 'check_output', return_value=install_nunchaku.REVISION):
                install_nunchaku.install(root)
            self.assertEqual((root / 'ComfyUI/custom_nodes/another-node/user.py').read_text(), 'user content')
            addon = root / 'ComfyUI/custom_nodes/ComfyUI-Nunchaku-AMD'
            self.assertTrue((addon / 'web/report.js').is_file())
            self.assertTrue((addon / 'fixtures/qwen-int4-layer.safetensors').is_file())
            self.assertFalse((addon / '.cache').exists())
            self.assertTrue((root / 'ComfyUI/user/default/workflows/Nunchaku-AMD-Qwen-Layer-Test.json').is_file())
            (addon / 'previous-user-file.txt').write_text('preserve me')
            with patch.object(install_nunchaku.subprocess, 'run', side_effect=download), patch.object(install_nunchaku.subprocess, 'check_output', return_value=install_nunchaku.REVISION):
                install_nunchaku.install(root)
            backups = list((root / 'amd/nunchaku-backups').iterdir())
            self.assertEqual((backups[0] / 'previous-user-file.txt').read_text(), 'preserve me')
            self.assertTrue((addon / '.git/config').is_file())

    def test_nunchaku_download_failure_preserves_installed_addon(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            addon = root / 'ComfyUI/custom_nodes/ComfyUI-Nunchaku-AMD'
            addon.mkdir(parents=True)
            (root / 'ComfyUI/main.py').touch()
            (addon / 'user.txt').write_text('keep working add-on')
            with patch.object(install_nunchaku.subprocess, 'run', side_effect=install_nunchaku.subprocess.CalledProcessError(1, 'git')):
                with self.assertRaises(install_nunchaku.subprocess.CalledProcessError):
                    install_nunchaku.install(root)
            self.assertEqual((addon / 'user.txt').read_text(), 'keep working add-on')
            self.assertFalse(list((root / 'amd').glob('nunchaku-download-*')))

    def test_nunchaku_entry_uses_local_rocm_addon(self):
        batch = (ROOT / 'helper-source/ComfyUI-Easy-Install/Add-Ons/Nunchaku.bat').read_text()
        self.assertIn('install_nunchaku.py', batch)
        self.assertNotIn('pip install', batch)
        html = (ROOT / 'helper-source/ComfyUI-Easy-Install/Add-Ons/Tools/Helper-CEI/ComfyUI-EZi-shell.html').read_text(encoding='utf-8')
        self.assertIn('Nunchaku AMD — RX 9070 XT only', html)
    def test_existing_workflows_survive_clone_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ComfyUI'
            (path / 'user').mkdir(parents=True)
            (path / 'user/workflow.json').write_text('personal workflow')
            def fake_clone(command, **kwargs):
                target = Path(command[-1])
                (target / '.git').mkdir(parents=True)
                (target / 'main.py').write_text('source')
            with patch.object(setup.subprocess, 'run', side_effect=fake_clone):
                setup.clone('test-repository', path)
            self.assertEqual((path / 'user/workflow.json').read_text(), 'personal workflow')
            self.assertTrue((path / '.git').exists())
            backup = next(Path(directory).glob('ComfyUI-preserved-*'))
            self.assertEqual((backup / 'user/workflow.json').read_text(), 'personal workflow')

    def test_clone_failure_leaves_existing_workflows_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ComfyUI'
            (path / 'user').mkdir(parents=True)
            (path / 'user/workflow.json').write_text('personal workflow')
            with patch.object(setup.subprocess, 'run', side_effect=setup.subprocess.CalledProcessError(128, 'git')):
                with self.assertRaises(setup.subprocess.CalledProcessError):
                    setup.clone('test-repository', path)
            self.assertEqual((path / 'user/workflow.json').read_text(), 'personal workflow')

    def test_download_contains_one_pinned_bootstrap(self):
        with zipfile.ZipFile(ROOT / 'dist/ComfyUI-Easy-Install-AMD.zip') as archive:
            self.assertEqual(len(archive.namelist()), 7)
            self.assertTrue(all(name.startswith('ComfyUI-Easy-Install-AMD/') for name in archive.namelist()))
            self.assertIn('ComfyUI-Easy-Install-AMD/LICENSE', archive.namelist())
            bat = archive.read('ComfyUI-Easy-Install-AMD/ComfyUI-Easy-Install-AMD.bat').decode()
            self.assertIn('set "AMD_ROOT=%~dp0ComfyUI-Easy-Install-AMD"', bat)
            self.assertIn('github.com/BoomerCyb/ComfyUI-Easy-Install-AMD.git', bat)
            self.assertNotIn('set "AMD_SOURCE_REF=Windows"', bat)
            self.assertIn('checkout --detach FETCH_HEAD', bat)
            self.assertIn('stage_payload.py', bat)
            self.assertNotIn('Helper-AMD.zip', bat)
            self.assertIsNone(archive.testzip())

    def test_git_payload_staging_preserves_user_workflows(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('stage_payload', ROOT / 'tools/stage_payload.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'portable'
            workflow = destination / 'ComfyUI/user/default/workflows/personal.json'
            workflow.parent.mkdir(parents=True)
            workflow.write_text('personal workflow')
            module.stage(ROOT, destination)
            self.assertEqual(workflow.read_text(), 'personal workflow')
            self.assertTrue((destination / 'amd/setup.py').is_file())
            self.assertTrue((destination / 'Add-Ons/Tools/Helper-CEI/ComfyUI-EZi-Launcher.py').is_file())
            self.assertTrue((destination / 'documentation/licenses/EASY-INSTALL-LICENSE').is_file())
            self.assertTrue((destination / 'preset-files/ComfyUI').is_dir())
            module.stage(ROOT, destination)
            self.assertEqual(workflow.read_text(), 'personal workflow')
            with self.assertRaises(ValueError):
                module.stage(ROOT, ROOT / 'unsafe-target')

    def test_launcher_shortcuts_target_separate_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helper = root / 'Add-Ons/Tools/Helper-CEI'
            helper.mkdir(parents=True)
            (helper / 'ComfyUI-EZi-Launcher.py').touch()
            (root / 'python_embeded').mkdir()
            (root / 'python_embeded/pythonw.exe').touch()
            shell = MagicMock()
            shell.SpecialFolders.return_value = str(root / 'Desktop')
            links = [MagicMock(), MagicMock()]
            shell.CreateShortcut.side_effect = links
            client = SimpleNamespace(Dispatch=lambda name: shell)
            with patch.dict(sys.modules, {'win32com': SimpleNamespace(client=client), 'win32com.client': client}):
                shortcuts.create_launcher_shortcuts(root)
            self.assertEqual(shell.CreateShortcut.call_count, 2)
            for link in links:
                self.assertEqual(link.TargetPath, str(root / 'python_embeded/pythonw.exe'))
                self.assertIn('ComfyUI-EZi-Launcher.py', link.Arguments)
                link.Save.assert_called_once()
        self.assertTrue((ROOT / 'helper-source/ComfyUI-Easy-Install/ComfyUI-Easy-Install-AMD Launcher.bat').exists())

    def test_constraint_probe_is_executable_python(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'constraints.txt'
            bundles.constraints(Path(sys.executable), path)
            self.assertTrue(path.exists())
            self.assertIn('onnx==1.17.0', path.read_text())
            self.assertIn('protobuf==4.25.8', path.read_text())

    def test_embedded_source_installs_use_local_build_backend(self):
        with patch.object(bundles.subprocess, 'run') as run:
            bundles.pip(Path('python.exe'), 'install', 'some-source-package')
            self.assertIn('--no-build-isolation', run.call_args.args[0])
            self.assertIn('--only-binary=onnx,protobuf', run.call_args.args[0])
            bundles.pip(Path('python.exe'), 'uninstall', '-y', 'some-package')
            self.assertNotIn('--no-build-isolation', run.call_args.args[0])
            self.assertNotIn('--only-binary=onnx,protobuf', run.call_args.args[0])

    def test_build_backend_bootstrap_precedes_rocm_install(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            py = Path(directory) / 'python.exe'
            with patch.object(bundles, 'pip', side_effect=lambda *args, **kwargs: calls.append(args)), patch.object(bundles.subprocess, 'run'):
                bundles.install_gpu(py, 'gfx1201')
        self.assertIn('setuptools==81', calls[0])
        self.assertIn('--only-binary=:all:', calls[0])
        self.assertIn('torch[device-gfx1201]', calls[1])

    def test_no_shell_dependency_in_runtime(self):
        paths = [ROOT / 'ComfyUI-Easy-Install-AMD.bat']
        for directory in ('amd', 'helper-source'):
            paths.extend(p for p in (ROOT / directory).rglob('*') if p.suffix in ('.py', '.bat', '.ps1'))
        for path in paths:
            self.assertNotEqual(path.suffix, '.ps1', str(path))
            self.assertNotIn('powershell', path.read_text(encoding='utf-8-sig').lower(), str(path))

    def test_bundle_switch_retains_previous_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'amd').mkdir()
            active = root / 'python_embeded'
            active.mkdir()
            (active / 'marker.txt').write_text('old')
            bundle = root / 'bundles/20250101-000000'
            (bundle / 'python_embeded').mkdir(parents=True)
            (bundle / 'python_embeded/marker.txt').write_text('new')
            receipt = json.dumps({'verified': {'hip': 'test'}})
            (bundle / 'bundle.json').write_text(receipt)
            (bundle / 'amd-constraints.txt').write_text('new-constraint')
            (root / 'amd/active-bundle.json').write_text(receipt)
            (root / 'amd/amd-constraints.txt').write_text('old-constraint')
            (root / 'amd/pending-bundle.txt').write_text(bundle.name)
            process_api = SimpleNamespace(process_iter=lambda fields: [], NoSuchProcess=ProcessLookupError, AccessDenied=PermissionError)
            with patch('builtins.input', return_value=''), patch.dict(sys.modules, {'psutil': process_api}):
                bundle_switch.activate(root)
            self.assertEqual((active / 'marker.txt').read_text(), 'new')
            backups = [p for p in (root / 'bundles').iterdir() if p != bundle]
            self.assertEqual((backups[0] / 'python_embeded/marker.txt').read_text(), 'old')
            self.assertEqual((root / 'amd/amd-constraints.txt').read_text(), 'new-constraint')
            self.assertFalse((root / 'amd/pending-bundle.txt').exists())

    def test_rdna4_package_selection(self):
        specs, index = bundles.package_specs('gfx1201')
        self.assertIn('torch[device-gfx1201]', specs)
        self.assertIn('torchvision[device-gfx1201]', specs)
        self.assertIn('rocm-sdk-devel', specs)
        self.assertEqual(index, bundles.NIGHTLY)

    def test_exact_versions_and_legacy_architecture(self):
        specs, index = bundles.package_specs('gfx942', {'torch': '2.9.0', 'rocm': '7.2.0'})
        self.assertIn('torch==2.9.0', specs)
        self.assertIn('rocm[devel,libraries]==7.2.0', specs)
        self.assertIn('gfx942-dcgpu', index)

    def test_unsupported_architecture_rejected(self):
        with self.assertRaises(RuntimeError):
            bundles.package_specs('gfx1250')

    def test_rdna_attention_preserves_user_selection(self):
        self.assertIn('--use-ck-attention', runtime.startup_args('gfx1201', []))
        self.assertIn('--use-quad-cross-attention', runtime.startup_args('gfx1030', []))
        self.assertEqual(runtime.startup_args('gfx1201', ['--use-sage-attention']), ['--use-sage-attention'])

    def test_gpu_installs_do_not_inherit_active_bundle_constraints(self):
        with patch.dict(bundles.os.environ, {'PIP_CONSTRAINT': 'active.txt', 'UV_CONSTRAINT': 'active.txt'}):
            with patch.object(bundles.subprocess, 'run') as run:
                bundles.pip(Path('candidate/python.exe'), 'install', 'torch', constrained=False)
                self.assertNotIn('PIP_CONSTRAINT', run.call_args.kwargs['env'])
                bundles.pip(Path('active/python.exe'), 'install', 'some-node')
                self.assertEqual(run.call_args.kwargs['env']['PIP_CONSTRAINT'], 'active.txt')

    def test_all_python_sources_parse(self):
        for base in ('amd', 'tools', 'helper-source'):
            for path in (ROOT / base).rglob('*.py'):
                ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))

    def test_ezi_recognizes_and_edits_amd_launcher(self):
        script = ROOT / 'helper-source/ComfyUI-Easy-Install/Add-Ons/Tools/Helper-CEI/ComfyUI-EZi.py'
        tree = ast.parse(script.read_text(encoding='utf-8'))
        find_line = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_find_bat_comfy_line')
        scope = {'re': __import__('re')}
        exec(compile(ast.Module(body=[find_line], type_ignores=[]), str(script), 'exec'), scope)
        bat = (ROOT / 'helper-source/ComfyUI-Easy-Install/Start ComfyUI.bat').read_text()
        line = scope['_find_bat_comfy_line'](bat)
        self.assertIsNotNone(line)
        self.assertIn('amd\\runtime.py', line)
        self.assertIn('--enable-manager', line)

    def test_node_list_preserved(self):
        nodes = json.loads((ROOT / 'amd/nodes.json').read_text())
        self.assertEqual(len(nodes), 30)
        self.assertIn('Comfyui-Spectrum-Qwen2.1', {node['name'] for node in nodes})
        names = {n['name'] for n in nodes}
        self.assertIn('ComfyUI-GGUF', names)
        self.assertIn('ComfyUI-WanVideoWrapper', names)
        self.assertIn('ComfyUI-INT8-Fast-ROCM', names)

    def test_payload_has_no_cuda_installer(self):
        payload = ROOT / 'helper-source/ComfyUI-Easy-Install'
        for path in payload.rglob('*.bat'):
            text = path.read_text(encoding='utf-8-sig')
            self.assertNotIn('download.pytorch.org/whl/cu', text, str(path))
            self.assertNotIn('llama_cpp_python-0.3.46+cu', text, str(path))
        html = (payload / 'Add-Ons/Tools/Helper-CEI/ComfyUI-EZi-shell.html').read_text(encoding='utf-8')
        self.assertIn('ROCm Bundle Manager.bat', html)
        self.assertNotIn("_batBtn('Torch 2.", html)


if __name__ == '__main__':
    unittest.main()
