"""Disable Gradio's source-stub generation after PyInstaller initializes runtime hooks."""

import sys


def _no_op(*a, **k):
    return None


class _PatchGradio:
    """Delay import until normal application startup (after numpy runtime setup)."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "gradio.component_meta":
            return None
        sys.meta_path.remove(self)
        from importlib.util import find_spec

        spec = find_spec(fullname)
        if spec is not None and spec.loader is not None:
            original_exec = spec.loader.exec_module

            def exec_module(module):
                original_exec(module)
                module.create_or_modify_pyi = _no_op

            spec.loader.exec_module = exec_module
        return spec


sys.meta_path.insert(0, _PatchGradio())
