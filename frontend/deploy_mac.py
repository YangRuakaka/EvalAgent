import os
import shutil
import subprocess
import sys
import time


AUTH_ERROR_PATTERNS = (
    'authentication error',
    'your credentials are no longer valid',
    'please run firebase login --reauth',
    'no authorized accounts',
    'failed to authenticate, have you run firebase login',
    'firebase login:ci',
    'not logged in',
)

LOGIN_SUCCESS_PATTERNS = (
    'logged in as',
    'already logged in as',
)


def _is_known_post_success_error(line):
    text = (line or '').strip().lower()
    return text in {
        'error: an unexpected error has occurred.',
        'error: an unexpected error has occurred',
    }


def _contains_auth_error(text):
    lowered = (text or '').lower()
    return any(pattern in lowered for pattern in AUTH_ERROR_PATTERNS)


def _contains_login_success(text):
    lowered = (text or '').lower()
    return any(pattern in lowered for pattern in LOGIN_SUCCESS_PATTERNS)


def _print_reauth_instructions():
    print("\nFirebase authentication is invalid or expired.")
    print("Please re-authenticate and run deployment again:")
    print("  1) npx --yes firebase-tools login")
    print("     (or: firebase login --reauth if global firebase CLI is installed)")
    print("  2) python deploy_mac.py")


def _pause_if_interactive():
    if sys.stdin.isatty() and os.environ.get('CI', '').lower() != 'true':
        input("\nPress Enter to close...")


def _resolve_firebase_command(env):
    if shutil.which('firebase', path=env.get('PATH')):
        return ['firebase']

    if shutil.which('npx', path=env.get('PATH')):
        print("Global 'firebase' CLI not found. Falling back to 'npx --yes firebase-tools'.")
        return ['npx', '--yes', 'firebase-tools']

    raise FileNotFoundError("Neither 'firebase' nor 'npx' command is available in PATH.")


def main():
    print("Initializing macOS deployment script...")

    # Use a clean environment for macOS deployment.
    # Explicitly remove proxy-related variables so no VPN/proxy is required.
    env = os.environ.copy()
    for key in (
        'http_proxy',
        'https_proxy',
        'HTTP_PROXY',
        'HTTPS_PROXY',
        'all_proxy',
        'ALL_PROXY',
        'no_proxy',
        'NO_PROXY',
        'NODE_TLS_REJECT_UNAUTHORIZED',
    ):
        env.pop(key, None)

    print("Proxy settings: disabled for macOS deployment")

    try:
        firebase_cmd = _resolve_firebase_command(env)

        # Install dependencies
        print("\nInstalling dependencies...")
        subprocess.check_call(["npm", "install"], env=env)

        # Build project
        print("\nBuilding project...")
        subprocess.check_call(["npm", "run", "build"], env=env)

        # Preflight Firebase auth check
        print("\nChecking Firebase authentication...")
        auth_check = subprocess.run(
            firebase_cmd + ["login:list"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        auth_output = auth_check.stdout or ''
        print(auth_output, end='')

        auth_has_success = _contains_login_success(auth_output)
        auth_has_error = _contains_auth_error(auth_output)

        if auth_check.returncode != 0 and auth_has_error and not auth_has_success:
            _print_reauth_instructions()
            _pause_if_interactive()
            sys.exit(1)

        if auth_check.returncode != 0 and not auth_has_success:
            print("\nFirebase authentication check returned a non-zero exit code without clear auth status.")
            print("Deployment will continue and rely on deploy step result.")

        # Deploy to Firebase
        print("\nDeploying to Firebase...")

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            print(f"\n[Attempt {attempt}/{max_retries}] Starting deployment...")

            env["FIREBASE_CLI_PREVIEWS"] = "hostingchannels"
            process = subprocess.Popen(
                firebase_cmd + ["deploy", "--only", "hosting"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            completed_successfully = False
            saw_known_post_success_error = False
            auth_error_detected = False
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    if "Deploy complete!" in line:
                        completed_successfully = True
                        print(line, end='')
                        continue

                    if completed_successfully and _is_known_post_success_error(line):
                        saw_known_post_success_error = True
                        continue

                    if _contains_auth_error(line):
                        auth_error_detected = True

                    print(line, end='')

            return_code = process.poll()

            if return_code == 0:
                print("\nDeployment completed successfully.")
                break
            elif completed_successfully:
                if saw_known_post_success_error:
                    print("\nDeployment completed successfully (Firebase CLI returned a known post-success generic error line).")
                else:
                    print("\nDeployment completed successfully (despite minor errors).")
                break
            else:
                print(f"\nDeployment failed with exit code {return_code}.")
                if auth_error_detected:
                    _print_reauth_instructions()
                    _pause_if_interactive()
                    sys.exit(1)
                if attempt < max_retries:
                    print("Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    print("\nMax retries reached. Deployment failed.")
                    sys.exit(1)

    except subprocess.CalledProcessError as e:
        print(f"\nError occurred during execution: {e}")
        _pause_if_interactive()
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        _pause_if_interactive()
        sys.exit(1)

    _pause_if_interactive()


if __name__ == "__main__":
    main()
