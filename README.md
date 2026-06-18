DeepSeek CLI 🤖
​An unofficial, reverse-engineered Python client for the DeepSeek Android API. This project successfully bypasses the API's security measures by locally solving the required WebAssembly (WASM) Proof-of-Work (PoW) challenge (@peekuptime.wasm).
​Provides a seamless command-line interface (CLI) with support for streamed responses, session management, and DeepSeek's "Thinking" mode.
​✨ Features
​WASM PoW Solver: Integrates wasmtime to compute the required challenge hashes locally without needing a browser environment.
​Real-time Streaming: Streams chat responses directly to the console for a native feel.
​Session Management: Create new chat sessions or maintain context in the current one.
​Thinking Mode Toggle: Easily switch the model's expert thinking capabilities on or off.
​Lightweight & Fast: Optimized for terminal use, working perfectly across Linux and other OS environments.
​🛠️ Prerequisites
​Before running the script, make sure you have Python 3.7+ installed along with the following dependencies:
​pip install requests wasmtime numpy
​Important: You must have the @peekuptime.wasm file in the same directory as the script. This file contains the compiled WebAssembly logic required to solve the PoW challenge.
​🚀 Installation & Setup
​Clone the repository:
git clone https://github.com/peekuptime/deepseek-cli.git
cd deepseek-cli
​Add the WASM file:
Ensure @peekuptime.wasm is placed inside the root directory of the project.
​Configure your Token:
Open the Python script and replace YOUR_TOKEN with your actual DeepSeek Bearer token.
​💻 Usage
​Run the script from your terminal:
​python main.py
​CLI Commands
​Once inside the chat interface, you can use the following commands:
​/think - Toggles "Thinking Mode" on or off.
​/new - Generates a fresh chat session ID and clears previous context.
​/exit - Safely terminates the script.
​⚠️ Disclaimer
​This is an unofficial project meant for educational and research purposes only, specifically regarding API reverse-engineering and WebAssembly integration. It is not affiliated with, maintained, or endorsed by DeepSeek. Use it responsibly and at your own risk.