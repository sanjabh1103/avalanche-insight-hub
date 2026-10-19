import zipfile
import io
import numpy as np
from pathlib import Path

def create_synthetic_archive():
    path = Path(__file__).parent.parent / "docs" / "assets" / "snowslide_mock.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as archive:
        # Create a valid minimal TIFF and NPZ for the seed script
        # The script does not use rasterio to parse it unless memoryfile is available,
        # but it just reads the bytes and uploads them.
        archive.writestr('validation/colorado_rockies/S1A_001/truth_mask.tif', b'mock_tiff_bytes')
        
        stack_payload = io.BytesIO()
        np.savez(stack_payload, stack=np.ones((2, 4, 4), dtype=np.float32))
        archive.writestr('validation/colorado_rockies/S1A_001/stack.npz', stack_payload.getvalue())
        
    print(f"Created synthetic archive at {path.absolute()}")

if __name__ == '__main__':
    create_synthetic_archive()
