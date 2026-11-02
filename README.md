# totp

TOTP codes on the Linux desktop, with the secrets locked to a FIDO2 security key.

Pick an account in a rofi menu, touch the key, and the code is copied to the clipboard (or typed for you). Each secret is stored in its own file, encrypted with [age](https://github.com/FiloSottile/age) through [age-plugin-fido2-hmac](https://github.com/olastor/age-plugin-fido2-hmac). Without the key the files can't be read, and every code needs a touch.

## How it works

| Step | What happens |
|---|---|
| `totp init` | Creates a FIDO2 credential on the key and saves its public recipient to `~/.config/totp/recipient`. |
| `totp add` | Encrypts the `otpauth://` URI to that recipient into `~/.local/share/totp/<name>.age`. No key needed. |
| `totp pick` | Shows the accounts in rofi, decrypts the chosen one (touch the key), computes the code and copies it. |

- The clipboard is cleared after 45 s, but only if it still holds the code.
- If the code has less than 5 s left, it waits for the next one.
- Only one key request runs at a time: a new `totp pick` cancels the pending one, so a touch can't unlock the wrong account.
- Notifications (`notify-send`) show the touch prompt and then the result, replacing each other.

## Requirements

- Linux x86_64 and a Wayland session (`wl-clipboard`, `wtype`). Tested on Ubuntu 26.04 with sway.
- A FIDO2 key with the `hmac-secret` extension, for example any YubiKey 5 or Bio.
- Python 3.10+ (standard library only).

```bash
sudo apt install python3 age rofi wl-clipboard libnotify-bin libfido2-1
sudo apt install wtype zbar-tools v4l-utils   # optional: --type, import-google
```

## Install

```bash
git clone https://github.com/jaborvs/totp.git
cd totp
./install.sh
```

`install.sh` doesn't use sudo. It checks the packages above and prints the `apt install` line for any that are missing. Then it downloads `age-plugin-fido2-hmac` v0.5.0, verifies its SHA-256, and installs both into `~/.local/bin`. Set `TOTP_BIN` to install somewhere else.

Then, with the key plugged in:

```bash
totp init
```

The plugin asks two questions. Answer no to "PIN to decrypt", since a touch is enough, and no to "separate identity", so nothing secret is left on disk.

## Usage

```
totp init                       create the key-bound recipient (key plugged in, run in a terminal)
totp add NAME [URI|SECRET]      add an account (reads from stdin/prompt if omitted)
totp import-google [--dev /dev/videoN] [IMAGE...]
                                import Google Authenticator export QRs (webcam if no IMAGE)
totp list                       list accounts
totp code NAME                  print the current code
totp pick [--type]              rofi picker: copy the code (or type it with wtype)
totp rm NAME                    delete an account
```

Adding an account: when a site shows its 2FA QR code, it usually also offers "can't scan? enter this key". Pass that secret, or the full `otpauth://` URI:

```bash
totp add github                 # prompts for the secret without echoing it
```

Avoid passing the secret as an argument: it would end up in your shell history.

### Moving from Google Authenticator

In the app, open *Transfer accounts* and choose *Export*. Then run `totp import-google` and show each QR to the webcam, or pass screenshots of the QRs as `IMAGE` arguments. While the webcam scans, totp adjusts the exposure so the phone screen stays readable.

### Keybinding (sway)

```
bindsym $mod+o exec ~/.local/bin/totp pick
bindsym $mod+Shift+t exec ~/.local/bin/totp pick --type
```

If the menu is started from a key binding, `~/.local/bin` doesn't need to be in the session `PATH`: `totp` adds its own directory to `PATH` so `age` can find the plugin.

### Customising

| What | How |
|---|---|
| Menu icons | `~/.local/share/totp/icons/<name>.svg` or `.png`. Otherwise it uses the matching Papirus app icon if installed, else a generic key. |
| rofi prompt | `TOTP_PROMPT` environment variable, e.g. a Nerd Font glyph. |

### With yubikey-touch-detector and mako

If you run [yubikey-touch-detector](https://github.com/maximbaz/yubikey-touch-detector) for touch prompts in `ssh`, git signing and the browser, `totp pick` would show two prompts at once. While it waits for the touch, `totp pick` turns on the mako mode `totp`, so a rule in `~/.config/mako/config` can hide the detector's prompt:

```ini
[mode=totp app-name=yubikey-touch-detector]
invisible=1
```

Without mako, `totp` skips this step.

## Backups and losing the key

The `.age` files only open with the same physical key. If you lose it or reset its FIDO2 application, every account is gone, so set up at least one fallback before you rely on this:

- Keep the recovery codes most sites show when you enable 2FA, somewhere safe.
- Add a second key. age encrypts to every recipient line in `~/.config/totp/recipient`, so add the second key's recipient there and add the accounts again with `totp add NAME --force`. Files encrypted before that still open only with the first key.

Back up `~/.local/share/totp/` and `~/.config/totp/recipient` along with your other files. Neither is secret on its own: they only open with the key.

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests check the RFC 6238 test vectors, URI and Google export parsing, and a full run of `add`, `code` and `rm`. They encrypt to an ordinary age key, so you don't need a security key to run them. They don't exercise the rofi menu or a real key.

## License

MIT. `age-plugin-fido2-hmac` is a separate project, also under MIT, and is downloaded at install time.
