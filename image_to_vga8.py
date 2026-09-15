#!/usr/bin/env python3
"""
8-Bit VGA Image Converter for SystemVerilog / DE10 FPGA
Converts any image (PNG, JPG, BMP, WEBP, GIF, etc.) into 8-bit RGB332 format matching
the lab appendix table (Bits [7:5] Red, Bits [4:2] Green, Bits [1:0] Blue).

Outputs:
  - .hex   (For SystemVerilog $readmemh)
  - .mif   (Intel Quartus Memory Initialization File)
  - .sv    (SystemVerilog ROM module, package, and 2D logic array definition)
  - .c/.h  (C/C++ array header for embedded / Nios II / HPS projects)
  - .png   (Preview of converted 8-bit image)
"""

import sys
import os
import re
import argparse
from pathlib import Path

try:
    from PIL import Image, ImageOps
    import numpy as np
except ImportError:
    print("Error: Pillow and NumPy are required.")
    print("Please install them using: pip install pillow numpy")
    sys.exit(1)


def rgb888_to_rgb332(r_255, g_255, b_255):
    """
    Convert 24-bit RGB (0-255 each) to 8-bit RGB332 byte value.
    - Red:   3 bits (bits [7:5], values 0-7)
    - Green: 3 bits (bits [4:2], values 0-7)
    - Blue:  2 bits (bits [1:0], values 0-3)
    """
    r3 = int(round(r_255 * 7.0 / 255.0))
    g3 = int(round(g_255 * 7.0 / 255.0))
    b2 = int(round(b_255 * 3.0 / 255.0))
    
    r3 = max(0, min(7, r3))
    g3 = max(0, min(7, g3))
    b2 = max(0, min(3, b2))
    
    return (r3 << 5) | (g3 << 2) | b2


def rgb332_to_rgb888(val_8bit):
    """
    Reconstruct 24-bit RGB (0-255) from 8-bit RGB332 byte value for preview.
    """
    r3 = (val_8bit >> 5) & 0x07
    g3 = (val_8bit >> 2) & 0x07
    b2 = val_8bit & 0x03
    
    r8 = int(round(r3 * 255.0 / 7.0))
    g8 = int(round(g3 * 255.0 / 7.0))
    b8 = int(round(b2 * 255.0 / 3.0))
    
    return (r8, g8, b8)


def sanitize_identifier(name):
    """
    Sanitize string to be a valid SystemVerilog / C identifier.
    """
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    clean = re.sub(r'_+', '_', clean).strip('_')
    if clean and clean[0].isdigit():
        clean = 'img_' + clean
    return clean or 'image_rom'


def quantize_image_rgb332(img, dither=True):
    """
    Convert a PIL RGB Image object to an 8-bit RGB332 numpy array (H, W)
    and a preview RGB888 PIL Image.
    Uses Floyd-Steinberg error diffusion dithering if dither=True.
    """
    arr = np.array(img, dtype=np.float32)
    height, width, _ = arr.shape
    
    rgb332_out = np.zeros((height, width), dtype=np.uint8)
    preview_out = np.zeros((height, width, 3), dtype=np.uint8)
    
    if dither:
        for y in range(height):
            for x in range(width):
                old_r = arr[y, x, 0]
                old_g = arr[y, x, 1]
                old_b = arr[y, x, 2]
                
                # Quantize to RGB332
                val = rgb888_to_rgb332(old_r, old_g, old_b)
                rgb332_out[y, x] = val
                
                # Reconstructed color
                new_r, new_g, new_b = rgb332_to_rgb888(val)
                preview_out[y, x] = [new_r, new_g, new_b]
                
                # Error diffusion
                err_r = old_r - new_r
                err_g = old_g - new_g
                err_b = old_b - new_b
                
                if x + 1 < width:
                    arr[y, x + 1, 0] += err_r * 7 / 16.0
                    arr[y, x + 1, 1] += err_g * 7 / 16.0
                    arr[y, x + 1, 2] += err_b * 7 / 16.0
                if y + 1 < height:
                    if x - 1 >= 0:
                        arr[y + 1, x - 1, 0] += err_r * 3 / 16.0
                        arr[y + 1, x - 1, 1] += err_g * 3 / 16.0
                        arr[y + 1, x - 1, 2] += err_b * 3 / 16.0
                    arr[y + 1, x, 0] += err_r * 5 / 16.0
                    arr[y + 1, x, 1] += err_g * 5 / 16.0
                    arr[y + 1, x, 2] += err_b * 5 / 16.0
                    if x + 1 < width:
                        arr[y + 1, x + 1, 0] += err_r * 1 / 16.0
                        arr[y + 1, x + 1, 1] += err_g * 1 / 16.0
                        arr[y + 1, x + 1, 2] += err_b * 1 / 16.0
    else:
        for y in range(height):
            for x in range(width):
                r, g, b = arr[y, x]
                val = rgb888_to_rgb332(r, g, b)
                rgb332_out[y, x] = val
                preview_out[y, x] = rgb332_to_rgb888(val)
                
    return rgb332_out, Image.fromarray(preview_out, 'RGB')


