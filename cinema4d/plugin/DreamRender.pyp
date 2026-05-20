from __future__ import annotations

import os
import runpy

import c4d
from c4d import plugins


PLUGIN_ID = 1069957
PLUGIN_NAME = "DreamRender Submit Render"


class DreamRenderSubmitCommand(plugins.CommandData):
    def Execute(self, doc):
        script_path = os.path.join(os.path.dirname(__file__), "DreamRenderSubmit.py")
        runpy.run_path(script_path, run_name="__main__")
        return True


if __name__ == "__main__":
    plugins.RegisterCommandPlugin(
        id=PLUGIN_ID,
        str=PLUGIN_NAME,
        info=0,
        icon=None,
        help="Submit the current Cinema 4D render to DreamRender.",
        dat=DreamRenderSubmitCommand(),
    )
