import importlib.util
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

__version__ = "2.0.0"
DISPLAY_VERSION = "v2"


def _banner():
    import discord
    line = "=" * 56
    print(line)
    print(f"  Flight Hub {DISPLAY_VERSION}")
    print(f"  discord.py v{discord.__version__} / Python {sys.version.split()[0]}")
    print(line)


def _check_voice_dependencies():
    missing = []
    if importlib.util.find_spec("nacl") is None:
        missing.append("PyNaCl")
    if shutil.which("ffmpeg") is None:
        try:
            import flighthub.core as _core
            path = _core._ffmpeg_executable()
            if not path or path == "ffmpeg":
                missing.append("ffmpeg")
        except Exception:
            missing.append("ffmpeg")
    try:
        import discord
        if not discord.opus.is_loaded():
            discord.opus._load_default()
        if not discord.opus.is_loaded():
            missing.append("libopus")
    except Exception:
        missing.append("libopus")
    if missing:
        print("[WARN] Voice playback is missing: " + ", ".join(missing))
        print("       Install them to enable voice features (the rest still works).")
    return missing


def main():
    try:
        import flighthub.core as core
    except ModuleNotFoundError as error:
        missing = getattr(error, "name", None) or "unknown"
        print(f"[ERROR] Missing required module: {missing}")
        print("        Run: pip install -r requirements.txt")
        sys.exit(1)

    _banner()
    _check_voice_dependencies()

    if not core.TOKEN:
        print("[ERROR] DISCORD_BOT_TOKEN is not set.")
        print("        Copy .env.example to .env and add your token.")
        sys.exit(1)

    from flighthub import config_store
    if not config_store.is_configured():
        print("[INFO] Not configured yet. Start the bot and run /setup in your staff server.")

    print("[INFO] Starting bot... (Ctrl+C to stop)")
    try:
        core.client.run(core.TOKEN)
    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped.")


if __name__ == "__main__":
    main()
