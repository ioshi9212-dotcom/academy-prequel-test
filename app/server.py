# Runtime shim for Railway test build.
# Loads the existing Academy runtime and then adds the compact scene-packet endpoint.
from app.scene_packet_runtime_patch import app
