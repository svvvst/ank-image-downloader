# ank-image-downloader
An image downloader for the Anki notecard app.

This project is based on **kelciour**'s *Batch Download Pictures From Google Images* available on AnkiWeb [here](https://ankiweb.net/shared/info/561924305). If you would like to support his work, please by him a coffee on Ko-Fi here: https://ko-fi.com/kelciour

Instructions below are originally from Kelciour's AnkiWeb page for the add-on. They may be updated along with future commits to the add-on on this fork.

## Description
An Anki add-on to batch download pictures from Google Images.

### Compatibility
**The latest compatible version is Anki 2.1.49**
*The add-on needs to be updated to work on Anki 2.1.50+*

For information on compatibility with older versions, see below.

### Instructions
1. Open the card browser - select a few cards - menu Edit - Add Google Images.
2. Select "Source Field".
3. Select "Target Field" instead of "<ignored>".
4. Select how many pictures to download. (optional)
5. Set the maximum width or height. (optional)
6. Click "Start".

If the source field contains cloze deletions, only clozes will be used to search for pictures.

By default, multiple pictures will be separated by a space character (" "). It can be changed, for example, to a newline character ("<br>") by editing the "Delimiter" option in the config window (Tools - Add-ons - ... - Config).

### Legacy Versions of Anki
#### For Anki 2.1.15
The add-on depends on mpv video player to be able to resize pictures. By default, the pictures will be downsized by height to 260 px if mpv video player can be found. On macOS it can be installed via brew.sh and on Linux it should be already installed with Anki 2.1. On Windows download mpv video player from http://mpv.io and update the PATH environment variable.

#### For Anki 2.1.20+
The latest version contains a built-in image resizer but requires Anki 2.1.20+, i.e. there's no need to additionally install mpv video player to be able to resize pictures, but mpv is still required to be able to resize gifs.
