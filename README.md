# 8-Bit VGA Image Converter for SystemVerilog / DE10 FPGA & Discord Bot

This project converts any image file (`PNG`, `JPG`, `BMP`, `WEBP`, etc.) into an 8-bit color representation matching the standard **RGB332** table format used in DE10 FPGA VGA labs (**נספח - טבלת המרה של כל צבעים**).

It includes both a **command-line/interactive Python script** (`image_to_vga8.py`) and a **Discord Bot** (`bot.py`) so you can upload images directly in Discord and receive converted FPGA memory files!

---

## 🎨 Color Mapping Specification (RGB332)

The 8-bit byte output `[7:0]` maps to 256 colors as follows:

| Component | Bits | Bit Range | Values Range |
| :--- | :--- | :--- | :--- |
| **Red** | 3 bits | `[7:5]` | `0` to `7` |
| **Green** | 3 bits | `[4:2]` | `0` to `7` |
| **Blue** | 2 bits | `[1:0]` | `0` to `3` |

---

## 🤖 Discord Bot (`bot.py`)

### 1. How to Set Up the Discord Bot
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**.
2. Go to **Bot** -> click **Add Bot**.
3. Under **Privileged Gateway Intents**, enable **Message Content Intent**.
4. Click **Reset Token** and copy your Bot Token.
5. Create a `.env` file in this folder with:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   ```
6. Run the bot:
   ```bash
   python bot.py
   ```

### 2. How to Use the Discord Bot
In any channel where the bot is present:
- **Slash Command**: Type `/convert` and attach your image with target `width` and `height`.
- **Message Command**: Upload an image with the caption `!convert 64 64` (or `!convert 160 120`).

The bot will reply with:
- 🖼️ **Preview Image** (`_preview.png`) embedded right in the chat.
- 📁 **Files attached**: `.mif`, `.hex`, `.sv`, and `.h`.

---

## 💻 Local Script (`image_to_vga8.py`)

### Interactive Mode (Easiest)
```bash
python image_to_vga8.py
```

### Command Line Mode (CLI)
```bash
# Convert image to 64x64 resolution
python image_to_vga8.py -i my_photo.png -W 64 -H 64 -o my_sprite

# Convert image to 160x120 resolution
python image_to_vga8.py -i character.png -W 160 -H 120 -o character_rom
```

---

## 📁 Generated Output Files

1. **`.mif` (Intel Quartus Memory Initialization File)**:
   Directly load into Quartus ROM megafunction (`altsyncram`).

2. **`.hex` (Verilog Memory File)**:
   For SystemVerilog testbenches using `$readmemh("image.hex", memory_array);`.

3. **`.sv` (SystemVerilog Module & 2D Array)**:
   Contains a ready-to-use ROM module and package:
   ```systemverilog
   my_sprite_rom sprite_inst (
       .addr(pixel_address), // addr = y * WIDTH + x
       .color(pixel_color_8bit)
   );
   ```

4. **`.h` (C/C++ Header)**:
   Contains 8-bit array for Nios II / HPS software.

5. **`_preview.png`**:
   Visual preview showing how your image will look on the 8-bit VGA display.
