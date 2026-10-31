#!/usr/bin/env python3
"""A labelled PTY transport fixture, never a Copilot or model emulator."""

import os
import signal
import sys
import termios
import tty


def main() -> None:
    if '--version' in sys.argv:
        print('GHCP PTY fixture 1.0 (not Copilot)')
        return
    history = ['PTY transport fixture. No model or shell execution.']
    pending = ''

    def paint(*_args):
        size = os.get_terminal_size()
        visible = history[-max(1, size.lines - 4):]
        sys.stdout.write('\x1b[2J\x1b[H' + '\r\n'.join(visible))
        sys.stdout.write(f'\x1b[{size.lines - 2};1H> {pending}\x1b[{size.lines};1H@ files  / commands  ? help')
        sys.stdout.flush()

    original = termios.tcgetattr(0)
    tty.setraw(0)
    signal.signal(signal.SIGWINCH, paint)
    paint()
    try:
        while True:
            data = os.read(0, 4096).decode('utf-8', errors='replace')
            if not data or '\x04' in data:
                break
            data = data.replace('\x1b[200~', '').replace('\x1b[201~', '')
            for character in data:
                if character == '\x03':
                    pending = ''
                    history.append('Fixture interrupt received')
                elif character in '\r\n':
                    history.append(f'Fixture received: {pending}')
                    pending = ''
                elif character in '\x7f\b':
                    pending = pending[:-1]
                elif character.isprintable():
                    pending += character
            paint()
    finally:
        termios.tcsetattr(0, termios.TCSANOW, original)


if __name__ == '__main__':
    main()