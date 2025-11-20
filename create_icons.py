"""
Create minimal placeholder icon files for the application.
"""
import os
import subprocess
from pathlib import Path

try:
    from PIL import Image, ImageDraw
    
    def create_icon_image(size=(256, 256)):
        """Create a simple icon image with a 'V' shape."""
        img = Image.new('RGB', size, color=(70, 130, 180))  # Steel blue color
        draw = ImageDraw.Draw(img)
        
        # Draw a simple "V" shape
        width, height = size
        margin = width // 4
        line_width = max(width // 8, 4)
        draw.line([(margin, margin), (width//2, height - margin)], fill=(255, 255, 255), width=line_width)
        draw.line([(width//2, height - margin), (width - margin, margin)], fill=(255, 255, 255), width=line_width)
        
        return img
    
    def create_ico_file(output_path="icon.ico"):
        """Create a minimal ICO file."""
        img = create_icon_image((256, 256))
        img.save(output_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
        print(f"✓ Created {output_path}")
        return True
    
    def create_icns_file(output_path="icon.icns"):
        """Create a minimal ICNS file (macOS) using iconutil."""
        # Create PNG first
        png_path = "icon.png"
        img = create_icon_image((512, 512))
        img.save(png_path, format='PNG')
        
        # Check if iconutil is available
        if not subprocess.run(["which", "iconutil"], capture_output=True).returncode == 0:
            print("⚠ iconutil not found. Cannot create .icns file.")
            print(f"  Created {png_path} instead. Convert manually using:")
            print(f"  iconutil -c icns icon.iconset")
            return False
        
        # Create iconset directory
        iconset_dir = "icon.iconset"
        os.makedirs(iconset_dir, exist_ok=True)
        
        # Create all required sizes
        sizes = [
            (16, 16, "icon_16x16.png"),
            (32, 32, "icon_16x16@2x.png"),
            (32, 32, "icon_32x32.png"),
            (64, 64, "icon_32x32@2x.png"),
            (128, 128, "icon_128x128.png"),
            (256, 256, "icon_128x128@2x.png"),
            (256, 256, "icon_256x256.png"),
            (512, 512, "icon_256x256@2x.png"),
            (512, 512, "icon_512x512.png"),
            (1024, 1024, "icon_512x512@2x.png"),
        ]
        
        # Use sips to resize if available, otherwise use PIL
        if subprocess.run(["which", "sips"], capture_output=True).returncode == 0:
            for size, _, filename in sizes:
                subprocess.run(["sips", "-z", str(size), str(size), png_path, 
                              "--out", os.path.join(iconset_dir, filename)], 
                             capture_output=True)
        else:
            # Fallback: use PIL to create all sizes
            for size, _, filename in sizes:
                resized = create_icon_image((size, size))
                resized.save(os.path.join(iconset_dir, filename), format='PNG')
        
        # Convert iconset to icns
        result = subprocess.run(["iconutil", "-c", "icns", iconset_dir, "-o", output_path],
                              capture_output=True)
        
        # Clean up
        import shutil
        if os.path.exists(iconset_dir):
            shutil.rmtree(iconset_dir)
        
        if result.returncode == 0:
            print(f"✓ Created {output_path}")
            return True
        else:
            print(f"⚠ Failed to create {output_path}: {result.stderr.decode()}")
            return False
    
    if __name__ == "__main__":
        print("Creating icon files...")
        create_ico_file()
        create_icns_file()
        print("\n✓ Icon files created successfully!")
        
except ImportError:
    print("PIL/Pillow not found. Creating minimal icon files using basic method...")
    
    # Create a minimal valid ICO file (Windows)
    # ICO file format: header + directory + image data
    ico_data = bytes([
        0x00, 0x00,  # Reserved (must be 0)
        0x01, 0x00,  # Type (1 = ICO)
        0x01, 0x00,  # Number of images
        
        # Image directory entry
        0x10, 0x10,  # Width (16)
        0x10, 0x10,  # Height (16)
        0x00,        # Color palette (0 = no palette)
        0x00,        # Reserved
        0x01, 0x00,  # Color planes
        0x20, 0x00,  # Bits per pixel (32)
        0x00, 0x04, 0x00, 0x00,  # Image size (1024 bytes)
        0x16, 0x00, 0x00, 0x00,  # Offset to image data (22 bytes)
        
        # BMP header (40 bytes)
        0x28, 0x00, 0x00, 0x00,  # Header size (40)
        0x10, 0x00, 0x00, 0x00,  # Width (16)
        0x20, 0x00, 0x00, 0x00,  # Height (32, double for ICO)
        0x01, 0x00,              # Planes (1)
        0x20, 0x00,              # Bits per pixel (32)
        0x00, 0x00, 0x00, 0x00,  # Compression (0 = none)
        0x00, 0x04, 0x00, 0x00,  # Image size (1024)
        0x00, 0x00, 0x00, 0x00,  # X pixels per meter
        0x00, 0x00, 0x00, 0x00,  # Y pixels per meter
        0x00, 0x00, 0x00, 0x00,  # Colors used
        0x00, 0x00, 0x00, 0x00,  # Important colors
        
        # Image data (16x16x4 = 1024 bytes) - simple blue color
    ])
    
    # Fill with blue color (RGBA: 70, 130, 180, 255)
    blue_pixel = bytes([180, 130, 70, 255])  # BGR format
    ico_data += blue_pixel * (16 * 16)
    
    with open("icon.ico", "wb") as f:
        f.write(ico_data)
    
    print("Created icon.ico (minimal valid ICO file)")
    print("Note: For macOS, you'll need to create icon.icns separately")
    print("You can use: iconutil or an online converter")

