citadel_logo.png — the official Citadel shield (purple/violet gradient with white "C"),
                   sampled into the in-app theme colors. Use this as the source for
                   exporting a Windows ICO when packaging the EXEs.

To enable a branded EXE icon, create `citadel.ico` here (multi-resolution ICO, sizes
16 / 32 / 48 / 64 / 128 / 256). PyInstaller picks it up automatically via the build
scripts. Without it the EXEs build with the default Python icon.

Quick conversion (requires Pillow):
    python -c "from PIL import Image; im = Image.open('citadel_logo.png'); im.save('citadel.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
