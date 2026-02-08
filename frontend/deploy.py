import os
import subprocess
import sys

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
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    print(line, end='')
                    if "Deploy complete!" in line:
                        completed_successfully = True

            return_code = process.poll()

            if return_code == 0:
                print("\nDeployment completed successfully.")
                break # Exit loop on success
            elif completed_successfully:
                print("\nDeployment completed successfully (despite minor errors).")
                break # Exit loop on success
            else:
                print(f"\nDeployment failed with exit code {return_code}.")
                if attempt < max_retries:
                    print("Retrying in 5 seconds...")
                    import time
                    time.sleep(5)
                else:
                    print("\nMax retries reached. Deployment failed.")
                    sys.exit(1)

    except subprocess.CalledProcessError as e:
        print(f"\nError occurred during execution: {e}")
        input("Press Enter to close...")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        input("Press Enter to close...")
        sys.exit(1)

    input("\nPress Enter to close...")

if __name__ == "__main__":
    main()
