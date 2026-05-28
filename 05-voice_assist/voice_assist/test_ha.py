#!/usr/bin/env python3
"""
Test script for Home Assistant device control.
Tests control by English names, Bulgarian aliases and actions.
Usage: python ha_test.py
"""
import sys
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
log = logging.getLogger(__name__)

# Load .env
with open(os.path.expanduser('~/.env')) as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            os.environ[k] = v

sys.path.insert(0, '/home/chochko/voiceAssist')
from smarthome import SmartHome

def separator(title):
    print()
    print(f'{"="*60}')
    print(f'  {title}')
    print(f'{"="*60}')

def test_find(sh, names):
    separator('Entity Search')
    for name in names:
        result = sh._find_entity(name)
        status = '✓' if result else '✗'
        print(f'  {status} {name!r:40} → {result or "NOT FOUND"}')

def test_status(sh, names):
    separator('Device Status')
    for name in names:
        result = sh.control('status', name)
        print(f'  {name!r:30} → {result}')

def test_control(sh, tests):
    """
    tests: list of (action, entity_name, kwargs)
    """
    separator('Device Control')
    for action, name, kwargs in tests:
        result = sh.control(action, name, **kwargs)
        print(f'  [{action:15}] {name!r:30} → {result}')
        import time; time.sleep(1)

def main():
    print()
    print('Connecting to Home Assistant...')
    sh = SmartHome()
    if not sh.connect():
        print('ERROR: Cannot connect to Home Assistant')
        sys.exit(1)

    print(f'Connected ✓ — {len(sh._entities)} names/aliases loaded')

    # ── 1. Show all loaded names ──────────────────────────────────────
    separator('All Loaded Names & Aliases')
    by_entity = {}
    for name, eid in sorted(sh._entities.items()):
        by_entity.setdefault(eid, []).append(name)
    for eid in sorted(by_entity.keys()):
        names = by_entity[eid]
        print(f'  {eid}')
        for n in names:
            print(f'    • {n!r}')

    # ── 2. Test entity search ─────────────────────────────────────────
    # Add names from your actual HA setup to test
    test_find(sh, [
        # English names
        'chandelier',
        'office lamp',
        'aquarium',
        # Bulgarian aliases
        'плафониерата',
        'лампата в хола',
        'лампата във хола',
        # Should NOT find
        'nonexistent device',
        'несъществуващо',
    ])

    # ── 3. Test status ────────────────────────────────────────────────
    # Get status using both English and Bulgarian names
    lights   = sh.list_devices('light')[:3]
    switches = sh.list_devices('switch')[:2]
    test_status(sh, lights + switches)

    # ── 4. Interactive control ────────────────────────────────────────
    separator('Interactive Control Test')
    print('Available devices:')
    for i, (name, eid) in enumerate(sorted(sh._entities.items())[:20]):
        print(f'  {i+1:2}. {name!r:40} ({eid})')

    print()
    print('Commands: on, off, toggle, set_brightness, set_color, status, quit')
    print()

    while True:
        try:
            device = input('Device name (or alias): ').strip()
            if device.lower() in ('quit', 'q', 'exit'):
                break
            if not device:
                continue

            action = input('Action (on/off/toggle/status/set_brightness/set_color): ').strip()
            if not action:
                continue

            kwargs = {}
            if action == 'set_brightness':
                val = input('Brightness (0-100): ').strip()
                kwargs['brightness'] = int(val)
            elif action == 'set_color':
                val = input('Color (red/green/blue/white/yellow/warm/cool/...): ').strip()
                kwargs['color'] = val

            result = sh.control(action, device, **kwargs)
            print(f'  → {result}')
            print()

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f'  Error: {e}')

    separator('Done')
    print('HA test complete ✓')

if __name__ == '__main__':
    main()