def resize_image(img, target_width, target_height, aspect_mode='stretch', bg_color=(0, 0, 0)):
    """
    Resize image to target width and height according to aspect_mode:
    - 'stretch': force resize to target_width x target_height
    - 'fit': resize preserving aspect ratio, pad remaining area with bg_color
    - 'crop': resize preserving aspect ratio to fill area, crop overflow
    """
    if aspect_mode == 'stretch':
        return img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    elif aspect_mode == 'fit':
        img_fitted = ImageOps.contain(img, (target_width, target_height), method=Image.Resampling.LANCZOS)
        bg = Image.new('RGB', (target_width, target_height), bg_color)
        offset = ((target_width - img_fitted.width) // 2, (target_height - img_fitted.height) // 2)
        bg.paste(img_fitted, offset)
        return bg
    elif aspect_mode == 'crop':
        return ImageOps.fit(img, (target_width, target_height), method=Image.Resampling.LANCZOS)
    else:
        raise ValueError(f"Unknown aspect_mode: {aspect_mode}")


def export_hex(data_2d, filepath):
    """
    Export 2D numpy array of 8-bit bytes to a .hex file (space-separated hex per line)
    suitable for Verilog $readmemh.
    """
    height, width = data_2d.shape
    with open(filepath, 'w') as f:
        f.write(f"// 8-Bit RGB332 Image Data ({width}x{height}, total {width*height} bytes)\n")
        f.write(f"// Format: [7:5]=Red, [4:2]=Green, [1:0]=Blue\n")
        for y in range(height):
            line_hex = [f"{data_2d[y, x]:02X}" for x in range(width)]
            f.write(" ".join(line_hex) + "\n")


def export_mif(data_2d, filepath):
    """
    Export to Intel Quartus Memory Initialization File (.mif).
    """
    height, width = data_2d.shape
    total_words = height * width
    
    with open(filepath, 'w') as f:
        f.write(f"-- Quartus Memory Initialization File (.mif)\n")
        f.write(f"-- Generated for VGA 8-bit color display ({width}x{height})\n\n")
        f.write(f"DEPTH = {total_words};\n")
        f.write(f"WIDTH = 8;\n")
        f.write(f"ADDRESS_RADIX = HEX;\n")
        f.write(f"DATA_RADIX = HEX;\n\n")
        f.write(f"CONTENT BEGIN\n")
        
        addr = 0
        for y in range(height):
            for x in range(width):
                val = data_2d[y, x]
                f.write(f"    {addr:04X} : {val:02X};\n")
                addr += 1
                
        f.write(f"END;\n")


def export_sv(data_2d, filepath, raw_name="image_rom"):
    """
    Export SystemVerilog module, package, 2D logic array declaration, and testbench (.sv).
    """
    height, width = data_2d.shape
    total_words = height * width
    addr_bits = max(1, (total_words - 1).bit_length())
    
    clean_name = sanitize_identifier(raw_name)
    mod_name = f"{clean_name}_rom"
    pkg_name = f"{clean_name}_pkg"
    
    with open(filepath, 'w') as f:
        f.write(f"// ============================================================================\n")
        f.write(f"// SystemVerilog ROM Module & Data Package\n")
        f.write(f"// Image Resolution: {width} x {height} ({total_words} pixels)\n")
        f.write(f"// Color Format    : 8-bit RGB332 ([7:5] Red, [4:2] Green, [1:0] Blue)\n")
        f.write(f"// ============================================================================\n\n")
        
        # Package
        f.write(f"package {pkg_name};\n")
        f.write(f"    localparam int IMG_WIDTH    = {width};\n")
        f.write(f"    localparam int IMG_HEIGHT   = {height};\n")
        f.write(f"    localparam int TOTAL_PIXELS = {total_words};\n")
        f.write(f"    localparam int ADDR_WIDTH   = {addr_bits};\n")
        f.write(f"endpackage : {pkg_name}\n\n")
        
        # ROM Module
        f.write(f"module {mod_name} (\n")
        f.write(f"    input  logic [{addr_bits-1}:0] addr,\n")
        f.write(f"    output logic [7:0]       color\n")
        f.write(f");\n\n")
        f.write(f"    always_comb begin\n")
        f.write(f"        case (addr)\n")
        
        addr = 0
        for y in range(height):
            for x in range(width):
                val = data_2d[y, x]
                f.write(f"            {addr_bits}'h{addr:X}: color = 8'h{val:02X};\n")
                addr += 1
                
        f.write(f"            default: color = 8'h00;\n")
        f.write(f"        endcase\n")
        f.write(f"    end\n")
        f.write(f"endmodule : {mod_name}\n\n")
        
        # 2D Array Literal Example Comment
        f.write(f"/* \n2D Array Initialization Example:\n")
        f.write(f"const logic [7:0] IMAGE_2D [0:{height-1}][0:{width-1}] = '{{\n")
        for y in range(height):
            row_str = ", ".join([f"8'h{data_2d[y, x]:02X}" for x in range(width)])
            comma = "," if y < height - 1 else ""
            f.write(f"    '{{{row_str}}}{comma}\n")
        f.write(f"}};\n*/\n")


def export_c_header(data_2d, filepath, raw_name="image"):
    """
    Export C/C++ header (.h) array for Nios II / ARM HPS / embedded software.
    """
    height, width = data_2d.shape
    clean_name = sanitize_identifier(raw_name)
    guard = f"{clean_name.upper()}_H"
    
    with open(filepath, 'w') as f:
        f.write(f"#ifndef {guard}\n#define {guard}\n\n")
        f.write(f"#include <stdint.h>\n\n")
        f.write(f"#define {clean_name.upper()}_WIDTH  {width}\n")
        f.write(f"#define {clean_name.upper()}_HEIGHT {height}\n")
        f.write(f"#define {clean_name.upper()}_SIZE   {width * height}\n\n")
        f.write(f"// 8-bit RGB332 pixel array ({width}x{height})\n")
        f.write(f"static const uint8_t {clean_name}_data[{height * width}] = {{\n")
        
        for y in range(height):
            row_str = ", ".join([f"0x{data_2d[y, x]:02X}" for x in range(width)])
            comma = "," if y < height - 1 else ""
            f.write(f"    {row_str}{comma}\n")
            
        f.write(f"}};\n\n#endif // {guard}\n")


def convert_image(input_path, output_prefix, width=64, height=64, dither=True, aspect_mode='stretch', bg_color=(0, 0, 0), formats=['hex', 'mif', 'sv', 'c', 'png']):
    """
    Main conversion routine.
    """
    print(f"[+] Loading image: {input_path}")
    try:
        raw_img = Image.open(input_path)
        # Handle transparency by composite onto background color
        if raw_img.mode in ('RGBA', 'LA') or (raw_img.mode == 'P' and 'transparency' in raw_img.info):
            raw_img = raw_img.convert('RGBA')
            bg = Image.new('RGBA', raw_img.size, bg_color + (255,))
            img = Image.alpha_composite(bg, raw_img).convert('RGB')
        else:
            img = raw_img.convert('RGB')
    except Exception as e:
        print(f"[-] Error opening image '{input_path}': {e}")
        return False
        
    print(f"[+] Original size: {img.width}x{img.height}")
    print(f"[+] Resizing to: {width}x{height} (Mode: {aspect_mode})")
    
    img_resized = resize_image(img, width, height, aspect_mode=aspect_mode, bg_color=bg_color)
    
    print(f"[+] Quantizing colors to 8-bit RGB332 (Dithering: {'ON' if dither else 'OFF'})...")
    data_2d, img_preview = quantize_image_rgb332(img_resized, dither=dither)
    
    out_dir = os.path.dirname(output_prefix)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
        
    base_name = Path(output_prefix).stem
    dir_name = Path(output_prefix).parent
    
    for fmt in formats:
        fmt = fmt.lower()
        if fmt == 'hex':
            out_file = dir_name / f"{base_name}.hex"
            export_hex(data_2d, out_file)
            print(f"  -> Generated HEX file: {out_file}")
        elif fmt == 'mif':
            out_file = dir_name / f"{base_name}.mif"
            export_mif(data_2d, out_file)
            print(f"  -> Generated MIF file: {out_file}")
        elif fmt == 'sv':
            out_file = dir_name / f"{base_name}.sv"
            export_sv(data_2d, out_file, raw_name=base_name)
            print(f"  -> Generated SystemVerilog file: {out_file}")
        elif fmt == 'c' or fmt == 'h':
            out_file = dir_name / f"{base_name}.h"
            export_c_header(data_2d, out_file, raw_name=base_name)
            print(f"  -> Generated C/C++ Header file: {out_file}")
        elif fmt == 'png':
            out_file = dir_name / f"{base_name}_preview.png"
            scale = max(1, 256 // width)
            if scale > 1:
                img_preview_scaled = img_preview.resize((width * scale, height * scale), Image.Resampling.NEAREST)
                img_preview_scaled.save(out_file)
            else:
                img_preview.save(out_file)
            print(f"  -> Generated Preview PNG: {out_file}")
            
    print("[+] Conversion complete successfully!\n")
    return True


def interactive_mode():
    """
    User-friendly terminal prompt mode when run without arguments.
    """
    print("=" * 65)
    print("      DE10 FPGA / SystemVerilog 8-Bit VGA Image Converter")
    print("=" * 65)
    
    while True:
        path_in = input("\n[?] Enter path to image file (e.g. image.png or photo.jpg): ").strip(' "\'')
        if os.path.isfile(path_in):
            break
        print(f"[-] File not found: '{path_in}'. Please enter a valid path.")
        
    print("\n[?] Select target image dimensions:")
    print("  1) 64  x 64   (4,096 pixels)")
    print("  2) 100 x 100  (10,000 pixels)")
    print("  3) 160 x 120  (19,200 pixels)")
    print("  4) 320 x 240  (76,800 pixels)")
    print("  5) Custom Width x Height")
    
    choice = input("Choice [1-5, default 1]: ").strip()
    if choice == '2':
        width, height = 100, 100
    elif choice == '3':
        width, height = 160, 120
    elif choice == '4':
        width, height = 320, 240
    elif choice == '5':
        w_in = input("Enter Target Width [e.g. 80]: ").strip()
        h_in = input("Enter Target Height [e.g. 80]: ").strip()
        width = int(w_in) if w_in.isdigit() else 64
        height = int(h_in) if h_in.isdigit() else 64
    else:
        width, height = 64, 64
        
    dith_in = input("\n[?] Enable Floyd-Steinberg dithering for smoother gradients? (Y/n): ").strip().lower()
    dither = False if dith_in == 'n' else True
    
    default_out = Path(path_in).stem
    out_in = input(f"\n[?] Enter output filename prefix [default '{default_out}']: ").strip(' "\'')
    output_prefix = out_in if out_in else default_out
    
    convert_image(
        input_path=path_in,
        output_prefix=output_prefix,
        width=width,
        height=height,
        dither=dither,
        aspect_mode='stretch',
        formats=['hex', 'mif', 'sv', 'c', 'png']
    )


def main():
    parser = argparse.ArgumentParser(
        description="Convert image to 8-bit RGB332 color for DE10 FPGA SystemVerilog VGA display."
    )
    parser.add_argument("-i", "--input", help="Path to input image file")
    parser.add_argument("-o", "--output", help="Output filename prefix (default: input image name)")
    parser.add_argument("-W", "--width", type=int, default=64, help="Target width in pixels (default: 64)")
    parser.add_argument("-H", "--height", type=int, default=64, help="Target height in pixels (default: 64)")
    parser.add_argument("--no-dither", action="store_true", help="Disable Floyd-Steinberg dithering")
    parser.add_argument(
        "--aspect", choices=["stretch", "fit", "crop"], default="stretch",
        help="Aspect ratio resize mode: stretch, fit (padded), crop"
    )
    parser.add_argument(
        "--format", nargs="+", choices=["hex", "mif", "sv", "c", "png", "all"], default=["all"],
        help="Output formats to generate (default: all)"
    )
    
    args = parser.parse_args()
    
    if not args.input:
        interactive_mode()
        return
        
    formats = ["hex", "mif", "sv", "c", "png"] if "all" in args.format else args.format
    output_prefix = args.output if args.output else Path(args.input).stem
    
    convert_image(
        input_path=args.input,
        output_prefix=output_prefix,
        width=args.width,
        height=args.height,
        dither=not args.no_dither,
        aspect_mode=args.aspect,
        formats=formats
    )


if __name__ == "__main__":
    main()
