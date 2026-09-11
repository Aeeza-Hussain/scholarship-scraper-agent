import sys, pathlib
root_dir = pathlib.Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from agent import root_agent

