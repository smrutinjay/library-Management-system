from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def index():
    return "Hello from Debug App! Environment is working."

@app.route('/env')
def env():
    # Print installed packages
    import subprocess
    try:
        freeze = subprocess.check_output(['pip', 'freeze']).decode('utf-8')
        return f"<pre>{freeze}</pre>"
    except Exception as e:
        return f"Error: {e}"

if __name__ == '__main__':
    app.run()
