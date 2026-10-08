"""The ComfyUI arguments in a Start ComfyUI launcher, kept across Easy Install updates.

The Triton and dynamic VRAM toggles and EZi Desktop's folder settings change the
arguments on a launcher's command line. Updates carry those changes over to the
new launcher instead of treating the file as edited by hand.
"""
import re

COMMAND = re.compile(r'^(?P<head>[^\r\n]*python_embeded\\python\.exe"?[ \t]+"?(?:amd\\runtime|ComfyUI\\main)\.py"?)'
                     r'(?P<args>[^\r\n]*)(?=\r?$)', re.M | re.I)
TOKEN = re.compile(r'(?:"[^"]*"|[^\s"])+')
PLACEHOLDER = '{COMFYUI-ARGUMENTS}'


def split(text):
    """(launcher text with the arguments replaced by a placeholder, argument tokens), or None."""
    matches = list(COMMAND.finditer(text))
    if len(matches) != 1 or PLACEHOLDER in text or matches[0]['args'].rstrip().endswith('^'):
        return None
    match = matches[0]
    return text[:match.start('args')] + PLACEHOLDER + text[match.end('args'):], TOKEN.findall(match['args'])


def join(body, args):
    return body.replace(PLACEHOLDER, ''.join(' ' + token for token in args), 1)


def options(args):
    """Ordered {key: tokens}: each option with its values. --enable-X and --disable-X share one key."""
    result, key = {}, ''
    for token in args:
        if token.startswith('--'):
            key = re.sub(r'^--(?:enable|disable)-', '--', token)
            result[key] = [token]
        else:
            result.setdefault(key, []).append(token)
    return result


def merge(old, user, new):
    """The new release's arguments with the user's changes to the old ones applied."""
    old, user, new = options(old), options(user), options(new)
    merged = {}
    for key, value in new.items():
        if key in old and key not in user:
            continue  # removed by the user
        changed = key in user and (key not in old or user[key] != old[key])
        merged[key] = user[key] if changed else value
    for key, value in user.items():
        if key not in old and key not in merged:
            merged[key] = value  # added by the user
    return [token for value in merged.values() for token in value]
