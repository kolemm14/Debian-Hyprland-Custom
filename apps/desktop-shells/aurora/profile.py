import sys
import json
import os

class AuroraProfileManager:
    PROFILES = {
        "lite": {
            "blur": False,
            "animations": False,
            "shadows": False,
            "animated_wallpaper": False,
            "dock_effects": "minimal"
        },
        "balanced": {
            "blur": True,
            "animations": True,
            "shadows": True,
            "animated_wallpaper": False,
            "dock_effects": "smooth"
        },
        "ultra": {
            "blur": True,
            "animations": True,
            "shadows": True,
            "animated_wallpaper": True,
            "dock_effects": "wave"
        }
    }

    def __init__(self, config_dir=None):
        self.config_dir = config_dir or os.path.expanduser("~/.config/aurora")
        self.state_file = os.path.join(self.config_dir, "state.json")

    def get_current_profile(self):
        if not os.path.exists(self.state_file):
            return "balanced"
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
                return data.get("profile", "balanced")
        except:
            return "balanced"

    def set_profile(self, profile_name):
        profile_name = (profile_name or "").lower()
        if profile_name == "full":
            profile_name = "ultra"
        elif profile_name == "legacy":
            profile_name = "lite"
        if profile_name not in self.PROFILES:
            return False

        os.makedirs(self.config_dir, exist_ok=True)
        state = {"profile": profile_name, "eco": False}

        # Preserve eco state if file exists
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    old_state = json.load(f)
                    state["eco"] = old_state.get("eco", False)
            except:
                pass

        with open(self.state_file, 'w') as f:
            json.dump(state, f)

        self.generate_hyprland_profile(profile_name, state["eco"])
        return True

    def toggle_eco(self, state):
        os.makedirs(self.config_dir, exist_ok=True)
        current_profile = self.get_current_profile()
        new_state = {"profile": current_profile, "eco": state}
        with open(self.state_file, 'w') as f:
            json.dump(new_state, f)
        self.generate_hyprland_profile(current_profile, state)
        return True

    def generate_hyprland_profile(self, profile_name, eco=False):
        settings = self.PROFILES.get(profile_name, self.PROFILES["balanced"]).copy()
        if eco:
            settings["blur"] = False
            settings["animations"] = False
            settings["animated_wallpaper"] = False

        hypr_dir = os.path.join(self.config_dir, "hypr", "profiles")
        os.makedirs(hypr_dir, exist_ok=True)

        conf = []
        conf.append(f"# Auto-generated Aurora Profile: {profile_name.upper()} (Eco: {eco})")

        if settings["blur"]:
            conf.append("decoration {\n    blur {\n        enabled = true\n        size = 3\n        passes = 2\n    }\n}")
        else:
            conf.append("decoration {\n    blur {\n        enabled = false\n    }\n}")

        if settings["animations"]:
            conf.append("animations {\n    enabled = true\n}")
        else:
            conf.append("animations {\n    enabled = false\n}")

        with open(os.path.join(hypr_dir, "active.conf"), 'w') as f:
            f.write("\n".join(conf))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)

    cmd = sys.argv[1]
    manager = AuroraProfileManager()

    if cmd == "set":
        manager.set_profile(sys.argv[2])
    elif cmd == "eco":
        manager.toggle_eco(sys.argv[2].lower() == "on")
    elif cmd == "get":
        print(manager.get_current_profile())
