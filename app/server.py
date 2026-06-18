# Final runtime shim for Railway.
# Importing scene_packet_runtime_patch loads the existing runtime chain first
# and then adds Variant A /scene-packet endpoint.
from app.scene_packet_runtime_patch import app
