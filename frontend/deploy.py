import os
import subprocess
import sys


AUTH_ERROR_PATTERNS = (
    'authentication error',
    'your credentials are no longer valid',
    'please run firebase login --reauth',
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
    print("  1) firebase login --reauth")
    print("  2) python deploy.py")


def _pause_if_interactive():
    if sys.stdin.isatty() and os.environ.get('CI', '').lower() != 'true':
        input("\nPress Enter to close...")

def main():
    print("Initializing deployment script...")

    # Set environment variables
    env = os.environ.copy()
    env["http_proxy"] = "http://127.0.0.1:1080"
    env["https_proxy"] = "http://127.0.0.1:1080"
    env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"

    print("Setting proxy variables...")
    print(f"http_proxy: {env['http_proxy']}")
    print(f"https_proxy: {env['https_proxy']}")
    print(f"NODE_TLS_REJECT_UNAUTHORIZED: {env['NODE_TLS_REJECT_UNAUTHORIZED']}")

    try:
        # Install dependencies
        print("\nInstalling dependencies...")
        subprocess.check_call(["npm", "install"], env=env, shell=True)

        # Build project
        print("\nBuilding project...")
        subprocess.check_call(["npm", "run", "build"], env=env, shell=True)

        # Preflight Firebase auth check
        print("\nChecking Firebase authentication...")
        auth_check = subprocess.run(
            ["firebase", "login:list"],
            env=env,
            shell=True,
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
            
            # Add --debug for more info and increase timeout via env vars
            # HTTP_TIMEOUT for firebase-tools might help
            env["FIREBASE_CLI_PREVIEWS"] = "hostingchannels" # sometimes helps
            
            # Removed --debug to avoid circular structure error in logging
            process = subprocess.Popen(
                ["firebase", "deploy", "--only", "hosting"], 
                env=env, 
                shell=True,
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
                break # Exit loop on success
            elif completed_successfully:
                if saw_known_post_success_error:
                    print("\nDeployment completed successfully (Firebase CLI returned a known post-success generic error line).")
                else:
                    print("\nDeployment completed successfully (despite minor errors).")
                break # Exit loop on success
            else:
                print(f"\nDeployment failed with exit code {return_code}.")
                if auth_error_detected:
                    _print_reauth_instructions()
                    _pause_if_interactive()
                    sys.exit(1)
                if attempt < max_retries:
                    print("Retrying in 5 seconds...")
                    import time
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
