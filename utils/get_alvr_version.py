import subprocess

def check_command(command):
    """Check if a command can be executed."""
    try:
        # Run the command with --version to see if it exists
        subprocess.check_output([command, '--version'], text=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def get_alvr_version():
    # Check for Arch Linux (pacman)
    if check_command('pacman'):
        try:
            result = subprocess.check_output(
                ['pacman', '-Qi', 'alvr'], text=True)
            for line in result.splitlines():
                if 'Version' in line:
                    return line.split(':')[1].strip()
        except subprocess.CalledProcessError:
            print("Failed to retrieve ALVR version from pacman.")

    # Check for rpm-based systems (rpm)
    if check_command('rpm'):
        try:
            result = subprocess.check_output(['rpm', '-qi', 'alvr'], text=True)
            for line in result.splitlines():
                if 'Version' in line:
                    return line.split(':')[1].strip()
        except subprocess.CalledProcessError:
            print("Failed to retrieve ALVR version from rpm.")

    return None
