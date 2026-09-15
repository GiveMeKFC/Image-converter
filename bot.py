#!/usr/bin/env python3
"""
Discord Bot for DE10 FPGA 8-Bit VGA Image Conversion
Allows users to upload images in Discord channels or DMs and get back
8-bit RGB332 converted .mif, .hex, .sv, .h, and .png preview files.

Usage:
  - Drag and drop an image with caption: !convert 64 64
  - Or use Slash Command: /convert image: [upload] width: 64 height: 64
"""

import os
import sys
import tempfile
import asyncio
from pathlib import Path

import discord
from discord.ext import commands
from discord import app_commands

# Import our image converter module
from image_to_vga8 import convert_image

# Set up Discord bot intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print("=" * 60)
    print(f"  [+] Logged in as Discord Bot: {bot.user} (ID: {bot.user.id})")
    print("  [+] Syncing slash commands...")
    try:
        synced = await bot.tree.sync()
        print(f"  [+] Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"  [-] Failed to sync slash commands: {e}")
    print("  [+] Bot is online and ready to convert images!")
    print("=" * 60)


async def process_conversion(ctx_or_interaction, image_attachment, width: int = 64, height: int = 64, dither: bool = True):
    """
    Helper to download attachment, convert image, and upload converted files back to Discord.
    """
    if width < 8 or width > 640 or height < 8 or height > 640:
        msg = "❌ Error: Target dimensions must be between 8x8 and 640x640 pixels."
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(msg, ephemeral=True)
        else:
            await ctx_or_interaction.send(msg)
        return

    # Check content type
    valid_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif')
    if not any(image_attachment.filename.lower().endswith(ext) for ext in valid_exts):
        msg = f"❌ Error: Please attach a valid image file ({', '.join(valid_exts)})."
        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.response.send_message(msg, ephemeral=True)
        else:
            await ctx_or_interaction.send(msg)
        return

    # Defer response if interaction
    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.defer()

    status_msg = None
    if isinstance(ctx_or_interaction, commands.Context):
        status_msg = await ctx_or_interaction.send(f"⏳ Processing **{image_attachment.filename}** ({width}x{height} RGB332)...")

    with tempfile.TemporaryDirectory() as temp_dir:
        input_file = os.path.join(temp_dir, image_attachment.filename)
        output_prefix = os.path.join(temp_dir, Path(image_attachment.filename).stem)

        # Download attachment
        await image_attachment.save(input_file)

        # Run conversion in thread pool to prevent blocking event loop
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(
            None,
            lambda: convert_image(
                input_path=input_file,
                output_prefix=output_prefix,
                width=width,
                height=height,
                dither=dither,
                aspect_mode='stretch',
                formats=['hex', 'mif', 'sv', 'c', 'png']
            )
        )

        if not success:
            err = "❌ Error converting image. Please check the file and try again."
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(err)
            else:
                await ctx_or_interaction.send(err)
            return

        # Prepare Discord file attachments
        files_to_send = []
        preview_file = None

        exts = ['.mif', '.hex', '.sv', '.h', '_preview.png']
        for ext in exts:
            fp = f"{output_prefix}{ext}"
            if os.path.exists(fp):
                d_file = discord.File(fp)
                files_to_send.append(d_file)
                if ext == '_preview.png':
                    preview_file = d_file

        # Embed message
        embed = discord.Embed(
            title="🎨 DE10 FPGA 8-Bit VGA Image Conversion",
            description=f"**File**: `{image_attachment.filename}`\n"
                        f"**Resolution**: `{width} x {height}` ({width * height} pixels)\n"
                        f"**Format**: `8-Bit RGB332` ([7:5] R, [4:2] G, [1:0] B)\n"
                        f"**Dithering**: `{'ON' if dither else 'OFF'}`",
            color=discord.Color.blue()
        )
        embed.set_footer(text="SystemVerilog / DE10 FPGA VGA Converter")

        if preview_file:
            embed.set_image(url=f"attachment://{preview_file.filename}")

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.followup.send(embed=embed, files=files_to_send)
        else:
            if status_msg:
                await status_msg.delete()
            await ctx_or_interaction.send(embed=embed, files=files_to_send)


# Prefix Command (!convert [width] [height])
@bot.command(name="convert", help="Convert an attached image to 8-bit RGB332 VGA files. Example: !convert 64 64")
async def convert_cmd(ctx, width: int = 64, height: int = 64, dither: bool = True):
    if not ctx.message.attachments:
        await ctx.send("⚠️ Please attach an image to your message! Example: upload image with caption `!convert 64 64`")
        return
    await process_conversion(ctx, ctx.message.attachments[0], width=width, height=height, dither=dither)


# Slash Command (/convert)
@bot.tree.command(name="convert", description="Convert image to DE10 FPGA 8-bit VGA format (.mif, .hex, .sv, .h)")
@app_commands.describe(
    image="The image file to convert",
    width="Target width in pixels (default: 64)",
    height="Target height in pixels (default: 64)",
    dither="Enable Floyd-Steinberg dithering for smooth color gradients (default: True)"
)
async def convert_slash(interaction: discord.Interaction, image: discord.Attachment, width: int = 64, height: int = 64, dither: bool = True):
    await process_conversion(interaction, image, width=width, height=height, dither=dither)


def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        token_file = Path(".env")
        if token_file.is_file():
            with open(token_file) as f:
                for line in f:
                    if line.startswith("DISCORD_TOKEN="):
                        token = line.strip().split("=", 1)[1].strip(' "\'')
                        break

    if not token:
        print("=" * 65)
        print("  [!] DISCORD_TOKEN not found!")
        print("  Please create a Discord Bot Token on the Discord Developer Portal:")
        print("  https://discord.com/developers/applications\n")
        token = input("  [?] Enter your Discord Bot Token: ").strip(' "\'')
        print("=" * 65)

    if not token:
        print("Error: No bot token provided. Exiting.")
        sys.exit(1)

    try:
        bot.run(token)
    except Exception as e:
        print(f"Error starting Discord Bot: {e}")


if __name__ == "__main__":
    main()
